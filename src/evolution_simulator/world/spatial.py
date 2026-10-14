"""A uniform grid for finding things near a point without checking everything.

It stores ids against positions, and optionally an extent (a body or canopy radius). ``query``
returns the ids within a radius, sorted, so callers that walk the result do so in the same order on
every run. ``within_reach`` finds things by their surfaces instead and does not sort.
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
        self._cells: dict[tuple[int, ...], list[tuple[int, tuple[float, ...], float]]] = {}
        self._where: dict[int, tuple[tuple[int, ...], tuple[int, tuple[float, ...], float]]] = {}
        self._max_extent: float = 0.0
        """Largest extent ever inserted; widens the cells a surface search has to look in."""

    def __len__(self) -> int:
        return len(self._where)

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._where

    def _cell(self, coords: tuple[float, ...]) -> tuple[int, ...]:
        size = self.cell_size
        return tuple([math.floor(c / size) for c in coords])

    def insert(self, item_id: int, position: Vec, extent: float = 0.0) -> None:
        if item_id in self._where:
            raise ValueError(f"Item {item_id} is already in the index.")
        coords = position.coords
        cell = self._cell(coords)
        entry = (item_id, coords, extent)
        self._cells.setdefault(cell, []).append(entry)
        self._where[item_id] = (cell, entry)
        self._max_extent = max(self._max_extent, extent)

    def remove(self, item_id: int) -> None:
        cell, entry = self._where.pop(item_id)
        members = self._cells[cell]
        members.remove(entry)
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
                for item_id, coords, _ in members:
                    distance = dist(coords, origin)
                    if distance <= radius:
                        found.append((item_id, distance))
        found.sort()
        return found

    def within_reach(self, position: Vec, reach: float) -> list[tuple[int, float, float]]:
        """``(id, distance, extent)`` of every item whose surface is within ``reach`` of the point:
        ``distance - extent <= reach``, so a point-like creature at ``position`` that reaches
        ``reach`` touches it. In no particular order (sort if the order matters)."""
        origin = position.coords
        size = self.cell_size
        span = reach + self._max_extent
        spans = [
            range(math.floor((c - span) / size), math.floor((c + span) / size) + 1) for c in origin
        ]
        cells = self._cells
        dist = math.dist
        found: list[tuple[int, float, float]] = []
        for cell in itertools.product(*spans):
            members = cells.get(cell)
            if members:
                for item_id, coords, extent in members:
                    distance = dist(coords, origin)
                    if distance - extent <= reach:
                        found.append((item_id, distance, extent))
        return found
