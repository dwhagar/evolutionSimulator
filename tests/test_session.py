"""The simulation session: commands, pacing, frames, details and events (UX.6).

Most cases run against both the real world and the FakeSimulation, which is the point of the fake:
a screen built on it sees the same session behaviour.
"""

import pickle

import pytest
from world_support import animal_dna

from evolution_simulator.session import (
    ANIMAL_COLUMNS,
    FRAME_FORMAT,
    CommandError,
    Deselect,
    FakeSimulation,
    Pause,
    Play,
    Select,
    Session,
    SessionRules,
    SetSpeed,
    Status,
    StatusChanged,
    Step,
)
from evolution_simulator.world import Died, TimeScale, Vec, World, WorldConfig
from evolution_simulator.world.timescale import SPEED_PRESETS


class Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def real_world(animals=20, plants=80, seed=1):
    world = World(WorldConfig(seed=seed))
    world.populate(animals=animals, plants=plants)
    return world


def fake_world(animals=20, plants=80, seed=1):
    return FakeSimulation(animals, plants, seed=seed)


@pytest.fixture(params=[real_world, fake_world], ids=["world", "fake"])
def sim(request):
    return request.param()


def make(sim, **rules):
    clock = Clock()
    return Session(sim, rules=SessionRules(**rules), clock=clock), clock


# --- starting state and commands --------------------------------------------------


def test_a_new_session_is_paused_and_runs_nothing(sim):
    session, clock = make(sim)
    clock.advance(5.0)
    update = session.update()
    assert update.ticks == 0 and sim.tick == 0
    assert not session.status.running


def test_play_runs_the_ticks_real_time_owes(sim):
    session, clock = make(sim, work_budget=10.0)
    session.handle(SetSpeed("day"))  # 24 ticks a real second at the hourly tick
    session.handle(Play())
    session.update()
    clock.advance(0.5)
    update = session.update()
    assert update.ticks == 12 and sim.tick == 12
    clock.advance(0.5)
    assert session.update().ticks == 12


def test_pause_stops_the_ticks(sim):
    session, clock = make(sim, work_budget=10.0)
    session.handle(SetSpeed("day"))
    session.handle(Play())
    clock.advance(0.25)
    session.update()
    session.handle(Pause())
    before = sim.tick
    clock.advance(1.0)
    assert session.update().ticks == 0 and sim.tick == before


def test_step_runs_exactly_that_many_ticks_and_pauses(sim):
    session, clock = make(sim, work_budget=10.0)
    session.handle(Play())
    session.handle(Step(5))
    assert not session.status.running and session.status.steps_left == 5
    update = session.update()
    assert update.ticks == 5 and sim.tick == 5
    assert session.status.steps_left == 0
    clock.advance(10.0)
    assert session.update().ticks == 0


def test_a_long_step_is_worked_off_over_several_updates(sim):
    session, _ = make(sim, work_budget=0.0)  # one tick per update
    session.handle(Step(3))
    assert [session.update().ticks for _ in range(4)] == [1, 1, 1, 0]
    assert sim.tick == 3


def test_a_step_needs_a_whole_positive_number():
    for bad in (0, -1, 1.5):
        with pytest.raises(CommandError):
            Step(bad)  # type: ignore[arg-type]


def test_speeds_are_checked(sim):
    session, _ = make(sim)
    for bad in ("fortnight", 0.0, -3.0, float("nan"), float("inf")):
        with pytest.raises(CommandError):
            session.handle(SetSpeed(bad))
    session.handle(SetSpeed("year"))
    assert session.status.speed_preset == "year"
    assert session.status.speed_asked == SPEED_PRESETS["year"]
    session.handle(SetSpeed(1234.5))
    assert session.status.speed_asked == 1234.5 and session.status.speed_preset is None
    session.handle(SetSpeed("max"))
    assert session.status.speed_asked is None and session.status.speed_preset == "max"


