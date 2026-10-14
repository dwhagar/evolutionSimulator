"""The brain whose shape evolves (BRAIN.23), the operating genes and the pain input (SENSE.9)."""

import math
import random

import pytest

from evolution_simulator.brain import DEFAULT_BLUEPRINT, DEFAULT_SHAPE, Brain, BrainBlueprint
from evolution_simulator.brain_adapter import INPUT_NAMES, Percepts
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, BRAIN_GENE
from evolution_simulator.sensing import Neighbour, SenseOrgans, SensingConditions, sense
from evolution_simulator.traits import (
    BRAIN_DEAD_ZONE,
    PAIN_FULL_FRACTION,
    AnimalTraits,
)
from evolution_simulator.world.vector import Vec

SMALL = BrainBlueprint(
    inputs=2, max_hidden=3, outputs=1
)  # slot: gate, bias, 2 in, 1 out = 5 values


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


def small(slots: list[list[float]], output_biases: list[float]) -> list[float]:
    return [v for slot in slots for v in slot] + output_biases


# --- the blueprint ------------------------------------------------------------------


def test_the_blueprint_sizes():
    assert SMALL.neuron_size == 5 and SMALL.value_count == 16
    assert SMALL.group_sizes == (5, 5, 5, 1)
    bp = DEFAULT_BLUEPRINT
    assert (bp.inputs, bp.max_hidden, bp.outputs) == (20, 16, 6)
    assert bp.neuron_size == 28 and bp.value_count == 454
    assert bp.group_sizes == (28,) * 16 + (6,)
    assert bp.signed_outputs == DEFAULT_SHAPE.signed_outputs
    with pytest.raises(ValueError):
        BrainBlueprint(0, 4, 2)


def test_a_slot_exists_when_its_gate_is_above_zero():
    values = small(
        [[0.5, 0, 0, 0, 0], [-0.5, 0, 0, 0, 0], [0.0, 0, 0, 0, 0]],
        [0.0],
    )
    assert SMALL.slots_on(values) == (0,)  # a gate of exactly zero is off
    values[5] = 1.0
    assert SMALL.slots_on(values) == (0, 1)
    with pytest.raises(ValueError):
        SMALL.slots_on([0.0] * 15)


def test_every_gate_off_keeps_the_one_nearest_to_on():
    values = small([[-1.0, 0, 0, 0, 0], [-0.2, 0, 0, 0, 0], [-0.7, 0, 0, 0, 0]], [0.0])
    assert SMALL.slots_on(values) == (1,)
    tie = small([[-1.0, 0, 0, 0, 0]] * 3, [0.0])
    assert SMALL.slots_on(tie) == (0,)  # the lowest on a tie
    assert SMALL.build(values).shape.hidden == 1  # a brain always has a hidden neuron


def test_build_keeps_the_slots_that_are_on_without_their_gates():
    values = small(
        [
            [1.0, 0.1, 0.2, 0.3, 0.4],
            [-1.0, 9.0, 9.0, 9.0, 9.0],  # off: none of it reaches the brain
            [1.0, 0.5, 0.6, 0.7, 0.8],
        ],
        [0.9],
    )
    brain = SMALL.build(values)
    assert brain.shape.hidden == 2
    assert brain.to_values() == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def test_the_built_brain_is_the_same_as_a_fixed_shape_brain():
    r = rng(2)
    values = [r.uniform(-2, 2) for _ in range(DEFAULT_BLUEPRINT.value_count)]
    for j in range(16):
        values[j * 28] = 1.0 if j < 8 else -1.0  # eight slots on
    built = DEFAULT_BLUEPRINT.build(values)
    fixed = Brain.from_values(
        DEFAULT_SHAPE,
        [v for j in range(8) for v in values[j * 28 + 1 : (j + 1) * 28]] + values[16 * 28 :],
    )
    assert built == fixed
    x = [r.uniform(-1, 1) for _ in range(20)]
    assert built.decide(x) == fixed.decide(x)


