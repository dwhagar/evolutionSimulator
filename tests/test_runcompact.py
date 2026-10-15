"""Compacting a run file (STORE.3): the size drops, the run is the same, a running writer is refused,
and a compaction that is interrupted anywhere leaves the run whole."""

import atexit
import multiprocessing
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing

import pytest
from persistence_support import rich_world
from run_support import compact_forever

from evolution_simulator.history import Recorder
from evolution_simulator.runs import RunError, RunStore, RunStoreRules
from evolution_simulator.runs import compact as compact_module
from evolution_simulator.runs.database import RunFile
from evolution_simulator.world import TimeScale, World, WorldConfig

DAY = 86400.0


def store_in(tmp_path) -> RunStore:
    return RunStore(tmp_path / "runs", RunStoreRules(min_wall_seconds=0.0, keep_newest=6))


_TEMPLATE: dict = {}


def _build_template():
    """A run with several checkpoints, all but the newest then deleted without giving their pages
    back. Built once; every test works on its own copy."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="compact-template-"))
    atexit.register(shutil.rmtree, root, True)
    store = RunStore(root / "runs", RunStoreRules(min_wall_seconds=0.0, keep_newest=6))
    world = World(WorldConfig(seed=3).with_time_scale(TimeScale(seconds_per_tick=2 * DAY)))
    world.populate(animals=60, plants=200)
    recorder = Recorder(world)
    run = store.create(world, name="big", recorder=recorder)
    for _ in range(5):
        world.run(6)
        run.checkpoint(world, recorder)
    run.close()
    run = store.open(run.id)
    newest = run.checkpoints()[-1]
    with closing(sqlite3.connect(run.file_path)) as db, db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM checkpoints WHERE tick != ?", (newest.tick,))
    run_id = run.id
    run.close()
    return root, run_id, newest


def run_with_free_space(tmp_path):
    if not _TEMPLATE:
        _TEMPLATE["built"] = _build_template()
    root, run_id, newest = _TEMPLATE["built"]
    shutil.copytree(root / "runs", tmp_path / "runs")
    return store_in(tmp_path), run_id, newest


def whole(store, run_id, newest) -> None:
    run = store.open(run_id)
    try:
        with closing(sqlite3.connect(run.file_path)) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert [c.tick for c in run.checkpoints()] == [newest.tick]
        assert run.resume().world.state_digest() == newest.state_digest
        assert run.history() is not None
        assert run._file.table_counts()["samples"] > 0
        assert run.writer() is None
    finally:
        run.close()
    folder = store.root / run_id
    assert sorted(p.name for p in folder.iterdir()) == ["run.sqlite"]


def test_compacting_gives_the_space_back_and_keeps_the_run(tmp_path) -> None:
    store, run_id, newest = run_with_free_space(tmp_path)
    before = store.open(run_id)
    history = before.history()
    manifest = {k: v for k, v in before.manifest.items() if k != "writer"}
    before.close()
    result = store.compact(run_id)
    assert result.run_id == run_id
    assert result.after < result.before
    assert result.saved == result.before - result.after
    whole(store, run_id, newest)
    after = store.open(run_id)
    assert {k: v for k, v in after.manifest.items() if k != "writer"} == manifest
    assert after.history().series("animals") == history.series("animals")
    after.close()
    assert store.compact(run_id).after <= result.after  # and again changes nothing for the worse


def test_compacting_keeps_the_blobs_byte_for_byte(tmp_path) -> None:
    store, run_id, newest = run_with_free_space(tmp_path)
    run = store.open(run_id)
    world, recorder = run._file.checkpoint_blobs(newest.tick)
    run.close()
    store.compact(run_id)
    run = store.open(run_id)
    assert run._file.checkpoint_blobs(newest.tick) == (world, recorder)
    run.close()


# --- a run that is being written is refused -----------------------------------------------------


def test_a_live_writer_in_another_program_refuses_it(tmp_path) -> None:
    store, run_id, newest = run_with_free_space(tmp_path)
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        run = store.open(run_id)
        run._file.set_meta(writer={"pid": other.pid, "started": "now"})
        run.close()
        size = (store.root / run_id / "run.sqlite").stat().st_size
        with pytest.raises(RunError, match="being written"):
            store.compact(run_id)
        assert (store.root / run_id / "run.sqlite").stat().st_size == size  # not touched
        run = store.open(run_id)
        assert run.writer()["pid"] == other.pid  # and the other writer's claim is still its own
        run.close()
    finally:
        other.kill()
        other.wait()
    store.compact(run_id)  # it has gone: its claim no longer counts
    whole(store, run_id, newest)


def test_a_run_this_program_is_writing_refuses_it(tmp_path) -> None:
    store = store_in(tmp_path)
    world = rich_world()
    recorder = Recorder(world)
    run = store.create(world, recorder=recorder)
    saver = run.autosave(world, recorder)
    with pytest.raises(RunError, match="being written by this program"):
        store.compact(run.id)
    saver.close()
    assert store.compact(run.id).before > 0
    run.close()


def test_a_claim_taken_by_another_compaction_refuses_it_too(tmp_path) -> None:
    store, run_id, _ = run_with_free_space(tmp_path)
    run = store.open(run_id)
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        run._file.set_meta(writer={"pid": other.pid, "started": "now", "task": "compact"})
        run.close()
        with pytest.raises(RunError, match="being written"):
            store.compact(run_id)
    finally:
        other.kill()
        other.wait()


def test_an_old_folder_run_or_a_missing_one_is_refused(tmp_path) -> None:
    store = store_in(tmp_path)
    with pytest.raises(RunError, match="There is no run"):
        store.compact("nothing")


# --- interrupted --------------------------------------------------------------------------------


def test_a_failure_while_putting_the_copy_in_place_leaves_the_run_as_it_was(
    tmp_path, monkeypatch
) -> None:
    store, run_id, newest = run_with_free_space(tmp_path)

    def refuse(*_args):
        raise OSError("in use")

    monkeypatch.setattr(compact_module.os, "replace", refuse)
    with pytest.raises(RunError, match="could not be put in place"):
        store.compact(run_id)
    monkeypatch.undo()
    whole(store, run_id, newest)  # the original, whole, no copy left, no claim left


def test_an_interruption_while_the_copy_is_written_leaves_the_run_as_it_was(
    tmp_path, monkeypatch
) -> None:
    store, run_id, newest = run_with_free_space(tmp_path)
    real = RunFile.vacuum_into

    def interrupted(self, target):
        real(self, target)
        raise KeyboardInterrupt  # the copy is there but the compaction does not finish

    monkeypatch.setattr(RunFile, "vacuum_into", interrupted)
    with pytest.raises(KeyboardInterrupt):
        store.compact(run_id)
    monkeypatch.undo()
    whole(store, run_id, newest)


def test_a_copy_that_does_not_match_is_never_put_in_place(tmp_path, monkeypatch) -> None:
    store, run_id, newest = run_with_free_space(tmp_path)
    real = RunFile.vacuum_into

    def lossy(self, target):
        real(self, target)
        with closing(sqlite3.connect(target)) as db, db:
            db.execute("DELETE FROM names WHERE id = (SELECT MAX(id) FROM names)")

    monkeypatch.setattr(RunFile, "vacuum_into", lossy)
    with pytest.raises(RunError, match="same rows"):
        store.compact(run_id)
    monkeypatch.undo()
    whole(store, run_id, newest)


def test_a_copy_left_by_an_attempt_that_was_cut_short_is_replaced(tmp_path) -> None:
    store, run_id, newest = run_with_free_space(tmp_path)
    folder = store.root / run_id
    (folder / "run.sqlite.compact").write_bytes(b"half a file")
    (folder / "run.sqlite.compact-wal").write_bytes(b"junk")
    store.compact(run_id)
    whole(store, run_id, newest)


@pytest.mark.parametrize("delay", [0.02, 0.07, 0.13, 0.2, 0.31])
def test_a_program_killed_while_compacting_leaves_the_run_whole(tmp_path, delay) -> None:
    store, run_id, newest = run_with_free_space(tmp_path)
    marker = tmp_path / "marker"
    child = multiprocessing.get_context("spawn").Process(
        target=compact_forever, args=(str(store.root), run_id, str(marker))
    )
    child.start()
    try:
        deadline = time.monotonic() + 60
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "the child never started"
        time.sleep(delay)
    finally:
        child.kill()
        child.join()
    run = store.open(run_id)  # whatever was left behind, the run opens and every checkpoint reads
    with closing(sqlite3.connect(run.file_path)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert run.writer() is None
    assert [c.tick for c in run.checkpoints()] == [newest.tick]
    assert run.resume().world.state_digest() == newest.state_digest
    run.close()
    store.compact(run_id)  # a stray copy and a dead claim do not stop the next one
    whole(store, run_id, newest)
