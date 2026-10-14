"""Brain adapter: the seam between the world and the brain.

The brain only sees a list of numbers (17 now) and returns 6. This module owns what they mean (the
contract in ``docs/design/brain.md``, the table in ``sense_channels.py``) so that the world model can
change how it measures things without touching the brain: it fills in a ``Percepts`` and reads a
``BrainDecision``.

Inputs are egocentric and scaled. A direction is measured from the way the creature faces, -1 hard
left to +1 hard right. A closeness runs from 0 (not sensed) to 1 (touching), scaled by the
creature's own sense range. A sense that cannot see a thing reports 0 for it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

from evolution_simulator.sense_channels import (
    INPUT_CHANNELS,
    input_names,
    inputs_builder,
    percepts_class,
)

ACTION_THRESHOLD: float = 0.5
"""An action output above this value counts as "do it" (eat or attack, seek mate, call)."""

INPUT_NAMES: tuple[str, ...] = input_names(INPUT_CHANNELS)
"""The brain's inputs in order, generated from the sense-channel table (``sense_channels.py``)."""

OUTPUT_NAMES: tuple[str, ...] = (
    "turn",
    "speed",
    "eat_or_attack",
    "seek_mating",
    "alarm_call",
    "mating_call",
)


Percepts = percepts_class(INPUT_CHANNELS, "Percepts", __name__)
"""The world's side of the brain's inputs, generated from the sense-channel table: one field per
world channel, defaulting to "nothing", and a ``senses_nothing`` property."""


TEMPERAMENT_STRENGTH: float = 0.6
"""How far temperament bends perception: 0 ignores it; at 0.6 an extreme gene scales a closeness
input by 0.4 (at 0) or 1.6 (at 1) and a middling gene (0.5) leaves it alone."""


@dataclass(frozen=True)
class Temperament:
    """The inherited behaviour genes, as the brain's adapter sees them (``BRAIN.14``).

    Behaviour comes from genetic factors as well as the network. These values bend what the brain
    perceives rather than adding brain inputs, so the brain's shape (and the genome that stores it)
    does not change when senses or behaviour genes do. Each runs from 0 to 1 and 0.5 is neutral.

    - ``aggression`` scales how close prey looks: bold animals are drawn to it harder.
    - ``fear`` scales how close a threat looks: timid animals react to it sooner and harder.
    - ``repro_drive`` scales how close a possible mate looks (``REPRO.5``): a driven animal feels
      pulled toward a mate harder. The other reproduction genes act on energy and timing, not on
      what the brain perceives.

    More behaviour genes are added as more fields here, each bending the input it concerns.
    """

    aggression: float = 0.5
    fear: float = 0.5
    repro_drive: float = 0.5

    def __post_init__(self) -> None:
        for name in ("aggression", "fear", "repro_drive"):
            value = getattr(self, name)
            if not (math.isfinite(value) and 0.0 <= value <= 1.0):
                raise ValueError(f"Temperament {name} must be between 0 and 1, got {value}.")

    @staticmethod
    def factor(gene: float) -> float:
        """The multiplier a gene value puts on the input it concerns."""
        return 1.0 + TEMPERAMENT_STRENGTH * (2.0 * gene - 1.0)


@dataclass(frozen=True)
class BrainDecision:
    """The brain's six outputs: ``turn`` from -1 to 1, the rest from 0 to 1."""

    turn: float
    speed: float
    eat_or_attack: float
    seek_mating: float
    alarm_call: float
    mating_call: float
    wandering: bool = False
    """True when the wander fallback replaced the brain's steering (see ``Wanderer``)."""

    @property
    def eats_or_attacks(self) -> bool:
        return self.eat_or_attack > ACTION_THRESHOLD

    @property
    def seeks_mating(self) -> bool:
        return self.seek_mating > ACTION_THRESHOLD

    @property
    def calls_alarm(self) -> bool:
        return self.alarm_call > ACTION_THRESHOLD

    @property
    def calls_for_mate(self) -> bool:
        return self.mating_call > ACTION_THRESHOLD

    @property
    def has_action(self) -> bool:
        """Any of the four action outputs is above the action threshold."""
        return self.eats_or_attacks or self.seeks_mating or self.calls_alarm or self.calls_for_mate


