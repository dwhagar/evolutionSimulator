"""The tick length scales the physics, and the defaults are an hour and a 24-hour day (WORLD.7)."""

import pytest
from world_support import ANIMAL_BASE, PLANT_BASE, animal_dna, hourly_world, plant_dna, world_config

from evolution_simulator.config import DEFAULT_RULES
from evolution_simulator.world import (
    SPEED_PRESETS,
    DayCycle,
    PlantRules,
    TimeScale,
    Vec,
    World,
    WorldConfig,
)

HERE = Vec.of(500, 500)
SECOND = TimeScale(seconds_per_tick=1.0)
HOUR = TimeScale(seconds_per_tick=3600.0)
DAY = TimeScale(seconds_per_tick=24 * 3600.0)
RUNNER = {"speed": 2.0}
EATER = {"speed": -2.0, "eat": 2.0}
STILL = {"speed": -2.0}


def world_of(time_scale, **config):
    config.setdefault("day_cycle", None)
    return World(world_config(seed=1, time_scale=time_scale, **config))


# --- the defaults ---------------------------------------------------------------


def test_the_default_world_has_an_hour_tick_and_a_24_hour_day():
    config = WorldConfig()
    assert config.time_scale.seconds_per_tick == 3600.0
    assert config.day_cycle is not None and config.day_cycle.length_seconds == 24 * 3600.0
    world = World()
    assert world.dt == 1.0
    assert world.daylight == pytest.approx(1.0)  # starts at noon
    world.run(12)
    assert world.daylight == pytest.approx(0.0, abs=1e-9)  # midnight twelve ticks later
    assert world.day == 1  # the first midnight has passed
    world.run(24)
    assert world.day == 2 and world.daylight == pytest.approx(0.0, abs=1e-9)


def test_a_day_is_24_ticks_with_about_nine_of_night():
    world = World()
    nights = 0
    for _ in range(24):
        nights += world.is_night
        world.step()
    assert 8 <= nights <= 10


def test_a_default_animal_lives_a_year_of_ticks_and_a_default_plant_a_month():
    from evolution_simulator.traits import AnimalTraits, PlantTraits

    animal = AnimalTraits(ANIMAL_BASE)
    assert 3000 < animal.lifespan_ticks < 20000
    plant = PlantTraits(PLANT_BASE)
    assert 300 < plant.lifespan_ticks < 1500


# --- movement -------------------------------------------------------------------


def test_an_animal_moves_in_proportion_to_the_tick_length():
    def moved(time_scale):
        world = world_of(time_scale)
        animal = world.add_animal(animal_dna(brain=RUNNER), HERE, heading=0.0)
        world.step()
        return animal.position.distance_to(HERE), animal.traits.current_max_speed

    hour, speed = moved(HOUR)
    second, _ = moved(SECOND)
    day, _ = moved(DAY)
    assert hour == pytest.approx(speed * 0.88, rel=0.15)  # logistic(2) of top speed
    assert second == pytest.approx(hour / 3600.0, rel=1e-3)
    assert day == pytest.approx(hour * 24.0, rel=1e-2)  # a day of wear slows it a little


def test_a_turn_is_scaled_by_the_tick_length_too():
    def heading(time_scale):
        world = world_of(time_scale)
        animal = world.add_animal(animal_dna(brain={"turn": 2.0, "speed": -2.0}), HERE, heading=0.0)
        world.step()
        return abs(animal.heading)

    assert heading(SECOND) == pytest.approx(heading(HOUR) / 3600.0, rel=1e-3)


def test_the_energy_spent_moving_is_charged_for_the_time_moved():
    for time_scale in (SECOND, HOUR, DAY):
        world = world_of(time_scale)
        animal = world.add_animal(animal_dna(brain=RUNNER), HERE, heading=0.0)
        traits = animal.traits
        start = traits.current_energy
        world.step()
        ratio = animal.last_decision.speed
        speed = ratio * traits.current_max_speed
        expected = (
            traits.energy_burn + DEFAULT_RULES.body.kinetic_burn * traits.mass * (speed / 3.5) ** 2
        ) * world.dt
        assert start - traits.current_energy == pytest.approx(expected)


