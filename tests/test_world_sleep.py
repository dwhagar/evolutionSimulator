"""The day-night cycle and sleep (WORLD.5)."""

import pytest
from world_support import animal_dna, plant_dna

from evolution_simulator.world import (
    BasicSenses,
    DayCycle,
    SleepRules,
    Vec,
    World,
    WorldConfig,
)

HERE = Vec.of(500, 500)
FAST = {"speed": 2.0}
EATER = {"eat": 2.0}
LOVER = {"mate": 2.0}
SHORT_DAY = DayCycle(length_seconds=100.0)  # noon at tick 0, night from tick 32 to 68


def make(seed=0, **config):
    config.setdefault("day_cycle", SHORT_DAY)
    return World(WorldConfig(seed=seed, **config))


class Recorder:
    def __init__(self):
        self.events = []

    def fell_asleep(self, world, animal):
        self.events.append(("sleep", animal.id, world.tick))

    def woke(self, world, animal):
        self.events.append(("wake", animal.id, world.tick))


# --- the cycle ----------------------------------------------------------------


def test_daylight_runs_from_noon_to_midnight_and_back():
    day = DayCycle(length_seconds=100.0)
    assert day.daylight(0) == pytest.approx(1.0)
    assert day.daylight(25) == pytest.approx(0.5)
    assert day.daylight(50) == pytest.approx(0.0)
    assert day.daylight(100) == pytest.approx(1.0)
    assert [day.phase(t) for t in (0, 50)] == pytest.approx([0.5, 0.0])


def test_night_is_when_daylight_is_below_the_threshold():
    day = DayCycle(length_seconds=100.0, night_below=0.3)
    assert not day.is_night(0)
    assert not day.is_night(31)
    assert day.is_night(33)
    assert day.is_night(50)
    assert day.is_night(67)
    assert not day.is_night(70)
    assert day.night_fraction == pytest.approx(0.369, abs=0.001)


def test_day_number_counts_midnights():
    day = DayCycle(length_seconds=100.0)
    assert day.day_number(0) == 0
    assert day.day_number(49) == 0
    assert day.day_number(51) == 1
    assert day.day_number(151) == 2


def test_a_day_cycle_rejects_bad_values():
    with pytest.raises(ValueError):
        DayCycle(length_seconds=0)
    with pytest.raises(ValueError):
        DayCycle(start_phase=1.0)
    with pytest.raises(ValueError):
        DayCycle(night_below=1.5)
    with pytest.raises(ValueError):
        SleepRules(metabolism_factor=2.0)


def test_the_world_reports_the_light_and_the_day():
    world = make()
    assert world.daylight == pytest.approx(1.0)
    assert not world.is_night
    world.run(50)
    assert world.daylight == pytest.approx(0.0)
    assert world.is_night
    assert world.day == 1


def test_without_a_day_cycle_it_is_always_light_and_nobody_sleeps():
    world = make(day_cycle=None)
    animal = world.add_animal(animal_dna(), HERE, heading=0.0)
    world.run(150)
    assert world.daylight == 1.0 and not world.is_night and world.day == 0
    assert not animal.asleep


# --- sleeping -----------------------------------------------------------------


def test_animals_fall_asleep_at_night_and_wake_in_the_morning():
    world = make()
    recorder = Recorder()
    world.add_sleep_listener(recorder)
    first = world.add_animal(animal_dna(), Vec.of(100, 100), heading=0.0)
    second = world.add_animal(animal_dna(), Vec.of(800, 800), heading=0.0)
    for _ in range(31):
        world.step()
    assert not first.asleep
    world.run(3)
    assert first.asleep and second.asleep
    assert first.last_decision is None
    world.run(40)
    assert not first.asleep and not second.asleep
    assert recorder.events == [
        ("sleep", first.id, 32),
        ("sleep", second.id, 32),
        ("wake", first.id, 69),
        ("wake", second.id, 69),
    ]


def test_a_sleeper_does_not_move_eat_or_mate():
    world = make()
    grazed = []
    world._graze = grazed.append  # record any attempt to eat
    world.add_plant(plant_dna(), HERE)
    runner = world.add_animal(animal_dna(brain={**FAST, **EATER, **LOVER}), HERE, heading=0.0)
    partner = world.add_animal(animal_dna(brain={**FAST, **LOVER}), Vec.of(501, 500), heading=0.0)
    world.run(34)  # now asleep
    assert runner.asleep and partner.asleep
    spot, eaten = runner.position, len(grazed)
    births = world.run(20).animal_births
    assert runner.position == spot
    assert len(grazed) == eaten
    assert births == 0
    assert runner.traits.age_ticks == 54  # ageing carries on


def test_sleep_saves_and_regains_energy():
    sleeper = make()
    awake = make(day_cycle=None)
    still = {"speed": -2.0}
    a = sleeper.add_animal(animal_dna(brain=still), HERE, heading=0.0)
    b = awake.add_animal(animal_dna(brain=still), HERE, heading=0.0)
    a.traits.current_energy = b.traits.current_energy = 0.4 * a.traits.max_energy
    sleeper.run(31)
    awake.run(31)
    before = a.traits.current_energy
    assert a.traits.current_energy == pytest.approx(b.traits.current_energy, rel=0.3)
    sleeper.run(10)
    assert a.asleep
    assert a.traits.current_energy > before  # a net gain while asleep
    awake.run(10)
    assert b.traits.current_energy < before


def test_a_starving_animal_stays_awake_at_night():
    world = make()
    animal = world.add_animal(animal_dna(brain={"speed": -2.0}), HERE, heading=0.0)
    animal.traits.current_energy = 0.14 * animal.traits.max_energy
    world.run(40)
    assert world.is_night
    assert animal.is_alive and not animal.asleep


def test_falling_asleep_forgets_the_wander_turn_and_cached_decision():
    world = make()
    animal = world.add_animal(animal_dna(), HERE, heading=0.0)
    world.run(5)
    animal.traits.wanderer._turn = 0.7
    world.run(30)
    assert animal.asleep
    assert animal.traits.wanderer._turn is None
    assert animal.traits._decision is None


def test_a_run_through_several_nights_is_repeatable():
    digests = []
    for _ in range(2):
        world = make(seed=6)
        world.populate(animals=10, plants=40)
        world.run(350)
        digests.append(world.state_digest())
    assert digests[0] == digests[1]


# --- light --------------------------------------------------------------------


def test_plants_get_the_daylight_as_sunlight():
    world = make()
    plant = world.add_plant(plant_dna(), HERE)
    world.step()
    assert plant.traits.sunlight_factor == pytest.approx(1.0)
    world.run(50)
    assert plant.traits.sunlight_factor == pytest.approx(0.05)  # the floor for darkness


def test_animals_see_less_at_night():
    senses = BasicSenses()
    wide = {"sight_range": "3333", "sight_fov": "3333"}  # 33 units, all round
    seen = []
    for start in (0.5, 0.0):  # noon, midnight
        world = make(day_cycle=DayCycle(length_seconds=100.0, start_phase=start))
        animal = world.add_animal(animal_dna(**wide), HERE, heading=0.0)
        world.add_plant(plant_dna(), Vec.of(520, 500))
        seen.append(senses.perceive(world, animal).plant_closeness)
    assert seen[0] > 0.0
    assert seen[1] == 0.0
