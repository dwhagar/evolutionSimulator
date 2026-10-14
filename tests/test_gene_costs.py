"""The genes that used to be free now pay (TRAIT.9)."""

import random

import pytest
from world_support import ANIMAL_BASE, animal_dna

from evolution_simulator.config import DEFAULT_RULES
from evolution_simulator.traits import AnimalTraits


def animal(**genes: str) -> AnimalTraits:
    return AnimalTraits(animal_dna(**genes))


def burn(traits: AnimalTraits, ratio: float = 1.0) -> float:
    """Energy lost in one reference tick of moving at ``ratio`` of top speed, less the basal part."""
    traits.current_energy = traits.max_energy
    traits.update_metabolism_and_aging(ratio, 1.0)
    return traits.max_energy - traits.current_energy - traits.basal_metabolism


# --- speed ----------------------------------------------------------------------


def test_a_faster_animal_burns_more_when_it_moves_at_full_speed():
    slow, fast = animal(speed="0000"), animal(speed="3333")
    assert fast.base_max_speed > slow.base_max_speed
    assert burn(fast) > 4 * burn(slow)  # the burn goes with the square of the speed moved


def test_moving_twice_as_fast_costs_four_times_the_energy_and_twice_the_energy_per_distance():
    traits = animal()
    full = burn(traits, 1.0)
    half = burn(animal(), 0.5)
    assert full == pytest.approx(4 * half, rel=0.02)
    assert (full / 1.0) == pytest.approx(2 * (half / 0.5), rel=0.02)


def test_an_average_animal_at_the_reference_speed_burns_the_old_amount():
    traits = animal(speed="1333", size="1333")  # speed 0.5, size 0.5: about 3.57 per tick
    assert traits.base_max_speed == pytest.approx(DEFAULT_RULES.body.speed_reference, rel=0.05)
    assert burn(traits) == pytest.approx(DEFAULT_RULES.body.kinetic_burn * traits.mass, rel=0.1)


def test_standing_still_costs_nothing_extra():
    assert burn(animal(speed="3333"), 0.0) == pytest.approx(0.0, abs=1e-12)


# --- agility, temperament, learning ------------------------------------------------


def test_agility_costs_upkeep_with_its_square():
    assert animal(agility="0000").agility_upkeep == 0.0
    top, half = animal(agility="3333"), animal(agility="1111")
    assert top.agility_upkeep == pytest.approx(DEFAULT_RULES.body.agility_cost)
    assert half.agility_upkeep == pytest.approx(top.agility_upkeep / 9, rel=0.02)  # 1/3 squared
    assert top.basal_metabolism > animal(agility="0000").basal_metabolism


def test_aggression_and_fear_both_cost_upkeep():
    calm = animal(aggression="0000", fear="0000")
    assert calm.temperament_upkeep == 0.0
    both = animal(aggression="3333", fear="3333")
    assert both.temperament_upkeep == pytest.approx(2 * DEFAULT_RULES.body.temperament_cost)
    one = animal(aggression="3333", fear="0000")
    assert one.temperament_upkeep == pytest.approx(DEFAULT_RULES.body.temperament_cost)


def test_learning_costs_upkeep_in_proportion_to_the_rate():
    assert animal(learning_rate="0000").learning_upkeep == 0.0
    top = animal(learning_rate="3333")
    assert top.learning_upkeep == pytest.approx(
        DEFAULT_RULES.brain.learning_cost * top.learning_rate
    )
    assert top.learning_rate == pytest.approx(2.0)


def test_the_upkeeps_are_part_of_the_basal_metabolism():
    plain = animal(agility="0000", aggression="0000", fear="0000", learning_rate="0000")
    loaded = animal(agility="3333", aggression="3333", fear="3333", learning_rate="3333")
    extra = loaded.agility_upkeep + loaded.temperament_upkeep + loaded.learning_upkeep
    assert loaded.basal_metabolism - plain.basal_metabolism == pytest.approx(extra)


# --- the sex digit ----------------------------------------------------------------


def test_an_amplified_drive_wears_and_costs_more_and_a_subdued_one_less():
    plain = animal(repro_drive="222", sex_strategy="0")
    loud = animal(repro_drive="222", sex_strategy="2")
    quiet = animal(repro_drive="222", sex_strategy="3")
    assert loud.effective_drive > plain.effective_drive > quiet.effective_drive
    assert loud.drive_upkeep > plain.drive_upkeep > quiet.drive_upkeep
    assert loud.wear_per_tick > plain.wear_per_tick > quiet.wear_per_tick
    assert loud.lifespan_ticks < plain.lifespan_ticks < quiet.lifespan_ticks


def test_the_two_sexes_with_no_modifier_pay_the_same_for_the_drive():
    male, female = animal(sex_strategy="0"), animal(sex_strategy="1")
    assert male.drive_upkeep == female.drive_upkeep
    assert male.wear_per_tick == female.wear_per_tick


# --- the genes left free have a reason -------------------------------------------


def test_noise_on_the_speed_output_costs_energy():
    # curiosity: a noisy speed burns more than a steady one at the same mean, because the burn is
    # convex in the speed, which is the recorded reason it needs no cost of its own.
    rng = random.Random(1)
    steady = burn(animal(), 0.5)
    noisy = (
        sum(burn(animal(), min(1.0, max(0.0, 0.5 + rng.uniform(-0.5, 0.5)))) for _ in range(200))
        / 200
    )
    assert noisy > steady * 1.1


def test_the_free_genes_are_recorded_with_their_reasons():
    from evolution_simulator.trait_defs import ANIMAL_TRAITS

    assert "weights" in ANIMAL_TRAITS.free["brain_gain"]
    assert "square of the speed" in ANIMAL_TRAITS.free["curiosity"]
    assert ANIMAL_BASE.layout.name == ANIMAL_TRAITS.layout.name
