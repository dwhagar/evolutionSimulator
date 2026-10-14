import math
import random

import pytest

from evolution_simulator.brain import DEFAULT_SHAPE, Brain, BrainShape
from evolution_simulator.brain_adapter import (
    ACTION_THRESHOLD,
    INPUT_NAMES,
    OUTPUT_NAMES,
    BrainDecision,
    Percepts,
    Temperament,
    build_inputs,
    decode_outputs,
)


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


def random_values(shape: BrainShape, seed: int, scale: float = 2.0) -> list[float]:
    r = rng(seed)
    return [r.uniform(-scale, scale) for _ in range(shape.weight_count)]


def reference_forward(shape: BrainShape, values: list[float], x: list[float]) -> list[float]:
    """The forward pass from the design note, written against the documented flat layout only."""
    w1, b1 = [], []  # hidden weights and biases
    w2 = [[0.0] * shape.hidden for _ in range(shape.outputs)]
    position = 0
    for j in range(shape.hidden):
        b1.append(values[position])
        w1.append(values[position + 1 : position + 1 + shape.inputs])
        for k in range(shape.outputs):
            w2[k][j] = values[position + 1 + shape.inputs + k]
        position += 1 + shape.inputs + shape.outputs
    b2 = values[position:]
    hidden = [math.tanh(sum(w * xi for w, xi in zip(row, x)) + b) for row, b in zip(w1, b1)]
    out = []
    for k in range(shape.outputs):
        total = sum(w * h for w, h in zip(w2[k], hidden)) + b2[k]
        out.append(math.tanh(total) if shape.signed_outputs[k] else 1 / (1 + math.exp(-total)))
    return out


# --- shape ------------------------------------------------------------------


def test_default_shape_is_the_designed_network():
    assert (DEFAULT_SHAPE.inputs, DEFAULT_SHAPE.hidden, DEFAULT_SHAPE.outputs) == (20, 8, 6)
    assert DEFAULT_SHAPE.weight_count == 222
    assert DEFAULT_SHAPE.signed_outputs == (True, False, False, False, False, False)
    assert len(INPUT_NAMES) == DEFAULT_SHAPE.inputs
    assert len(OUTPUT_NAMES) == DEFAULT_SHAPE.outputs


def test_groups_are_one_per_hidden_neuron_then_the_output_biases():
    groups = DEFAULT_SHAPE.group_sizes
    assert groups == (27,) * 8 + (6,)
    assert sum(groups) == DEFAULT_SHAPE.weight_count


def test_the_note_counts_other_sizes_the_same_way():
    assert BrainShape(17, 12, 6).weight_count - 12 * 17 - 12 - 12 * 6 - 6 == 0
    assert BrainShape(24, 16, 6).weight_count == 24 * 16 + 16 + 16 * 6 + 6 == 502


def test_shape_validation():
    with pytest.raises(ValueError):
        BrainShape(0, 1, 1)
    with pytest.raises(ValueError):
        BrainShape(2, 2, 2, signed_outputs=(True,))
    assert BrainShape(2, 2, 2).signed_outputs == (True, True)


# --- the forward pass --------------------------------------------------------


def worked_example() -> Brain:
    """The three-input, two-hidden, two-output network worked through in the design note."""
    shape = BrainShape(3, 2, 2, signed_outputs=(False, True))  # outputs: speed, turn
    values = [
        -0.2, 1.0, -1.5, 0.0, 1.5, 0.0,  # hidden 1: bias, three inputs, weights to speed and turn
        0.0, 0.0, 0.0, 1.0, 0.0, 2.0,  # hidden 2
        0.0, 0.0,  # output biases
    ]  # fmt: skip
    return Brain.from_values(shape, values)


def test_the_design_note_worked_example():
    speed, turn = worked_example().decide([0.9, 0.3, -0.5])
    assert speed == pytest.approx(0.5908, abs=1e-4)  # the note rounds this to 0.59
    assert turn == pytest.approx(-0.7279, abs=1e-4)  # and this to -0.73
    hidden_1 = math.tanh(1.0 * 0.9 + -1.5 * 0.3 - 0.2)
    assert hidden_1 == pytest.approx(0.2449, abs=1e-4)


