"""Measurements behind docs/design/storage.md (STORE.1): the folder run store against a SQLite file.

    python scripts/bench_storage.py [--animals 1000] [--plants 5000] [--checkpoints 8]

It builds a world, then writes the same checkpoints two ways (the folder layout of ``UX.10`` through
``RunStore``, and the schema proposed in the note into a WAL-mode ``run.sqlite``) and prints the time
each took and the size on disk. It also appends 100 simulated years of daily history samples to the
history tables, reads them back, reads one while a writer has a transaction open, and kills a writer
in the middle of a checkpoint to see what is left. Standard library only; nothing is written outside
a temporary folder. The schema here is a draft for STORE.2, not the final one.
"""

from __future__ import annotations

import argparse
import gzip
import json
import multiprocessing
import os
import shutil
import signal
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

from evolution_simulator.history import Recorder
from evolution_simulator.history.recorder import DEFAULT_TIERS, TierRule
from evolution_simulator.history.samples import Sample, Stat
from evolution_simulator.runs import RunStore, RunStoreRules
from evolution_simulator.world import World, WorldConfig
from evolution_simulator.world.persistence import world_to_dict

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE checkpoints (
    id INTEGER PRIMARY KEY, tick INTEGER NOT NULL UNIQUE, simulated_seconds REAL NOT NULL,
    state_digest TEXT NOT NULL, animals INTEGER NOT NULL, plants INTEGER NOT NULL,
    written TEXT NOT NULL, has_history INTEGER NOT NULL);
CREATE TABLE checkpoint_data (
    id INTEGER PRIMARY KEY REFERENCES checkpoints(id) ON DELETE CASCADE,
    world BLOB NOT NULL, recorder BLOB);