def test_the_session_starts_at_the_simulations_own_speed():
    sim = World(WorldConfig(time_scale=TimeScale(speed=SPEED_PRESETS["day"])))
    assert Session(sim).status.speed_preset == "day"


def test_ticks_the_computer_cannot_run_are_dropped_not_queued(sim):
    session, clock = make(sim, work_budget=0.0, max_elapsed=10.0)
    session.handle(SetSpeed("day"))
    session.handle(Play())
    session.update()
    clock.advance(1.0)  # owes 24 ticks, the budget allows one
    update = session.update()
    assert update.ticks == 1 and update.dropped == 23
    assert session.status.ticks_dropped == 23 and session.status.behind
    clock.advance(0.0)
    assert session.update().ticks == 0  # nothing queued behind it


def test_the_slowest_computer_is_not_flooded_after_a_stall(sim):
    session, clock = make(sim, work_budget=10.0, max_elapsed=0.5)
    session.handle(SetSpeed("day"))
    session.handle(Play())
    session.update()
    clock.advance(3600.0)  # the host was frozen for an hour
    assert session.update().ticks == 12  # half a second's worth


def test_max_speed_runs_until_the_budget_is_spent(sim):
    session, _ = make(sim, work_budget=0.0, max_ticks_per_update=7)
    session.handle(SetSpeed("max"))
    session.handle(Play())
    update = session.update()
    assert update.ticks == 1  # the budget is zero: one tick, then stop
    session2, _ = make(sim, work_budget=10.0, max_ticks_per_update=7)
    session2.handle(SetSpeed("max"))
    session2.handle(Play())
    assert session2.update().ticks == 7


def test_the_speed_achieved_is_measured(sim):
    session, clock = make(sim, work_budget=10.0, max_elapsed=10.0)
    session.handle(SetSpeed("day"))
    session.handle(Play())
    session.update()
    for _ in range(10):
        clock.advance(0.1)
        session.update()
    achieved = session.status.speed_achieved
    assert achieved == pytest.approx(SPEED_PRESETS["day"], rel=0.2)
    session.handle(Pause())
    assert session.status.speed_achieved is None


def test_the_same_commands_give_the_same_world_whatever_the_timing():
    digests = []
    for slices in (1, 8, 32):  # powers of two add up exactly
        world = real_world(seed=6)
        session, clock = make(world, work_budget=10.0, max_elapsed=10.0)
        session.handle(SetSpeed("day"))  # 24 ticks a real second
        session.handle(Play())
        session.update()
        for _ in range(slices):
            clock.advance(1.0 / slices)
            session.update()
        assert world.tick == 24
        digests.append(world.state_digest())
    stepped = real_world(seed=6)
    session, _ = make(stepped)
    for _ in range(24):
        session.handle(Step(1))
        session.update()
    digests.append(stepped.state_digest())
    plain = real_world(seed=6)
    plain.run(24)
    digests.append(plain.state_digest())
    assert len(set(digests)) == 1


def test_a_session_with_a_selection_and_listeners_does_not_change_the_world():
    plain = real_world(seed=7)
    plain.run(120)
    watched = real_world(seed=7)
    session, _ = make(watched, work_budget=10.0)
    session.subscribe(lambda event: None)
    session.handle(Select(watched.animal_views()[0].id))
    session.handle(Step(120))
    session.update()
    assert watched.state_digest() == plain.state_digest()


# --- frames -----------------------------------------------------------------------


def test_the_first_update_sends_a_frame_with_everything(sim):
    session, _ = make(sim)
    frame = session.update().frame
    assert frame is not None
    assert frame.format == FRAME_FORMAT and frame.seq == 1
    assert frame.tick == sim.tick and frame.world_size == sim.bounds.size
    assert frame.animal_count == frame.animals.count == len(sim.animal_views())
    assert frame.plants is not None and frame.plant_count == frame.plants.count == sim.plant_count
    assert frame.animals.columns == ANIMAL_COLUMNS
    assert isinstance(frame.status, Status)


