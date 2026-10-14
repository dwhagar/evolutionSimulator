"""The brain as part of an animal: read from DNA at birth, costs energy, answers `think`."""

import random

import pytest

from evolution_simulator import traits as traits_module
from evolution_simulator.brain import DEFAULT_SHAPE, Brain
from evolution_simulator.brain_adapter import BrainDecision, Percepts, build_inputs, decode_outputs
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.traits import (
    BRAIN_ACTIVE_THRESHOLD,
    BRAIN_CONNECTION_COST,
    BRAIN_NEURON_COST,
    AnimalTraits,
    PlantTraits,
)

BODY = ("0123" * 17)[:65]
BRAIN = "".join(str((i * 7 + i // 5) % 4) for i in range(396))  # fixed, varied, not saturated
PINNED = DNA(ANIMAL_LAYOUT, BODY + BRAIN)
FAINT = "13" * 198  # every weight is level 7 of 16: -0.133, below the active threshold
STRONG = "3" * 396  # every weight is +2.0

SEEN = Percepts(
    plant_direction=-0.5, plant_closeness=0.8, threat_direction=0.2, threat_closeness=0.1
)


def with_brain(digits: str) -> DNA:
    return PINNED.replaced("brain", [int(d) for d in digits])


# --- reading the brain from the genome ---------------------------------------


def test_the_brain_is_built_from_the_genome_at_birth():
    traits = AnimalTraits(PINNED)
    assert traits.brain == Brain.from_values(DEFAULT_SHAPE, PINNED.values("brain"))
    assert traits.brain.shape is DEFAULT_SHAPE
    assert len(traits.brain.to_values()) == 198


def test_different_genomes_give_different_brains_and_the_same_genome_the_same():
    other = DNA.random(ANIMAL_LAYOUT, random.Random(4))
    assert AnimalTraits(other).brain != AnimalTraits(PINNED).brain
    assert AnimalTraits(PINNED).brain == AnimalTraits(PINNED).brain


def test_the_brain_does_not_change_the_body():
    a, b = AnimalTraits(with_brain(FAINT)), AnimalTraits(with_brain(STRONG))
    assert dict(a.phenotype) == dict(b.phenotype)
    assert a.mass == b.mass and a.max_energy == b.max_energy
    assert a.base_max_speed == b.base_max_speed


def test_plants_have_no_brain():
    assert not hasattr(PlantTraits(DNA.random(PLANT_LAYOUT, random.Random(1))), "brain")


# --- what thinking costs -----------------------------------------------------


def test_upkeep_charges_per_neuron_and_per_active_connection():
    faint, strong = AnimalTraits(with_brain(FAINT)), AnimalTraits(with_brain(STRONG))
    assert faint.brain.active_connections(BRAIN_ACTIVE_THRESHOLD) == 0
    assert faint.brain_upkeep == pytest.approx(BRAIN_NEURON_COST * 14)
    assert strong.brain.active_connections(BRAIN_ACTIVE_THRESHOLD) == 17 * 8 + 8 * 6
    assert strong.brain_upkeep == pytest.approx(
        BRAIN_NEURON_COST * 14 + BRAIN_CONNECTION_COST * 184
    )


def test_upkeep_is_part_of_basal_metabolism():
    faint, strong = AnimalTraits(with_brain(FAINT)), AnimalTraits(with_brain(STRONG))
    assert strong.basal_metabolism - faint.basal_metabolism == pytest.approx(
        strong.brain_upkeep - faint.brain_upkeep
    )
    assert strong.basal_metabolism > faint.basal_metabolism


def test_a_heavily_wired_brain_drains_energy_faster():
    def energy_after_ten_ticks(dna: DNA) -> float:
        traits = AnimalTraits(dna)
        for _ in range(10):
            traits.update_metabolism_and_aging(0.0)
        return traits.current_energy

    assert energy_after_ten_ticks(with_brain(STRONG)) < energy_after_ten_ticks(with_brain(FAINT))


def test_a_typical_random_brain_costs_a_few_percent_of_the_basal_budget():
    ratios = []
    for seed in range(100):
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(seed)))
        ratios.append(traits.brain_upkeep / traits.basal_metabolism)
    assert 0.01 < sum(ratios) / len(ratios) < 0.08
    assert max(ratios) < 0.15


def test_the_cost_constants_are_module_level_so_they_can_move_to_config():
    assert traits_module.BRAIN_NEURON_COST > 0
    assert traits_module.BRAIN_CONNECTION_COST > 0
    assert 0 < traits_module.BRAIN_ACTIVE_THRESHOLD < 2.0


# --- thinking ---------------------------------------------------------------


def test_think_runs_the_brain_on_the_animals_state_and_the_percepts():
    traits = AnimalTraits(PINNED)
    expected = decode_outputs(
        traits.brain.decide(
            build_inputs(
                traits.current_energy / traits.max_energy,
                traits.current_health / traits.max_damage_capacity,
                traits.vitality,
                True,
                SEEN,
            )
        )
    )
    assert traits.think(SEEN) == expected


def test_pinned_decision_for_a_fixed_genome():
    decision = AnimalTraits(PINNED).think(SEEN)
    assert decision.turn == pytest.approx(-0.744400851)
    assert decision.speed == pytest.approx(0.994610372)
    assert decision.eat_or_attack == pytest.approx(0.376072255)
    assert decision.seek_mating == pytest.approx(0.981196777)
    assert decision.alarm_call == pytest.approx(0.983103972)
    assert decision.mating_call == pytest.approx(0.276822535)
    assert decision.eats_or_attacks is False and decision.seeks_mating is True


def test_think_is_repeatable_and_changes_nothing():
    traits = AnimalTraits(PINNED)
    before = (traits.current_energy, traits.age_ticks, traits.flag_wants_mate, traits.vitality)
    assert traits.think(SEEN) == traits.think(SEEN)
    assert (
        traits.current_energy,
        traits.age_ticks,
        traits.flag_wants_mate,
        traits.vitality,
    ) == before


def test_think_sees_hunger_health_and_readiness_to_mate():
    fed = AnimalTraits(PINNED).think(Percepts())
    hungry = AnimalTraits(PINNED)
    hungry.current_energy *= 0.2
    assert hungry.think(Percepts()) != fed
    hurt = AnimalTraits(PINNED)
    hurt.apply_damage(hurt.max_damage_capacity * 0.5)
    assert hurt.think(Percepts()) != fed
    resting = AnimalTraits(PINNED)
    resting.mating_cooldown = 5
    assert resting.think(Percepts()) != fed


def test_think_sees_the_world():
    traits = AnimalTraits(PINNED)
    assert traits.think(SEEN) != traits.think(Percepts())
    assert traits.think(Percepts(touching=True)) != traits.think(Percepts())


def test_decisions_over_a_run_are_deterministic():
    def run() -> list[BrainDecision]:
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(9)))
        r = random.Random(3)
        decisions = []
        for _ in range(50):
            percepts = Percepts(plant_closeness=r.random(), plant_direction=r.uniform(-1, 1))
            decisions.append(traits.think(percepts))
            traits.update_metabolism_and_aging(0.5)
        return decisions

    assert run() == run()


def test_random_animals_always_decide_inside_the_output_ranges():
    r = random.Random(12)
    for seed in range(60):
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(seed)))
        percepts = Percepts(
            plant_direction=r.uniform(-1, 1),
            plant_closeness=r.random(),
            threat_direction=r.uniform(-1, 1),
            threat_closeness=r.random(),
            touching=r.random() < 0.5,
            crowding=r.random(),
        )
        d = traits.think(percepts)
        assert -1.0 <= d.turn <= 1.0
        assert all(0.0 <= v <= 1.0 for v in (d.speed, d.eat_or_attack, d.seek_mating))
        assert all(0.0 <= v <= 1.0 for v in (d.alarm_call, d.mating_call))
