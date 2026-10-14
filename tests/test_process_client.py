"""The simulation in its own process (UX.7): a real spawned process over a real pipe."""

import pickle
import time

import pytest
from session_support import BrokenRecipe, FailsAtTick

from evolution_simulator.session import (
    CommandRejected,
    FakeSpec,
    HostRules,
    Inbox,
    Pause,
    Play,
    ProcessClient,
    Select,
    SessionRules,
    SetFrameRate,
    SetSpeed,
    Step,
    WorldSpec,
)
from evolution_simulator.world import World, WorldConfig

TIMEOUT = 30.0


def wait_for(client, done, timeout=TIMEOUT):
    """Poll until ``done(inbox_so_far)`` is true; returns everything seen, merged."""
    if not hasattr(client, "seen"):
        client.seen = {"frame": None, "detail": None, "events": [], "rejected": [], "info": None,
                       "ready": False, "stopped": False, "crash": None}  # fmt: skip
    seen = client.seen
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        inbox = client.poll()
        for key in ("frame", "detail", "info"):
            if getattr(inbox, key) is not None:
                seen[key] = getattr(inbox, key)
        seen["events"].extend(inbox.events)
        seen["rejected"].extend(inbox.rejected)
        seen["ready"] = seen["ready"] or inbox.ready
        seen["stopped"] = seen["stopped"] or inbox.stopped
        seen["crash"] = seen["crash"] or inbox.crash
        if done(seen):
            return seen
        time.sleep(0.01)
    raise AssertionError(f"timed out; saw {seen}")


@pytest.fixture
def client():
    clients = []

    def start(recipe, rules=None):
        started = ProcessClient(recipe, rules)
        clients.append(started)
        return started

    yield start
    for started in clients:
        started.close()


def test_recipes_pickle_so_a_spawned_process_can_build_them():
    for recipe in (FakeSpec(animals=5), WorldSpec(WorldConfig(seed=4), animals=3, plants=9)):
        assert pickle.loads(pickle.dumps(recipe)) == recipe
    assert isinstance(WorldSpec(WorldConfig(seed=1), 2, 5)(), World)


def test_the_simulation_comes_up_runs_commands_and_stops_cleanly(client):
    c = client(FakeSpec(animals=15, plants=20, seed=5))
    seen = wait_for(c, lambda s: s["ready"])
    assert seen["frame"].tick == 0 and seen["frame"].plants is not None
    assert c.process.is_alive() and c.process.pid != __import__("os").getpid()

    c.send(Step(6))
    seen = wait_for(c, lambda s: s["frame"] and s["frame"].tick == 6)
    assert seen["frame"].status.running is False

    c.send(SetSpeed("fortnight"))
    seen = wait_for(c, lambda s: s["rejected"])
    assert isinstance(seen["rejected"][0], CommandRejected)

    target = seen["frame"].animals.id_list()[0]
    c.send(Select(target))
    seen = wait_for(c, lambda s: s["detail"] is not None)
    assert seen["detail"].id == target

    c.close()
    assert not c.process.is_alive()
    assert c.process.exitcode == 0
    assert c.poll().empty


def test_a_real_world_runs_in_the_other_process_and_matches_a_local_one(client):
    spec = WorldSpec(WorldConfig(seed=7), animals=12, plants=40)
    c = client(spec)
    wait_for(c, lambda s: s["ready"])
    c.send(Step(30))
    seen = wait_for(c, lambda s: s["frame"] and s["frame"].tick == 30)
    local = spec()
    local.run(30)
    local_ids = [v.id for v in local.animal_views()]
    assert seen["frame"].animals.id_list() == local_ids
    assert seen["frame"].animal_count == len(local_ids)
    assert seen["frame"].simulated_seconds == local.simulated_seconds


def test_playing_and_pausing_move_the_clock_in_the_other_process(client):
    c = client(FakeSpec(animals=10, plants=10), HostRules(session=SessionRules(work_budget=0.01)))
    wait_for(c, lambda s: s["ready"])
    c.send(SetSpeed("day"))
    c.send(Play())
    seen = wait_for(c, lambda s: s["frame"] and s["frame"].tick >= 5)
    assert seen["frame"].status.running
    c.send(Pause())
    seen = wait_for(c, lambda s: s["frame"] and not s["frame"].status.running)
    stopped_at = seen["frame"].tick
    time.sleep(0.2)
    c.poll()
    assert c.poll().frame is None  # a paused, settled session sends nothing
    assert stopped_at >= 5


