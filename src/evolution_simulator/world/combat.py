"""Attacks and meat (``BRAIN.10``).

An animal whose brain says "eat or attack" and that touches no plant bites the nearest animal in
contact that it counts as prey (``senses.classify``: a meat eater at most 0.8 times its mass). The
bite does ``damage * carnivore efficiency * sqrt(attacker mass / prey mass)`` damage; the animal
that lands the killing bite eats ``meat_share`` of the victim's energy store, through the same
``feed`` as any other food, so its carnivore efficiency decides how much of it is gained.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AttackRules:
    damage: float = 30.0
    """Damage of one bite at carnivore efficiency 1 against prey of the attacker's own mass; a
    full-health animal of average size has 200, so a good hunter needs several bites."""
    meat_share: float = 0.5
    """Share of a killed animal's maximum energy that becomes food for the one that killed it."""

    def __post_init__(self) -> None:
        for name in ("damage", "meat_share"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be zero or more, got {value}.")

    def bite(self, carnivore_eff: float, attacker_mass: float, prey_mass: float) -> float:
        """The damage of one bite."""
        return self.damage * carnivore_eff * math.sqrt(attacker_mass / prey_mass)

    def meat(self, prey_max_energy: float) -> float:
        """The food a kill is worth."""
        return self.meat_share * prey_max_energy