CREATE TABLE names (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE samples (
    tier INTEGER NOT NULL, day INTEGER NOT NULL, span INTEGER NOT NULL, tick INTEGER NOT NULL,
    PRIMARY KEY (tier, day)) WITHOUT ROWID;
CREATE TABLE level (
    tier INTEGER NOT NULL, day INTEGER NOT NULL, name INTEGER NOT NULL, value REAL NOT NULL,
    PRIMARY KEY (tier, day, name)) WITHOUT ROWID;
CREATE TABLE stat (
    tier INTEGER NOT NULL, day INTEGER NOT NULL, name INTEGER NOT NULL, n INTEGER NOT NULL,
    mean REAL NOT NULL, std REAL NOT NULL, lo REAL NOT NULL, hi REAL NOT NULL, p10 REAL, p90 REAL,
    PRIMARY KEY (tier, day, name)) WITHOUT ROWID;
CREATE TABLE histogram (
    tier INTEGER NOT NULL, day INTEGER NOT NULL, name INTEGER NOT NULL, bins BLOB NOT NULL,
    PRIMARY KEY (tier, day, name)) WITHOUT ROWID;
"""


def connect(path: Path, auto_vacuum: bool = False) -> sqlite3.Connection:
    db = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    if auto_vacuum:
        db.execute("PRAGMA auto_vacuum = INCREMENTAL")  # only takes hold on a new file
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = NORMAL")
    db.execute("PRAGMA foreign_keys = ON")
    return db


def create(path: Path, auto_vacuum: bool = False) -> sqlite3.Connection:
    db = connect(path, auto_vacuum)
    db.executescript(SCHEMA)
    return db


def ms(seconds: float) -> str:
    return f"{seconds * 1000:8.1f} ms"


def size_of(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def mb(n: int) -> str:
    return f"{n / 1024 / 1024:7.2f} MB"


# ---- the world --------------------------------------------------------------------------------


def build(animals: int, plants: int, ticks: int) -> tuple[World, Recorder]:
    world = World(WorldConfig(seed=1))
    world.populate(animals=animals, plants=plants)
    recorder = Recorder(world)
    for _ in range(ticks):
        world.step()
    recorder.observe()
    return world, recorder


def serialise(world: World, recorder: Recorder) -> tuple[bytes, bytes, float]:
    """The two blobs of a checkpoint (the bytes the folder layout writes to its two .gz files)."""
    start = time.perf_counter()
    text = json.dumps(world_to_dict(world), separators=(",", ":"), sort_keys=True)
    world_blob = gzip.compress(text.encode(), compresslevel=6, mtime=0)
    text = json.dumps(recorder.to_dict(), separators=(",", ":"), sort_keys=True)
    recorder_blob = gzip.compress(text.encode(), compresslevel=6, mtime=0)
    return world_blob, recorder_blob, time.perf_counter() - start


# ---- the history rows -------------------------------------------------------------------------


class Names:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db
        self.ids = {name: i for i, name in db.execute("SELECT name, id FROM names")}

    def of(self, name: str) -> int:
        found = self.ids.get(name)
        if found is None:
            found = self.db.execute("INSERT INTO names(name) VALUES (?)", (name,)).lastrowid
            self.ids[name] = found
        return found


def put_sample(db: sqlite3.Connection, names: Names, tier: int, s: Sample) -> None:
    db.execute("INSERT INTO samples VALUES (?,?,?,?)", (tier, s.day, s.span, s.tick))
    db.executemany(
        "INSERT INTO level VALUES (?,?,?,?)",
        [(tier, s.day, names.of(k), v) for k, v in s.values.items()],
    )
    db.executemany(
        "INSERT INTO stat VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (tier, s.day, names.of(k), t.n, t.mean, t.std, t.lo, t.hi, t.p10, t.p90)
            for k, t in s.stats.items()
        ],
    )
    db.executemany(
        "INSERT INTO histogram VALUES (?,?,?,?)",
        [(tier, s.day, names.of(k), json.dumps(list(b)).encode()) for k, b in s.histograms.items()],
    )


def drop_sample(db: sqlite3.Connection, tier: int, s: Sample) -> None:
    for table in ("samples", "level", "stat", "histogram"):
        db.execute(f"DELETE FROM {table} WHERE tier=? AND day=?", (tier, s.day))


def push(
    tiers: list[list[Sample]],
    rules: tuple[TierRule, ...],
    level: int,
    sample: Sample,
    ops: list[tuple[str, int, Sample]],
) -> None:
    """``recorder.push_sample``, also saying what changed: ('drop'|'put', tier, sample)."""
    tier, rule = tiers[level], rules[level]
    if tier and (tier[-1].day - 1) // rule.periods == (sample.day - 1) // rule.periods:
        ops.append(("drop", level, tier[-1]))
        tier[-1] = tier[-1].merge(sample)
        ops.append(("put", level, tier[-1]))
    else:
        tier.append(sample)
        ops.append(("put", level, sample))
    while len(tier) > rule.capacity:
        oldest = tier.pop(0)
        ops.append(("drop", level, oldest))
        if level + 1 < len(tiers):
            push(tiers, rules, level + 1, oldest, ops)
        else:
            ops.append(("drop", level, tier[0]))
            tier[0] = oldest.merge(tier[0])
            ops.append(("put", level, tier[0]))


def history_bench(db: sqlite3.Connection, template: Sample, years: int) -> None:
    names = Names(db)
    tiers: list[list[Sample]] = [[] for _ in DEFAULT_TIERS]
    times: list[float] = []
    rows = 0
    for day in range(1, years * 365 + 1):
        wobble = 1.0 + 0.01 * ((day * 7919) % 13 - 6)
        sample = Sample(
            day=day,
            span=1,
            tick=day * 24,
            values={k: v * wobble for k, v in template.values.items()},
            stats={
                k: Stat(t.n, t.mean * wobble, t.std, t.lo, t.hi, t.p10, t.p90)
                for k, t in template.stats.items()
            },
            histograms=template.histograms if day % 30 == 1 else {},
        )
        ops: list[tuple[str, int, Sample]] = []
        push(tiers, DEFAULT_TIERS, 0, sample, ops)
        start = time.perf_counter()
        db.execute("BEGIN IMMEDIATE")
        for kind, tier, s in ops:
            if kind == "drop":
                drop_sample(db, tier, s)
            else:
                put_sample(db, names, tier, s)
        db.execute("COMMIT")
        times.append(time.perf_counter() - start)
        rows += len(ops)
    held = sum(len(t) for t in tiers)
    print(f"  {years} years = {len(times)} daily appends, {held} samples held at the end")
    print(
        f"  per daily append: mean {ms(statistics.mean(times))}, "
        f"median {ms(statistics.median(times))}, worst {ms(max(times))}"
    )
    counts = {
        t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("samples", "level", "stat", "histogram", "names")
    }
    print(f"  rows: {counts}")
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def history_reads(path: Path) -> None:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    start = time.perf_counter()
    samples = db.execute(
        "SELECT tier, day, span, tick FROM samples ORDER BY tier DESC, day"
    ).fetchall()
    levels = db.execute("SELECT tier, day, name, value FROM level").fetchall()
    stats = db.execute(
        "SELECT tier, day, name, n, mean, std, lo, hi, p10, p90 FROM stat"
    ).fetchall()
    hists = db.execute("SELECT tier, day, name, bins FROM histogram").fetchall()
    whole = time.perf_counter() - start
    print(
        f"  whole history read ({len(samples)} samples, {len(levels)} levels, {len(stats)} stats, "
        f"{len(hists)} histograms): {ms(whole)}"
    )
    (animals,) = db.execute("SELECT id FROM names WHERE name='animals'").fetchone()
    start = time.perf_counter()
    rows = db.execute(
        "SELECT tier, day, value FROM level WHERE name=? ORDER BY tier DESC, day", (animals,)
    ).fetchall()
    print(f"  one series (animals, {len(rows)} points) read: {ms(time.perf_counter() - start)}")
    db.close()


def reader_beside_writer(path: Path) -> None:
    writer = sqlite3.connect(path, isolation_level=None)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO meta VALUES ('probe', 'uncommitted') ON CONFLICT DO NOTHING")
    reader = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.0)
    start = time.perf_counter()
    count = reader.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    probe = reader.execute("SELECT value FROM meta WHERE key='probe'").fetchone()
    print(
        f"  reader with a write transaction open: read {count} samples in "
        f"{ms(time.perf_counter() - start)}, sees the uncommitted row: {probe is not None}"
    )
    writer.execute("ROLLBACK")
    reader.close()
    writer.close()


# ---- crash safety -----------------------------------------------------------------------------


def _writer(path: str, world_blob: bytes, recorder_blob: bytes, marker: str) -> None:
    db = connect(Path(path))
    n = 0
    while True:
        n += 1
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute(
            "INSERT INTO checkpoints(tick, simulated_seconds, state_digest, animals, plants, written, "
            "has_history) VALUES (?,?,?,?,?,?,1)",
            (n, float(n), f"digest-{n}", 1, 1, "now"),
        )
        # Several blobs per checkpoint, so a kill is likely to land in the middle of the write.
        db.execute(
            "INSERT INTO checkpoint_data VALUES (?,?,?)",
            (cursor.lastrowid, world_blob, recorder_blob),
        )
        db.execute("COMMIT")
        Path(marker).write_text(str(n))


def crash_bench(root: Path, world_blob: bytes, recorder_blob: bytes, tries: int) -> None:
    ok = 0
    ctx = multiprocessing.get_context("spawn")
    for attempt in range(tries):
        folder = root / f"crash-{attempt}"
        folder.mkdir()
        path = folder / "run.sqlite"
        create(path).close()
        marker = str(folder / "last")
        child = ctx.Process(target=_writer, args=(str(path), world_blob, recorder_blob, marker))
        child.start()
        while not Path(marker).exists():
            time.sleep(0.01)
        time.sleep(0.05 + 0.013 * attempt)  # a different moment each time
        os.kill(child.pid, signal.SIGKILL)
        child.join()
        db = connect(path)
        check = db.execute("PRAGMA integrity_check").fetchone()[0]
        good = 0
        for (row_id,) in db.execute("SELECT id FROM checkpoints"):
            world, recorder = db.execute(
                "SELECT world, recorder FROM checkpoint_data WHERE id=?", (row_id,)
            ).fetchone()
            gzip.decompress(world)
            gzip.decompress(recorder)
            good += 1
        rows = db.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        data = db.execute("SELECT COUNT(*) FROM checkpoint_data").fetchone()[0]
        db.close()
        if check == "ok" and rows == data == good:
            ok += 1
    print(
        f"  {ok} of {tries} writers killed mid-write left a file that opens, checks ok, and whose"
    )
    print("  every checkpoint reads whole (a half-written one is never there)")


# ---- the bench --------------------------------------------------------------------------------


def folder_bench(root: Path, world: World, recorder: Recorder, count: int) -> None:
    store = RunStore(
        root / "folder", RunStoreRules(checkpoint_every_days=1.0, min_wall_seconds=0.0)
    )
    times = []
    run = None
    for _ in range(count):
        for _ in range(2):
            world.step()
        start = time.perf_counter()
        if run is None:
            run = store.create(world, name="bench", recorder=recorder)
        else:
            run.checkpoint(world, recorder)
        times.append(time.perf_counter() - start)
    assert run is not None
    print(
        f"  checkpoint (world + recorder, folder layout): mean {ms(statistics.mean(times))}, "
        f"worst {ms(max(times))}; folder holds {mb(size_of(run.path))} for {len(run.checkpoints())} kept"
    )


def sqlite_bench(root: Path, world: World, recorder: Recorder, count: int) -> bytes:
    """Store the same ``count`` checkpoints three ways and keep the newest three each time."""
    blobs = []
    for _ in range(count):
        for _ in range(2):
            world.step()
        world_blob, recorder_blob, spent = serialise(world, recorder)
        blobs.append(
            (
                world.tick,
                world.simulated_seconds,
                world.state_digest(),
                len(world.animals),
                world.plant_count,
                world_blob,
                recorder_blob,
                spent,
            )
        )
    spent = [b[7] for b in blobs]
    print(
        f"  serialising a checkpoint (the same cost in the folder layout): "
        f"mean {ms(statistics.mean(spent))}; {blobs[0][3]} animals and {blobs[0][4]} plants in the "
        f"first, {blobs[-1][3]} and {blobs[-1][4]} in the last"
    )
    print(
        f"  one checkpoint: world {mb(len(blobs[-1][5]))} + recorder {mb(len(blobs[-1][6]))} (gzip)"
    )
    variants = (
        ("freed pages are reused", False, "PASSIVE"),
        ("freed pages are reused, WAL truncated each time", False, "TRUNCATE"),
        ("incremental_vacuum after pruning, WAL truncated", True, "TRUNCATE"),
    )
    for label, auto, mode in variants:
        folder = root / f"sqlite-{len(list(root.glob('sqlite-*')))}"
        folder.mkdir()
        db = create(folder / "run.sqlite", auto_vacuum=auto)
        stored: list[float] = []
        seen: list[int] = []
        for tick, seconds, digest, animals, plants, world_blob, recorder_blob, _ in blobs:
            start = time.perf_counter()
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "INSERT INTO checkpoints(tick, simulated_seconds, state_digest, animals, plants, "
                "written, has_history) VALUES (?,?,?,?,?,?,1)",
                (tick, seconds, digest, animals, plants, "now"),
            ).lastrowid
            db.execute(
                "INSERT INTO checkpoint_data VALUES (?,?,?)", (row, world_blob, recorder_blob)
            )
            db.execute(
                "DELETE FROM checkpoints WHERE id NOT IN "
                "(SELECT id FROM checkpoints ORDER BY tick DESC LIMIT 3)"
            )
            db.execute("COMMIT")
            if auto:
                db.execute("PRAGMA incremental_vacuum").fetchall()  # one page per row fetched
            db.execute(f"PRAGMA wal_checkpoint({mode})")
            stored.append(time.perf_counter() - start)
            seen.append((folder / "run.sqlite").stat().st_size)
        main_file = (folder / "run.sqlite").stat().st_size
        wal = (
            (folder / "run.sqlite-wal").stat().st_size
            if (folder / "run.sqlite-wal").exists()
            else 0
        )
        print(f"  [{label}]")
        print(
            f"    storing a checkpoint (insert, prune, commit, WAL checkpoint): "
            f"mean {ms(statistics.mean(stored))}, worst {ms(max(stored))}"
        )
        free = db.execute("PRAGMA freelist_count").fetchone()[0]
        page = db.execute("PRAGMA page_size").fetchone()[0]
        print(
            f"    after {count} checkpoints with 3 kept: file {mb(main_file)} (largest {mb(max(seen))}, "
            f"{mb(free * page)} of it free pages) + WAL {mb(wal)}"
        )
        if not auto and mode == "TRUNCATE":
            start = time.perf_counter()
            db.execute("VACUUM")
            spent = time.perf_counter() - start
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            print(f"    VACUUM: {ms(spent)}, file now {mb((folder / 'run.sqlite').stat().st_size)}")
        db.close()
    return blobs[-1][5]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--animals", type=int, default=1000)
    parser.add_argument("--plants", type=int, default=5000)
    parser.add_argument("--checkpoints", type=int, default=8)
    parser.add_argument("--years", type=int, default=100)
    parser.add_argument("--kills", type=int, default=10)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="bench-storage-"))
    try:
        print(f"sqlite {sqlite3.sqlite_version}; {args.animals} animals, {args.plants} plants")
        start = time.perf_counter()
        world, recorder = build(args.animals, args.plants, ticks=24)
        print(f"world built and stepped two days in {time.perf_counter() - start:.1f} s")
        template = recorder.history().samples()[0]  # the first sample carries gene histograms
        print("the folder layout (UX.10):")
        folder_bench(root, world, recorder, args.checkpoints)
        print("the SQLite file (proposed):")
        world_blob = sqlite_bench(root, world, recorder, args.checkpoints)
        print(f"history appended to the tables, {args.years} years of days:")
        (root / "history").mkdir()
        db = create(root / "history" / "run.sqlite")
        history_bench(db, template, args.years)
        db.close()
        print(f"  file: {mb(size_of(root / 'history'))}")
        history_reads(root / "history" / "run.sqlite")
        reader_beside_writer(root / "history" / "run.sqlite")
        print("a writer killed in the middle of a checkpoint:")
        crash_bench(root, world_blob, gzip.compress(b"x" * 200_000), args.kills)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
