"""Seeded first-generation brains (BRAIN.9, ``docs/design/brain.md`` "Getting evolution started").

A population of random brains walks in circles, ignores food and dies before it breeds. The seed is a
brain fitted to a simple reference rule, so founders head for food, run from what frightens them and
look for a mate when fed. Evolution then improves on it.

Three pieces:

* ``reference_rule``: what the seeded brain imitates, written on the brain's inputs and outputs. It
  is the old fixed rule (the behaviour flags of ``AnimalTraits``) reduced to what the world acts on
  today: steering, speed, eating and seeking a mate. It does not chase prey or call yet, because the
  world does not act on attacking or calling (``BRAIN.10``).
* ``SEED_SLOTS`` and ``SEED_OUTPUT_BIASES``: the fitted weights, as levels of the genome's brain
  block (0 to 15 of 16, so they survive being written into DNA exactly). The table is made by
  ``src/evolution_tools/fit_seed_brain.py``; rerun it when the inputs or the rule change.
* ``seeded_dna``: a random animal genome with the seed written into the first ``SEED_HIDDEN`` (10) hidden slots (gates
  on, the rest of the slots off), the gain gene at the seed's gain and a little variation so founders are not
  clones.

``agreement`` measures how often a brain agrees with the rule on sampled inputs; the tests hold the
seed to 95%.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from evolution_simulator.brain import DEFAULT_BLUEPRINT, Brain
from evolution_simulator.brain_adapter import ACTION_THRESHOLD, INPUT_NAMES
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, BRAIN_GENE
from evolution_simulator.sense_channels import INPUT_CHANNELS, TARGETS

SEED_HIDDEN = 10
"""Hidden neurons the seed uses: the first slots of the genome's brain block."""

# --- the reference rule -------------------------------------------------------

WALK_SPEED: float = 0.6
WALK_PULL: float = 2.0
"""Sensing food or a mate walks: speed rises by ``WALK_PULL`` per unit of closeness (plant and mate
and prey added) up to ``WALK_SPEED``, a ramp and not a step so a small network can hold it."""
SLOW_NEAR: float = 0.5
"""A plant close by slows the walk (by this much at contact), so the animal arrives instead of
passing over the plant, which it can only eat by overlapping it."""
RUN_SLOPE: float = 4.0
RUN_OFFSET: float = 0.4
"""A threat makes it run: its speed is added, rising from 0 at closeness 0.1 to 1 at 0.35, so the
animal is running (above 0.8) from a closeness of 0.3 whatever else it senses."""
SEEKING_ENERGY: float = 0.6
"""Energy fraction at which a ready animal starts looking for a mate (a typical drive gene)."""
EAT_CLOSENESS: float = 0.5
"""A plant or prey this close is eaten or attacked."""
REPULSION: float = 3.0
"""How hard a threat's bearing turns the animal away, against 1 for the pull of food or a mate."""
EDGE_REPULSION: float = 1.5
"""How hard the bearing of the world's edge (when one is felt or seen) turns the animal away."""
EDGE_ABSENT: float = 0.7
"""Chance the sampled situation has the edge out of reach (its bearing and closeness both zero)."""

_INDEX = {name: i for i, name in enumerate(INPUT_NAMES)}


