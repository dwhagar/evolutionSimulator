"""The decision interval and the learning window follow simulated time (WORLD.16)."""

import pytest
from world_support import animal_dna, world_config

from evolution_simulator.learning import Learner, LearningRules
from evolution_simulator.traits import AnimalTraits
from evolution_simulator.world import TimeScale, Vec, World

SLOW, FAST = "0000", "3333"


def test_the_reaction_time_gene_is_a_time_in_hours():
    hourly = AnimalTraits(animal_dna(reaction_time=SLOW))
    slowest = AnimalTraits(animal_dna(reaction_time=FAST))
    assert (hourly.decision_interval, slowest.decision_interval) == (1, 4)


def test_a_shorter_tick_means_more_ticks_between_decisions():
    for dt in (0.5, 1 / 60, 1 / 3600):
        a = AnimalTraits(animal_dna(reaction_time=FAST), dt=dt)
        assert a.decision_interval == round(4 / dt)


def test_a_longer_tick_still_decides_every_tick():
    day = AnimalTraits(animal_dna(reaction_time=FAST), dt=24.0)
    assert day.decision_interval == 1


def test_an_explicit_interval_in_ticks_wins():
    assert AnimalTraits(animal_dna(), decision_interval=3, dt=1 / 60).decision_interval == 3


def test_thinking_costs_the_same_per_hour_whatever_the_tick():
    hourly = AnimalTraits(animal_dna(reaction_time=FAST))
    seconds = AnimalTraits(animal_dna(reaction_time=FAST), dt=1 / 3600)
    assert seconds.brain_upkeep == pytest.approx(hourly.brain_upkeep, rel=1e-3)


def test_dt_must_be_above_zero():
    with pytest.raises(ValueError):
        AnimalTraits(animal_dna(), dt=0.0)


def test_the_reward_window_is_in_hours_too():
    rules = LearningRules(reward_window=10.0)
    assert Learner(2, 1, rules).window == 10
    assert Learner(2, 1, rules, dt=0.5).window == 20
    assert Learner(2, 1, rules, dt=24.0).window == 1
    with pytest.raises(ValueError):
        LearningRules(reward_window=0.0)


def test_the_world_hands_its_tick_to_its_animals():
    for seconds in (60.0, 3600.0):
        world = World(world_config(time_scale=TimeScale(seconds_per_tick=seconds), day_cycle=None))
        animal = world.add_animal(animal_dna(reaction_time=FAST), Vec.of(500, 500), heading=0.0)
        assert animal.traits.dt == pytest.approx(seconds / 3600.0)
        assert animal.traits.decision_interval == round(4 * 3600.0 / seconds)
