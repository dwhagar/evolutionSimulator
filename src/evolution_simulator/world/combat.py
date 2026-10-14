"""Attacks and meat (``BRAIN.10``).

An animal whose brain says "eat or attack" and that touches no plant bites the nearest animal in
contact that it counts as prey (``senses.classify``: a meat eater at most 0.8 times its mass). The
bite does ``damage * carnivore efficiency * sqrt(attacker mass / prey mass)`` damage. What a kill
is worth is the corpse it leaves (``corpses.py``), which the killer eats like any other meat.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AttackRules:
    damage: float = 30.0
    """Damage of one bite at carnivore efficiency 1 against prey of the attacker's own mass; a
    full-health animal of average size has 200, so a good hunter needs several bites."""

    def __post_init__(self) -> None:
        if not math.isfinite(self.damage) or self.damage < 0.0:
            raise ValueError(f"damage must be zero or more, got {self.damage}.")

    def bite(self, carnivore_eff: float, attacker_mass: float, prey_mass: float) -> float:
        """The damage of one bite."""
        return self.damage * carnivore_eff * math.sqrt(attacker_mass / prey_mass)
