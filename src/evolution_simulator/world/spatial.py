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
        self._cells: dict[tuple[int, ...], list[int]] = {}
        self._where: dict[int, tuple[tuple[int, ...], Vec]] = {}

    def __len__(self) -> int:
        return len(self._where)

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._where

    def _cell(self, position: Vec) -> tuple[int, ...]:
        return tuple(math.floor(c / self.cell_size) for c in position.coords)

    def insert(self, item_id: int, position: Vec) -> None:
        if item_id in self._where:
            raise ValueError(f"Item {item_id} is already in the index.")
        cell = self._cell(position)
        self._cells.setdefault(cell, []).append(item_id)
        self._where[item_id] = (cell, position)

    def remove(self, item_id: int) -> None:
        cell, _ = self._where.pop(item_id)
        members = self._cells[cell]
        members.remove(item_id)
        if not members:
            del self._cells[cell]

    def clear(self) -> None:
        self._cells.clear()
        self._where.clear()

    def query(self, position: Vec, radius: float) -> list[int]:
        """Ids whose stored position is within ``radius`` of ``position``, in id order."""
        low = self._cell(position - Vec((radius,) * position.dimensions))
        high = self._cell(position + Vec((radius,) * position.dimensions))
        found: list[int] = []
        for cell in itertools.product(*(range(lo, hi + 1) for lo, hi in zip(low, high))):
            for item_id in self._cells.get(cell, ()):
                if self._where[item_id][1].distance_to(position) <= radius:
                    found.append(item_id)
        found.sort()
        return found
