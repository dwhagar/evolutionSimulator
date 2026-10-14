"""Smell trails (``SENSE.20``): a coarse grid of scent that animals and corpses leave and that fades.

Each tick every living animal adds a little scent to the cell it stands in and every corpse a little
carrion scent to its own, up to 1. Scent fades by half every ``half_life_hours``; instead of
sweeping the grid each tick, a cell keeps the tick it was last written and its strength then, and
the fade is worked out when the cell is read or written. An occasional sweep drops cells too weak to
matter. Each cell remembers who left the latest scent in it (the body mass and whether it eats
meat, which is what the world needs to say whether a smelling animal takes it for prey or a threat)
and an id, so that an animal ignores its own trail.

A trail is smelled from the cell's centre and only by smell: it is not seen, heard or felt, does
not crowd, and says nothing about a mate (that has to be met). ``WorldSenses`` reads it with
``smelled``. Nothing here reads a clock or a random generator.
"""

from __future__ import annotations

import math
from typing import Any

from evolution_simulator.config import ScentRules
from evolution_simulator.world.vector import Vec

ANIMAL = 0
"""Kind of a trail left by a living animal."""
CARRION = 1
"""Kind of a trail left by a corpse."""

# A record is [strength, tick, mass, meat_eater, source]: the strength at ``tick``.
_STRENGTH, _TICK, _MASS, _MEAT, _SOURCE = range(5)

Smelled = tuple[int, int, int, float, float, float, bool]
"""``(kind, cx, cy, distance, strength, mass, meat_eater)`` of a trail within reach."""


class ScentField:
    def __init__(self, rules: ScentRules, dt: float) -> None:
        self.rules = rules
        self._decay = 0.5 ** (dt / rules.half_life_hours)
        """What is left of a trail after one tick."""
        self._cells: dict[tuple[int, int], list[Any]] = {}
        """``(cx, cy)`` to ``[animal record, carrion record]``, each a record or ``None``."""

    def __len__(self) -> int:
        return sum((r is not None) + (c is not None) for r, c in self._cells.values())

    def cell_of(self, position: Vec) -> tuple[int, int]:
        x, y = position.coords
        size = self.rules.cell_size
        return math.floor(x / size), math.floor(y / size)

    def centre_of(self, cx: int, cy: int) -> Vec:
        size = self.rules.cell_size
        return Vec.of((cx + 0.5) * size, (cy + 0.5) * size)

    def strength(self, record: list[Any], tick: int) -> float:
        return float(record[_STRENGTH] * self._decay ** (tick - record[_TICK]))

    def deposit(
        self,
        kind: int,
        position: Vec,
        amount: float,
        tick: int,
        mass: float,
        meat_eater: bool,
        source: int,
    ) -> None:
        """Add ``amount`` of scent to the cell at ``position`` at tick ``tick``."""
        x, y = position.coords
        size = self.rules.cell_size
        key = (math.floor(x / size), math.floor(y / size))
        cell = self._cells.get(key)
        if cell is None:
            cell = self._cells[key] = [None, None]
        record = cell[kind]
        if record is None:
            cell[kind] = [min(1.0, amount), tick, mass, meat_eater, source]
        else:
            record[_STRENGTH] = min(
                1.0, record[_STRENGTH] * self._decay ** (tick - record[_TICK]) + amount
            )
            record[_TICK] = tick
            record[_MASS] = mass
            record[_MEAT] = meat_eater
            record[_SOURCE] = source

    def smelled(
        self,
        position: Vec,
        reach: float,
        tick: int,
        exclude: int | None = None,
        carrion: bool = True,
    ) -> list[Smelled]:
        """The trails a nose with this ``reach`` could pick up from ``position`` at ``tick``: those
        whose centre is within ``reach * strength``. Not in any particular order. Cells whose latest
        scent is ``exclude``'s own are left out, and carrion too unless ``carrion``."""
        x, y = position.coords
        size = self.rules.cell_size
        cells = self._cells
        decay = self._decay
        hypot = math.hypot
        floor = math.floor
        kinds = (ANIMAL, CARRION) if carrion else (ANIMAL,)
        found: list[Smelled] = []
        y_cells = range(floor((y - reach) / size), floor((y + reach) / size) + 1)
        for cx in range(floor((x - reach) / size), floor((x + reach) / size) + 1):
            for cy in y_cells:
                cell = cells.get((cx, cy))
                if cell is None:
                    continue
                for kind in kinds:
                    record = cell[kind]
                    if record is None or record[_SOURCE] == exclude:
                        continue
                    strength = record[_STRENGTH] * decay ** (tick - record[_TICK])
                    distance = hypot((cx + 0.5) * size - x, (cy + 0.5) * size - y)
                    if distance <= reach * strength:
                        found.append(
                            (kind, cx, cy, distance, strength, record[_MASS], record[_MEAT])
                        )
        return found

    def purge(self, tick: int) -> None:
        """Forget trails weaker than ``min_strength``."""
        floor = self.rules.min_strength
        empty = []
        for key, cell in self._cells.items():
            for kind in (ANIMAL, CARRION):
                record = cell[kind]
                if record is not None and self.strength(record, tick) < floor:
                    cell[kind] = None
            if cell[ANIMAL] is None and cell[CARRION] is None:
                empty.append(key)
        for key in empty:
            del self._cells[key]

    # ---- saving ------------------------------------------------------------------------------

    def records(self) -> list[list[Any]]:
        """Every trail as ``[kind, cx, cy, strength, tick, mass, meat_eater, source]``, in a fixed
        order, for the save and the state digest."""
        return sorted(
            [kind, cx, cy, r[_STRENGTH], r[_TICK], r[_MASS], r[_MEAT], r[_SOURCE]]
            for (cx, cy), cell in self._cells.items()
            for kind, r in enumerate(cell)
            if r is not None
        )

    def restore(self, records: list[list[Any]]) -> None:
        self._cells = {}
        for kind, cx, cy, strength, tick, mass, meat, source in records:
            cell = self._cells.setdefault((int(cx), int(cy)), [None, None])
            cell[int(kind)] = [float(strength), int(tick), float(mass), bool(meat), int(source)]