def reference_rule(inputs: Sequence[float]) -> tuple[float, ...]:
    """The six outputs (turn, speed, eat, seek mating, alarm call, mating call) the seed imitates.

    The old fixed rule (the behaviour flags ``AnimalTraits`` used to set, retired in ``BRAIN.10``)
    cut down to what the world acts on and to what a small network can hold: a bearing reads zero
    when nothing is sensed, so steering is a sum of pulls (food, prey, a mate) and a push away from a
    threat, with no priority list. A threat close makes it run, sensing food, prey or a mate makes it
    walk (both ramp up with closeness); a plant or prey within reach is eaten or attacked (the world
    takes the plant first); a ready animal with enough energy is willing to mate. Calls stay off:
    when to call is left to evolution. The fed and hungry distinctions of the flags are left to
    evolution too. Its own young, still dependent, pull like a mate (it stays with them), and the
    world's edge pushes it away like a threat. Tiredness, mate similarity and the clock are left to
    evolution: the seed does not use them.
    """
    pull = (
        inputs[_INDEX["plant_direction"]]
        + inputs[_INDEX["prey_direction"]]
        + inputs[_INDEX["mate_direction"]]
        + inputs[_INDEX["young_direction"]]
    )
    push = (
        REPULSION * inputs[_INDEX["threat_direction"]]
        + EDGE_REPULSION * inputs[_INDEX["edge_direction"]]
    )
    turn = max(-1.0, min(1.0, pull - push))
    plant = inputs[_INDEX["plant_closeness"]]
    prey = inputs[_INDEX["prey_closeness"]]
    mate = inputs[_INDEX["mate_closeness"]]
    young = inputs[_INDEX["young_closeness"]]
    walk = min(WALK_SPEED, WALK_PULL * (plant + prey + mate + young)) - SLOW_NEAR * plant
    run = max(0.0, min(1.0, RUN_SLOPE * inputs[_INDEX["threat_closeness"]] - RUN_OFFSET))
    speed = max(0.0, min(1.0, walk + run))
    eat = 1.0 if max(plant, prey) > EAT_CLOSENESS else 0.0
    ready = inputs[_INDEX["ready_to_mate"]] > 0.5
    seek = 1.0 if ready and inputs[_INDEX["energy_ratio"]] >= SEEKING_ENERGY else 0.0
    return turn, speed, eat, seek, 0.0, 0.0


def sample_inputs(rng: random.Random, realistic: bool = True) -> list[float]:
    """One random input vector. ``realistic`` makes each kind of thing absent (its bearing and
    closeness both zero) with some chance, as the world reports it; otherwise every input is uniform
    over its range, including situations the world never produces."""
    present = {target: rng.random() < 0.45 for target in TARGETS}
    values: list[float] = []
    for channel in INPUT_CHANNELS:
        if realistic:
            absent = channel.target is not None and not present[channel.target]
            quiet = channel.source == "world" and channel.role == "strength"
            if absent or (quiet and rng.random() < 0.6):
                values.append(0.0)
                continue
            if channel.role == "flag":
                values.append(float(rng.random() < 0.5))
                continue
        values.append(rng.uniform(channel.low, channel.high))
    if realistic:
        # The edge is only reported when it is in reach, and a mate's likeness only with a mate.
        if rng.random() < EDGE_ABSENT:
            values[_INDEX["edge_direction"]] = values[_INDEX["edge_closeness"]] = 0.0
        if not present["mate"]:
            values[_INDEX["mate_similarity"]] = 0.0
    return values


STEER_SLACK: float = 0.5
"""How far a turn may differ from the rule's when the rule is not clearly steering."""
STEERING: float = 0.15
"""A rule turn beyond this (either way) is steering; the brain must turn the same way."""
STILL_BELOW: float = 0.3
"""A speed output below this is standing still, one from ``RUNNING_FROM`` is running, and between
the two is walking."""
RUNNING_FROM: float = 0.8
SPEED_SLACK: float = 0.2
"""Speeds also agree when they are this close, so a brain is not marked wrong for being a hair
across a class boundary."""


def speed_class(speed: float) -> int:
    """0 standing, 1 walking, 2 running."""
    return 0 if speed < STILL_BELOW else (1 if speed < RUNNING_FROM else 2)


def agrees(outputs: Sequence[float], wanted: Sequence[float]) -> bool:
    """Whether a brain's outputs behave like the rule's: it turns the same way when the rule
    steers (otherwise within ``STEER_SLACK``), it stands, walks or runs as the rule does (or is within ``SPEED_SLACK`` of its speed) and each of the
    four actions is on the same side of the action threshold."""
    turn, goal = outputs[0], wanted[0]
    if abs(goal) > STEERING:
        if turn * goal <= 0.0:
            return False
    elif abs(turn - goal) > STEER_SLACK:
        return False
    if speed_class(outputs[1]) != speed_class(wanted[1]) and (
        abs(outputs[1] - wanted[1]) > SPEED_SLACK
    ):
        return False
    return all(
        (o > ACTION_THRESHOLD) == (w > ACTION_THRESHOLD)
        for o, w in zip(outputs[2:], wanted[2:], strict=True)
    )


