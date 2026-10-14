"""The run store (UX.10): checkpoints, retention, resume equals uninterrupted, listing."""

import json
import shutil
from pathlib import PurePosixPath, PureWindowsPath

import pytest
from persistence_support import MORE_TICKS, SAVE_TICK, assert_same_world, rich_world
from world_support import hourly_world

from evolution_simulator.history import Recorder, RecorderRules, TierRule
from evolution_simulator.runs import RunError, RunStore, RunStoreRules, default_runs_root
from evolution_simulator.world import TimeScale, World, WorldConfig, persistence

DAY = 86400.0


class Clock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def store_in(tmp_path, clock=None, **rules) -> RunStore:
    rules.setdefault("min_wall_seconds", 0.0)
    return RunStore(tmp_path / "runs", RunStoreRules(**rules), clock or Clock())


def day_world(seed: int = 3) -> World:
    """An empty world that advances five days a tick, so years pass in a few dozen steps."""
    return World(WorldConfig(seed=seed).with_time_scale(TimeScale(seconds_per_tick=5 * DAY)))


# --- the default location ----------------------------------------------------------------------


def test_default_root_per_platform() -> None:
    windows = default_runs_root({"LOCALAPPDATA": r"C:\Users\a\AppData\Local"}, "win32")
    assert windows == PureWindowsPath(r"C:\Users\a\AppData\Local\evolutionSimulator\runs")
    assert default_runs_root({"XDG_DATA_HOME": "/d"}, "linux") == PurePosixPath(
        "/d/evolutionSimulator/runs"
    )
    from pathlib import Path

    home = Path("/home/x")
    assert default_runs_root({}, "linux", home) == PurePosixPath(
        "/home/x/.local/share/evolutionSimulator/runs"
    )
    assert "Application Support" in str(default_runs_root({}, "darwin", home))
    assert str(default_runs_root({}, "win32", home)).endswith(
        "AppData\\Local\\evolutionSimulator\\runs"
    )


# --- creating, listing, deleting ---------------------------------------------------------------


def test_create_writes_manifest_and_first_checkpoint(tmp_path) -> None:
    store = store_in(tmp_path)
    world = hourly_world(seed=7)
    world.populate(animals=5, plants=20)
    run = store.create(world, name="First try")
    assert run.id.endswith("-first-try")
    manifest = json.loads((run.path / "run.json").read_text())
    assert manifest["seed"] == 7
    assert manifest["name"] == "First try"
    assert manifest["config"]["seed"] == 7
    assert manifest["program_version"]
    assert manifest["summary"]["animals"] == 5
    assert [c.tick for c in run.checkpoints()] == [0]
    assert run.config == world.config


def test_run_ids_do_not_collide(tmp_path) -> None:
    store = store_in(tmp_path)
    a = store.create(hourly_world(), name="same")
    b = store.create(hourly_world(), name="same")
    assert a.id != b.id


def test_list_runs_newest_first_and_skips_junk(tmp_path) -> None:
    clock = Clock()
    store = store_in(tmp_path, clock)
    old = store.create(hourly_world(seed=1), name="old")
    clock.now += 100
    new = store.create(hourly_world(seed=2), name="new")
    (store.root / "not-a-run").mkdir()
    (store.root / "broken").mkdir()
    (store.root / "broken" / "run.json").write_text("{")
    runs = store.list_runs()
    assert [r.id for r in runs] == [new.id, old.id]
    assert runs[0].seed == 2
    assert runs[0].checkpoints == 1
    assert RunStore(tmp_path / "nowhere").list_runs() == []


def test_open_and_delete(tmp_path) -> None:
    store = store_in(tmp_path)
    run = store.create(hourly_world(seed=4))
    assert store.open(run.id).name == "seed 4"
    store.delete(run.id)
    assert store.list_runs() == []
    with pytest.raises(RunError):
        store.open(run.id)
    with pytest.raises(RunError):
        store.delete(run.id)


def test_space_warning(tmp_path) -> None:
    store = store_in(tmp_path, warn_bytes=10**9)
    store.create(hourly_world())
    assert store.total_bytes() > 0
    assert store.space_warning() is None
    small = RunStore(store.root, RunStoreRules(warn_bytes=10))
    assert "Delete runs" in (small.space_warning() or "")


def test_rules_are_checked() -> None:
    with pytest.raises(ValueError):
        RunStoreRules(keep_newest=0)
    with pytest.raises(ValueError):
        RunStoreRules(checkpoint_every_days=0.0)


# --- autosave and retention --------------------------------------------------------------------


