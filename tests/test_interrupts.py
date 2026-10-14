"""Pain, a new threat or touch cut the decision interval short (BRAIN.22)."""

import random

from test_animal_brain import counted
from world_support import animal_dna, world_config

from evolution_simulator.brain_adapter import Percepts
from evolution_simulator.config import DEFAULT_RULES
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import PLANT_LAYOUT
from evolution_simulator.world import Vec, World

INTERRUPT_PAIN = DEFAULT_RULES.brain.interrupt_pain
QUIET = Percepts(plant_direction=0.2, plant_closeness=0.5)
THREAT = Percepts(
    plant_direction=0.2, plant_closeness=0.5, threat_direction=-0.3, threat_closeness=0.4
)
TOUCHED = Percepts(plant_direction=0.2, plant_closeness=0.5, touching=True)


def test_a_quiet_world_keeps_the_interval():
    traits, counter = counted(4)
    for _ in range(8):
        traits.think(QUIET)
    assert counter.calls == 2


def test_a_threat_that_appears_cuts_the_interval_short():
    traits, counter = counted(4)
    traits.think(QUIET)
    traits.think(QUIET)
    assert counter.calls == 1
    traits.think(THREAT)
    assert counter.calls == 2


def test_a_threat_that_was_already_there_does_not_interrupt_again():
    traits, counter = counted(4)
    traits.think(THREAT)
    for _ in range(3):
        traits.think(THREAT)
    assert counter.calls == 1
    traits.think(THREAT)  # the scheduled decision
    assert counter.calls == 2


def test_a_threat_that_leaves_and_returns_interrupts_at_the_next_decision_and_then_again():
    traits, counter = counted(4)
    traits.think(THREAT)
    traits.think(QUIET)  # nothing: it gone, but no reason to decide early
    assert counter.calls == 1
    for _ in range(3):
        traits.think(QUIET)
    assert counter.calls == 2  # scheduled
    traits.think(THREAT)  # returns: new again
    assert counter.calls == 3


def test_new_contact_interrupts_but_continuing_contact_does_not():
    traits, counter = counted(4)
    traits.think(QUIET)
    traits.think(TOUCHED)
    assert counter.calls == 2
    traits.think(TOUCHED)
    traits.think(TOUCHED)
    assert counter.calls == 2


def test_pain_cuts_the_interval_short_and_a_scratch_does_not():
    traits, counter = counted(4)
    traits.think(QUIET)
    traits.apply_damage(0.2 * 0.5 * INTERRUPT_PAIN * traits.max_damage_capacity)  # half of it
    traits.think(QUIET)
    assert counter.calls == 1  # below the interrupt
    traits.apply_damage(0.2 * traits.max_damage_capacity)  # pain is now above it
    assert traits.pain >= INTERRUPT_PAIN
    traits.think(QUIET)
    assert counter.calls == 2
    assert traits.pain == 0.0  # the decision cleared it
    traits.think(QUIET)
    assert counter.calls == 2


def test_pain_lets_the_world_skip_the_cache_without_any_percepts():
    traits, _ = counted(4)
    traits.think(QUIET)
    assert traits.cached_decision() is not None
    traits.apply_damage(0.2 * traits.max_damage_capacity)
    assert traits.cached_decision() is None


def test_interrupt_makes_the_next_cached_decision_miss():
    traits, _ = counted(4)
    traits.think(QUIET)
    traits.interrupt()
    assert traits.cached_decision() is None


def test_an_interrupted_decision_restarts_the_interval():
    traits, counter = counted(3)
    traits.think(QUIET)
    traits.think(THREAT)  # interrupt: decides, interval restarts
    traits.think(THREAT)
    traits.think(THREAT)
    assert counter.calls == 2
    traits.think(THREAT)
    assert counter.calls == 3


def test_every_tick_thinkers_are_unaffected():
    traits, counter = counted(1)
    for p in (QUIET, THREAT, TOUCHED, QUIET):
        traits.think(p)
    assert counter.calls == 4


# --- the world ----------------------------------------------------------------


def make_world(**genes):
    world = World(world_config(seed=3, day_cycle=None))
    dna = animal_dna(**genes)
    animal = world.add_animal(dna, Vec.of(500, 500), heading=0.0)
    return world, animal


def test_the_world_lets_a_new_contact_cut_the_interval_short():
    world, animal = make_world()
    traits = animal.traits
    traits.decision_interval = 4
    world.step()  # decides: nothing in contact
    assert not traits.decided_touch
    assert not world._newly_touched(animal)
    world.add_plant(DNA.random(PLANT_LAYOUT, random.Random(1)), animal.position)
    assert world._newly_touched(animal)


def test_continuing_contact_and_every_tick_thinkers_are_not_reported():
    world, animal = make_world()
    traits = animal.traits
    traits.decision_interval = 1
    world.add_plant(DNA.random(PLANT_LAYOUT, random.Random(1)), animal.position)
    assert not world._newly_touched(animal)  # interval 1: it decides every tick anyway
    traits.decision_interval = 4
    world.step()  # decides while touching
    assert traits.decided_touch
    assert not world._newly_touched(animal)


def test_an_animal_without_a_touch_organ_is_not_interrupted_by_contact():
    world, animal = make_world(touch="0000")
    animal.traits.decision_interval = 4
    world.add_plant(DNA.random(PLANT_LAYOUT, random.Random(1)), animal.position)
    world.step()
    assert not world._newly_touched(animal)
