"""The seeded first-generation brain (BRAIN.9)."""

import random

import pytest

from evolution_simulator.brain import DEFAULT_BLUEPRINT
from evolution_simulator.brain_adapter import INPUT_NAMES
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, BRAIN_GENE
from evolution_simulator.seed_brain import (
    GATE_OFF,
    GATE_ON,
    LEVELS,
    SEED_GAIN,
    SEED_HIDDEN,
    SEED_OUTPUT_BIASES,
    SEED_SLOTS,
    agreement,
    agrees,
    reference_rule,
    sample_inputs,
    seed_levels,
    seeded_dna,
)
from evolution_simulator.traits import AnimalTraits
from evolution_simulator.world import World, WorldConfig

INDEX = {name: i for i, name in enumerate(INPUT_NAMES)}


def inputs(**given):
    values = [0.0] * len(INPUT_NAMES)
    for name, value in given.items():
        values[INDEX[name]] = value
    return values


def samples(count, seed):
    rng = random.Random(seed)
    return [sample_inputs(rng) for _ in range(count)]


# --- the reference rule -------------------------------------------------------


def test_a_close_threat_on_the_right_makes_it_turn_left_and_run():
    turn, speed, eat, seek, *calls = reference_rule(
        inputs(threat_direction=0.4, threat_closeness=0.8)
    )
    assert turn < -0.5
    assert speed == 1.0
    assert (eat, seek, calls) == (0.0, 0.0, [0.0, 0.0])


def test_a_plant_ahead_is_walked_to_and_a_plant_in_reach_is_eaten():
    far = reference_rule(inputs(plant_direction=0.3, plant_closeness=0.2))
    near = reference_rule(inputs(plant_direction=0.3, plant_closeness=0.8))
    assert far[0] == pytest.approx(0.3)
    assert 0.3 <= far[1] < 0.8
    assert far[2] == 0.0
    assert near[2] == 1.0


def test_prey_is_walked_to_and_attacked_in_reach():
    far = reference_rule(inputs(prey_direction=-0.3, prey_closeness=0.2))
    near = reference_rule(inputs(prey_direction=-0.3, prey_closeness=0.8))
    assert far[0] == pytest.approx(-0.3)
    assert 0.3 <= far[1] < 0.8
    assert far[2] == 0.0
    assert near[2] == 1.0


def test_a_ready_animal_with_energy_is_willing_to_mate_and_steers_to_a_mate():
    ready = reference_rule(inputs(ready_to_mate=1.0, energy_ratio=0.8, mate_direction=-0.4))
    assert ready[3] == 1.0
    assert ready[0] == pytest.approx(-0.4)
    for weak in (inputs(ready_to_mate=1.0, energy_ratio=0.3), inputs(energy_ratio=0.9)):
        assert reference_rule(weak)[3] == 0.0


def test_sensing_nothing_asks_for_nothing_and_the_wander_fallback_takes_over():
    assert reference_rule(inputs(energy_ratio=0.5)) == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_the_samples_read_zero_for_things_that_are_absent():
    for values in samples(300, 1):
        for target in ("plant", "prey", "threat", "mate"):
            if values[INDEX[f"{target}_closeness"]] == 0.0:
                assert values[INDEX[f"{target}_direction"]] == 0.0
        assert values[INDEX["ready_to_mate"]] in (0.0, 1.0)


def test_agreement_compares_turn_speed_class_and_actions():
    assert agrees((0.5, 0.6, 1.0, 0.0, 0.0, 0.0), (0.3, 0.6, 1.0, 0.0, 0.0, 0.0))
    assert not agrees((-0.5, 0.6, 1.0, 0.0, 0.0, 0.0), (0.3, 0.6, 1.0, 0.0, 0.0, 0.0))
    assert not agrees((0.3, 0.1, 1.0, 0.0, 0.0, 0.0), (0.3, 0.6, 1.0, 0.0, 0.0, 0.0))
    assert not agrees((0.3, 0.6, 0.0, 0.0, 0.0, 0.0), (0.3, 0.6, 1.0, 0.0, 0.0, 0.0))
    assert agrees((0.2, 0.0, 0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))  # not steering


# --- the seed -----------------------------------------------------------------


def test_the_table_is_complete_and_in_range():
    body = DEFAULT_BLUEPRINT.neuron_size - 1
    assert len(SEED_SLOTS) == SEED_HIDDEN
    assert all(len(slot) == body for slot in SEED_SLOTS)
    assert len(SEED_OUTPUT_BIASES) == DEFAULT_BLUEPRINT.outputs
    levels = seed_levels()
    assert len(levels) == DEFAULT_BLUEPRINT.value_count
    assert all(0 <= level < LEVELS for level in levels)


