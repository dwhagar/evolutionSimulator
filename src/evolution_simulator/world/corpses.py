"""Corpses: what a dead animal leaves behind (``WORLD.12``, ``BRAIN.10``).

Every animal that dies leaves a corpse at the place it died: a store of meat that rots away and
that animals able to digest meat eat from when their brain says "eat or attack" and no plant is
underfoot. A corpse is smelled (and seen) by meat eaters as something to eat, so a hunter finds its
kill again and a scavenger finds what others left. Corpses make no sound and do not crowd.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from evolution_simulator.world.vector import Vec


@dataclass(frozen=True)
class CorpseRules:
    meat_share: float = 0.5
    """Share of a dead animal's maximum energy that is left as meat."""
    bite: float = 25.0
    """Meat one animal can take from a corpse in one reference tick (an hour)."""
    rot_halflife: float = 72.0
    """Reference ticks (hours) for half the meat to rot away."""
    scent_meat: float = 100.0
    """A corpse with this much meat or more can be smelled as far as a meat eater's smell reaches;
    one with less is smelled from proportionally closer, like a plant's biomass."""
    gone_below: float = 1.0
    """A corpse with less meat than this is removed."""

    def __post_init__(self) -> None:
        for name in ("meat_share", "bite", "rot_halflife", "scent_meat", "gone_below"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be zero or more, got {value}.")
        if self.rot_halflife == 0.0 or self.scent_meat == 0.0:
            raise ValueError("rot_halflife and scent_meat must be above zero.")

    def meat(self, max_energy: float) -> float:
        """The meat a dead animal with this energy store leaves."""
        return self.meat_share * max_energy


class Corpse:
    """A dead animal's remains: a place, a size and the meat still on it."""

    __slots__ = ("id", "mass", "meat", "position", "radius")

    kind = "corpse"

    def __init__(self, corpse_id: int, position: Vec, radius: float, mass: float, meat: float):
        self.id = corpse_id
        self.position = position
        self.radius = radius
        self.mass = mass
        self.meat = meat

    def __repr__(self) -> str:
        return f"Corpse(id={self.id}, position={self.position.coords}, meat={self.meat:.1f})"