def test_spare_slots_do_nothing_whatever_they_hold():
    r = rng(3)
    values = [r.uniform(-2, 2) for _ in range(DEFAULT_BLUEPRINT.value_count)]
    for j in range(16):
        values[j * 28] = 1.0 if j % 2 == 0 else -1.0
    before = DEFAULT_BLUEPRINT.build(values)
    for j in range(1, 16, 2):  # scramble every spare slot (but keep the gates off)
        for i in range(1, 28):
            values[j * 28 + i] = r.uniform(-2, 2)
    after = DEFAULT_BLUEPRINT.build(values)
    x = [r.uniform(-1, 1) for _ in range(20)]
    assert before.decide(x) == after.decide(x)
    assert before == after


def test_flipping_one_gate_changes_the_neuron_count_by_exactly_one():
    r = rng(4)
    values = [r.uniform(-2, 2) for _ in range(DEFAULT_BLUEPRINT.value_count)]
    for j in range(16):
        values[j * 28] = 1.0 if j < 6 else -1.0
    base = DEFAULT_BLUEPRINT.build(values).shape.hidden
    assert base == 6
    values[10 * 28] = 0.3  # wake a spare
    assert DEFAULT_BLUEPRINT.build(values).shape.hidden == 7
    values[0] = -0.3  # switch one off
    values[10 * 28] = -0.3
    assert DEFAULT_BLUEPRINT.build(values).shape.hidden == 5


def test_the_dead_zone_and_gain_reach_the_built_brain():
    values = small([[1.0, 0.3, 0.4, 0.9, 0.2]] + [[-1.0, 0, 0, 0, 0]] * 2, [0.0])
    brain = SMALL.build(values, dead_zone=0.5, gain=2.0)
    assert brain.dead_zone == 0.5 and brain.gain == 2.0
    assert brain.active_connections() == 1  # only the 0.9 incoming weight survives


# --- gain --------------------------------------------------------------------------


def test_gain_sharpens_decisions_and_one_is_the_old_network():
    shape = SMALL.build(small([[1.0, 0.0, 0.5, 0.5, 1.0]] + [[-1.0] + [0.0] * 4] * 2, [0.0]))
    values = shape.to_values()
    plain = Brain.from_values(shape.shape, values)
    assert plain == Brain.from_values(shape.shape, values, gain=1.0)
    x = [0.0, 1.0]
    soft, sharp = (
        Brain.from_values(shape.shape, values, gain=0.5),
        Brain.from_values(shape.shape, values, gain=3.0),
    )
    # one hidden neuron, signed output: a larger gain pushes the output further from 0
    assert abs(soft.decide(x)[0]) < abs(plain.decide(x)[0]) < abs(sharp.decide(x)[0]) < 1.0
    # a neuron with nothing to say stays at the middle whatever the gain
    zero = Brain.zeros(shape.shape)
    assert Brain.from_values(shape.shape, zero.to_values(), gain=5.0).decide(x) == zero.decide(x)


def test_the_gain_must_be_positive_and_is_part_of_the_brain():
    for bad in (0.0, -1.0, math.nan, math.inf):
        with pytest.raises(ValueError):
            Brain.from_values(DEFAULT_SHAPE, [0.0] * 222, gain=bad)
    a = Brain.from_values(DEFAULT_SHAPE, [0.1] * 222)
    assert a != Brain.from_values(DEFAULT_SHAPE, [0.1] * 222, gain=2.0)
    assert a.to_values() == Brain.from_values(DEFAULT_SHAPE, [0.1] * 222, gain=2.0).to_values()


# --- the genome ---------------------------------------------------------------------


def test_the_brain_block_matches_the_blueprint():
    assert BRAIN_GENE.count == DEFAULT_BLUEPRINT.value_count
    assert BRAIN_GENE.groups == DEFAULT_BLUEPRINT.group_sizes
    assert ANIMAL_LAYOUT.version == 4 and ANIMAL_LAYOUT.length == 86 + 908


