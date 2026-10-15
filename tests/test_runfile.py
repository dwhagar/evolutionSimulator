"""The run file (STORE.2): the history kept in step with the recorder, a run that is read while it is
written, a writer killed in the middle of a checkpoint, the import of the first version's folders."""

import multiprocessing
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing

import pytest
from persistence_support import SAVE_TICK, assert_same_world, rich_world
from run_support import checkpoint_forever, make_legacy_run, table_count

from evolution_simulator.history import Recorder, RecorderRules, TierRule
from evolution_simulator.runs import RunError, RunStore, RunStoreRules
from evolution_simulator.runs.database import APPLICATION_ID, SCHEMA_VERSION, RunFile
from evolution_simulator.world import TimeScale, World, WorldConfig
from evolution_simulator.world.persistence import FORMAT_VERSION

DAY = 86400.0
SMALL_TIERS = RecorderRules(tiers=(TierRule("a", 1, 4), TierRule("b", 3, 3), TierRule("c", 9, 2)))


def store_in(tmp_path, **rules) -> RunStore:
    rules.setdefault("min_wall_seconds", 0.0)
    return RunStore(tmp_path / "runs", RunStoreRules(**rules))


def day_world(seed: int = 3) -> World:
    """An empty world that advances two days a tick, so many samples are taken in few steps."""
    return World(WorldConfig(seed=seed).with_time_scale(TimeScale(seconds_per_tick=2 * DAY)))


# --- the history follows the recorder -----------------------------------------------------------


def test_the_history_rows_equal_the_recorders_after_every_sample(tmp_path) -> None:
    world = day_world()
    recorder = Recorder(world, SMALL_TIERS)
    run = store_in(tmp_path).create(world, recorder=recorder)
    saver = run.autosave(world, recorder)
    for _ in range(60):  # 120 simulated days through tiers that hold 4, 3 and 2 samples
        world.step()
        assert run.history() == recorder.history()
    saver.close()
    assert recorder.history().tiers[-1].samples  # the oldest samples merged all the way down


def test_the_rows_hold_every_kind_of_value_exactly(tmp_path) -> None:
    world = rich_world()
    recorder = Recorder(world)
    run = store_in(tmp_path, checkpoint_every_days=1000.0).create(world, recorder=recorder)
    saver = run.autosave(world, recorder)
    world.run(SAVE_TICK)
    history = run.history()
    assert history == recorder.history()
    assert history.stat_names() and any(s.histograms for s in history.samples())
    assert any(
        s.p10 is not None
        for _, stats in [history.stat_series(history.stat_names()[0])]
        for s in stats
    )
    saver.close()


def test_a_run_without_a_recorder_has_no_history(tmp_path) -> None:
    run = store_in(tmp_path).create(day_world())
    assert run.history() is None
    assert table_count(run, "samples") == 0


def test_following_a_recorder_makes_the_rows_match_it(tmp_path) -> None:
    store = store_in(tmp_path, keep_newest=5)
    world = rich_world()
    recorder = Recorder(
        world, RecorderRules(period_seconds=3600.0, tiers=(TierRule("h", 1, 1000),))
    )
    run = store.create(world, recorder=recorder)
    world.run(30)
    early = run.checkpoint(world, recorder)
    world.run(30)
    run.checkpoint(world, recorder)
    assert len(run.history().samples()) == recorder.sample_count

    # Going back to the earlier checkpoint and carrying on from there: the rows become that history.
    resumed = run.resume(checkpoint=early.name)
    saver = run.autosave(resumed.world, resumed.recorder)
    assert run.history() == resumed.recorder.history()
    assert len(run.history().samples()) < recorder.sample_count
    saver.close()


def test_a_failing_history_write_does_not_stop_the_world_and_is_repaired(
    tmp_path, monkeypatch
) -> None:
    world = day_world()
    recorder = Recorder(world, SMALL_TIERS)
    run = store_in(tmp_path).create(world, recorder=recorder)
    saver = run.autosave(world, recorder)

    def broken(_changes):
        raise RunError("disk full")

    monkeypatch.setattr(run._file, "history_apply", broken)
    for _ in range(6):
        world.step()  # nothing is raised into the world
    monkeypatch.undo()
    assert run.history() != recorder.history()
    run.checkpoint(world, recorder)
    assert run.history() == recorder.history()
    saver.close()


# --- storage behaviour --------------------------------------------------------------------------


