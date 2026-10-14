"""A uniform grid for finding things near a point without checking everything.

It stores ids against positions. ``query`` returns the ids within a radius, sorted, so callers
that walk the result do so in the same order on every run.
"""

from __future__ import annotations

import itertools
import math

from evolution_simulator.world.vector import Vec


class SpatialIndex:
    def __init__(self, cell_size: float) -> None:
        if not math.isfinite(cell_size) or cell_size <= 0.0:
            raise ValueError(f"Cell size must be a positive finite number, got {cell_size}.")
        self.cell_size = cell_size
        self._cells: dict[tuple[int, ...], list[tuple[int, tuple[float, ...]]]] = {}
        self._where: dict[int, tuple[tuple[int, ...], tuple[float, ...]]] = {}

    def __len__(self) -> int:
        return len(self._where)

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._where

    def _cell(self, coords: tuple[float, ...]) -> tuple[int, ...]:
        size = self.cell_size
        return tuple([math.floor(c / size) for c in coords])

    def insert(self, item_id: int, position: Vec) -> None:
        if item_id in self._where:
            raise ValueError(f"Item {item_id} is already in the index.")
        coords = position.coords
        cell = self._cell(coords)
        self._cells.setdefault(cell, []).append((item_id, coords))
        self._where[item_id] = (cell, coords)

    def remove(self, item_id: int) -> None:
        cell, coords = self._where.pop(item_id)
        members = self._cells[cell]
        members.remove((item_id, coords))
        if not members:
            del self._cells[cell]

    def clear(self) -> None:
        self._cells.clear()
        self._where.clear()

    def query(self, position: Vec, radius: float) -> list[int]:
        """Ids whose stored position is within ``radius`` of ``position``, in id order."""
        return [item_id for item_id, _ in self.query_with_distance(position, radius)]

    def query_with_distance(self, position: Vec, radius: float) -> list[tuple[int, float]]:
        """Like ``query`` but each id comes with its distance, so callers need not measure again."""
        origin = position.coords
        size = self.cell_size
        spans = [
            range(math.floor((c - radius) / size), math.floor((c + radius) / size) + 1)
            for c in origin
        ]
        cells = self._cells
        dist = math.dist
        found: list[tuple[int, float]] = []
        for cell in itertools.product(*spans):
            members = cells.get(cell)
            if members:
                for item_id, coords in members:
                    distance = dist(coords, origin)
                    if distance <= radius:
                        found.append((item_id, distance))
        found.sort()
        return found