def test_unit_crossover_keeps_a_slot_with_its_gate():
    a, b = DNA.random(ANIMAL_LAYOUT, rng(1)), DNA.random(ANIMAL_LAYOUT, rng(2))
    start = ANIMAL_LAYOUT.gene("brain").start
    for seed in range(20):
        child = a.crossover_by_unit(b, rng(seed))
        for j in range(16):
            lo, hi = start + j * 56, start + (j + 1) * 56  # 28 values of two digits
            piece = child.get_slice(lo, hi)
            assert piece in (a.get_slice(lo, hi), b.get_slice(lo, hi))
            assert child.values("brain")[j * 28] in (
                a.values("brain")[j * 28],
                b.values("brain")[j * 28],
            )


def test_random_animals_have_about_half_their_slots_on_and_a_quarter_of_weights_off():
    on = off = total = 0
    for seed in range(60):
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, rng(seed)))
        values = traits.dna.values("brain")
        on += len(DEFAULT_BLUEPRINT.slots_on(values))
        weights = [v for j in range(16) for v in values[j * 28 + 2 : (j + 1) * 28]]
        off += sum(1 for w in weights if abs(w) <= BRAIN_DEAD_ZONE)
        total += len(weights)
    assert on / 60 == pytest.approx(8.0, abs=1.0)
    assert off / total == pytest.approx(0.25, abs=0.03)


# --- the operating genes ------------------------------------------------------------


def animal_with(**genes: str) -> AnimalTraits:
    digits = ["0"] * ANIMAL_LAYOUT.length
    for name, text in genes.items():
        gene = ANIMAL_LAYOUT.gene(name)
        digits[gene.start : gene.end] = text
    return AnimalTraits(DNA(ANIMAL_LAYOUT, "".join(digits)))


def test_the_operating_genes_map_onto_their_ranges():
    low, high = (
        animal_with(),
        animal_with(
            brain_gain="3333", reaction_time="3333", curiosity="3333", learning_rate="3333"
        ),
    )
    assert (low.brain.gain, high.brain.gain) == (pytest.approx(0.5), pytest.approx(2.0))
    assert (low.decision_interval, high.decision_interval) == (1, 4)
    assert (low.curiosity, high.curiosity) == (0.0, pytest.approx(0.5))
    assert (low.learning_rate, high.learning_rate) == (0.0, pytest.approx(2.0))


def test_the_gain_gene_is_log_scaled_so_the_middle_is_neutral():
    middle = animal_with(brain_gain="1333")  # 127 / 255, just under half
    assert middle.brain.gain == pytest.approx(1.0, abs=0.01)


def test_the_reaction_time_gene_sets_how_often_the_brain_runs_and_what_it_costs():
    quick, slow = animal_with(), animal_with(reaction_time="3333")
    assert quick.brain_upkeep == pytest.approx(slow.brain_upkeep * 4)
    # an explicit interval still wins
    assert AnimalTraits(slow.dna, decision_interval=2).decision_interval == 2
    assert AnimalTraits(slow.dna, decision_interval=1).decision_interval == 1
    with pytest.raises(ValueError):
        AnimalTraits(slow.dna, decision_interval=0)


def test_the_operating_genes_leave_the_body_alone():
    a, b = animal_with(), animal_with(brain_gain="3333", curiosity="3333")
    assert (
        a.mass == b.mass and a.max_energy == b.max_energy and a.base_max_speed == b.base_max_speed
    )


# --- pain (SENSE.9) --------------------------------------------------------------------


class RecordingBrain:
    """Stands in for the real brain to see what ``think`` feeds it."""

    def __init__(self) -> None:
        self.inputs: list[tuple[float, ...]] = []

    def decide(self, inputs):
        self.inputs.append(tuple(inputs))
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_pain_is_health_lost_since_the_last_decision():
    t = animal_with()
    assert t.pain == 0.0
    t.apply_damage(0.05 * t.max_damage_capacity)
    assert t.pain == pytest.approx(0.05 / PAIN_FULL_FRACTION)
    t.apply_damage(0.05 * t.max_damage_capacity)
    assert t.pain == pytest.approx(0.5)  # damage adds up until the brain has seen it
    t.apply_damage(0.5 * t.max_damage_capacity)
    assert t.pain == 1.0  # capped
    assert t.damage_since_decision > 0.2 * t.max_damage_capacity


