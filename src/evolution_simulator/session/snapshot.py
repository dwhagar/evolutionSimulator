"""Snapshot types (UX.6): the frame the simulation publishes and how it is packed.

A ``Frame`` is a small, immutable picture of the world at one tick: the clock and the light, the
session's status, and one packed ``Block`` per kind of thing (animals, plants, corpses). A block
is three byte strings, so a frame pickles as a handful of ``bytes`` objects and a viewer reads it
without a loop (``numpy.frombuffer`` on each, shaped by ``Block.columns``; ``Block.rows()`` does
the same in plain Python for tests and tools):

- ``ids``: one unsigned 32-bit integer per row (an id never loses digits the way a float would),
- ``values``: ``len(columns)`` 32-bit floats per row, row after row,
- ``flags``: one byte per row, the bits named in ``ANIMAL_FLAGS`` and ``PLANT_FLAGS``.

All numbers are little-endian. The core has no numpy, so packing uses ``array`` from the standard
library; ``FRAME_FORMAT`` is bumped whenever the columns or the flag bits change.

Size: about 37 bytes an animal, 21 a plant and 21 a corpse, so 300 animals and 3,000 plants come to
about 74 KB when the plants go out with the frame and about 11 KB when they do not (plants change
slowly and are sent a couple of times a second, see ``Session``).
"""

from __future__ import annotations

import sys
from array import array
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from evolution_simulator.world.views import AnimalView, CorpseView, PlantView

FRAME_FORMAT: int = 1
"""Version of the frame layout below."""

ANIMAL_COLUMNS: tuple[str, ...] = (
    "x",
    "y",
    "heading",
    "radius",
    "energy_ratio",
    "health_ratio",
    "age_ratio",
    "diet",
)
PLANT_COLUMNS: tuple[str, ...] = ("x", "y", "radius", "biomass_ratio")
CORPSE_COLUMNS: tuple[str, ...] = ("x", "y", "radius", "meat")

ANIMAL_FLAGS: dict[str, int] = {
    "asleep": 1,
    "pregnant": 2,
    "ready_to_mate": 4,
    "wandering": 8,
    "female": 16,
}
"""Bit of the animal flag byte for each yes-or-no field (``female`` is the view's ``sex`` of 1)."""
PLANT_FLAGS: dict[str, int] = {"ready_to_seed": 1}

_ID_CODE = "I"
_FLOAT_CODE = "f"
assert array(_ID_CODE).itemsize == 4 and array(_FLOAT_CODE).itemsize == 4


def _le(values: array) -> bytes:
    if sys.byteorder == "big":  # pragma: no cover - the packed form is little-endian everywhere
        values = array(values.typecode, values)
        values.byteswap()
    return values.tobytes()


@dataclass(frozen=True, slots=True)
class Block:
    """One kind of thing, packed: ``count`` rows of an id, ``len(columns)`` floats and a flag byte."""

    columns: tuple[str, ...]
    ids: bytes = b""
    values: bytes = b""
    flags: bytes = b""

    @property
    def count(self) -> int:
        return len(self.flags)

    @property
    def nbytes(self) -> int:
        return len(self.ids) + len(self.values) + len(self.flags)

    def rows(self) -> Iterator[tuple[int, tuple[float, ...], int]]:
        """``(id, floats, flags)`` for each row, in the order they were packed."""
        ids = array(_ID_CODE)
        ids.frombytes(self.ids)
        values = array(_FLOAT_CODE)
        values.frombytes(self.values)
        if sys.byteorder == "big":  # pragma: no cover
            ids.byteswap()
            values.byteswap()
        width = len(self.columns)
        for row, (organism_id, flag) in enumerate(zip(ids, self.flags, strict=True)):
            yield organism_id, tuple(values[row * width : (row + 1) * width]), flag

    def column(self, name: str) -> list[float]:
        """One column's values in row order."""
        index = self.columns.index(name)
        return [floats[index] for _, floats, _ in self.rows()]

    def id_list(self) -> list[int]:
        return [organism_id for organism_id, _, _ in self.rows()]


def pack_animals(views: Sequence[AnimalView]) -> Block:
    ids = array(_ID_CODE)
    values = array(_FLOAT_CODE)
    flags = bytearray()
    for v in views:
        ids.append(v.id)
        values.extend(
            (v.x, v.y, v.heading, v.radius, v.energy_ratio, v.health_ratio, v.age_ratio, v.diet)
        )
        flags.append(
            v.asleep
            | (v.pregnant << 1)
            | (v.ready_to_mate << 2)
            | (v.wandering << 3)
            | ((v.sex == 1) << 4)
        )
    return Block(ANIMAL_COLUMNS, _le(ids), _le(values), bytes(flags))


def pack_plants(views: Sequence[PlantView]) -> Block:
    ids = array(_ID_CODE)
    values = array(_FLOAT_CODE)
    flags = bytearray()
    for v in views:
        ids.append(v.id)
        values.extend((v.x, v.y, v.radius, v.biomass_ratio))
        flags.append(v.ready_to_seed)
    return Block(PLANT_COLUMNS, _le(ids), _le(values), bytes(flags))


def pack_corpses(views: Sequence[CorpseView]) -> Block:
    ids = array(_ID_CODE)
    values = array(_FLOAT_CODE)
    for v in views:
        ids.append(v.id)
        values.extend((v.x, v.y, v.radius, v.meat))
    return Block(CORPSE_COLUMNS, _le(ids), _le(values), bytes(len(ids)))


@dataclass(frozen=True, slots=True)
class Status:
    """How the session is running, sent with every frame and when it changes."""

    running: bool
    """Playing; false when paused, or when only a ``Step`` is being worked off."""
    steps_left: int
    """Ticks still owed by a ``Step`` command."""
    speed_asked: float | None
    """Simulated seconds per real second that was asked for; ``None`` for "as fast as possible"."""
    speed_preset: str | None
    """The preset name that matches the speed asked for (``"day"``, ``"max"``), if any."""
    speed_achieved: float | None
    """Simulated seconds per real second measured over the last second or so of running; ``None``
    while paused or before enough has been measured."""
    behind: bool
    """The computer could not keep up with the speed asked for in the last second."""
    ticks_dropped: int
    """Ticks the speed asked for owed that the computer skipped, in all."""
    selected: int | None
    """The animal whose details are being sent."""


@dataclass(frozen=True, slots=True)
class Frame:
    """The world at one tick, small enough to send thirty times a second."""

    format: int
    seq: int
    """Counts the frames this session built, from 1."""
    tick: int
    simulated_seconds: float
    elapsed: str
    """Simulated time as text, for example ``3d 04:00:00``."""
    day: int
    daylight: float
    is_night: bool
    world_size: tuple[float, ...]
    status: Status
    animal_count: int
    plant_count: int
    corpse_count: int
    animals: Block
    corpses: Block
    plants: Block | None
    """``None`` when this frame does not carry the plants (they go out less often); a viewer keeps
    the last plants it was sent."""

    @property
    def nbytes(self) -> int:
        """Packed size of the blocks."""
        return (
            self.animals.nbytes + self.corpses.nbytes + (self.plants.nbytes if self.plants else 0)
        )