@pytest.mark.parametrize("seed", range(10))
def test_forward_pass_matches_the_reference(seed):
    values = random_values(DEFAULT_SHAPE, seed)
    r = rng(seed + 100)
    x = [r.uniform(-1, 1) for _ in range(DEFAULT_SHAPE.inputs)]
    got = Brain.from_values(DEFAULT_SHAPE, values).decide(x)
    assert list(got) == pytest.approx(reference_forward(DEFAULT_SHAPE, values, x), abs=1e-12)


def test_outputs_stay_in_range_for_any_input_in_range():
    brain = Brain.from_values(DEFAULT_SHAPE, random_values(DEFAULT_SHAPE, 3, scale=20.0))
    r = rng(4)
    for _ in range(300):
        outputs = brain.decide([r.uniform(-1, 1) for _ in range(DEFAULT_SHAPE.inputs)])
        assert -1.0 <= outputs[0] <= 1.0
        assert all(0.0 <= o <= 1.0 for o in outputs[1:])


def test_huge_inputs_do_not_overflow():
    brain = Brain.from_values(DEFAULT_SHAPE, random_values(DEFAULT_SHAPE, 3, scale=2.0))
    outputs = brain.decide([1e6] * DEFAULT_SHAPE.inputs)
    assert all(math.isfinite(o) for o in outputs)
    outputs = brain.decide([-1e6] * DEFAULT_SHAPE.inputs)
    assert all(math.isfinite(o) for o in outputs)


def test_decisions_are_repeatable():
    values = random_values(DEFAULT_SHAPE, 5)
    x = [0.1 * i - 0.8 for i in range(DEFAULT_SHAPE.inputs)]
    a, b = Brain.from_values(DEFAULT_SHAPE, values), Brain.from_values(DEFAULT_SHAPE, values)
    assert a.decide(x) == b.decide(x) == a.decide(x)


def test_an_all_zero_brain_is_harmless_and_defined():
    outputs = Brain.zeros(DEFAULT_SHAPE).decide([1.0] * DEFAULT_SHAPE.inputs)
    assert outputs == (0.0, 0.5, 0.5, 0.5, 0.5, 0.5)  # no turn, and no action crosses 0.5
    decision = decode_outputs(outputs)
    assert not (decision.eats_or_attacks or decision.seeks_mating)
    assert not (decision.calls_alarm or decision.calls_for_mate)


def test_wrong_sizes_are_rejected():
    brain = Brain.zeros(DEFAULT_SHAPE)
    with pytest.raises(ValueError):
        brain.decide([0.0] * 16)
    with pytest.raises(ValueError):
        Brain.from_values(DEFAULT_SHAPE, [0.0] * 197)
    with pytest.raises(ValueError):
        Brain.from_values(DEFAULT_SHAPE, [math.nan] + [0.0] * 197)


# --- value semantics ---------------------------------------------------------


def test_values_round_trip_and_equality():
    values = random_values(DEFAULT_SHAPE, 8)
    brain = Brain.from_values(DEFAULT_SHAPE, values)
    assert brain.to_values() == tuple(values)
    assert Brain.from_values(DEFAULT_SHAPE, brain.to_values()) == brain
    assert hash(brain) == hash(Brain.from_values(DEFAULT_SHAPE, values))
    assert brain != Brain.from_values(DEFAULT_SHAPE, random_values(DEFAULT_SHAPE, 9))
    assert repr(brain) == "Brain(20-8-6)"


def test_brain_is_immutable():
    brain = Brain.zeros(DEFAULT_SHAPE)
    with pytest.raises(AttributeError):
        brain.shape = DEFAULT_SHAPE
    with pytest.raises(AttributeError):
        del brain.shape


# --- size, for the energy cost ----------------------------------------------


def test_neuron_count_is_hidden_plus_outputs():
    assert Brain.zeros(DEFAULT_SHAPE).neuron_count == 14


def test_active_connections_counts_weights_above_the_threshold_not_biases():
    shape = BrainShape(2, 2, 1)
    # neuron: bias, 2 incoming, 1 outgoing; then the output bias
    values = [9.0, 0.5, 0.0, 0.3] + [9.0, -0.5, 0.1, 0.0] + [9.0]
    brain = Brain.from_values(shape, values)
    assert brain.active_connections(0.0) == 4  # the two zero weights are inactive
    assert brain.active_connections(0.25) == 3  # 0.5, 0.3, -0.5
    assert brain.active_connections(0.6) == 0
    assert Brain.zeros(shape).active_connections() == 0