def test_damage_that_cannot_be_taken_is_not_pain():
    t = animal_with()
    t.current_health = 1.0
    t.apply_damage(50.0)  # only the 1.0 left could be lost
    assert not t.is_alive
    assert t.damage_since_decision == pytest.approx(1.0)


def test_think_gives_the_brain_the_pain_and_then_clears_it():
    t = animal_with()
    t.brain = RecordingBrain()
    t.apply_damage(PAIN_FULL_FRACTION * t.max_damage_capacity / 2)
    t.think(Percepts(daylight=0.8))
    first = dict(zip(INPUT_NAMES, t.brain.inputs[0]))
    assert first["pain"] == pytest.approx(0.5)
    assert first["daylight"] == 0.8
    assert t.pain == 0.0
    t.think(Percepts())
    t.think(Percepts())
    assert dict(zip(INPUT_NAMES, t.brain.inputs[-1]))["pain"] == 0.0


# --- relative size and daylight in the sensing step ----------------------------------------


def look(neighbours, organs=None, mass=2.0, **kwargs):
    organs = organs or SenseOrgans(vision_range=50.0, hearing_range=50.0, hearing_noise=0.4)
    return sense(Vec.of(0.0, 0.0), 0.0, 0.0, organs, neighbours, mass=mass, **kwargs)


def near(role, distance, mass, ident=1):
    return Neighbour(ident, role, Vec.of(distance, 0.0), mass=mass)


def test_relative_size_is_log2_of_the_mass_ratio_over_two():
    assert look([near("prey", 10.0, 0.5)]).relative_size == pytest.approx(-1.0)  # a quarter
    assert look([near("prey", 10.0, 1.0)]).relative_size == pytest.approx(-0.5)  # half
    assert look([near("threat", 10.0, 2.0)]).relative_size == pytest.approx(0.0)  # equal
    assert look([near("threat", 10.0, 8.0)]).relative_size == pytest.approx(1.0)  # four times
    assert look([near("threat", 10.0, 64.0)]).relative_size == 1.0  # clamped


def test_the_nearer_of_prey_and_threat_decides_and_other_roles_are_not_sized():
    prey_nearer = look([near("prey", 10.0, 1.0, 1), near("threat", 20.0, 8.0, 2)])
    assert prey_nearer.relative_size == pytest.approx(-0.5)
    threat_nearer = look([near("prey", 20.0, 1.0, 1), near("threat", 10.0, 8.0, 2)])
    assert threat_nearer.relative_size == pytest.approx(1.0)
    assert look([near("mate", 10.0, 1.0), near("plant", 5.0, 1.0)]).relative_size == 0.0


def test_relative_size_needs_both_masses():
    assert look([near("prey", 10.0, 1.0)], mass=0.0).relative_size == 0.0
    assert look([near("prey", 10.0, 0.0)]).relative_size == 0.0


def test_sound_only_reports_of_size_are_noisy_but_sight_is_exact():
    ears = SenseOrgans(hearing_range=50.0, hearing_noise=0.4)
    target = [near("prey", 10.0, 1.0)]
    exact = look(target, ears)
    noisy = look(target, ears, rng=rng(1))
    assert exact.relative_size == pytest.approx(-0.5)
    assert noisy.relative_size != exact.relative_size
    eyes = SenseOrgans(vision_range=50.0, vision_noise=0.4, hearing_range=50.0, hearing_noise=0.4)
    seen = look(target, eyes, rng=rng(1))
    assert seen.relative_size == pytest.approx(-0.5)  # vision found it: no size error


def test_daylight_is_passed_through():
    assert look([], conditions=SensingConditions(daylight=0.3)).daylight == 0.3
