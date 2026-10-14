"""The random wander fallback (BRAIN.16)."""

import math
import random

import pytest

from evolution_simulator.brain_adapter import (
    BrainDecision,
    Percepts,
    Wanderer,
    WanderPolicy,
    decode_outputs,
)
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT
from evolution_simulator.traits import AnimalTraits

SEEN = Percepts(plant_closeness=0.5, plant_direction=0.2)
IDLE = BrainDecision(0.0, 0.0, 0.2, 0.1, 0.0, 0.3)
BUSY = BrainDecision(0.6, 0.9, 0.2, 0.1, 0.0, 0.3)


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


# --- what counts as "cannot decide" ------------------------------------------


def test_nothing_sensed_means_blind():
    assert Percepts().senses_nothing
    for one_thing in (
        Percepts(plant_closeness=0.1),
        Percepts(prey_direction=-0.2),
        Percepts(touching=True),
        Percepts(alarm_strength=0.1),
        Percepts(crowding=0.3),
    ):
        assert not one_thing.senses_nothing


def test_a_quiet_brain_is_undecided_even_when_it_sees_something():
    wanderer = Wanderer()
    assert wanderer.undecided(IDLE, SEEN)
    assert not wanderer.undecided(BUSY, SEEN)


@pytest.mark.parametrize(
    "decision",
    [
        BrainDecision(0.5, 0.0, 0.0, 0.0, 0.0, 0.0),  # steering
        BrainDecision(0.0, 0.5, 0.0, 0.0, 0.0, 0.0),  # moving
        BrainDecision(0.0, 0.0, 0.9, 0.0, 0.0, 0.0),  # eating or attacking
        BrainDecision(0.0, 0.0, 0.0, 0.9, 0.0, 0.0),  # seeking a mate
        BrainDecision(0.0, 0.0, 0.0, 0.0, 0.9, 0.0),  # alarm call
        BrainDecision(0.0, 0.0, 0.0, 0.0, 0.0, 0.9),  # mating call
    ],
)
def test_any_output_above_its_threshold_counts_as_a_decision(decision):
    assert not Wanderer().undecided(decision, SEEN)


def test_blind_creatures_wander_even_if_the_brain_moves():
    assert Wanderer().undecided(BUSY, Percepts())


def test_policy_can_turn_either_reason_off():
    assert not Wanderer(WanderPolicy(when_blind=False)).undecided(BUSY, Percepts())
    assert not Wanderer(WanderPolicy(when_idle=False)).undecided(IDLE, SEEN)
    assert Wanderer(WanderPolicy(when_idle=False)).undecided(IDLE, Percepts())


def test_thresholds_are_configurable():
    strict = Wanderer(WanderPolicy(idle_speed=0.95, idle_turn=0.95))
    assert strict.undecided(BUSY, SEEN)


# --- what wandering does -----------------------------------------------------


def test_a_decided_brain_is_passed_through_untouched_and_uses_no_randomness():
    r = rng(3)
    state = r.getstate()
    assert Wanderer().apply(BUSY, SEEN, r) is BUSY
    assert r.getstate() == state


def test_wandering_replaces_steering_and_keeps_the_actions():
    out = Wanderer().apply(IDLE, SEEN, rng(2))
    assert out.wandering
    assert -1.0 <= out.turn <= 1.0 and out.turn != 0.0
    assert out.speed == WanderPolicy().speed
    assert (out.eat_or_attack, out.seek_mating, out.alarm_call, out.mating_call) == (
        IDLE.eat_or_attack,
        IDLE.seek_mating,
        IDLE.alarm_call,
        IDLE.mating_call,
    )
    assert not IDLE.wandering


def test_wandering_never_slows_a_creature_the_brain_was_speeding_up():
    fast = BrainDecision(0.0, 0.8, 0.0, 0.0, 0.0, 0.0)
    out = Wanderer().apply(fast, Percepts(), rng(2))
    assert out.wandering and out.speed == 0.8


