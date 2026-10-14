"""World bounds (WORLD.4): a box from the origin to ``size``, set by the user.

The default is 1000 by 1000 world units. What happens at the edges is not decided yet (issue 36
question 3 is open), so edges are walls: a position is clamped back inside. When the owner answers,
another edge rule goes in ``clamp``; the rest of the world only calls ``clamp`` and ``contains``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from evolution_simulator.world.vector import Vec

DEFAULT_SIZE: tuple[float, ...] = (1000.0, 1000.0)
"""World units along each axis."""


@dataclass(frozen=True)
class Bounds:
    """A box with one corner at the origin and the opposite corner at ``size``."""

    size: tuple[float, ...] = DEFAULT_SIZE

    def __post_init__(self) -> None:
        size = tuple(float(s) for s in self.size)
        if not size:
            raise ValueError("Bounds need at least one dimension.")
        if not all(math.isfinite(s) and s > 0.0 for s in size):
            raise ValueError(f"Every bounds size must be a positive finite number, got {size}.")
        object.__setattr__(self, "size", size)

    @property
    def dimensions(self) -> int:
        return len(self.size)

    @property
    def centre(self) -> Vec:
        return Vec(tuple(s / 2.0 for s in self.size))

    def contains(self, position: Vec) -> bool:
        self._check(position)
        return all(0.0 <= c <= s for c, s in zip(position.coords, self.size))

    def clamp(self, position: Vec) -> Vec:
        """The nearest position inside the box (walls at the edges)."""
        self._check(position)
        return Vec(tuple(min(s, max(0.0, c)) for c, s in zip(position.coords, self.size)))

    def _check(self, position: Vec) -> None:
        if position.dimensions != self.dimensions:
            raise ValueError(
                f"A {position.dimensions}D position does not fit {self.dimensions}D bounds."
            )