def test_the_first_slots_are_on_and_the_rest_off():
    dna = seeded_dna(random.Random(0), variation=0.0)
    values = dna.values("brain")
    assert DEFAULT_BLUEPRINT.slots_on(values) == tuple(range(SEED_HIDDEN))
    size = DEFAULT_BLUEPRINT.neuron_size
    assert [values[j * size] > 0 for j in range(DEFAULT_BLUEPRINT.max_hidden)] == (
        [True] * SEED_HIDDEN + [False] * (DEFAULT_BLUEPRINT.max_hidden - SEED_HIDDEN)
    )
    levels = seed_levels()
    assert levels[0] == GATE_ON and levels[SEED_HIDDEN * size] == GATE_OFF


def test_the_seed_survives_being_written_into_dna_exactly():
    dna = seeded_dna(random.Random(0), variation=0.0)
    assert BRAIN_GENE.encode(dna.values("brain")) == dna.slice_of("brain")


def test_the_creature_gets_the_seed_sized_brain_at_the_seed_gain():
    traits = AnimalTraits(seeded_dna(random.Random(1), variation=0.0))
    assert traits.brain.shape.hidden == SEED_HIDDEN
    assert traits.brain.gain == pytest.approx(SEED_GAIN)


def test_the_seeded_brain_agrees_with_the_rule_on_95_percent_of_random_inputs():
    traits = AnimalTraits(seeded_dna(random.Random(2), variation=0.0))
    assert agreement(traits.brain, samples(4000, 3)) >= 0.95


def test_founders_differ_a_little_and_still_agree_with_the_rule():
    founders = [seeded_dna(random.Random(i)) for i in range(12)]
    assert len({str(f) for f in founders}) == 12
    brains = [AnimalTraits(f).brain for f in founders]
    data = samples(1500, 4)
    shares = [agreement(b, data) for b in brains]
    assert sum(shares) / len(shares) >= 0.9
    assert min(shares) >= 0.75


def test_variation_moves_only_that_many_levels_and_never_a_gate():
    seed = seeded_dna(random.Random(0), variation=0.0).values("brain")
    for n in (1, 3, 6):
        varied = seeded_dna(random.Random(n), variation=float(n)).values("brain")
        moved = [i for i, (a, b) in enumerate(zip(seed, varied, strict=True)) if a != b]
        assert len(moved) <= n
        size = DEFAULT_BLUEPRINT.neuron_size
        assert all(i % size != 0 or i >= SEED_HIDDEN * size for i in moved)
        assert DEFAULT_BLUEPRINT.slots_on(varied) == tuple(range(SEED_HIDDEN))
        assert all(abs(seed[i] - varied[i]) < 0.3 for i in moved)


def test_variation_zero_gives_the_same_brain_whatever_the_generator():
    a = seeded_dna(random.Random(1), variation=0.0)
    b = seeded_dna(random.Random(2), variation=0.0)
    assert a.slice_of("brain") == b.slice_of("brain")
    assert a != b  # the body is still random


def test_a_given_body_is_kept():
    body = DNA.random(ANIMAL_LAYOUT, random.Random(9))
    dna = seeded_dna(random.Random(1), base=body, variation=0.0)
    for gene in ("mass", "speed", "size"):
        if gene in ANIMAL_LAYOUT:
            assert dna.slice_of(gene) == body.slice_of(gene)


def test_negative_variation_is_rejected():
    with pytest.raises(ValueError):
        seeded_dna(random.Random(0), variation=-1.0)


# --- in the world -------------------------------------------------------------


def populated(seed, seeded):
    world = World(WorldConfig(seed=seed, day_cycle=None))
    world.populate(animals=20, plants=120, seeded=seeded)
    return world


def test_populate_seeds_the_brains_by_default():
    world = populated(1, True)
    assert all(a.traits.brain.shape.hidden == SEED_HIDDEN for a in world.animals)
    assert all(a.traits.innate_brain.gain == pytest.approx(SEED_GAIN) for a in world.animals)


def test_populate_can_still_make_random_brains():
    world = populated(1, False)
    assert any(a.traits.brain.shape.hidden != SEED_HIDDEN for a in world.animals)


def test_seeded_founders_outlive_random_ones():
    def survivors(seeded):
        total = 0
        for seed in range(4):
            world = populated(seed, seeded)
            world.run(200)
            total += len(world.animals)
        return total

    assert survivors(True) > survivors(False)