def test_the_frame_rate_can_be_stopped_from_the_window(client):
    c = client(FakeSpec(animals=10, plants=10))
    wait_for(c, lambda s: s["ready"])
    c.send(SetFrameRate(0))
    time.sleep(0.3)
    c.poll()  # whatever was already on its way
    c.send(SetSpeed("max"))
    c.send(Play())
    time.sleep(0.5)
    assert c.poll().frame is None  # the simulation runs on, nothing is sent
    c.send(SetFrameRate(30))
    seen = wait_for(c, lambda s: s["frame"] and s["frame"].tick > 0)
    assert seen["frame"].status.running


def test_a_window_that_stops_polling_is_not_flooded_and_catches_up(client):
    rules = HostRules(max_in_flight=2, info_interval=0.2, session=SessionRules(work_budget=0.01))
    c = client(FakeSpec(animals=10, plants=10), rules)
    wait_for(c, lambda s: s["ready"])
    c.send(SetSpeed("max"))
    c.send(Play())
    time.sleep(1.0)  # the window is "busy": no polling
    seen = wait_for(c, lambda s: s["info"] is not None and s["info"].frames_dropped > 0)
    assert seen["info"].frames_dropped > 0
    seen = wait_for(
        c, lambda s: s["frame"] and s["frame"].tick > 100
    )  # the simulation ran on without it
    assert seen["frame"].plants is not None  # and plants survive the folding


def test_a_simulation_that_cannot_be_built_reports_why(client):
    c = client(BrokenRecipe())
    seen = wait_for(c, lambda s: s["crash"])
    assert "RuntimeError" in seen["crash"] and "would not build" in seen["crash"]
    assert c.crashed == seen["crash"]
    c.process.join(10)
    assert c.process.exitcode == 1


def test_a_simulation_that_fails_while_running_reports_the_traceback(client):
    c = client(FailsAtTick(4))
    wait_for(c, lambda s: s["ready"])
    c.send(Step(10))
    seen = wait_for(c, lambda s: s["crash"])
    assert "ValueError" in seen["crash"] and "broke at tick 4" in seen["crash"]
    assert "Traceback" in seen["crash"]


def test_a_process_that_dies_without_a_word_is_noticed(client):
    c = client(FakeSpec(animals=5, plants=5))
    wait_for(c, lambda s: s["ready"])
    c.process.kill()
    seen = wait_for(c, lambda s: s["crash"])
    assert "ended without a word" in seen["crash"]
    c.send(Step(1))  # harmless
    assert c.poll().crash == seen["crash"]


def test_the_inbox_knows_when_it_is_empty():
    assert Inbox().empty
    assert not Inbox(ready=True).empty


# --- a viewer that does not read (the pipe-block finding of UX.19) -------------------------


def test_a_viewer_that_never_reads_cannot_stop_the_simulation():
    """A pipe holds a few KB on Windows and about 200 KB on Linux, and a send waits for the reader.
    Frames here are 390 KB, so the first one already fills it. The host sends from its own thread:
    the world keeps ticking, and closing the client still ends the process."""
    import multiprocessing

    from session_support import TickCounter

    from evolution_simulator.session import Play, SetSpeed

    tick = multiprocessing.get_context("spawn").Value("q", 0)
    client = ProcessClient(TickCounter(tick))
    try:
        client.send(SetSpeed("max"))
        client.send(Play())  # and never poll: nothing is acknowledged or read
        deadline = time.monotonic() + TIMEOUT
        while tick.value == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        first = tick.value
        assert first > 0, "the simulation never started"
        time.sleep(1.0)
        assert tick.value > first + 10, "the simulation stopped while the viewer was not reading"
    finally:
        started = time.monotonic()
        client.close()
        assert time.monotonic() - started < 10.0
    assert not client.process.is_alive()
