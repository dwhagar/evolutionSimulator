"""The run store (``UX.10``, rebuilt on SQLite by ``STORE.2``): one folder per run, with one file in it.

::

    <root>/<run id>/
        run.sqlite                the whole run (docs/design/storage.md); -wal and -shm beside it
                                  while a program has it open

``run.sqlite`` holds the manifest (name, seed, versions, config, the starting setup and a summary),
the checkpoints and the recorded history. ``RunStore.list_runs`` reads only the manifests to list
every run with its seed, versions, simulated age, last population and last checkpoint, and a short
population series for a small chart, without opening a world. A run saved in the folder layout of the
first version (``run.json`` and a folder per checkpoint) is imported into a ``run.sqlite`` the first
time it is opened (``legacy.py``).

No pickle: a checkpoint is the world's JSON (``persistence``) and the recorder's, compressed, each
with a format number, so a run opens after the classes change. A checkpoint is written in one
transaction, so a crash leaves the previous one intact. ``Run.resume`` restores the newest one that
reads (falling back to older ones), and a resumed run goes on exactly as an uninterrupted one would.
``Run.autosave`` writes checkpoints as the run goes: every ``checkpoint_every_days`` simulated days
(and no more often than ``min_wall_seconds`` of real time), keeping the newest ``keep_newest`` plus
the first checkpoint of each simulated year. The history is kept in step with the recorder as samples
are taken, so a program reading the file sees it current to the day. Runs are never deleted unless
asked; ``space_warning`` says when the folder holds more than ``warn_bytes``.

Nothing here reads a clock but the one passed in, and there are no dependencies outside the core.
"""

from __future__ import annotations

import contextlib
import ctypes
import gzip
import json
import logging
import math
import os
import re
import shutil
import sys
import time
import weakref
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from evolution_simulator import __version__
from evolution_simulator.history import (
    Recorder,
    TierChange,
    dump_history,
    load_history_bytes,
)
from evolution_simulator.history.samples import HistorySamples
from evolution_simulator.runs.compact import Compacted, compact_file
from evolution_simulator.runs.database import (
    FILE_NAME,
    CheckpointRow,
    RunFile,
)
from evolution_simulator.runs.errors import RunError
from evolution_simulator.runs.paths import default_runs_root
from evolution_simulator.species import SpeciesRow, SpeciesTracker
from evolution_simulator.world.persistence import (
    FORMAT_VERSION,
    SaveFormatError,
    config_from_dict,
    config_to_dict,
    dump_world,
    load_world_bytes,
)
from evolution_simulator.world.world import StepReport, World, WorldConfig

log = logging.getLogger(__name__)

RUN_FORMAT = 2
"""The layout of the manifest in ``run.sqlite`` (the folder layout of the first version was 1)."""
LEGACY_MANIFEST = "run.json"
CHECKPOINT_PREFIX = "checkpoint-"
POPULATION_POINTS = 60
"""Points of the animal and plant counts kept in the manifest for a run list's small chart."""
GIGABYTE = 1024**3


@dataclass(frozen=True)
class RunStoreRules:
    checkpoint_every_days: float = 10.0
    """Simulated days between automatic checkpoints."""
    min_wall_seconds: float = 60.0
    """And never more often than this many real seconds, however fast the run goes."""
    keep_newest: int = 3
    """Checkpoints kept besides the yearly ones: the newest this many."""
    keep_yearly: bool = True
    """Also keep the first checkpoint of every simulated year (the first one of all included)."""
    year_days: float = 365.25
    warn_bytes: int = 5 * GIGABYTE
    """``space_warning`` speaks once the store holds more than this."""

    def __post_init__(self) -> None:
        for name in ("checkpoint_every_days", "year_days"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value > 0.0):
                raise ValueError(f"{name} must be above zero, got {value}.")
        if not (math.isfinite(self.min_wall_seconds) and self.min_wall_seconds >= 0.0):
            raise ValueError(f"min_wall_seconds must be zero or more, got {self.min_wall_seconds}.")
        if self.keep_newest < 1:
            raise ValueError("keep_newest must be at least 1.")
        if self.warn_bytes < 0:
            raise ValueError("warn_bytes must not be negative.")


@dataclass(frozen=True, slots=True)
class CheckpointInfo:
    name: str
    path: Path
    """The run's file, which holds the checkpoint."""
    tick: int
    simulated_seconds: float
    state_digest: str
    animals: int
    plants: int
    written: str
    has_history: bool
    world_format: int | None = None
    """The world save format of the checkpoint's blob (``None`` for an imported one)."""
    encoding: str = "json+gzip"