# --- the dead zone (BRAIN.21) --------------------------------------------------


def test_a_weight_inside_the_dead_zone_does_nothing_but_biases_still_count():
    shape = BrainShape(2, 2, 1)
    values = [0.4, 0.5, 0.1, 0.3] + [-0.2, -0.5, 0.25, 0.0] + [0.7]
    zone = Brain.from_values(shape, values, dead_zone=0.25)
    # the same brain with the weights at or below 0.25 set to zero by hand
    by_hand = Brain.from_values(shape, [0.4, 0.5, 0.0, 0.3, -0.2, -0.5, 0.0, 0.0, 0.7])
    for x in ([0.0, 0.0], [1.0, -1.0], [0.3, 0.9]):
        assert zone.decide(x) == by_hand.decide(x)
    assert zone.active_connections() == 3  # 0.5, 0.3, -0.5; 0.25 is on the line, so off
    assert zone.active_connections(0.4) == 2
    biases_only = Brain.from_values(shape, [0.4, 0.0, 0.1, 0.0, -0.2, 0.0, 0.2, 0.0, 0.7], 0.25)
    assert biases_only.active_connections() == 0
    assert biases_only.decide([1.0, 1.0]) == biases_only.decide([-1.0, 0.0])
    assert biases_only.decide([1.0, 1.0]) != Brain.zeros(shape).decide([1.0, 1.0])


def test_the_dead_zone_does_not_change_the_numbers_a_brain_reports():
    shape = BrainShape(2, 2, 1)
    values = [0.4, 0.5, 0.1, 0.3, -0.2, -0.5, 0.2, 0.0, 0.7]
    brain = Brain.from_values(shape, values, dead_zone=0.25)
    assert brain.to_values() == tuple(values)
    assert Brain.from_values(shape, brain.to_values(), brain.dead_zone) == brain
    assert brain != Brain.from_values(shape, values)  # it behaves differently
    assert Brain.from_values(shape, values).dead_zone == 0.0  # off unless asked for


def test_the_dead_zone_must_be_a_sensible_number():
    for bad in (-0.1, math.nan, math.inf):
        with pytest.raises(ValueError):
            Brain.from_values(BrainShape(1, 1, 1), [0.0] * 4, dead_zone=bad)


# --- the adapter ------------------------------------------------------------


def test_inputs_are_in_the_documented_order():
    percepts = Percepts(
        plant_direction=-0.5,
        plant_closeness=0.25,
        prey_direction=0.1,
        prey_closeness=0.2,
        threat_direction=0.3,
        threat_closeness=0.4,
        mate_direction=0.5,
        mate_closeness=0.6,
        touching=True,
        alarm_strength=0.7,
        mating_call_strength=0.8,
        call_direction=-0.9,
        crowding=0.35,
    )
    inputs = build_inputs(
        percepts, energy_ratio=0.75, health_ratio=0.5, vitality=0.9, ready_to_mate=True, pain=0.0
    )
    assert len(inputs) == len(INPUT_NAMES) == 20
    named = dict(zip(INPUT_NAMES, inputs))
    assert named["energy_ratio"] == 0.75
    assert named["health_ratio"] == 0.5
    assert named["vitality"] == 0.9
    assert named["ready_to_mate"] == 1.0
    assert named["plant_direction"] == -0.5
    assert named["threat_closeness"] == 0.4
    assert named["touching"] == 1.0
    assert named["mating_call_strength"] == 0.8
    assert named["call_direction"] == -0.9
    assert named["crowding"] == 0.35


def test_nothing_sensed_gives_zeros_for_the_world_inputs():
    inputs = build_inputs(
        Percepts(), energy_ratio=1.0, health_ratio=1.0, vitality=1.0, ready_to_mate=False, pain=0.0
    )
    assert inputs[:4] == (1.0, 1.0, 1.0, 0.0)
    assert inputs[4:] == (0.0,) * 16


def test_inputs_are_clamped_and_must_be_finite():
    inputs = build_inputs(
        Percepts(plant_direction=-3.0, crowding=9.0),
        energy_ratio=2.0,
        health_ratio=-1.0,
        vitality=5.0,
        ready_to_mate=False,
        pain=0.0,
    )
    assert inputs[:3] == (1.0, 0.0, 1.0)
    assert inputs[4] == -1.0
    assert inputs[16] == 1.0
    with pytest.raises(ValueError):
        build_inputs(
            Percepts(),
            energy_ratio=math.nan,
            health_ratio=1.0,
            vitality=1.0,
            ready_to_mate=False,
            pain=0.0,
        )
    with pytest.raises(ValueError):
        build_inputs(
            Percepts(mate_closeness=math.inf),
            energy_ratio=1.0,
            health_ratio=1.0,
            vitality=1.0,
            ready_to_mate=False,
            pain=0.0,
        )


