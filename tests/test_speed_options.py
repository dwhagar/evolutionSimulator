"""WORLD.17: the speed options default to today's behaviour and do what they say when turned on."""

from dataclasses import replace

import pytest
from persistence_support import assert_same_world
from world_support import TEST_RULES, animal_dna, hourly_world

from evolution_simulator.config import BrainRules
from evolution_simulator.world import Bounds, Vec, persistence

SLOW = "3333"  # the reaction_time gene at its top: the longest decision interval


def rules_with(**brain):
    return replace(TEST_RULES, brain=replace(TEST_RULES.brain, **brain))


def lone_animal(world, **genes):
    animal = world.add_animal(animal_dna(brain={"speed": -2.0}, **genes), Vec.of(500, 500))
    animal.traits.current_energy = animal.traits.max_energy
    return animal


def count_brain_runs(animal):
    runs = []
    original = animal.traits.brain.decide_with_hidden
    # The brain is immutable, so count through the traits' own call.
    traits = animal.traits
    brain = traits.brain

    class Counting:
        def __getattr__(self, name):
            return getattr(brain, name)

        def decide_with_hidden(self, inputs):
            runs.append(1)
            return original(inputs)

    traits.brain = Counting()
    return runs


def test_the_options_are_off_by_default() -> None:
    rules = BrainRules()
    assert (rules.interval_scale, rules.idle_interval_factor) == (1.0, 1.0)


@pytest.mark.parametrize("name", ["interval_scale", "idle_interval_factor"])
@pytest.mark.parametrize("value", [0.5, 0.0, -1.0, float("inf"), float("nan")])
def test_the_options_must_be_one_or_more(name, value) -> None:
    with pytest.raises(ValueError):
        BrainRules(**{name: value})


def test_interval_scale_multiplies_the_genes_interval() -> None:
    plain = lone_animal(hourly_world(), reaction_time=SLOW)
    scaled = lone_animal(hourly_world(traits=rules_with(interval_scale=3.0)), reaction_time=SLOW)
    quick = lone_animal(hourly_world(traits=rules_with(interval_scale=3.0)), reaction_time="0000")
    assert plain.traits.decision_interval == 4
    assert scaled.traits.decision_interval == 12
    assert quick.traits.decision_interval == 3  # 1 hour times 3


def test_a_longer_interval_means_fewer_brain_runs() -> None:
    def runs_in(ticks, **brain):
        world = hourly_world(traits=rules_with(**brain))
        animal = lone_animal(world, reaction_time="0000")
        counter = count_brain_runs(animal)
        world.run(ticks)
        return len(counter)

    assert runs_in(60) == 60
    assert runs_in(60, interval_scale=3.0) == 20


def test_an_animal_that_senses_nothing_looks_less_often() -> None:
    def runs_in(ticks, **brain):
        world = hourly_world(traits=rules_with(**brain))
        animal = lone_animal(world, reaction_time="0000")
        counter = count_brain_runs(animal)
        world.run(ticks)
        return len(counter)

    assert runs_in(60) == 60
    assert runs_in(60, idle_interval_factor=4.0) == 15


def test_something_in_view_keeps_the_normal_interval() -> None:
    # Plants all round it, so every look finds something.
    world = hourly_world(traits=rules_with(idle_interval_factor=4.0), bounds=Bounds((60.0, 60.0)))
    world.populate(plants=80)
    animal = world.add_animal(
        animal_dna(brain={"speed": -2.0}, reaction_time="0000"), Vec.of(30, 30)
    )
    counter = count_brain_runs(animal)
    world.run(40)
    assert len(counter) > 30


def test_contact_cuts_an_idle_wait_short() -> None:
    world = hourly_world(traits=rules_with(idle_interval_factor=8.0))
    animal = lone_animal(world, reaction_time="0000", touch="3333")
    world.run(2)  # looked, sensed nothing, now waiting
    assert animal.traits.looks_every_tick is False
    assert animal.traits._ticks_since_decision < 0
    # Another animal arrives in contact: the wait ends and the brain looks again.
    x, y = animal.position.coords
    world.add_animal(animal_dna(brain={"speed": -2.0}), Vec.of(x + 1.0, y))
    world.step()
    assert animal.traits._ticks_since_decision >= 0


def test_a_save_in_the_middle_of_an_idle_wait_goes_on_the_same(tmp_path) -> None:
    def build():
        world = hourly_world(
            seed=4, traits=rules_with(idle_interval_factor=4.0, interval_scale=2.0)
        )
        world.populate(animals=12, plants=60)
        world.run(30)
        return world

    world = build()
    assert any(a.traits._ticks_since_decision < 0 for a in world.animals)
    path = persistence.save_world(world, tmp_path / "w.json.gz")
    loaded = persistence.load_world(path)
    assert_same_world(loaded, world)
    world.run(60)
    loaded.run(60)
    assert loaded.state_digest() == world.state_digest()
