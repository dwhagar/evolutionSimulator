"""Learning during life (BRAIN.24): the reward, the nightly update, the log and the sleep hook."""

import random

import pytest

from evolution_simulator.brain import Brain, BrainShape
from evolution_simulator.brain_adapter import Percepts
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT
from evolution_simulator.learning import (
    Learner,
    LearningRules,
    Snapshot,
    State,
    nightly_update,
    reward,
    zero_offsets,
)
from evolution_simulator.traits import AnimalTraits
from evolution_simulator.world import DayCycle, World, WorldConfig

RULES = LearningRules()
CALM = State(energy=0.5, damage=0.0, matings=0, threat=0.0)


def snap(reward_value, hidden=(1.0, 0.5), proposal=(0.0,), action=(0.2,)):
    return Snapshot(hidden, proposal, action, reward_value)


# --- reward -------------------------------------------------------------------


def test_reward_counts_outcomes_with_the_weights():
    end = State(energy=0.6, damage=0.05, matings=1, threat=0.0)
    start = State(energy=0.5, damage=0.0, matings=0, threat=0.4)
    expected = 1.0 * 0.1 - 2.0 * 0.05 + 1.0 * 1 + 0.5 * 0.4
    assert reward(start, end, RULES) == pytest.approx(expected)


def test_nothing_happening_earns_nothing():
    assert reward(CALM, CALM, RULES) == 0.0


def test_a_threat_getting_closer_is_not_punished_by_the_safety_term():
    near = State(0.5, 0.0, 0, 0.9)
    assert reward(CALM, near, RULES) == 0.0


# --- the nightly update -------------------------------------------------------


def test_no_noise_means_no_change():
    snaps = [snap(1.0, action=(0.0,)), snap(-1.0, action=(0.0,))]
    offsets = zero_offsets(2, 1)
    assert nightly_update(offsets, snaps, 1.0, RULES) == offsets


def test_zero_learning_rate_means_no_change():
    offsets = zero_offsets(2, 1)
    assert nightly_update(offsets, [snap(1.0), snap(-1.0)], 0.0, RULES) == offsets


def test_no_snapshots_means_no_change():
    offsets = zero_offsets(2, 1)
    assert nightly_update(offsets, [], 1.0, RULES) == offsets


def test_a_rewarded_extra_strengthens_and_a_punished_extra_weakens():
    # Both snapshots did more than proposed; one was rewarded above the day's usual, one below.
    good = nightly_update(zero_offsets(2, 1), [snap(1.0), snap(0.0, action=(0.0,))], 1.0, RULES)
    bad = nightly_update(zero_offsets(2, 1), [snap(-1.0), snap(0.0, action=(0.0,))], 1.0, RULES)
    assert all(w > 0 for w in good[0][0])
    assert good[1][0] > 0
    assert all(w < 0 for w in bad[0][0])
    assert bad[1][0] < 0


def test_doing_less_than_proposed_reverses_the_direction():
    less = nightly_update(zero_offsets(2, 1), [snap(1.0, action=(-0.2,)), snap(0.0)], 1.0, RULES)
    # Average reward is 0.5: the first (rewarded, did less) pushes down, the second (below usual,
    # did more) pushes down too.
    assert less[1][0] < 0


def test_the_update_matches_the_formula():
    snaps = [snap(2.0, hidden=(1.0, -1.0), action=(0.3,)), snap(0.0, hidden=(0.5, 0.5))]
    # usual = 1; changes: (2-1)*0.3 and (0-1)*0.2, times the hidden activations.
    weights, biases = nightly_update(zero_offsets(2, 1), snaps, 1.0, RULES)
    assert biases[0] == pytest.approx(0.3 - 0.2)
    assert weights[0][0] == pytest.approx(0.3 * 1.0 - 0.2 * 0.5)
    assert weights[0][1] == pytest.approx(0.3 * -1.0 - 0.2 * 0.5)