def test_decision_names_outputs_and_thresholds_actions():
    decision = decode_outputs((-0.5, 0.9, 0.6, 0.4, 0.51, 0.5))
    assert decision == BrainDecision(-0.5, 0.9, 0.6, 0.4, 0.51, 0.5)
    assert decision.eats_or_attacks
    assert not decision.seeks_mating
    assert decision.calls_alarm
    assert not decision.calls_for_mate  # exactly at the threshold is not "above" it
    assert ACTION_THRESHOLD == 0.5
    with pytest.raises(ValueError):
        decode_outputs((0.0,) * 5)


# --- temperament (BRAIN.14) ---------------------------------------------------


def test_a_neutral_temperament_changes_nothing():
    percepts = Percepts(prey_closeness=0.4, threat_closeness=0.6, plant_closeness=0.3)
    plain = build_inputs(
        percepts, energy_ratio=0.5, health_ratio=0.5, vitality=0.5, ready_to_mate=True, pain=0.0
    )
    assert (
        build_inputs(
            percepts,
            energy_ratio=0.5,
            health_ratio=0.5,
            vitality=0.5,
            ready_to_mate=True,
            pain=0.0,
            temperament=Temperament(),
        )
        == plain
    )
    assert (
        build_inputs(
            percepts,
            energy_ratio=0.5,
            health_ratio=0.5,
            vitality=0.5,
            ready_to_mate=True,
            pain=0.0,
            temperament=Temperament(0.5, 0.5),
        )
        == plain
    )


def test_fear_scales_only_the_threat_closeness_and_aggression_only_the_prey_closeness():
    percepts = Percepts(prey_closeness=0.4, threat_closeness=0.4, plant_closeness=0.4)

    def named(t: Temperament) -> dict[str, float]:
        return dict(
            zip(
                INPUT_NAMES,
                build_inputs(
                    percepts,
                    energy_ratio=0.5,
                    health_ratio=0.5,
                    vitality=0.5,
                    ready_to_mate=True,
                    pain=0.0,
                    temperament=t,
                ),
            )
        )

    timid = named(Temperament(aggression=0.5, fear=1.0))
    assert timid["threat_closeness"] == pytest.approx(0.4 * 1.6)
    assert timid["prey_closeness"] == pytest.approx(0.4)
    assert timid["plant_closeness"] == pytest.approx(0.4)
    fierce = named(Temperament(aggression=1.0, fear=0.5))
    assert fierce["prey_closeness"] == pytest.approx(0.4 * 1.6)
    assert fierce["threat_closeness"] == pytest.approx(0.4)
    meek = named(Temperament(aggression=0.0, fear=0.0))
    assert meek["prey_closeness"] == pytest.approx(0.4 * 0.4)
    assert meek["threat_closeness"] == pytest.approx(0.4 * 0.4)


def test_temperament_is_monotonic_stays_in_range_and_cannot_invent_a_sense():
    percepts = Percepts(threat_closeness=0.7)
    seen = [
        build_inputs(
            percepts,
            energy_ratio=0.5,
            health_ratio=0.5,
            vitality=0.5,
            ready_to_mate=True,
            pain=0.0,
            temperament=Temperament(fear=f / 10),
        )[9]
        for f in range(11)
    ]
    assert seen == sorted(seen) and seen[-1] == 1.0  # 0.7 * 1.6 is clamped to 1
    nothing = build_inputs(
        Percepts(),
        energy_ratio=0.5,
        health_ratio=0.5,
        vitality=0.5,
        ready_to_mate=True,
        pain=0.0,
        temperament=Temperament(1.0, 1.0),
    )
    assert nothing[4:] == (0.0,) * 16


def test_temperament_values_are_validated():
    for bad in (-0.1, 1.1, math.nan):
        with pytest.raises(ValueError):
            Temperament(aggression=bad)
        with pytest.raises(ValueError):
            Temperament(fear=bad)
