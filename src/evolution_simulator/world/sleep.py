"""Sleep (WORLD.5): the rules, and the hook the learning step (BRAIN.24) listens on.

At night every animal that is not starving sleeps. A sleeper does not sense, think, move, eat or
mate. It burns less energy and regains some, which is the owner's reason for sleep (issue 26). Its
brain is untouched while it sleeps; the nightly weight update (BRAIN.24) attaches through
``World.add_sleep_listener`` and runs when an animal falls asleep or wakes.

The numbers are starting values to calibrate (SENSE.13, TRAIT.3), and two open owner questions
shape them: whether sleepers are vulnerable (issue 57, default partly: sleeping animals stay in the
world and are sensed like any other, and their own senses work at reduced strength through the
sensing rules) and whether a creature can skip sleep when starving (this default says yes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from evolution_simulator.world.organisms import Animal
    from evolution_simulator.world.world import World


@dataclass(frozen=True)
class SleepRules:
    starving_below: float = 0.15
    """An animal with less than this fraction of its energy store stays awake to find food."""
    metabolism_factor: float = 0.4
    """Fraction of its basal metabolism an animal burns while asleep."""
    energy_regain: float = 0.002
    """Fraction of its energy store an animal regains each tick of sleep, on top of burning less."""

    def __post_init__(self) -> None:
        for name in ("starving_below", "metabolism_factor", "energy_regain"):
            value = getattr(self, name)
            if not (math.isfinite(value) and 0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be between 0 and 1, got {value}.")


class SleepListener(Protocol):
    """Hears when an animal falls asleep or wakes; called in id order during the step."""

    def fell_asleep(self, world: World, animal: Animal) -> None: ...

    def woke(self, world: World, animal: Animal) -> None: ...