def agreement(brain: Brain, samples: Sequence[Sequence[float]]) -> float:
    """The share of ``samples`` on which the brain agrees with ``reference_rule``."""
    if not samples:
        raise ValueError("Need at least one sample.")
    hits = sum(agrees(brain.decide(s), reference_rule(s)) for s in samples)
    return hits / len(samples)


# --- the seed -----------------------------------------------------------------

LEVELS = 16
"""Levels of a brain value in the genome (two digits)."""


def level_value(level: int) -> float:
    """The brain value a genome level stands for (-2 to 2 in 16 steps)."""
    return BRAIN_GENE.low + level * (BRAIN_GENE.high - BRAIN_GENE.low) / (LEVELS - 1)


# Per seeded hidden neuron, the levels of its bias, 28 incoming weights and 6 outgoing weights, then
# the levels of the six output biases. Written by src/evolution_tools/fit_seed_brain.py.
# fitted: begin
SEED_SLOTS: tuple[tuple[int, ...], ...] = (
    (
        5,
        13,
        1,
        14,
        5,
        0,
        0,
        15,
        5,
        12,
        15,
        2,
        14,
        8,
        15,
        0,
        2,
        9,
        1,
        0,
        3,
        11,
        0,
        14,
        0,
        0,
        9,
        14,
        0,
        8,
        7,
        7,
        7,
        6,
        7,
    ),
    (
        7,
        7,
        8,
        7,
        7,
        8,
        15,
        7,
        15,
        7,
        8,
        7,
        15,
        8,
        7,
        7,
        8,
        8,
        7,
        7,
        8,
        6,
        15,
        8,
        7,
        8,
        7,
        8,
        7,
        8,
        11,
        7,
        7,
        0,
        2,
    ),
    (
        7,
        8,
        7,
        8,
        8,
        7,
        5,
        7,
        8,
        7,
        15,
        7,
        8,
        8,
        7,
        7,
        7,
        8,
        8,
        7,
        8,
        8,
        7,
        8,
        7,
        7,
        8,
        8,
        7,
        8,
        14,
        8,
        8,
        10,
        12,
    ),
    (
        5,
        7,
        7,
        8,
        7,
        7,
        13,
        9,
        1,
        6,
        6,
        7,
        7,
        8,
        7,
        6,
        8,
        7,
        6,
        7,
        8,
        6,
        8,
        8,
        7,
        9,
        7,
        7,
        7,
        7,
        7,
        11,
        8,
        10,
        14,
    ),
    (
        6,
        6,
        6,
        6,
        15,
        6,
        6,
        6,
        7,
        8,
        8,
        7,
        8,
        7,
        8,
        8,
        7,
        8,
        6,
        6,
        7,
        7,
        6,
        6,
        8,
        7,
        7,
        8,
        7,
        8,
        7,
        8,
        12,
        9,
        9,
    ),
    (
        3,
        15,
        8,
        8,
        7,
        7,
        8,
        8,
        7,
        7,
        7,
        8,
        8,
        7,
        8,
        7,
        8,
        8,
        8,
        7,
        8,
        8,
        7,
        8,
        8,
        8,
        7,
        8,
        7,
        7,
        7,
        7,
        13,
        7,
        4,
    ),
    (
        8,
        8,
        7,
        7,
        7,
        5,
        8,
        5,
        8,
        15,
        7,
        5,
        7,
        8,
        8,
        7,
        8,
        8,
        7,
        8,
        7,
        5,
        7,
        8,
        7,
        11,
        8,
        8,
        8,
        2,
        8,
        7,
        7,
        3,
        9,
    ),
    (
        6,
        8,
        6,
        6,
        7,
        7,
        1,
        7,
        8,
        8,
        7,
        8,
        7,
        8,
        6,
        6,
        7,
        7,
        7,
        8,
        8,
        8,
        8,
        8,
        8,
        8,
        7,
        8,
        7,
        8,
        2,
        7,
        8,
        14,
        15,
    ),
    (
        5,
        7,
        8,
        8,
        7,
        8,
        12,
        8,
        14,
        8,
        8,
        8,
        8,
        7,
        8,
        8,
        7,
        7,
        8,
        7,
        8,
        8,
        7,
        8,
        8,
        7,
        8,
        7,
        8,
        8,
        8,
        15,
        7,
        11,
        2,
    ),
    (
        3,
        7,
        0,
        9,
        12,
        2,
        10,
        9,
        0,
        10,
        9,
        13,
        12,
        2,
        5,
        7,
        1,
        3,
        6,
        3,
        4,
        11,
        0,
        9,
        0,
        12,
        0,
        5,
        8,
        8,
        8,
        8,
        8,
        15,
        6,
    ),
)
SEED_OUTPUT_BIASES: tuple[int, ...] = (9, 2, 8, 3, 3, 0)
# fitted: end

