"""Corpses: what a dead animal leaves behind (``WORLD.12``, ``BRAIN.10``).

Every animal that dies leaves a corpse at the place it died: a store of meat that rots away and
that animals able to digest meat eat from when their brain says "eat or attack" and no plant is
underfoot. A corpse is smelled (and seen) by meat eaters as something to eat, so a hunter finds its
kill again and a scavenger finds what others left. Corpses make no sound and do not crowd.

``CorpseRules`` lives in ``config.py`` (``TRAIT.11``) and is re-exported here.
"""

from __future__ import annotations

from evolution_simulator.config import CorpseRules
from evolution_simulator.world.vector import Vec

__all__ = ["Corpse", "CorpseRules"]


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