@dataclass(frozen=True, slots=True)
class RunSummary:
    """One line of the run list."""

    id: str
    path: Path
    name: str
    seed: int
    program_version: str
    created: str
    updated: str
    tick: int
    simulated_seconds: float
    elapsed: str
    animals: int
    plants: int
    checkpoints: int
    last_checkpoint: str | None
    animal_history: tuple[float, ...]
    """Up to ``POPULATION_POINTS`` animal counts across the run's recorded history, for a chart."""
    plant_history: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Resumed:
    world: World
    recorder: Recorder | None
    checkpoint: CheckpointInfo
    species: dict[str, Any] | None = None
    """What the species tracker saved with the checkpoint (``SpeciesTracker.to_dict()``), as it was
    written: the caller runs ``species.migrate`` and ``SpeciesTracker.restore`` on it. The store keeps
    it as an opaque document and does not know its format."""


class SupportsToDict(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


def _dump_document(data: Mapping[str, Any]) -> bytes:
    text = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return gzip.compress(text.encode("utf-8"), compresslevel=1, mtime=0)


def _load_document(blob: bytes) -> dict[str, Any]:
    data = json.loads(gzip.decompress(blob).decode("utf-8"))
    if not isinstance(data, dict):
        raise RunError("the species document is not an object")
    return data


def _utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "run"


def _downsample(values: tuple[float, ...], points: int) -> tuple[float, ...]:
    if len(values) <= points:
        return values
    return tuple(values[round(i * (len(values) - 1) / (points - 1))] for i in range(points))


def checkpoint_name(tick: int) -> str:
    return f"{CHECKPOINT_PREFIX}{tick:012d}"


def process_alive(pid: int) -> bool:
    """Whether a process with this id is running (a lease left by a crashed writer is not)."""
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except (AttributeError, OSError):
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class RunStore:
    """A folder of runs."""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        rules: RunStoreRules | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root) if root is not None else Path(str(default_runs_root()))
        self.rules = rules if rules is not None else RunStoreRules()
        self.clock = clock
        self._open: weakref.WeakSet[Run] = weakref.WeakSet()
        """The runs opened through this store, so deleting one can close them first (Windows will
        not delete a file that is open)."""

    # ---- creating and finding runs ----------------------------------------------------------

    def create(
        self,
        world: World,
        name: str | None = None,
        recorder: Recorder | None = None,
        setup: Mapping[str, Any] | None = None,
    ) -> Run:
        """Start a run for ``world`` (as it stands now) and write its first checkpoint, so the run can
        be resumed at once. Give the recorder to keep its history with the run. ``setup`` is what the
        world was started from (``animals``, ``plants``, ``seeded``), kept in the manifest beside the
        seed so a copy of the run can be started exactly; without it a world at tick 0 gives its
        counts and one that has run gives none."""
        label = name or f"seed {world.config.seed}"
        stamp = datetime.fromtimestamp(self.clock(), tz=UTC).strftime("%Y%m%d-%H%M%S")
        base = f"{stamp}-{_slug(label)}"
        run_id, n = base, 1
        while (self.root / run_id).exists():
            n += 1
            run_id = f"{base}-{n}"
        path = self.root / run_id
        path.mkdir(parents=True)
        now = _utc(self.clock())
        starting: dict[str, Any] = dict(setup) if setup is not None else {}
        if "animals" not in starting and world.tick == 0:
            starting.update(animals=len(world.animals), plants=world.plant_count)
        starting["seed"] = world.config.seed
        manifest: dict[str, Any] = {
            "format": RUN_FORMAT,
            "kind": "run",
            "id": run_id,
            "name": label,
            "seed": world.config.seed,
            "program_version": __version__,
            "created": now,
            "updated": now,
            "config": config_to_dict(world.config),
            "setup": starting,
            "summary": {},
        }
        part: RunFile | None = None
        try:
            part = RunFile.create(path / (FILE_NAME + ".part"), manifest)
            run = Run(self, path, part, manifest)
            run.checkpoint(world, recorder)
            run._file = part.publish(path / FILE_NAME)
        except BaseException:
            if part is not None:
                part.close()
            shutil.rmtree(path, ignore_errors=True)
            raise
        self._open.add(run)
        return run

    def open(self, run_id: str, readonly: bool = False) -> Run:
        """A saved run. A run in the folder layout of the first version is imported first (unless
        ``readonly``, which reads what is there and changes nothing, an old run included: it then
        cannot be opened). ``readonly`` is for looking at a run that a simulation may be writing."""
        path = self.root / run_id
        if not (path / FILE_NAME).is_file():
            if (path / LEGACY_MANIFEST).is_file():
                if readonly:
                    raise RunError(
                        f"Run {run_id!r} is in the old folder layout; open it once to import it."
                    )
                from evolution_simulator.runs import legacy

                legacy.import_run(path, self.clock)
            else:
                raise RunError(f"There is no run {run_id!r} in {self.root}.")
        elif (path / LEGACY_MANIFEST).is_file() and not readonly:
            from evolution_simulator.runs import legacy

            legacy.tidy(path)  # an import that was cut short after it had made the new file
        file = RunFile.open(path / FILE_NAME, readonly=readonly)
        try:
            manifest = self._check(path, file.manifest())
        except RunError:
            file.close()
            raise
        run = Run(self, path, file, manifest)
        self._open.add(run)
        return run

    @staticmethod
    def _check(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest.get("kind") != "run" or manifest.get("format") != RUN_FORMAT:
            raise RunError(f"{path.name} is not a run this program can read.")
        return manifest

    def list_runs(self) -> list[RunSummary]:
        """Every run in the folder, the most recently updated first. A folder that is not a readable
        run is left out. A run still in the folder layout of the first version is listed from its
        ``run.json`` and imported when it is opened."""
        if not self.root.is_dir():
            return []
        found: list[RunSummary] = []
        for path in sorted(self.root.iterdir()):
            try:
                if (path / FILE_NAME).is_file():
                    file = RunFile.open(path / FILE_NAME, readonly=True)
                    try:
                        manifest = self._check(path, file.manifest())
                    finally:
                        file.close()
                elif (path / LEGACY_MANIFEST).is_file():
                    from evolution_simulator.runs import legacy

                    manifest = legacy.read_manifest(path)
                else:
                    continue
                found.append(_summary(path, manifest))
            except (RunError, KeyError, TypeError, ValueError, OSError):
                continue
        return sorted(found, key=lambda r: (r.updated, r.id), reverse=True)

    def delete(self, run_id: str) -> None:
        """Remove a run and everything in it."""
        path = self.root / run_id
        if not (path / FILE_NAME).is_file() and not (path / LEGACY_MANIFEST).is_file():
            raise RunError(f"There is no run {run_id!r} in {self.root}.")
        for run in list(self._open):
            if run.path == path:
                run.close()
        try:
            shutil.rmtree(path)
        except OSError as error:
            raise RunError(f"Run {run_id!r} cannot be deleted: {error}") from error

    def compact(self, run_id: str) -> Compacted:
        """Rewrite a run's file without its free space (``STORE.3``): the size before and after. The
        run is refused while a program that is running writes it (this one included); the file is
        replaced whole or not at all. See ``compact.py``."""
        path = self.root / run_id
        if not (path / FILE_NAME).is_file():
            if (path / LEGACY_MANIFEST).is_file():
                raise RunError(
                    f"Run {run_id!r} is in the old folder layout; open it once to import it."
                )
            raise RunError(f"There is no run {run_id!r} in {self.root}.")
        mine = [run for run in self._open if run.path == path]
        if any(run.writing for run in mine):
            raise RunError(f"Run {run_id!r} is being written by this program; stop it first.")
        for run in mine:  # the file is replaced under them, so they let go of it
            run.close()
        return compact_file(
            path / FILE_NAME,
            run_id,
            {"pid": os.getpid(), "started": _utc(self.clock()), "task": "compact"},
            process_alive,
        )

    # ---- space -------------------------------------------------------------------------------

    def total_bytes(self) -> int:
        total = 0
        if self.root.is_dir():
            for folder, _, files in os.walk(self.root):
                for name in files:
                    with contextlib.suppress(OSError):
                        total += (Path(folder) / name).stat().st_size
        return total

    def space_warning(self) -> str | None:
        """A sentence when the runs take more than ``rules.warn_bytes``, else ``None``."""
        used = self.total_bytes()
        if used <= self.rules.warn_bytes:
            return None
        return (
            f"Saved runs use {used / GIGABYTE:.1f} GB in {self.root}; "
            f"more than {self.rules.warn_bytes / GIGABYTE:.1f} GB. Delete runs you no longer need."
        )


def _summary(path: Path, manifest: Mapping[str, Any]) -> RunSummary:
    summary = manifest.get("summary", {})
    return RunSummary(
        id=manifest["id"],
        path=path,
        name=manifest["name"],
        seed=int(manifest["seed"]),
        program_version=manifest["program_version"],
        created=manifest["created"],
        updated=manifest["updated"],
        tick=int(summary.get("tick", 0)),
        simulated_seconds=float(summary.get("simulated_seconds", 0.0)),
        elapsed=str(summary.get("elapsed", "")),
        animals=int(summary.get("animals", 0)),
        plants=int(summary.get("plants", 0)),
        checkpoints=int(summary.get("checkpoints", 0)),
        last_checkpoint=summary.get("last_checkpoint"),
        animal_history=tuple(float(v) for v in summary.get("animal_history", ())),
        plant_history=tuple(float(v) for v in summary.get("plant_history", ())),
    )


class Run:
    """One run: its folder and the file in it."""

    def __init__(
        self, store: RunStore, path: Path, file: RunFile, manifest: dict[str, Any]
    ) -> None:
        self.store = store
        self.path = path
        self._file = file
        self._manifest = manifest
        self._last_seconds: float | None = None
        self._last_wall: float | None = None
        self._recorder: Recorder | None = None
        self._tracker: SpeciesTracker | None = None
        self._history_stale = False
        """The history rows may be behind the recorder (a write failed); the next checkpoint
        rewrites them."""
        self._leased = False

    @property
    def manifest(self) -> dict[str, Any]:
        """The manifest, as of the last time this program looked. A run being written by another
        program is read again each time, so it stays current."""
        if not self._leased and not self._file.closed:
            with contextlib.suppress(RunError):
                self._manifest = self._file.manifest()
        return self._manifest

    @property
    def id(self) -> str:
        return str(self._manifest["id"])

    @property
    def name(self) -> str:
        return str(self._manifest["name"])

    @property
    def summary(self) -> RunSummary:
        return _summary(self.path, self.manifest)

    @property
    def config(self) -> WorldConfig:
        """The run's settings, read back from the manifest."""
        return config_from_dict(self._manifest["config"])

    @property
    def setup(self) -> dict[str, Any]:
        """What the world was started from: ``seed`` and, when it was known, ``animals``, ``plants``
        and ``seeded``. Empty for a run imported without them."""
        return dict(self._manifest.get("setup") or {})

    @property
    def file_path(self) -> Path:
        return self.path / FILE_NAME

    # ---- the file ----------------------------------------------------------------------------

    def close(self) -> None:
        """Let go of the file: stop following any recorder and close it. The run is no longer
        usable; open it again to read it."""
        with contextlib.suppress(RunError):
            self.release()
        self._file.close()

    def release(self) -> None:
        """Stop following the recorder and give up the writer's claim on the run, keeping the file
        open (what happens when a run's autosave ends)."""
        recorder, self._recorder = self._recorder, None
        if recorder is not None:
            recorder.remove_tier_listener(self._on_tiers)
        tracker, self._tracker = self._tracker, None
        if tracker is not None:
            tracker.remove_sample_listener(self._on_species)
        if self._leased and not self._file.closed and not self._file.readonly:
            self._leased = False
            self._file.set_meta(writer=None)
        self._leased = False

    @property
    def writing(self) -> bool:
        """This object is the run's writer: it follows a recorder or holds the claim."""
        return self._leased or self._recorder is not None

    def _writable(self) -> None:
        if self._file.closed:
            raise RunError(f"Run {self.id} is closed.")
        if self._file.readonly:
            raise RunError(f"Run {self.id} is open for reading only.")

    def writer(self) -> dict[str, Any] | None:
        """The program that has the run open for writing (``pid``, ``started``), or ``None``. A claim
        left by a program that is no longer running is not reported."""
        claim = self._file.get_meta("writer")
        if isinstance(claim, dict) and process_alive(int(claim.get("pid", -1))):
            return claim
        return None

    def _take_lease(self) -> None:
        claim = self.writer()
        if claim is not None and int(claim["pid"]) != os.getpid():
            raise RunError(
                f"Run {self.id} is being written by another program (process {claim['pid']})."
            )
        self._file.set_meta(writer={"pid": os.getpid(), "started": _utc(self.store.clock())})
        self._leased = True

    # ---- checkpoints -------------------------------------------------------------------------

    def checkpoints(self) -> list[CheckpointInfo]:
        """The checkpoints that are there, oldest first."""
        return [self._info(row) for row in self._file.checkpoints()]

    def _info(self, row: CheckpointRow) -> CheckpointInfo:
        return CheckpointInfo(
            name=checkpoint_name(row.tick),
            path=self.file_path,
            tick=row.tick,
            simulated_seconds=row.simulated_seconds,
            state_digest=row.state_digest,
            animals=row.animals,
            plants=row.plants,
            written=row.written,
            has_history=row.has_history,
            world_format=row.world_format,
            encoding=row.encoding,
        )

    def checkpoint(
        self,
        world: World,
        recorder: Recorder | None = None,
        species: SupportsToDict | None = None,
    ) -> CheckpointInfo:
        """Write a checkpoint of the world (and the recorder, if given) now, update the manifest, and
        drop the checkpoints the retention rules no longer keep. ``species`` is anything with a
        ``to_dict()`` (the species tracker); its document is stored with the checkpoint. All of it happens in one
        transaction: if anything fails the run is as it was."""
        self._writable()
        if recorder is not None:
            recorder.observe()  # a sample due at this very tick belongs in this checkpoint
            self._follow(recorder)
        now = self.store.clock()
        row = CheckpointRow(
            tick=world.tick,
            simulated_seconds=world.simulated_seconds,
            state_digest=world.state_digest(),
            animals=len(world.animals),
            plants=world.plant_count,
            written=_utc(now),
            has_history=recorder is not None,
            world_format=FORMAT_VERSION,
        )
        world_blob = dump_world(world)  # the slow part, before the transaction starts
        recorder_blob = dump_history(recorder) if recorder is not None else None
        species_blob = _dump_document(species.to_dict()) if species is not None else None
        history = recorder.history() if recorder is not None else None
        with self._file.transaction():
            if history is not None and self._history_stale:
                self._file.history_replace(history)
                self._history_stale = False
            self._file.add_checkpoint(row, world_blob, recorder_blob, species_blob)
            self._prune()
            self._update_manifest(world, history, row, now)
        self._file.settle()
        self._last_seconds = world.simulated_seconds
        self._last_wall = now
        return self._info(row)

    def _prune(self) -> None:
        rules = self.store.rules
        found = self._file.checkpoints()
        keep = {c.tick for c in found[-rules.keep_newest :]}
        if rules.keep_yearly:
            year = rules.year_days * 86400.0
            first_of_year: dict[int, CheckpointRow] = {}
            for c in found:
                first_of_year.setdefault(int(c.simulated_seconds // year), c)
            keep.update(c.tick for c in first_of_year.values())
        gone = [c.tick for c in found if c.tick not in keep]
        if gone:
            self._file.delete_checkpoints(gone)

    def _update_manifest(
        self, world: World, history: HistorySamples | None, row: CheckpointRow, now: float
    ) -> None:
        animals: tuple[float, ...] = ()
        plants: tuple[float, ...] = ()
        if history is not None:
            animals = _downsample(history.series("animals")[1], POPULATION_POINTS)
            plants = _downsample(history.series("plants")[1], POPULATION_POINTS)
        summary = {
            "tick": world.tick,
            "simulated_seconds": world.simulated_seconds,
            "elapsed": world.elapsed,
            "animals": len(world.animals),
            "plants": world.plant_count,
            "corpses": len(world.corpses),
            "checkpoints": len(self._file.checkpoints()),
            "last_checkpoint": checkpoint_name(row.tick),
            "animal_history": list(animals),
            "plant_history": list(plants),
        }
        updated = _utc(now)
        self._file.set_meta(updated=updated, summary=summary)
        self._manifest["updated"] = updated
        self._manifest["summary"] = summary

    # ---- following a recorder ----------------------------------------------------------------

    def _follow(self, recorder: Recorder) -> None:
        """Keep the history rows in step with ``recorder`` from now on (they are first made to
        match it)."""
        if recorder is self._recorder:
            return
        self.release()
        self._take_lease()
        self._recorder = recorder
        self._history_stale = False
        try:
            self._file.history_replace(recorder.history())
        except RunError:
            self._history_stale = True
            raise
        recorder.add_tier_listener(self._on_tiers)
        tracker = recorder.species
        if tracker is not None:
            self._tracker = tracker
            try:
                self._file.species_replace(tracker.rows())
            except RunError:
                log.exception("The species of %s could not be written", self.id)
            tracker.add_sample_listener(self._on_species)

    def _on_species(self, tracker: SpeciesTracker) -> None:
        if self._file.closed:
            return
        try:
            self._file.species_upsert(tracker.rows())
        except Exception:
            log.exception("The species of %s could not be written", self.id)

    def _on_tiers(self, changes: Sequence[TierChange]) -> None:
        if self._history_stale or self._file.closed:
            return
        try:
            self._file.history_apply(changes)
        except Exception:
            log.exception(
                "The history of %s could not be written; it is rewritten at the next checkpoint",
                self.id,
            )
            self._history_stale = True

    # ---- resuming and reading ---------------------------------------------------------------

    def resume(self, checkpoint: str | None = None) -> Resumed:
        """Restore the world (and the recorder, if the checkpoint has one). Without a name this is
        the newest checkpoint that reads, trying older ones if the newest is damaged. Nothing is
        written; the history rows are made to match when a recorder is followed."""
        found = self.checkpoints()
        if checkpoint is not None:
            found = [c for c in found if c.name == checkpoint]
            if not found:
                raise RunError(f"Run {self.id} has no checkpoint {checkpoint!r}.")
        errors: list[str] = []
        for info in reversed(found):
            try:
                if info.encoding != "json+gzip":
                    raise RunError("this checkpoint is stored in a way this program cannot read")
                world_blob, recorder_blob = self._file.checkpoint_blobs(info.tick)
                world = load_world_bytes(world_blob, name=info.name)
                recorder = None
                if info.has_history and recorder_blob is not None:
                    recorder = Recorder.restore(world, load_history_bytes(recorder_blob))
                self._last_seconds = world.simulated_seconds
                self._last_wall = self.store.clock()
                species_blob = self._file.species_blob(info.tick)
                species = None if species_blob is None else _load_document(species_blob)
                return Resumed(world, recorder, info, species)
            except (SaveFormatError, RunError, OSError, ValueError, KeyError, EOFError) as error:
                errors.append(f"{info.name}: {error}")
        raise RunError(
            f"Run {self.id} has no checkpoint that can be restored. " + "; ".join(errors)
        )

    def history(self) -> HistorySamples | None:
        """The recorded history, current to the last sample taken, or ``None`` if there is none."""
        return self._file.history_read()

    def species(self) -> list[SpeciesRow]:
        """Every species the run has seen (``SpeciesRow``: parent, first and last day, extinction,
        peak size, divergence), by kind and id. Their sizes over time are the history's
        ``species.<kind>.<id>`` series. Empty for a run with no species tracker."""
        return self._file.species_read()

    # ---- autosave ---------------------------------------------------------------------------

    def due(self, world: World) -> bool:
        """Whether an automatic checkpoint is owed: enough simulated days and enough real time have
        passed since the last one."""
        rules = self.store.rules
        if self._last_seconds is None or self._last_wall is None:
            return True
        days = (world.simulated_seconds - self._last_seconds) / 86400.0
        waited = self.store.clock() - self._last_wall
        return days >= rules.checkpoint_every_days and waited >= rules.min_wall_seconds

    def autosave(
        self,
        world: World,
        recorder: Recorder | None = None,
        species: SupportsToDict | None = None,
    ) -> Autosaver:
        """Write a checkpoint whenever one is due, after each step, until ``close()``."""
        return Autosaver(self, world, recorder, species)


class Autosaver:
    """Listens to the end of every step and checkpoints the run when one is due."""

    def __init__(
        self,
        run: Run,
        world: World,
        recorder: Recorder | None = None,
        species: SupportsToDict | None = None,
    ) -> None:
        self.run = run
        self.world = world
        self.recorder = recorder
        self.species = species
        self.written = 0
        """Checkpoints this autosaver has written."""
        if recorder is not None:
            run._writable()
            run._follow(recorder)
        world.add_step_listener(self._on_step)
        self._closed = False

    def _on_step(self, report: StepReport) -> None:
        if self.run.due(self.world):
            self.run.checkpoint(self.world, self.recorder, self.species)
            self.written += 1

    def finish(self) -> CheckpointInfo:
        """Checkpoint now (when a run ends or is stopped) and stop listening."""
        self._stop_listening()
        try:
            info = self.run.checkpoint(self.world, self.recorder, self.species)
        finally:
            self.run.release()
        self.written += 1
        return info

    def close(self) -> None:
        """Stop autosaving and following the recorder."""
        self._stop_listening()
        self.run.release()

    def _stop_listening(self) -> None:
        if not self._closed:
            self.world.remove_step_listener(self._on_step)
            self._closed = True