def test_no_number_moves_more_than_the_cap_in_a_night():
    rules = LearningRules(night_cap=0.1)
    snaps = [snap(100.0 * (i % 2), action=(0.9 * (i % 2),)) for i in range(50)]
    weights, biases = nightly_update(zero_offsets(2, 1), snaps, 2.0, rules)
    assert all(abs(w) <= 0.1 + 1e-12 for w in weights[0])
    assert abs(biases[0]) <= 0.1 + 1e-12
    assert max(abs(w) for w in weights[0]) == pytest.approx(0.1)


def test_repeated_nights_cannot_pass_the_total_limit():
    rules = LearningRules(night_cap=0.5, max_offset=0.8)
    offsets = zero_offsets(2, 1)
    for _ in range(10):
        offsets = nightly_update(offsets, [snap(1.0), snap(0.0)], 2.0, rules)
    assert all(abs(w) <= 0.8 for w in offsets[0][0])
    assert abs(offsets[1][0]) <= 0.8


def test_fading_pulls_offsets_toward_zero():
    rules = LearningRules(fade=0.25)
    start = (((0.4, -0.4),), (0.2,))
    weights, biases = nightly_update(start, [], 1.0, rules)
    assert weights[0] == pytest.approx((0.3, -0.3))
    assert biases == pytest.approx((0.15,))


def test_rules_reject_bad_values():
    for bad in ({"log_size": 0}, {"reward_window": 0}, {"night_cap": -1.0}, {"fade": 1.5}):
        with pytest.raises(ValueError):
            LearningRules(**bad)


# --- the log ------------------------------------------------------------------


def test_a_decision_gets_its_reward_after_the_window():
    learner = Learner(2, 1, LearningRules(reward_window=3))
    learner.observe(CALM)
    learner.record(CALM, (0.1, 0.2), (0.0,), (0.1,))
    fed = State(0.7, 0.0, 0, 0.0)
    learner.observe(fed)
    learner.observe(fed)
    assert learner.log == ()
    learner.observe(fed)
    assert [s.reward for s in learner.log] == [pytest.approx(0.2)]
    assert learner.open_decisions == 0


def test_the_log_keeps_only_the_latest_decisions():
    learner = Learner(1, 1, LearningRules(log_size=3, reward_window=1))
    for i in range(6):
        learner.observe(CALM)
        learner.record(CALM, (float(i),), (0.0,), (0.1,))
    learner.observe(CALM)
    assert [s.hidden[0] for s in learner.log] == [3.0, 4.0, 5.0]


def test_sleeping_closes_open_decisions_learns_and_empties_the_log():
    learner = Learner(2, 1, LearningRules(reward_window=50))
    full = State(0.9, 0.0, 0, 0.0)
    learner.observe(CALM)
    learner.record(CALM, (1.0, 1.0), (0.0,), (0.3,))
    learner.observe(full)
    learner.record(full, (1.0, 1.0), (0.0,), (0.1,))
    assert learner.log == () and learner.open_decisions == 2
    # The first decision started at half energy and ended full (+0.4); the second started full.
    assert learner.sleep(full, eta=1.0)
    assert learner.open_decisions == 0
    assert learner.log == ()
    assert learner.offsets[1][0] > 0.0  # the extra effort that was followed by gain is reinforced


# --- a toy task ---------------------------------------------------------------


def toy_accuracy(days, seed_count=150, eta=1.0, curiosity=0.3):
    """The design note's test: two foods, one nourishing, one toxic, learned from reward alone.

    Returns the share of right decisions on the last of ``days`` days, over ``seed_count`` lives.
    """
    shape = BrainShape(2, 4, 1, (False,))
    right = total = 0
    for seed in range(seed_count):
        rng = random.Random(seed)
        values = [rng.uniform(-1.0, 1.0) for _ in range(shape.weight_count)]
        good = rng.randrange(2)
        innate = Brain(shape, values)
        offsets = zero_offsets(shape.hidden, shape.outputs)
        for day in range(days):
            brain = innate.with_output_offsets(*offsets)
            log = []
            for _ in range(40):
                kind = rng.randrange(2)
                inputs = [1.0 if kind == 0 else 0.0, 1.0 if kind == 1 else 0.0]
                hidden, (p,) = brain.decide_with_hidden(inputs)
                a = max(0.0, min(1.0, p + rng.uniform(-curiosity, curiosity)))
                eats = a > 0.5
                gain = (1.0 if kind == good else -1.0) if eats else 0.0
                log.append(Snapshot(hidden, (p,), (a,), gain))
                if day == days - 1:
                    total += 1
                    right += eats == (kind == good)
            offsets = nightly_update(offsets, log, eta, RULES)
    return right / total


