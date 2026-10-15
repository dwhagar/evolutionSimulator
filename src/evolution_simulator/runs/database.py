"""The run file (``STORE.2``): one SQLite file per run, in WAL mode. See docs/design/storage.md.

``RunFile`` is the only code that knows the tables. It holds the manifest (``meta``), the checkpoints
(a small row each, and their world and recorder as compressed JSON blobs, no pickle) and the history
(a row per value and per statistic of each sample, in the recorder's tiers, applied as samples are
taken). ``RunStore`` and ``Run`` in ``store.py`` are the API over it.

Every change is a transaction (``RunFile.transaction``): a crash, a kill or a full disk leaves the
file as it was before the transaction. A reader opens the file read-only and sees the last committed
state while a writer works. Standard library only.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import sqlite3
import threading
import weakref
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evolution_simulator.history.recorder import TierChange
from evolution_simulator.history.samples import HistorySamples, Sample, Stat, Tier
from evolution_simulator.runs.errors import RunError

log = logging.getLogger(__name__)

FILE_NAME = "run.sqlite"
APPLICATION_ID = 0x45565331
"""``EVS1``: the file is an Evolution Simulator run (SQLite stores it in the file's header)."""
SCHEMA_VERSION = 1
"""The tables below. A later change is a function in ``MIGRATIONS`` that takes the file from the
number before it; a file with a higher number than this one is refused, not guessed at."""
BUSY_SECONDS = 5.0
WAL_LIMIT = 8 * 1024 * 1024
"""A WAL that grew for a big checkpoint is cut back to this when it is next emptied."""

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE checkpoints (
    id INTEGER PRIMARY KEY,
    tick INTEGER NOT NULL UNIQUE,
    simulated_seconds REAL NOT NULL,
    state_digest TEXT NOT NULL,
    animals INTEGER NOT NULL,
    plants INTEGER NOT NULL,
    written TEXT NOT NULL,
    has_history INTEGER NOT NULL,
    world_format INTEGER,
    encoding TEXT NOT NULL DEFAULT 'json+gzip');
CREATE TABLE checkpoint_data (
    id INTEGER PRIMARY KEY REFERENCES checkpoints(id) ON DELETE CASCADE,
    world BLOB NOT NULL,
    recorder BLOB,
    species BLOB);
CREATE TABLE names (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE samples (
    tier INTEGER NOT NULL, day INTEGER NOT NULL, span INTEGER NOT NULL, tick INTEGER NOT NULL,
    PRIMARY KEY (tier, day)) WITHOUT ROWID;
CREATE TABLE level (
    tier INTEGER NOT NULL, day INTEGER NOT NULL, name INTEGER NOT NULL, value REAL,
    PRIMARY KEY (tier, day, name)) WITHOUT ROWID;
CREATE TABLE stat (
    tier INTEGER NOT NULL, day INTEGER NOT NULL, name INTEGER NOT NULL, n INTEGER NOT NULL,
    mean REAL, std REAL, lo REAL, hi REAL, p10 REAL, p90 REAL,
    PRIMARY KEY (tier, day, name)) WITHOUT ROWID;
CREATE TABLE histogram (
    tier INTEGER NOT NULL, day INTEGER NOT NULL, name INTEGER NOT NULL, bins BLOB NOT NULL,
    PRIMARY KEY (tier, day, name)) WITHOUT ROWID;
"""
"""Values and statistics are REAL without NOT NULL because SQLite stores a NaN as NULL; reading a
NULL back gives NaN."""

MIGRATIONS: dict[int, Any] = {}
"""``{n: function(connection)}`` taking the file from schema ``n - 1`` to ``n``; none yet."""

TABLES = (
    "meta",
    "checkpoints",
    "checkpoint_data",
    "names",
    "samples",
    "level",
    "stat",
    "histogram",
)
_HISTORY_TABLES = ("samples", "level", "stat", "histogram")
_NAN = math.nan


@dataclass(frozen=True, slots=True)
class CheckpointRow:
    tick: int
    simulated_seconds: float
    state_digest: str
    animals: int
    plants: int
    written: str
    has_history: bool
    world_format: int | None = None
    """``persistence.FORMAT_VERSION`` of the world blob when it was written (``None``: not known,
    an imported checkpoint). The blob is read by ``persistence``, which owns its migrations; the
    store only keeps the number and the ``encoding`` so a later change of how worlds are written
    (a different layout, a different compression) can be told apart without opening them."""
    encoding: str = "json+gzip"


def _close_quietly(connection: sqlite3.Connection) -> None:
    with contextlib.suppress(sqlite3.Error):
        connection.close()


def _number(value: float | None) -> float:
    return _NAN if value is None else float(value)


class RunFile:
    """An open run file. Methods take the connection's lock, so a run may be used from the thread
    that steps the world and from the one that answers commands."""

    def __init__(self, path: Path, connection: sqlite3.Connection, readonly: bool) -> None:
        self.path = path
        self.readonly = readonly
        self._connection = connection
        self._lock = threading.RLock()
        self._depth = 0
        self._names: dict[str, int] | None = None
        self._finalizer = weakref.finalize(self, _close_quietly, connection)

    # ---- opening ------------------------------------------------------------------------------

    @classmethod
    def create(cls, path: Path, manifest: Mapping[str, Any]) -> RunFile:
        """A new file at ``path`` (which must not exist) with the tables and ``manifest`` in
        ``meta``. It is made in rollback-journal mode so it is one plain file until it is moved into
        place (``publish``), where it becomes a WAL file."""
        path = Path(path)
        if path.exists():
            raise RunError(f"{path.name} already exists.")
        try:
            connection = sqlite3.connect(
                path, isolation_level=None, timeout=BUSY_SECONDS, check_same_thread=False
            )
            connection.execute("PRAGMA auto_vacuum = INCREMENTAL")  # before the first table
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            connection.executescript(SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error as error:
            raise RunError(f"{path.name} cannot be created: {error}") from error
        file = cls(path, connection, readonly=False)
        file.set_meta(**manifest)
        return file

    @classmethod
    def open(cls, path: Path, readonly: bool = False) -> RunFile:
        """Open a run file. Read-only never writes (it is what a viewer uses on a run that a
        simulation is writing); otherwise the file is put in WAL mode and migrated if it is older."""
        path = Path(path)
        try:
            if readonly:
                connection = sqlite3.connect(
                    f"{path.resolve().as_uri()}?mode=ro",
                    uri=True,
                    isolation_level=None,
                    timeout=BUSY_SECONDS,
                    check_same_thread=False,
                )
            else:
                connection = sqlite3.connect(
                    path, isolation_level=None, timeout=BUSY_SECONDS, check_same_thread=False
                )
        except sqlite3.Error as error:
            raise RunError(f"{path.name} cannot be opened: {error}") from error
        try:
            application = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if application != APPLICATION_ID:
                raise RunError(f"{path.name} is not a run file.")
            if version > SCHEMA_VERSION:
                raise RunError(
                    f"{path.name} was made by a newer version of this program "
                    f"(file format {version}, this one reads up to {SCHEMA_VERSION})."
                )
            if not readonly:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(f"PRAGMA journal_size_limit = {WAL_LIMIT}")
                for number in range(version + 1, SCHEMA_VERSION + 1):
                    cls._migrate(connection, number)
        except sqlite3.Error as error:
            _close_quietly(connection)
            raise RunError(f"{path.name} cannot be read: {error}") from error
        except RunError:
            _close_quietly(connection)
            raise
        return cls(path, connection, readonly)

    @staticmethod
    def _migrate(connection: sqlite3.Connection, number: int) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            MIGRATIONS[number](connection)
            connection.execute(f"PRAGMA user_version = {number}")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        connection.execute("COMMIT")

    def publish(self, final: Path) -> RunFile:
        """Move this (new) file to ``final`` and reopen it there: either the whole first checkpoint is
        in a run folder or there is no run file at all."""
        self.close()
        try:
            self.path.replace(final)
        except OSError as error:
            raise RunError(f"{final.name} cannot be put in place: {error}") from error
        return RunFile.open(final)

    def close(self) -> None:
        with self._lock:
            self._finalizer()

    @property
    def closed(self) -> bool:
        return not self._finalizer.alive

    # ---- transactions -------------------------------------------------------------------------

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        """Everything done inside happens, all of it, or none of it. A transaction opened inside
        another joins it."""
        if self.readonly:
            raise RunError("This run is open for reading only.")
        with self._lock:
            if self._depth:
                yield
                return
            try:
                self._connection.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as error:
                raise RunError(f"{self.path.name} is busy: {error}") from error
            self._depth = 1
            try:
                yield
            except BaseException as error:
                self._names = None  # ids made in this transaction are gone with it
                with contextlib.suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                if isinstance(error, sqlite3.Error):
                    raise RunError(f"{self.path.name} cannot be written: {error}") from error
                raise
            else:
                try:
                    self._connection.execute("COMMIT")
                except sqlite3.Error as error:
                    self._names = None
                    with contextlib.suppress(sqlite3.Error):
                        self._connection.execute("ROLLBACK")
                    raise RunError(f"{self.path.name} cannot be written: {error}") from error
            finally:
                self._depth = 0

    def _query(self, sql: str, args: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        with self._lock:
            try:
                return self._connection.execute(sql, args).fetchall()
            except sqlite3.Error as error:
                raise RunError(f"{self.path.name} cannot be read: {error}") from error

    def _execute(self, sql: str, args: Sequence[Any] = ()) -> None:
        with self._lock:
            try:
                self._connection.execute(sql, args)
            except sqlite3.Error as error:
                raise RunError(f"{self.path.name} cannot be written: {error}") from error

    def settle(self) -> None:
        """After a checkpoint: give freed pages back to the file and empty the WAL, so neither stays
        the size of the biggest checkpoint. Best effort; a reader in the way only means later."""
        if self.readonly:
            return
        with self._lock:
            try:
                self._connection.execute("PRAGMA incremental_vacuum").fetchall()
                self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
            except sqlite3.Error:
                log.debug("The WAL of %s could not be emptied now", self.path, exc_info=True)

    def claim(self, claim: Mapping[str, Any], alive: Callable[[int], bool]) -> None:
        """Set ``meta.writer`` to ``claim`` unless a program that is still running has set it: the
        check and the write are one transaction, so two programs cannot both succeed."""
        with self.transaction():
            held = self.get_meta("writer")
            if isinstance(held, dict) and alive(int(held.get("pid", -1))):
                raise RunError(f"{self.path.parent.name} is being written (process {held['pid']}).")
            self.set_meta(writer=dict(claim))

    def vacuum_into(self, target: Path) -> None:
        """Write a compacted copy of the whole file to ``target`` (which must not exist). The copy
        is made from one snapshot and is not touched again; this file is unchanged."""
        with self._lock:
            try:
                self._connection.execute("VACUUM INTO ?", (str(target),))
            except sqlite3.Error as error:
                raise RunError(f"{self.path.name} cannot be compacted: {error}") from error

    def integrity(self) -> str:
        """``"ok"`` or what SQLite found wrong with the file."""
        rows = self._query("PRAGMA integrity_check")
        return "; ".join(str(row[0]) for row in rows)

    def table_counts(self) -> dict[str, int]:
        """Rows in every table and the bytes in the checkpoint blobs: what a copy must agree on."""
        counts = {
            table: int(self._query(f"SELECT COUNT(*) FROM {table}")[0][0]) for table in TABLES
        }
        counts["blob bytes"] = int(
            self._query(
                "SELECT COALESCE(SUM(LENGTH(world) + COALESCE(LENGTH(recorder), 0) "
                "+ COALESCE(LENGTH(species), 0)), 0) FROM checkpoint_data"
            )[0][0]
        )
        return counts

    # ---- the manifest -------------------------------------------------------------------------

    def manifest(self) -> dict[str, Any]:
        """Every key of ``meta``, its JSON decoded."""
        found: dict[str, Any] = {}
        for key, value in self._query("SELECT key, value FROM meta"):
            try:
                found[key] = json.loads(value)
            except ValueError:
                continue
        return found

    def get_meta(self, key: str, default: Any = None) -> Any:
        rows = self._query("SELECT value FROM meta WHERE key = ?", (key,))
        if not rows:
            return default
        try:
            return json.loads(rows[0][0])
        except ValueError:
            return default

    def set_meta(self, **values: Any) -> None:
        """Set keys of ``meta`` (a value of ``None`` removes the key)."""
        with self.transaction():
            for key, value in values.items():
                if value is None:
                    self._execute("DELETE FROM meta WHERE key = ?", (key,))
                else:
                    self._execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                        (key, json.dumps(value, sort_keys=True)),
                    )

    # ---- checkpoints --------------------------------------------------------------------------

    def checkpoints(self) -> list[CheckpointRow]:
        """The checkpoints, oldest first. No blob is read."""
        return [
            CheckpointRow(
                tick,
                seconds,
                digest,
                animals,
                plants,
                written,
                bool(has_history),
                world_format,
                encoding,
            )
            for (
                tick,
                seconds,
                digest,
                animals,
                plants,
                written,
                has_history,
                world_format,
                encoding,
            ) in self._query(
                "SELECT tick, simulated_seconds, state_digest, animals, plants, written, "
                "has_history, world_format, encoding FROM checkpoints ORDER BY tick"
            )
        ]

    def add_checkpoint(
        self,
        row: CheckpointRow,
        world: bytes,
        recorder: bytes | None,
        species: bytes | None = None,
    ) -> None:
        """Add (or, at the same tick, replace) a checkpoint. Inside a transaction."""
        with self.transaction():
            self._execute("DELETE FROM checkpoints WHERE tick = ?", (row.tick,))
            with self._lock:
                try:
                    cursor = self._connection.execute(
                        "INSERT INTO checkpoints(tick, simulated_seconds, state_digest, animals, "
                        "plants, written, has_history, world_format, encoding) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            row.tick,
                            row.simulated_seconds,
                            row.state_digest,
                            row.animals,
                            row.plants,
                            row.written,
                            int(row.has_history),
                            row.world_format,
                            row.encoding,
                        ),
                    )
                    self._connection.execute(
                        "INSERT INTO checkpoint_data(id, world, recorder, species) "
                        "VALUES (?, ?, ?, ?)",
                        (cursor.lastrowid, world, recorder, species),
                    )
                except sqlite3.Error as error:
                    raise RunError(f"{self.path.name} cannot be written: {error}") from error

    def delete_checkpoints(self, ticks: Sequence[int]) -> None:
        with self.transaction():
            for tick in ticks:
                self._execute("DELETE FROM checkpoints WHERE tick = ?", (tick,))

    def checkpoint_blobs(self, tick: int) -> tuple[bytes, bytes | None]:
        """The world and the recorder (if the checkpoint has one) of a checkpoint, still compressed."""
        rows = self._query(
            "SELECT d.world, d.recorder FROM checkpoint_data d "
            "JOIN checkpoints c ON c.id = d.id WHERE c.tick = ?",
            (tick,),
        )
        if not rows:
            raise RunError(f"There is no checkpoint at tick {tick}.")
        world, recorder = rows[0]
        return bytes(world), None if recorder is None else bytes(recorder)

    def species_blob(self, tick: int) -> bytes | None:
        """The species data of a checkpoint (``None`` if it has none), still compressed."""
        rows = self._query(
            "SELECT d.species FROM checkpoint_data d JOIN checkpoints c ON c.id = d.id "
            "WHERE c.tick = ?",
            (tick,),
        )
        return None if not rows or rows[0][0] is None else bytes(rows[0][0])

    # ---- the history --------------------------------------------------------------------------

    def _name_id(self, name: str) -> int:
        if self._names is None:
            self._names = {n: i for i, n in self._query("SELECT id, name FROM names")}
        found = self._names.get(name)
        if found is None:
            with self._lock:
                cursor = self._connection.execute("INSERT INTO names(name) VALUES (?)", (name,))
            found = cursor.lastrowid
            assert found is not None
            self._names[name] = found
        return found

    def _put_sample(self, tier: int, sample: Sample) -> None:
        day = sample.day
        with self._lock:
            c = self._connection
            c.execute(
                "INSERT OR REPLACE INTO samples(tier, day, span, tick) VALUES (?, ?, ?, ?)",
                (tier, day, sample.span, sample.tick),
            )
            c.executemany(
                "INSERT OR REPLACE INTO level(tier, day, name, value) VALUES (?, ?, ?, ?)",
                [(tier, day, self._name_id(k), v) for k, v in sample.values.items()],
            )
            c.executemany(
                "INSERT OR REPLACE INTO stat(tier, day, name, n, mean, std, lo, hi, p10, p90) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (tier, day, self._name_id(k), s.n, s.mean, s.std, s.lo, s.hi, s.p10, s.p90)
                    for k, s in sample.stats.items()
                ],
            )
            c.executemany(
                "INSERT OR REPLACE INTO histogram(tier, day, name, bins) VALUES (?, ?, ?, ?)",
                [
                    (tier, day, self._name_id(k), json.dumps(list(bins)).encode("ascii"))
                    for k, bins in sample.histograms.items()
                ],
            )

    def _drop_sample(self, tier: int, sample: Sample) -> None:
        with self._lock:
            for table in _HISTORY_TABLES:
                self._connection.execute(
                    f"DELETE FROM {table} WHERE tier = ? AND day = ?",
                    (tier, sample.day),
                )

    def history_replace(self, history: HistorySamples) -> None:
        """Make the history tables hold exactly ``history``."""
        with self.transaction():
            with self._lock:
                try:
                    for table in _HISTORY_TABLES:
                        self._connection.execute(f"DELETE FROM {table}")
                    for tier, group in enumerate(history.tiers):
                        for sample in group.samples:
                            self._put_sample(tier, sample)
                except sqlite3.Error as error:
                    raise RunError(f"{self.path.name} cannot be written: {error}") from error
            self.set_meta(
                history={
                    "period_seconds": history.period_seconds,
                    "tiers": [[t.name, t.periods] for t in history.tiers],
                }
            )

    def history_apply(self, changes: Sequence[TierChange]) -> None:
        """Do what the recorder just did to its ring buffers to the history tables."""
        with self.transaction(), self._lock:
            try:
                for change in changes:
                    if change.kind == "drop":
                        self._drop_sample(change.level, change.sample)
                    else:
                        self._put_sample(change.level, change.sample)
            except sqlite3.Error as error:
                raise RunError(f"{self.path.name} cannot be written: {error}") from error

    def history_read(self) -> HistorySamples | None:
        """The history tables as a ``HistorySamples``, or ``None`` if no history was ever kept."""
        info = self.get_meta("history")
        if info is None:
            return None
        with self._lock:
            names = {i: n for i, n in self._query("SELECT id, name FROM names")}
            keyed: dict[tuple[int, int], dict[str, Any]] = {}
            for tier, day, span, tick in self._query(
                "SELECT tier, day, span, tick FROM samples ORDER BY tier, day"
            ):
                keyed[(tier, day)] = {
                    "span": span,
                    "tick": tick,
                    "values": {},
                    "stats": {},
                    "h": {},
                }
            for tier, day, name, value in self._query("SELECT tier, day, name, value FROM level"):
                parts = keyed.get((tier, day))
                if parts is not None:
                    parts["values"][names[name]] = _number(value)
            for tier, day, name, n, mean, std, lo, hi, p10, p90 in self._query(
                "SELECT tier, day, name, n, mean, std, lo, hi, p10, p90 FROM stat"
            ):
                parts = keyed.get((tier, day))
                if parts is not None:
                    parts["stats"][names[name]] = Stat(
                        int(n),
                        _number(mean),
                        _number(std),
                        _number(lo),
                        _number(hi),
                        None if p10 is None else float(p10),
                        None if p90 is None else float(p90),
                    )
            for tier, day, name, bins in self._query("SELECT tier, day, name, bins FROM histogram"):
                parts = keyed.get((tier, day))
                if parts is not None:
                    parts["h"][names[name]] = tuple(int(b) for b in json.loads(bytes(bins)))
        groups: list[list[Sample]] = [[] for _ in info["tiers"]]
        for (tier, day), parts in keyed.items():
            if tier >= len(groups):
                continue
            groups[tier].append(
                Sample(
                    day=day,
                    span=parts["span"],
                    tick=parts["tick"],
                    values=dict(sorted(parts["values"].items())),
                    stats=dict(sorted(parts["stats"].items())),
                    histograms=dict(sorted(parts["h"].items())),
                )
            )
        return HistorySamples(
            float(info["period_seconds"]),
            tuple(
                Tier(str(name), int(periods), tuple(samples))
                for (name, periods), samples in zip(info["tiers"], groups, strict=True)
            ),
        )