def test_retention_gives_the_space_back(tmp_path) -> None:
    store = store_in(tmp_path, keep_newest=2, keep_yearly=False)
    world = rich_world()
    run = store.create(world)
    for _ in range(8):
        world.run(2)
        run.checkpoint(world)
    assert len(run.checkpoints()) == 2
    with closing(sqlite3.connect(run.file_path)) as db:
        assert db.execute("PRAGMA freelist_count").fetchone()[0] == 0
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert table_count(run, "checkpoint_data") == 2


def test_a_checkpoint_at_the_same_tick_replaces_the_old_one(tmp_path) -> None:
    store = store_in(tmp_path)
    world = rich_world()
    run = store.create(world)
    run.checkpoint(world)
    run.checkpoint(world)
    assert [c.tick for c in run.checkpoints()] == [world.tick]
    assert table_count(run, "checkpoint_data") == 1


def test_the_run_file_is_marked_and_versioned(tmp_path) -> None:
    run = store_in(tmp_path).create(day_world())
    with closing(sqlite3.connect(run.file_path)) as db:
        assert db.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_a_checkpoint_records_how_its_world_is_stored(tmp_path) -> None:
    store = store_in(tmp_path)
    world = rich_world()
    run = store.create(world)
    info = run.checkpoint(world)
    assert (info.world_format, info.encoding) == (FORMAT_VERSION, "json+gzip")
    run.close()
    with closing(sqlite3.connect(run.file_path)) as db:
        db.execute("UPDATE checkpoints SET encoding = 'columns+zstd'")
        db.commit()
    with pytest.raises(RunError, match="no checkpoint that can be restored"):
        store.open(run.id).resume()


def test_a_file_from_a_newer_version_or_another_program_is_refused(tmp_path) -> None:
    store = store_in(tmp_path)
    run = store.create(day_world())
    run.close()
    with closing(sqlite3.connect(run.file_path)) as db:
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(RunError, match="newer version"):
        store.open(run.id)
    assert store.list_runs() == []  # a run this program cannot read is left out of the list
    other = tmp_path / "other.sqlite"
    with closing(sqlite3.connect(other)) as db:
        db.execute("CREATE TABLE t (x)")
    with pytest.raises(RunError, match="not a run file"):
        RunFile.open(other)


def test_a_read_only_run_cannot_be_written(tmp_path) -> None:
    store = store_in(tmp_path)
    world = rich_world()
    run = store.create(world)
    reader = store.open(run.id, readonly=True)
    assert reader.checkpoints()[0].tick == world.tick
    with pytest.raises(RunError):
        reader.checkpoint(world)
    with pytest.raises(RunError):
        reader.autosave(world, Recorder(world))


def test_deleting_a_run_closes_it_first(tmp_path) -> None:
    store = store_in(tmp_path)
    run = store.create(day_world())
    opened = store.open(run.id)
    store.delete(run.id)
    assert opened._file.closed and run._file.closed
    assert not (store.root / run.id).exists()


# --- reading a run that is being written --------------------------------------------------------


def test_a_reader_sees_the_last_commit_while_a_writer_has_a_transaction_open(tmp_path) -> None:
    store = store_in(tmp_path)
    world = rich_world()
    recorder = Recorder(world, SMALL_TIERS)
    run = store.create(world, recorder=recorder)
    before = run.summary.checkpoints
    with run._file.transaction():
        run._file.set_meta(name="renamed, but not yet committed")
        reader = store.open(run.id, readonly=True)
        assert reader.name == run.name and reader.summary.checkpoints == before
        assert reader.history() == recorder.history()
        assert [r.id for r in store.list_runs()] == [run.id]
    assert store.open(run.id, readonly=True).manifest["name"].startswith("renamed")


def test_a_reader_follows_the_history_between_checkpoints(tmp_path) -> None:
    store = store_in(tmp_path, checkpoint_every_days=1000.0)
    world = day_world()
    recorder = Recorder(world, SMALL_TIERS)
    run = store.create(world, recorder=recorder)
    saver = run.autosave(world, recorder)
    reader = store.open(run.id, readonly=True)
    for _ in range(10):
        world.step()
    assert reader.history() == recorder.history()
    assert len(reader.history().samples()) == recorder.sample_count > 1
    saver.close()


# --- the writer's claim -------------------------------------------------------------------------


def test_the_writer_is_named_while_the_run_is_followed_and_cleared_after(tmp_path) -> None:
    world = day_world()
    recorder = Recorder(world)
    run = store_in(tmp_path).create(world, recorder=recorder)
    assert run.writer()["pid"] == os.getpid()
    saver = run.autosave(world, recorder)
    saver.finish()
    assert run.writer() is None