GATE_ON = LEVELS - 1
GATE_OFF = 0
SPARE_LEVEL = LEVELS // 2
"""What the unused slots hold: a level just above zero, which the dead zone switches off."""


def seed_levels() -> list[int]:
    """The whole brain block as levels: seeded slots with their gates on, spare slots off, then the
    output biases."""
    blueprint = DEFAULT_BLUEPRINT
    body = blueprint.neuron_size - 1
    levels: list[int] = []
    for j in range(blueprint.max_hidden):
        if j < len(SEED_SLOTS):
            if len(SEED_SLOTS[j]) != body:
                raise ValueError(f"Seed slot {j} needs {body} levels.")
            levels.append(GATE_ON)
            levels.extend(SEED_SLOTS[j])
        else:
            levels.append(GATE_OFF)
            levels.extend([SPARE_LEVEL] * body)
    levels.extend(SEED_OUTPUT_BIASES or (SPARE_LEVEL,) * blueprint.outputs)
    return levels


def seed_values() -> list[float]:
    """``seed_levels`` as brain values (what ``BlockSpec.encode`` takes)."""
    return [level_value(level) for level in seed_levels()]


SEED_GAIN_DIGITS = "3333"
"""Digits of the ``brain_gain`` gene that read as the largest gain, 2: the sharp, decisive setting the
seed is fitted at. Evolution can lower it."""
SEED_GAIN = 2.0


def seeded_dna(
    rng: random.Random,
    base: DNA | None = None,
    variation: float = 3.0,
) -> DNA:
    """An animal genome with the seeded brain.

    ``base`` is the genome to give a brain to (a random one if left out). The brain block is replaced
    by the seed and the gain gene set to the seed's (2, what it was fitted at; evolution moves it
    later). ``variation`` is the expected number of weights or biases moved one level (0.27) up or
    down, so founders differ a little and still behave like the seed; 0 gives the seed exactly. Gates
    are never touched, so every founder has the seed's ten neurons.
    """
    if variation < 0.0:
        raise ValueError(f"Variation must be zero or more, got {variation}.")
    dna = DNA.random(ANIMAL_LAYOUT, rng) if base is None else base
    levels = seed_levels()
    size = DEFAULT_BLUEPRINT.neuron_size
    movable = [
        i
        for i in range(len(SEED_SLOTS) * size)
        if i % size != 0  # not a gate
    ] + list(range(DEFAULT_BLUEPRINT.max_hidden * size, len(levels)))
    count = int(variation) + (1 if rng.random() < variation - int(variation) else 0)
    for i in rng.sample(movable, min(count, len(movable))):
        levels[i] = min(LEVELS - 1, max(0, levels[i] + rng.choice((-1, 1))))
    values = [level_value(level) for level in levels]
    dna = dna.replaced("brain", BRAIN_GENE.encode(values))
    return dna.replaced("brain_gain", SEED_GAIN_DIGITS)


__all__ = [
    "SEED_HIDDEN",
    "agreement",
    "agrees",
    "reference_rule",
    "sample_inputs",
    "seed_levels",
    "seed_values",
    "seeded_dna",
]
