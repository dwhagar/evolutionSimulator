"""The NewRun command: a session throws its world away and starts another (UX.17)."""

import pickle
import time
from dataclasses import replace

import pytest

from evolution_simulator.session import (
    CommandError,
    EventBatch,
    FakeSimulation,
    FakeSpec,
    Host,
    HostRules,
    NewRun,
    Play,
    ProcessClient,
    RunStarted,
    Select,
    Session,
    SessionRules,
    SetSpeed,
    StatusChanged,
    Step,
    build_world,
)
from evolution_simulator.world import World, WorldConfig


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


def session_on_fake(clock):
    return Session(
        FakeSimulation(20, 50, seed=1), rules=SessionRules(work_budget=10.0), clock=clock
    )


def small(seed=5, **kwargs):
    return NewRun(WorldConfig(seed=seed), **{"animals": 6, "plants": 20, **kwargs})


# --- the command ---------------------------------------------------------------------


def test_a_new_run_holds_its_config_and_counts_and_pickles():
    command = small(seed=9)
    assert command.label == "world, seed 9"
    assert pickle.loads(pickle.dumps(command)) == command


@pytest.mark.parametrize("animals", [-1, 1.5, True, "3"])
def test_a_bad_count_is_refused(animals):
    with pytest.raises(CommandError, match="whole number of animals"):
        small(animals=animals)


def test_counts_above_the_caps_of_the_config_are_refused():
    config = WorldConfig(max_animals=10, max_plants=30)
    NewRun(config, 10, 30)
    with pytest.raises(CommandError, match="at most 10 animals"):
        NewRun(config, 11, 0)
    with pytest.raises(CommandError, match="at most 30 plants"):
        NewRun(config, 0, 31)


def test_something_that_is_not_a_config_is_refused():
    with pytest.raises(CommandError, match="WorldConfig"):
        NewRun({"seed": 1})


# --- the session ---------------------------------------------------------------------


def test_a_new_run_replaces_the_world_with_a_populated_one_at_tick_zero(clock):
    session = session_on_fake(clock)
    session.handle(Step(5))
    session.update()
    session.handle(small(seed=5))
    world = session.simulation
    assert isinstance(world, World) and world.tick == 0
    assert world.config.seed == 5
    assert len(world.animal_views()) == 6 and world.plant_count == 20


def test_the_new_run_is_the_same_world_as_building_it_by_hand(clock):
    session = session_on_fake(clock)
    session.handle(small(seed=5))
    by_hand = World(WorldConfig(seed=5))
    by_hand.populate(animals=6, plants=20)
    session.handle(Step(30))
    session.update()
    by_hand.run(30)
    assert session.simulation.state_digest() == by_hand.state_digest()


def test_unseeded_founders_are_asked_for(clock):
    session = session_on_fake(clock)
    session.handle(small(seeded=False))
    seeded = World(WorldConfig(seed=5))
    seeded.populate(animals=6, plants=20)
    assert session.simulation.state_digest() != seeded.state_digest()


def test_the_new_run_starts_paused_and_keeps_the_speed_the_viewer_set(clock):
    session = session_on_fake(clock)
    session.handle(SetSpeed("year"))
    session.handle(Play())
    session.handle(NewRun(WorldConfig(seed=2), 3, 10))
    status = session.status
    assert not status.running and status.steps_left == 0
    assert status.speed_preset == "year"
    session.handle(Play())
    clock.advance(0.5)
    assert session.update().ticks > 0  # the pace follows the kept speed too


def test_as_fast_as_possible_is_kept_too(clock):
    session = session_on_fake(clock)
    session.handle(SetSpeed("max"))
    session.handle(small())
    assert session.status.speed_preset == "max"


def test_a_speed_set_in_the_config_is_used(clock):
    session = session_on_fake(clock)
    session.handle(SetSpeed("year"))
    fast = WorldConfig().with_rules(time=replace(WorldConfig().traits.time, speed=86_400.0))
    session.handle(NewRun(fast, 3, 10))
    assert session.status.speed_preset == "day"


def test_a_new_run_clears_the_selection(clock):
    session = session_on_fake(clock)
    animal_id = session.simulation.animal_views()[0].id
    session.handle(Select(animal_id))
    session.update()
    assert session.status.selected == animal_id
    session.handle(small())
    assert session.status.selected is None
    assert session.detail() is None


def test_the_first_frame_of_a_new_run_carries_the_plants_and_the_frame_counter_goes_on(clock):
    session = session_on_fake(clock)
    old = session.update().frame
    assert old is not None and old.plants is not None
    clock.advance(0.01)  # too soon for plants again
    session.handle(small())
    frame = session.update().frame
    assert frame is not None and frame.seq > old.seq
    assert frame.plants is not None and frame.plants.count == 20
    assert frame.tick == 0 and frame.animal_count == 6