def test_the_turn_persists_unless_redrawn():
    steady = Wanderer(WanderPolicy(redraw_chance=0.0))
    r = rng(5)
    turns = {steady.apply(IDLE, SEEN, r).turn for _ in range(20)}
    assert len(turns) == 1
    jumpy = Wanderer(WanderPolicy(redraw_chance=1.0))
    assert len({jumpy.apply(IDLE, SEEN, r).turn for _ in range(20)}) == 20


def test_a_new_direction_is_picked_after_the_creature_decides_again():
    wanderer = Wanderer(WanderPolicy(redraw_chance=0.0))
    r = rng(7)
    first = wanderer.apply(IDLE, SEEN, r).turn
    assert wanderer.apply(IDLE, SEEN, r).turn == first
    wanderer.apply(BUSY, SEEN, r)
    assert wanderer.apply(IDLE, SEEN, r).turn != first


def test_wandering_is_seeded_and_repeatable():
    def run(seed: int) -> list[float]:
        wanderer = Wanderer()
        r = rng(seed)
        return [wanderer.apply(IDLE, SEEN, r).turn for _ in range(40)]

    assert run(4) == run(4)
    assert run(4) != run(5)


def test_turns_cover_both_directions():
    wanderer = Wanderer(WanderPolicy(redraw_chance=1.0))
    r = rng(8)
    turns = [wanderer.apply(IDLE, SEEN, r).turn for _ in range(400)]
    assert min(turns) < -0.8 and max(turns) > 0.8
    assert abs(sum(turns) / len(turns)) < 0.15


def test_policy_validation():
    for name in ("idle_turn", "idle_speed", "speed", "redraw_chance"):
        with pytest.raises(ValueError):
            WanderPolicy(**{name: 1.5})
        with pytest.raises(ValueError):
            WanderPolicy(**{name: -0.1})


def test_wandering_explores_where_a_stuck_brain_goes_in_circles():
    """A fixed turn output on a blind creature circles a small patch; the fallback roams."""

    def cells_visited(decide) -> int:
        x = y = heading = 0.0
        visited = set()
        for _ in range(400):
            turn, speed = decide()
            heading += turn * 0.3
            x += math.cos(heading) * speed * 2.0
            y += math.sin(heading) * speed * 2.0
            visited.add((int(x // 5), int(y // 5)))
        return len(visited)

    circling = cells_visited(lambda: (0.9, 0.5))
    wanderer, r = Wanderer(), rng(11)
    stuck = BrainDecision(0.9, 0.5, 0.0, 0.0, 0.0, 0.0)

    def roam() -> tuple[float, float]:
        d = wanderer.apply(stuck, Percepts(), r)
        return d.turn, d.speed

    assert cells_visited(roam) > 2 * circling


# --- on an animal ------------------------------------------------------------


def animal(seed: int = 3) -> AnimalTraits:
    # Think on every call: the reaction-time gene would otherwise cache the first decision.
    return AnimalTraits(DNA.random(ANIMAL_LAYOUT, rng(seed)), decision_interval=1)


def test_think_without_an_rng_is_the_plain_brain_decision():
    traits = animal()
    assert traits.think(Percepts()) == traits.think(Percepts())
    assert not traits.think(Percepts()).wandering


def test_a_blind_animal_with_an_rng_wanders():
    traits = animal()
    plain = traits.think(Percepts())
    decision = traits.think(Percepts(), rng(1))
    assert decision.wandering
    assert decision.turn != plain.turn or decision.speed != plain.speed
    assert (decision.eat_or_attack, decision.seek_mating) == (
        plain.eat_or_attack,
        plain.seek_mating,
    )


def test_a_seeing_animal_with_a_decisive_brain_does_not_wander():
    for seed in range(40):
        traits = animal(seed)
        plain = traits.think(SEEN)
        if Wanderer().undecided(plain, SEEN):
            continue
        assert traits.think(SEEN, rng(1)) == plain
        return
    pytest.fail("no decisive random brain found")


def test_animal_wandering_is_repeatable():
    def run() -> list[BrainDecision]:
        traits = animal(6)
        r = rng(2)
        return [traits.think(Percepts(), r) for _ in range(30)]

    assert run() == run()


def test_decode_outputs_leaves_wandering_off():
    assert decode_outputs((0.0, 0.5, 0.5, 0.5, 0.5, 0.5)).wandering is False