def test_autosave_cadence_and_wall_clock_floor(tmp_path) -> None:
    clock = Clock()
    store = store_in(
        tmp_path, clock, checkpoint_every_days=10.0, min_wall_seconds=30.0, keep_newest=50
    )
    world = day_world()  # 5 days a tick
    run = store.create(world)
    saver = run.autosave(world)
    for _ in range(8):
        world.step()
    assert saver.written == 0  # simulated time is due from tick 2, but no real time has passed
    clock.now += 31
    world.step()
    assert saver.written == 1
    assert run.checkpoints()[-1].tick == 9
    world.step()
    world.step()  # 10 simulated days, but the wall clock has not moved
    assert saver.written == 1
    clock.now += 31
    world.step()
    assert saver.written == 2
    saver.close()
    world.step()
    clock.now += 100
    world.step()
    assert saver.written == 2


def test_retention_keeps_newest_and_one_per_year(tmp_path) -> None:
    store = store_in(tmp_path, checkpoint_every_days=20.0, keep_newest=2)
    world = day_world()
    run = store.create(world)
    run.autosave(world)
    world.run(226)  # 1130 simulated days: a little over three years
    kept = run.checkpoints()
    years = [int(c.simulated_seconds // (365.25 * DAY)) for c in kept]
    assert kept[0].tick == 0  # the start is always kept
    assert years[:4] == [0, 1, 2, 3]  # the first of every year
    assert len(kept) == 4 + 1  # the yearly ones and the newest not already among them
    ticks = [c.tick for c in kept]
    assert ticks == sorted(ticks)
    assert kept[-1].tick >= world.tick - 5  # the newest are the latest


def test_hidden_scratch_never_counts_as_a_checkpoint(tmp_path) -> None:
    store = store_in(tmp_path)
    run = store.create(hourly_world())
    (run.path / "checkpoints" / ".writing-checkpoint-000000000009").mkdir()
    assert [c.tick for c in run.checkpoints()] == [0]


# --- resuming ----------------------------------------------------------------------------------


def test_resume_goes_on_exactly_like_an_uninterrupted_run(tmp_path) -> None:
    store = store_in(tmp_path)
    reference = rich_world()
    ref_recorder = Recorder(reference)
    reference.run(SAVE_TICK + MORE_TICKS - reference.tick)
    ref_recorder.observe()

    world = rich_world()
    recorder = Recorder(world)
    run = store.create(world, recorder=recorder)
    world.run(SAVE_TICK - world.tick)
    run.checkpoint(world, recorder)

    resumed = store.open(run.id).resume()
    assert resumed.checkpoint.tick == world.tick
    assert resumed.recorder is not None
    assert_same_world(resumed.world, world)
    resumed.world.run(MORE_TICKS)
    resumed.recorder.observe()
    assert resumed.world.state_digest() == reference.state_digest()
    assert resumed.recorder.history() == ref_recorder.history()


def test_resume_older_checkpoint_has_its_own_history(tmp_path) -> None:
    store = store_in(tmp_path, keep_newest=5)
    world = rich_world()
    recorder = Recorder(
        world, RecorderRules(period_seconds=3600.0, tiers=(TierRule("hour", 1, 1000),))
    )
    run = store.create(world, recorder=recorder)
    world.run(30)
    run.checkpoint(world, recorder)
    world.run(30)
    run.checkpoint(world, recorder)
    early = run.resume(checkpoint=run.checkpoints()[1].name)
    assert early.world.tick == run.checkpoints()[1].tick
    assert early.recorder is not None
    assert early.recorder.sample_count < recorder.sample_count


def test_damaged_newest_checkpoint_falls_back(tmp_path) -> None:
    store = store_in(tmp_path, keep_newest=5)
    world = rich_world()
    run = store.create(world)
    world.run(20)
    newest = run.checkpoint(world)
    (newest.path / "world.json.gz").write_bytes(b"garbage")
    resumed = run.resume()
    assert resumed.checkpoint.tick == 1
    assert resumed.world.tick == 1
    shutil.rmtree(run.path / "checkpoints")
    (run.path / "checkpoints").mkdir()
    with pytest.raises(RunError):
        run.resume()


def test_unknown_checkpoint_name(tmp_path) -> None:
    run = store_in(tmp_path).create(hourly_world())
    with pytest.raises(RunError):
        run.resume("checkpoint-999")


def test_run_without_recorder_resumes_without_one(tmp_path) -> None:
    run = store_in(tmp_path).create(hourly_world())
    resumed = run.resume()
    assert resumed.recorder is None
    assert run.history() is None


def test_history_file_and_manifest_series(tmp_path) -> None:
    store = store_in(tmp_path)
    world = rich_world()
    recorder = Recorder(world)
    run = store.create(world, recorder=recorder)
    saver = run.autosave(world, recorder)
    world.run(SAVE_TICK)
    saver.finish()
    history = run.history()
    assert history is not None
    assert history == recorder.history()
    summary = store.list_runs()[0]
    assert summary.tick == world.tick
    assert summary.animals == len(world.animals)
    assert len(summary.animal_history) == len(history.series("animals")[1])


def test_config_round_trip() -> None:
    config = WorldConfig(seed=11)
    assert persistence.config_from_dict(persistence.config_to_dict(config)) == config