def test_subscribers_hear_run_started(clock):
    session = session_on_fake(clock)
    heard = []
    session.subscribe(heard.append)
    session.handle(small(seed=11))
    assert [e for e in heard if isinstance(e, RunStarted)] == [RunStarted("world, seed 11", 6, 20)]


def test_the_session_listens_to_the_new_world_and_lets_go_of_the_old_one(clock):
    old = FakeSimulation(20, 50, seed=1)
    session = Session(old, clock=clock)
    session.subscribe(lambda event: None)
    assert len(old._listeners) == 1
    session.handle(small())
    assert old._listeners == []
    assert len(session.simulation._event_listeners) == 1


def test_a_session_nobody_listens_to_does_not_listen_to_the_new_world_either(clock):
    session = session_on_fake(clock)
    session.handle(small())
    assert session.simulation._event_listeners == []


def test_status_changes_are_announced(clock):
    session = session_on_fake(clock)
    session.handle(Play())
    heard = []
    session.subscribe(heard.append)
    session.handle(small())
    assert any(isinstance(e, StatusChanged) and not e.status.running for e in heard)


def test_a_world_that_cannot_be_built_changes_nothing(clock):
    def refuse(command):
        raise CommandError("no room")

    before = FakeSimulation(20, 50, seed=1)
    session = Session(before, clock=clock, new_run=refuse)
    session.handle(Play())
    with pytest.raises(CommandError, match="no room"):
        session.handle(small())
    assert session.simulation is before and session.status.running


def test_a_session_can_be_given_its_own_way_to_build_runs(clock):
    built = []

    def build(command):
        built.append(command)
        return FakeSimulation(command.animals, command.plants, seed=command.config.seed)

    session = Session(FakeSimulation(1, 1), clock=clock, new_run=build)
    session.handle(small(animals=4, plants=9))
    assert built and isinstance(session.simulation, FakeSimulation)
    assert session.update().frame.animal_count == 4


def test_the_real_builder_turns_a_value_error_into_a_command_error():
    command = small()
    object.__setattr__(command, "animals", 10**9)  # past the cap, as a stale command might be
    with pytest.raises(CommandError, match="could not be built"):
        build_world(command)


# --- through the host, in the same process and in another ------------------------------------


def host_on_fake(**host_rules):
    clock = Clock()
    sim = FakeSimulation(30, 40, seed=2, period=20)
    session = Session(
        sim,
        rules=SessionRules(max_ticks_per_update=3, max_elapsed=10.0, work_budget=10.0),
        clock=clock,
    )
    return Host(session, HostRules(**host_rules), clock), clock


def world_events(host):
    return [e for e in host._events if not isinstance(e, StatusChanged)]


def test_the_host_sends_run_started_and_forgets_the_old_runs_pending_events():
    host, clock = host_on_fake(event_interval=100.0)
    host.first_message()
    host.receive(Step(60))
    for _ in range(30):
        host.step()
        if len(world_events(host)) >= 3:
            break
    assert len(world_events(host)) >= 3
    host.receive(small(seed=8))
    assert world_events(host) == [RunStarted("world, seed 8", 6, 20)]
    clock.advance(200.0)
    batches = [m for m in host.step() if isinstance(m, EventBatch)]
    assert [e for b in batches for e in b.events if isinstance(e, RunStarted)] == [
        RunStarted("world, seed 8", 6, 20)
    ]


def test_run_started_gets_through_when_the_event_cap_has_been_reached():
    host, _ = host_on_fake(max_events_per_second=1, max_buffered_events=2)
    host.first_message()
    host.receive(Step(60))
    for _ in range(30):
        host.step()
    assert host._events_dropped > 0  # the caps are in force
    host.receive(small())
    assert RunStarted in {type(e) for e in host._events}


def wait_for_frame(client, wanted, timeout=60.0):
    deadline = time.monotonic() + timeout
    events, frame = [], None
    while time.monotonic() < deadline:
        inbox = client.poll()
        events.extend(inbox.events)
        frame = inbox.frame or frame
        if frame is not None and wanted(frame):
            return frame, events
        time.sleep(0.01)
    raise AssertionError(f"timed out; last frame {frame}")


def test_a_new_run_is_built_in_the_other_process():
    client = ProcessClient(FakeSpec(animals=10, plants=10, seed=1))
    try:
        wait_for_frame(client, lambda f: True)
        client.send(NewRun(WorldConfig(seed=21), 7, 25))
        frame, events = wait_for_frame(client, lambda f: f.animal_count == 7)
        assert frame.tick == 0 and frame.plant_count == 25 and not frame.status.running
        deadline = time.monotonic() + 30.0
        while not any(isinstance(e, RunStarted) for e in events) and time.monotonic() < deadline:
            events.extend(client.poll().events)
            time.sleep(0.01)
        assert [e for e in events if isinstance(e, RunStarted)] == [
            RunStarted("world, seed 21", 7, 25)
        ]
        client.send(Step(5))
        frame, _ = wait_for_frame(client, lambda f: f.tick == 5)
        assert frame.animal_count <= 7
    finally:
        client.close()