# --- eating and growing -----------------------------------------------------------


def test_a_bite_is_in_proportion_to_the_tick_length():
    def eaten(time_scale):
        world = world_of(time_scale, graze_amount=10.0)
        plant = world.add_plant(plant_dna(max_biomass="3333", toxicity="0000"), HERE)
        plant.traits.current_biomass = 100.0
        world.add_animal(animal_dna(brain=EATER), HERE, heading=0.0)
        world.step()
        return 100.0 - plant.traits.current_biomass

    assert eaten(HOUR) == pytest.approx(10.0, abs=0.5)
    assert eaten(SECOND) == pytest.approx(10.0 / 3600.0, rel=0.05)
    assert eaten(DAY) == pytest.approx(100.0, abs=0.01)  # 240 wanted, only 100 there


def test_poison_in_a_bite_is_in_proportion_to_the_bite():
    from evolution_simulator.traits import AnimalTraits

    def damage(dt):
        traits = AnimalTraits(animal_dna(taste="0000"))
        traits.feed(5.0, is_meat=False, toxicity=1.0, dt=dt)
        return traits.max_damage_capacity - traits.current_health

    assert damage(1.0) > 0.0
    assert damage(1 / 3600) == pytest.approx(damage(1.0) / 3600.0)
    assert damage(2.0) == pytest.approx(damage(1.0) * 2.0)


def test_a_plant_grows_and_pays_upkeep_in_proportion_to_the_tick_length():
    def grown(time_scale, ticks):
        world = world_of(time_scale, plants=PlantRules(capacity=1e9))  # no soil limit
        plant = world.add_plant(plant_dna(growth_rate="3333", toxicity="0000"), HERE)
        plant.traits.current_biomass = 10.0
        plant.traits.current_health = plant.traits.max_damage_capacity
        plant.traits._refresh_vitality_dependents()
        start = plant.traits.current_biomass
        world.run(ticks)
        return plant.traits.current_biomass - start

    one_hour = grown(HOUR, 1)
    assert one_hour > 0.0
    assert grown(SECOND, 3600) == pytest.approx(one_hour * 1.0, rel=0.05)
    assert grown(DAY, 1) == pytest.approx(24 * one_hour, rel=0.1)


def test_a_sleeper_regains_energy_in_proportion_to_the_tick_length():
    def regained(time_scale, ticks):
        world = world_of(
            time_scale, day_cycle=DayCycle(length_seconds=24 * 3600.0, start_phase=0.0)
        )
        animal = world.add_animal(animal_dna(brain=STILL, recovery="333"), HERE, heading=0.0)
        animal.traits.current_energy = 0.5 * animal.traits.max_energy
        world.step()
        assert animal.asleep
        start = animal.traits.current_energy
        world.run(ticks)
        return animal.traits.current_energy - start

    assert regained(SECOND, 3600) == pytest.approx(regained(HOUR, 1), rel=0.05)


# --- the presets against the new lifespans ----------------------------------------


def test_the_presets_at_the_default_tick():
    rates = {
        name: TimeScale(speed=speed).ticks_per_real_second for name, speed in SPEED_PRESETS.items()
    }
    assert rates["hour"] == pytest.approx(1.0)
    assert rates["day"] == pytest.approx(24.0)
    assert rates["week"] == pytest.approx(168.0)
    assert rates["month"] == pytest.approx(730.5)
    assert rates["year"] == pytest.approx(8766.0)
    # A default animal lives about 8,765 ticks, so at the day preset a life takes about six minutes.
    assert 8765 / rates["day"] == pytest.approx(365.2, rel=0.01)


def test_hourly_world_helper_is_the_default_scale():
    assert hourly_world().config.time_scale == TimeScale()