def test_a_frame_holds_the_views_it_was_packed_from(sim):
    session, _ = make(sim)
    frame = session.frame()
    views = sim.animal_views()
    rows = list(frame.animals.rows())
    assert [r[0] for r in rows] == [v.id for v in views]
    for (_, floats, flags), view in zip(rows, views, strict=True):
        assert floats[0] == pytest.approx(view.x) and floats[1] == pytest.approx(view.y)
        assert floats[4] == pytest.approx(view.energy_ratio)
        assert bool(flags & 1) == view.asleep
        assert bool(flags & 2) == view.pregnant
        assert bool(flags & 16) == (view.sex == 1)
    assert frame.animals.column("radius") == pytest.approx([v.radius for v in views])


def test_a_frame_pickles_and_is_small(sim):
    session, _ = make(sim)
    frame = session.frame()
    assert pickle.loads(pickle.dumps(frame)) == frame
    assert len(pickle.dumps(frame)) < 10_000 + frame.nbytes


def test_a_frame_at_the_design_size_is_small():
    world = World(WorldConfig(seed=2))
    world.populate(animals=300, plants=3000)
    session = Session(world)
    full = session.frame(include_plants=True)
    light = session.frame(include_plants=False)
    assert light.plants is None and light.plant_count == 3000
    assert light.nbytes < 14_000  # the 30-a-second case
    assert full.nbytes < 80_000  # the twice-a-second case, vs 54 KB measured in the design note


def test_a_still_session_sends_no_frame_until_something_changes(sim):
    session, clock = make(sim)
    assert session.update().frame is not None
    clock.advance(1.0)
    assert session.update().frame is None
    session.handle(Step(1))
    clock.advance(0.001)
    update = session.update()
    assert update.ticks == 1 and update.frame is not None and update.frame.tick == 1


def test_frames_are_limited_to_the_frame_rate(sim):
    session, clock = make(sim, work_budget=10.0, max_ticks_per_update=2, frame_interval=0.1)
    session.handle(SetSpeed("max"))
    session.handle(Play())
    sent = 0
    for _ in range(100):
        clock.advance(0.01)
        sent += session.update().frame is not None
    assert 9 <= sent <= 11  # one a tenth of a second for a second


def test_plants_go_out_now_and_then_and_when_the_session_settles(sim):
    session, clock = make(
        sim, work_budget=10.0, max_ticks_per_update=2, frame_interval=0.0, plant_interval=0.5
    )
    session.handle(SetSpeed("max"))
    session.handle(Play())
    carried = []
    for _ in range(20):
        clock.advance(0.1)
        update = session.update()
        if update.frame is not None:
            carried.append(update.frame.plants is not None)
    assert carried[0]
    assert 3 <= sum(carried) <= 6  # about every half second of the two seconds
    session.handle(Pause())
    frame = session.update().frame
    assert frame is not None and frame.plants is not None and frame.tick == sim.tick


def test_the_frame_carries_the_clock_and_the_light(sim):
    session, _ = make(sim)
    session.handle(Step(5))
    frame = session.update().frame
    assert frame.tick == 5
    assert frame.simulated_seconds == sim.simulated_seconds
    assert frame.elapsed == sim.elapsed
    assert frame.day == sim.day and frame.daylight == sim.daylight
    assert frame.is_night == sim.is_night


# --- selection --------------------------------------------------------------------


def test_selecting_sends_the_animal_and_starts_the_brain_trace(sim):
    session, _ = make(sim)
    target = sim.animal_views()[0].id
    session.handle(Select(target))
    assert session.status.selected == target
    update = session.update()
    assert update.detail is not None and update.detail.id == target and update.detail.alive
    assert session.detail().id == target