def test_learning_beats_chance_on_the_toy_task_and_needs_curiosity():
    assert toy_accuracy(1, eta=0.0) == pytest.approx(0.5, abs=0.06)
    assert toy_accuracy(6) > 0.6
    # Without curiosity the action never differs from the proposal, so nothing is learned.
    assert toy_accuracy(6, curiosity=0.0) == pytest.approx(toy_accuracy(1, eta=0.0), abs=0.06)


# --- the brain and the creature ----------------------------------------------


def test_offsets_are_added_to_the_output_layer_only():
    shape = BrainShape(2, 2, 2, (True, False))
    rng = random.Random(1)
    brain = Brain(shape, [rng.uniform(-1, 1) for _ in range(shape.weight_count)])
    same = brain.with_output_offsets(((0.0, 0.0),) * 2, (0.0, 0.0))
    assert same == brain
    changed = brain.with_output_offsets(((0.5, 0.0), (0.0, 0.0)), (0.25, 0.0))
    old, new = brain.to_values(), changed.to_values()
    size = shape.neuron_size
    differing = [i for i, (a, b) in enumerate(zip(old, new)) if a != b]
    assert differing == [1 + 2, shape.hidden * size]  # neuron 0's weight to output 0; bias 0
    assert new[3] == pytest.approx(old[3] + 0.5)
    assert new[shape.hidden * size] == pytest.approx(old[shape.hidden * size] + 0.25)


def test_the_dead_zone_applies_to_learned_values():
    shape = BrainShape(1, 1, 1, (False,))
    # bias, input weight, output weight (inside the dead zone), output bias
    brain = Brain(shape, [0.0, 0.0, 0.3, 0.0], dead_zone=0.5)
    assert brain.active_connections() == 0
    woken = brain.with_output_offsets(((0.4,),), (0.0,))
    assert woken.active_connections() == 1  # 0.3 + 0.4 is outside the dead zone
    silenced = Brain(shape, [0.0, 0.0, 0.9, 0.0], dead_zone=0.5).with_output_offsets(
        ((-0.5,),), (0.0,)
    )
    assert silenced.active_connections() == 0


def test_decide_with_hidden_agrees_with_decide():
    rng = random.Random(4)
    shape = BrainShape(3, 5, 2, (True, False))
    brain = Brain(shape, [rng.uniform(-1, 1) for _ in range(shape.weight_count)])
    inputs = [0.3, -0.2, 0.9]
    hidden, outputs = brain.decide_with_hidden(inputs)
    assert outputs == brain.decide(inputs)
    assert len(hidden) == 5
    assert all(-1.0 <= h <= 1.0 for h in hidden)


def curious(seed=3, curiosity=0.3, learning_rate=1.0):
    traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(seed)), decision_interval=1)
    traits.curiosity = curiosity
    traits.learning_rate = learning_rate
    return traits


SEEN = Percepts(plant_direction=0.2, plant_closeness=0.5, threat_closeness=0.3)


def Percepts_inputs(traits):
    return [0.0] * traits.brain.shape.inputs


def test_curiosity_noise_needs_an_rng_and_stays_in_range():
    traits = curious()
    proposal = traits.brain.decide(Percepts_inputs(traits))
    assert traits._explore(proposal, None) is proposal
    noisy = traits._explore(proposal, random.Random(1))
    assert noisy != proposal
    for seed in range(30):
        acted = traits._explore((1.0, 0.0, 0.5, 1.0, 0.0, 0.5), random.Random(seed))
        assert -1.0 <= acted[0] <= 1.0
        assert all(0.0 <= v <= 1.0 for v in acted[1:])