@dataclass(frozen=True)
class WanderPolicy:
    """When a creature counts as unable to decide, and how it wanders instead.

    The brain has no memory, so a creature that senses nothing, or whose outputs all sit near zero,
    would stand still or circle forever and never give its senses anything new. The fallback replaces
    its steering with a random turn so it moves through the world.
    """

    when_blind: bool = True
    """Wander when the world reports nothing at all (``Percepts.senses_nothing``)."""
    when_idle: bool = True
    """Wander when the brain's own outputs say nothing: little turn, little speed, no action."""
    idle_turn: float = 0.1
    """Below this absolute turn output the creature is not steering."""
    idle_speed: float = 0.1
    """Below this speed output the creature is not moving."""
    speed: float = 0.4
    """Speed output while wandering (the brain's own speed is kept if it is higher)."""
    redraw_chance: float = 0.25
    """Chance per wandering tick of picking a new random turn; otherwise the last one is kept, so the
    path bends smoothly instead of jittering on the spot."""

    def __post_init__(self) -> None:
        for name in ("idle_turn", "idle_speed", "speed", "redraw_chance"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"Wander {name} must be between 0 and 1, got {value}.")


class Wanderer:
    """The random-wander fallback for one creature (``BRAIN.16``).

    Holds the current wander turn, so keep one per creature. ``apply`` returns the brain's decision
    untouched when the creature can decide, and otherwise a copy with a random turn, at least the
    wander speed, and ``wandering`` set. The action outputs are never changed. All randomness comes
    from the ``random.Random`` passed in, so runs are repeatable, and it is only used while wandering.
    """

    def __init__(self, policy: WanderPolicy | None = None) -> None:
        self.policy = policy if policy is not None else WanderPolicy()
        self._turn: float | None = None

    def undecided(self, decision: BrainDecision, percepts: Percepts) -> bool:
        """Whether this decision should be replaced by wandering."""
        policy = self.policy
        if policy.when_blind and percepts.senses_nothing:
            return True
        return (
            policy.when_idle
            and abs(decision.turn) < policy.idle_turn
            and decision.speed < policy.idle_speed
            and not decision.has_action
        )

    def apply(
        self, decision: BrainDecision, percepts: Percepts, rng: random.Random
    ) -> BrainDecision:
        if not self.undecided(decision, percepts):
            self._turn = None  # next time it gets stuck it picks a fresh direction
            return decision
        if self._turn is None or rng.random() < self.policy.redraw_chance:
            self._turn = rng.uniform(-1.0, 1.0)
        return replace(
            decision,
            turn=self._turn,
            speed=max(decision.speed, self.policy.speed),
            wandering=True,
        )


def _temperament_factor(field_name: str, temperament: Temperament) -> float:
    return Temperament.factor(getattr(temperament, field_name))


build_inputs = inputs_builder(INPUT_CHANNELS, _temperament_factor)
"""``build_inputs(percepts, temperament=None, **body)``: the brain's inputs in ``INPUT_NAMES`` order,
each clamped to its range and finite. ``body`` gives one keyword per body channel
(``energy_ratio``, ``health_ratio``, ``vitality``, ``ready_to_mate``); ``temperament`` (neutral if
left out) scales the channels the table marks ``scaled_by``, and a thing that is not sensed
(closeness 0) stays unsensed. Generated from the sense-channel table."""


def decode_outputs(outputs: tuple[float, ...] | list[float]) -> BrainDecision:
    """Name the six brain outputs."""
    if len(outputs) != len(OUTPUT_NAMES):
        raise ValueError(f"Expected {len(OUTPUT_NAMES)} brain outputs, got {len(outputs)}.")
    return BrainDecision(*outputs)
