"""Brain adapter: the seam between the world and the brain.

The brain only sees a list of 17 numbers and returns 6. This module owns what they mean (the
contract in ``docs/design/brain.md``) so that the world model (``WORLD.1``, still open) can change
how it measures things without touching the brain: it fills in a ``Percepts`` and reads a
``BrainDecision``.

Inputs are egocentric and scaled. A direction is measured from the way the creature faces, -1 hard
left to +1 hard right. A closeness runs from 0 (not sensed) to 1 (touching), scaled by the
creature's own sense range. A sense that cannot see a thing reports 0 for it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ACTION_THRESHOLD: float = 0.5
"""An action output above this value counts as "do it" (eat or attack, seek mate, call)."""

INPUT_NAMES: tuple[str, ...] = (
    "energy_ratio",
    "health_ratio",
    "vitality",
    "ready_to_mate",
    "plant_direction",
    "plant_closeness",
    "prey_direction",
    "prey_closeness",
    "threat_direction",
    "threat_closeness",
    "mate_direction",
    "mate_closeness",
    "touching",
    "alarm_strength",
    "mating_call_strength",
    "call_direction",
    "crowding",
)

OUTPUT_NAMES: tuple[str, ...] = (
    "turn",
    "speed",
    "eat_or_attack",
    "seek_mating",
    "alarm_call",
    "mating_call",
)


@dataclass(frozen=True)
class Percepts:
    """What the world tells a creature about its surroundings; everything defaults to "nothing".

    ``*_direction`` is -1 to 1, ``*_closeness`` and the other strengths are 0 to 1. Values outside
    the range are clamped when the inputs are built.
    """

    plant_direction: float = 0.0
    plant_closeness: float = 0.0
    prey_direction: float = 0.0
    prey_closeness: float = 0.0
    threat_direction: float = 0.0
    threat_closeness: float = 0.0
    mate_direction: float = 0.0
    mate_closeness: float = 0.0
    touching: bool = False
    alarm_strength: float = 0.0
    mating_call_strength: float = 0.0
    call_direction: float = 0.0
    crowding: float = 0.0


@dataclass(frozen=True)
class BrainDecision:
    """The brain's six outputs: ``turn`` from -1 to 1, the rest from 0 to 1."""

    turn: float
    speed: float
    eat_or_attack: float
    seek_mating: float
    alarm_call: float
    mating_call: float

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


def _scaled(value: float, low: float, high: float, name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"Brain input {name!r} must be a finite number, got {value}.")
    return min(high, max(low, value))


def build_inputs(
    energy_ratio: float,
    health_ratio: float,
    vitality: float,
    ready_to_mate: bool,
    percepts: Percepts,
) -> tuple[float, ...]:
    """The 17 brain inputs, in ``INPUT_NAMES`` order, each clamped to its range."""
    p = percepts
    return (
        _scaled(energy_ratio, 0.0, 1.0, "energy_ratio"),
        _scaled(health_ratio, 0.0, 1.0, "health_ratio"),
        _scaled(vitality, 0.0, 1.0, "vitality"),
        1.0 if ready_to_mate else 0.0,
        _scaled(p.plant_direction, -1.0, 1.0, "plant_direction"),
        _scaled(p.plant_closeness, 0.0, 1.0, "plant_closeness"),
        _scaled(p.prey_direction, -1.0, 1.0, "prey_direction"),
        _scaled(p.prey_closeness, 0.0, 1.0, "prey_closeness"),
        _scaled(p.threat_direction, -1.0, 1.0, "threat_direction"),
        _scaled(p.threat_closeness, 0.0, 1.0, "threat_closeness"),
        _scaled(p.mate_direction, -1.0, 1.0, "mate_direction"),
        _scaled(p.mate_closeness, 0.0, 1.0, "mate_closeness"),
        1.0 if p.touching else 0.0,
        _scaled(p.alarm_strength, 0.0, 1.0, "alarm_strength"),
        _scaled(p.mating_call_strength, 0.0, 1.0, "mating_call_strength"),
        _scaled(p.call_direction, -1.0, 1.0, "call_direction"),
        _scaled(p.crowding, 0.0, 1.0, "crowding"),
    )


def decode_outputs(outputs: tuple[float, ...] | list[float]) -> BrainDecision:
    """Name the six brain outputs."""
    if len(outputs) != len(OUTPUT_NAMES):
        raise ValueError(f"Expected {len(OUTPUT_NAMES)} brain outputs, got {len(outputs)}.")
    return BrainDecision(*outputs)