def test_a_second_writer_is_refused_while_the_first_lives_and_allowed_when_it_is_gone(
    tmp_path,
) -> None:
    store = store_in(tmp_path)
    world = day_world()
    run = store.create(world)
    run.close()
    run = store.open(run.id)
    recorder = Recorder(world)
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        run._file.set_meta(writer={"pid": other.pid, "started": "now"})
        with pytest.raises(RunError, match="being written by another program"):
            run.autosave(world, recorder)
    finally:
        other.kill()
        other.wait()
    assert run.writer() is None  # it has gone, as a crashed writer has: its claim does not count
    saver = run.autosave(world, recorder)
    assert run.writer()["pid"] == os.getpid()
    saver.close()


# --- a writer killed in the middle of a checkpoint ----------------------------------------------


@pytest.mark.parametrize("delay", [0.05, 0.11, 0.17, 0.23, 0.31, 0.43])
def test_a_writer_killed_mid_checkpoint_leaves_the_last_good_one(tmp_path, delay) -> None:
    root = tmp_path / "runs"
    marker = tmp_path / "marker"
    child = multiprocessing.get_context("spawn").Process(
        target=checkpoint_forever, args=(str(root), str(marker))
    )
    child.start()
    try:
        deadline = time.monotonic() + 60
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "the child never made its run"
        time.sleep(delay)
    finally:
        child.kill()
        child.join()
    store = RunStore(root)
    run = store.open(marker.read_text())
    with closing(sqlite3.connect(run.file_path)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert run.writer() is None  # the killed writer's claim does not count
    assert run.checkpoints()
    for info in run.checkpoints():  # every checkpoint there is whole
        assert run.resume(info.name).world.state_digest() == info.state_digest
    assert run.history() is not None
    run.autosave(rich_world(), Recorder(rich_world())).close()  # and a new writer can take over


# --- the first version's folders ----------------------------------------------------------------


def test_an_old_run_is_listed_then_imported_when_opened(tmp_path) -> None:
    root = tmp_path / "runs"
    world = rich_world()
    recorder = Recorder(world)
    world.run(SAVE_TICK)
    run_id = make_legacy_run(root, world, recorder)
    store = RunStore(root)

    [listed] = store.list_runs()  # from run.json, nothing imported yet
    assert listed.id == run_id and listed.tick == world.tick
    assert not (root / run_id / "run.sqlite").exists()
    with pytest.raises(RunError, match="old folder layout"):
        store.open(run_id, readonly=True)

    run = store.open(run_id)  # imports
    assert (root / run_id / "run.sqlite").is_file()
    assert not (root / run_id / "run.json").exists()
    assert (root / run_id / "imported" / "run.json").is_file()
    assert (root / run_id / "imported" / "checkpoints").is_dir()
    assert run.manifest["imported_from"] == 1
    assert [c.tick for c in run.checkpoints()] == [world.tick]
    assert run.checkpoints()[0].state_digest == world.state_digest()
    resumed = run.resume()
    assert_same_world(resumed.world, world)
    assert resumed.recorder is not None
    assert run.history() == recorder.history()
    assert [r.id for r in store.list_runs()] == [run_id]
    assert store.open(run_id).id == run_id  # a second open does not import again


def test_an_imported_run_starting_at_tick_zero_knows_its_counts(tmp_path) -> None:
    root = tmp_path / "runs"
    world = World(WorldConfig(seed=4))
    world.populate(animals=3, plants=11)
    run_id = make_legacy_run(root, world)
    assert RunStore(root).open(run_id).setup == {"animals": 3, "plants": 11, "seed": 4}


def test_an_import_cut_short_is_finished_on_the_next_open(tmp_path) -> None:
    root = tmp_path / "runs"
    world = rich_world()
    run_id = make_legacy_run(root, world)
    store = RunStore(root)
    store.open(run_id).close()
    # as if the process died after run.sqlite was in place but before the old files were moved
    for name in ("run.json",):
        (root / run_id / "imported" / name).replace(root / run_id / name)
    assert (root / run_id / "run.json").is_file()
    store.open(run_id).close()
    assert not (root / run_id / "run.json").exists()
    assert (root / run_id / "imported" / "run.json").is_file()


def test_a_damaged_old_checkpoint_is_carried_over_and_skipped_on_resume(tmp_path) -> None:
    root = tmp_path / "runs"
    world = rich_world()
    run_id = make_legacy_run(root, world)
    (next((root / run_id / "checkpoints").iterdir()) / "world.json.gz").write_bytes(b"garbage")
    run = RunStore(root).open(run_id)
    assert len(run.checkpoints()) == 1
    with pytest.raises(RunError, match="no checkpoint that can be restored"):
        run.resume()