def test_no_curiosity_means_no_noise_and_no_log():
    traits = curious(curiosity=0.0)
    proposal = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    assert traits._explore(proposal, random.Random(1)) is proposal
    traits.think(SEEN, random.Random(1))
    assert traits.learner is None


def test_a_day_of_thinking_is_logged_and_the_night_changes_the_brain_not_the_dna():
    traits = curious()
    dna_before = traits.dna
    innate = traits.brain
    rng = random.Random(7)
    for i in range(80):
        traits.current_energy = traits.max_energy * (0.4 + 0.5 * ((i * 7) % 10) / 10)
        traits.think(SEEN, rng)
    assert traits.learner is not None
    assert traits.learn_night()
    assert traits.brain is not innate
    assert traits.innate_brain is innate
    assert traits.brain.shape == innate.shape
    assert traits.dna is dna_before
    assert DNA.random(ANIMAL_LAYOUT, random.Random(3)) == traits.dna
    assert traits.learner.log == ()


def test_a_child_is_built_from_dna_alone():
    parent = curious()
    rng = random.Random(7)
    for i in range(80):
        parent.current_energy = parent.max_energy * (0.4 + 0.5 * ((i * 7) % 10) / 10)
        parent.think(SEEN, rng)
    parent.learn_night()
    child = AnimalTraits(parent.dna)
    assert child.brain == AnimalTraits(parent.dna).brain
    assert child.brain == parent.innate_brain
    assert child.learner is None


def test_the_same_seed_gives_the_same_night():
    def night():
        traits = curious()
        rng = random.Random(11)
        for i in range(60):
            traits.current_energy = traits.max_energy * (0.4 + 0.5 * ((i * 3) % 10) / 10)
            traits.think(SEEN, rng)
        traits.learn_night()
        return traits.brain

    assert night() == night()


def test_learning_off_in_the_rules_logs_nothing():
    traits = curious()
    traits.learning_rules = None
    for _ in range(10):
        traits.think(SEEN, random.Random(2))
    assert traits.learner is None
    assert not traits.learn_night()


def test_damage_and_matings_are_counted_over_a_life():
    traits = curious()
    traits.apply_damage(5.0)
    traits.apply_damage(3.0)
    assert traits.damage_taken == pytest.approx(8.0)
    traits.think(SEEN)
    assert traits.damage_taken == pytest.approx(8.0)  # unlike the pain input, never cleared


# --- the world ---------------------------------------------------------------


def world_with_animals(seed=5, count=8, **config):
    world = World(WorldConfig(seed=seed, day_cycle=DayCycle(length_seconds=100.0), **config))
    rng = random.Random(seed)
    for _ in range(count):
        world.add_animal(DNA.random(ANIMAL_LAYOUT, rng))
    return world


def test_animals_learn_when_they_fall_asleep_and_not_before():
    world = world_with_animals()
    for _ in range(30):  # day
        world.step()
    assert all(a.traits.brain is a.traits.innate_brain for a in world.animals)
    for _ in range(12):  # past dusk at tick 32
        world.step()
    learned = [a for a in world.animals if a.traits.brain is not a.traits.innate_brain]
    assert learned
    assert all(a.asleep for a in learned)


def test_a_world_with_learning_off_never_changes_a_brain():
    world = world_with_animals(learning=None)
    for _ in range(45):
        world.step()
    assert all(a.traits.brain is a.traits.innate_brain for a in world.animals)
    assert all(a.traits.learning_rules is None for a in world.animals)


def test_learning_is_repeatable():
    def run():
        world = world_with_animals(seed=9)
        for _ in range(45):
            world.step()
        return [a.traits.brain.to_values() for a in world.animals]

    assert run() == run()
