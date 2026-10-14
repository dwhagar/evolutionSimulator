"""Vectors for positions, written for any number of dimensions so 3D can follow 2D.

Only the angle helpers (``from_angle``, ``angle``) are 2D; everything else works on any length.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vec:
    """An immutable point or displacement: a tuple of finite floats with at least one component."""

    coords: tuple[float, ...]

    def __post_init__(self) -> None:
        coords = tuple(float(c) for c in self.coords)
        if not coords:
            raise ValueError("A vector needs at least one component.")
        if not all(math.isfinite(c) for c in coords):
            raise ValueError(f"Vector components must be finite numbers, got {coords}.")
        object.__setattr__(self, "coords", coords)

    @classmethod
    def of(cls, *coords: float) -> Vec:
        return cls(coords)

    @classmethod
    def zero(cls, dimensions: int) -> Vec:
        return cls((0.0,) * dimensions)

    @classmethod
    def from_angle(cls, angle: float, length: float = 1.0) -> Vec:
        """A 2D vector of the given length pointing at ``angle`` radians (0 is +x, counterclockwise)."""
        return cls((length * math.cos(angle), length * math.sin(angle)))

    @property
    def dimensions(self) -> int:
        return len(self.coords)

    @property
    def x(self) -> float:
        return self.coords[0]

    @property
    def y(self) -> float:
        return self.coords[1]

    def _same_size(self, other: Vec) -> None:
        if self.dimensions != other.dimensions:
            raise ValueError(
                f"Cannot combine a {self.dimensions}D and a {other.dimensions}D vector."
            )

    def __add__(self, other: Vec) -> Vec:
        self._same_size(other)
        return Vec(tuple(a + b for a, b in zip(self.coords, other.coords)))

    def __sub__(self, other: Vec) -> Vec:
        self._same_size(other)
        return Vec(tuple(a - b for a, b in zip(self.coords, other.coords)))

    def __mul__(self, scale: float) -> Vec:
        return Vec(tuple(c * scale for c in self.coords))

    __rmul__ = __mul__

    def __neg__(self) -> Vec:
        return Vec(tuple(-c for c in self.coords))

    def __iter__(self):
        return iter(self.coords)

    def __len__(self) -> int:
        return len(self.coords)

    def dot(self, other: Vec) -> float:
        self._same_size(other)
        return sum(a * b for a, b in zip(self.coords, other.coords))

    def length(self) -> float:
        return math.sqrt(sum(c * c for c in self.coords))

    def distance_to(self, other: Vec) -> float:
        self._same_size(other)
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(self.coords, other.coords)))

    def normalised(self) -> Vec:
        """The unit vector in the same direction; the zero vector stays zero."""
        size = self.length()
        return self if size == 0.0 else self * (1.0 / size)

    def angle(self) -> float:
        """The direction of a 2D vector in radians, from -pi to pi."""
        if self.dimensions != 2:
            raise ValueError("angle() is only defined for 2D vectors.")
        return math.atan2(self.coords[1], self.coords[0])

    @staticmethod
    def midpoint(a: Vec, b: Vec) -> Vec:
        return (a + b) * 0.5

    @staticmethod
    def total(vectors: Iterable[Vec]) -> Vec:
        items = list(vectors)
        if not items:
            raise ValueError("Cannot add up no vectors.")
        result = items[0]
        for item in items[1:]:
            result = result + item
        return result