def test_the_detail_is_sent_at_its_own_rate(sim):
    session, clock = make(sim, work_budget=10.0, max_ticks_per_update=2, detail_interval=0.1)
    session.handle(Select(sim.animal_views()[0].id))
    session.handle(SetSpeed("max"))
    session.handle(Play())
    sent = 0
    for _ in range(100):
        clock.advance(0.01)
        sent += session.update().detail is not None
    assert 9 <= sent <= 12


def test_selecting_nobody_is_an_error_and_changes_nothing(sim):
    session, _ = make(sim)
    with pytest.raises(CommandError):
        session.handle(Select(10**9))
    assert session.status.selected is None


def test_deselect_stops_the_details_and_the_trace(sim):
    session, clock = make(sim)
    session.handle(Select(sim.animal_views()[0].id))
    session.update()
    session.handle(Deselect())
    clock.advance(1.0)
    assert session.update().detail is None and session.status.selected is None


def test_the_trace_shows_in_the_detail_once_the_brain_has_run():
    world = real_world(animals=10, seed=8)
    session, _ = make(world, work_budget=10.0)
    target = world.animal_views()[0].id
    session.handle(Select(target))
    session.handle(Step(25))
    detail = session.update().detail
    if detail is not None and detail.alive:
        assert detail.brain is not None
        assert len(detail.brain.inputs) == 20


def test_when_the_selected_animal_dies_its_last_detail_is_sent_marked_dead():
    world = World(WorldConfig(seed=1, day_cycle=None))
    animal = world.add_animal(animal_dna(), Vec.of(500, 500), heading=0.0)
    session, clock = make(world)
    session.handle(Select(animal.id))
    first = session.update().detail
    assert first.alive
    animal.traits.current_energy = 0.001
    session.handle(Step(1))
    clock.advance(1.0)
    update = session.update()
    assert update.detail is not None
    assert not update.detail.alive
    assert update.detail.death_cause.value == "starvation"
    assert session.status.selected is None
    clock.advance(1.0)
    assert session.update().detail is None


# --- events -----------------------------------------------------------------------


def test_subscribers_hear_world_events_and_status_changes():
    world = World(WorldConfig(seed=1, day_cycle=None))
    animal = world.add_animal(animal_dna(), Vec.of(500, 500), heading=0.0)
    animal.traits.current_energy = 0.001
    session, _ = make(world)
    heard = []
    unsubscribe = session.subscribe(heard.append)
    session.handle(Step(1))
    session.update()
    assert any(isinstance(e, Died) and e.id == animal.id for e in heard)
    assert any(isinstance(e, StatusChanged) for e in heard)
    unsubscribe()
    heard.clear()
    session.handle(Play())
    assert heard == []


def test_the_world_builds_no_events_while_nobody_listens():
    world = real_world()
    session, _ = make(world)
    session.handle(Step(2))
    session.update()
    assert world._event_listeners == []
    unsubscribe = session.subscribe(lambda event: None)
    assert len(world._event_listeners) == 1
    unsubscribe()
    assert world._event_listeners == []


def test_a_selection_listens_for_the_death_and_lets_go_again():
    world = real_world()
    session, _ = make(world)
    session.handle(Select(world.animal_views()[0].id))
    assert len(world._event_listeners) == 1
    session.handle(Deselect())
    assert world._event_listeners == []


def test_the_fake_curve_gives_births_and_deaths_with_causes():
    fake = FakeSimulation(60, 10, seed=3, period=40)
    session, _ = make(fake)
    heard = []
    session.subscribe(heard.append)
    session.handle(Step(40))
    session.update()
    deaths = [e for e in heard if isinstance(e, Died)]
    assert deaths and len({d.cause for d in deaths}) > 1


def test_the_fake_is_repeatable_from_its_seed():
    a, b = FakeSimulation(30, 50, seed=4), FakeSimulation(30, 50, seed=4)
    for _ in range(20):
        a.step()
        b.step()
    assert a.animal_views() == b.animal_views()
    assert a.plant_views() == b.plant_views()
