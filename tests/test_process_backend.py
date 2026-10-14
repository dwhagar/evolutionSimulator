"""The window's backend over a simulation in another process (UX.33), without Qt."""

import time

import pytest
from session_support import BrokenRecipe, FailsAtTick

from evolution_simulator.runs import RunError, RunStore
from evolution_simulator.session import (
    CommandError,
    FakeSpec,
    InProcessClient,
    NewRunSpec,
    ResumeSpec,
    Select,
    Step,
    WorldSpec,
)
from evolution_simulator.viewer.process_backend import STARTING_STATUS, ProcessBackend
from evolution_simulator.world import WorldConfig

DAY = 24


def small_world(**more):
    return WorldSpec(WorldConfig(seed=5), animals=8, plants=30, **more)


def poll_until(backend, done, timeout=60.0):
    """Poll until ``done(batch)``; returns every batch seen."""
    seen = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        batch = backend.poll()
        seen.append(batch)
        if done(batch):
            return seen
        time.sleep(0.005)
    raise AssertionError("never happened")


@pytest.fixture
def made():
    backends = []

    def make(recipe, **kw):
        backend = ProcessBackend(recipe, **kw)
        backends.append(backend)
        return backend

    yield make
    for backend in backends:
        backend.close()


# --- starting, and what a batch carries -----------------------------------------------------------


def test_it_is_starting_until_the_host_says_ready(made):
    backend = made(FakeSpec(20, 30), client=InProcessClient(FakeSpec(20, 30)))
    assert backend.starting and backend.status == STARTING_STATUS
    first = backend.poll()
    assert first.ready and first.frame is not None and not backend.starting
    assert not backend.poll().ready  # said once


def test_a_real_process_starts_and_commands_sent_early_are_carried_out(made):
    backend = made(FakeSpec(20, 30))
    assert backend.starting
    backend.send(Step(5))  # before the process is up: waits in the pipe
    seen = poll_until(backend, lambda b: b.frame is not None and b.frame.tick >= 5)
    assert any(b.ready for b in seen) and not backend.starting
    assert backend.status == seen[-1].frame.status


def test_status_changes_reach_the_status_property_between_frames(made):
    from evolution_simulator.session import Pause, Play

    backend = made(FakeSpec(20, 30), client=InProcessClient(FakeSpec(20, 30)))
    backend.poll()
    backend.send(Play())
    poll_until(backend, lambda b: backend.status.running)
    backend.send(Pause())
    poll_until(backend, lambda b: not backend.status.running)


def test_history_comes_in_the_batch(made):
    backend = made(small_world())
    backend.send(Step(2 * DAY))
    seen = poll_until(backend, lambda b: b.history is not None and len(b.history) == 2)
    assert any(b.history is not None for b in seen)


def test_a_refused_command_comes_back_as_text(made):
    backend = made(FakeSpec(20, 30), client=InProcessClient(FakeSpec(20, 30)))
    backend.poll()
    backend.send(Select(987654))
    seen = poll_until(backend, lambda b: bool(b.rejected))
    assert seen[-1].rejected and isinstance(seen[-1].rejected[0], str)


def test_a_failed_simulation_is_reported_once_and_commands_are_then_refused(made):
    backend = made(FailsAtTick(3), client=InProcessClient(FailsAtTick(3)))
    backend.send(Step(10))
    seen = poll_until(backend, lambda b: b.crash is not None)
    assert "the simulation broke at tick 3" in seen[-1].crash
    assert backend.crashed == seen[-1].crash
    assert backend.poll().crash is None
    with pytest.raises(CommandError, match="stopped"):
        backend.send(Step(1))


def test_a_recipe_that_cannot_build_is_a_crash_at_start(made):
    backend = made(BrokenRecipe())
    seen = poll_until(backend, lambda b: b.crash is not None)
    assert "the world would not build" in seen[-1].crash and backend.starting
    with pytest.raises(RunError, match="stopped"):
        backend.wait_ready(timeout=2.0)


# --- runs --------------------------------------------------------------------------------------


def test_a_made_up_world_cannot_be_saved(made, tmp_path):
    backend = made(FakeSpec(5, 5))
    assert not backend.saveable
    with pytest.raises(RunError, match="not a real world"):
        backend.save_now(tmp_path)


def test_save_now_starts_a_run_and_then_checkpoints_it(made, tmp_path):
    backend = made(small_world())
    backend.send(Step(3 * DAY))
    poll_until(backend, lambda b: b.frame is not None and b.frame.tick >= 3 * DAY)
    first = backend.save_now(tmp_path, "mine")
    assert (first.name, first.checkpoints) == ("mine", 1)
    backend.send(Step(DAY))
    poll_until(backend, lambda b: b.frame is not None and b.frame.tick >= 4 * DAY)
    second = backend.save_now(tmp_path)
    assert second.run_id == first.run_id and second.saved > first.saved
    assert second.last_checkpoint.endswith(f"{4 * DAY:012d}")
    assert backend.run_notice == second


def test_closing_saves_the_run_unless_told_not_to(made, tmp_path):
    keep = made(small_world())
    keep.send(Step(2 * DAY))
    poll_until(keep, lambda b: b.frame is not None and b.frame.tick >= 2 * DAY)
    notice = keep.save_now(tmp_path)
    keep.send(Step(DAY))
    poll_until(keep, lambda b: b.frame is not None and b.frame.tick >= 3 * DAY)
    keep.close(save=False)
    run = RunStore(tmp_path).open(notice.run_id)
    assert [c.tick for c in run.checkpoints()] == [2 * DAY]  # nothing after the explicit save

    again = made(ResumeSpec(str(tmp_path), notice.run_id))
    again.send(Step(DAY))
    poll_until(again, lambda b: b.frame is not None and b.frame.tick >= 3 * DAY)
    again.close()  # saves
    assert [c.tick for c in run.checkpoints()][-1] == 3 * DAY


def test_a_run_made_at_start_is_known_at_once(made, tmp_path):
    backend = made(NewRunSpec(tmp_path, WorldConfig(seed=2), 8, 30, name="born"))
    poll_until(backend, lambda b: backend.run_notice is not None)
    assert backend.run_notice.name == "born"
    assert backend.save_now(tmp_path).saved >= 1


def test_restarted_resumes_the_run_it_was_saved_into_else_starts_again(made, tmp_path):
    fresh = made(small_world())
    again = fresh.restarted()
    assert again.recipe == fresh.recipe
    again.close()
    fresh.send(Step(DAY))
    poll_until(fresh, lambda b: b.frame is not None and b.frame.tick >= DAY)
    notice = fresh.save_now(tmp_path)
    resumed = fresh.restarted()
    try:
        assert resumed.recipe == ResumeSpec(str(tmp_path), notice.run_id)
        resumed.wait_ready()
        poll_until(resumed, lambda b: b.frame is not None)
        assert resumed.run_notice is None or resumed.run_notice.run_id == notice.run_id
    finally:
        resumed.close()
