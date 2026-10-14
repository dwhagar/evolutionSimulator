"""A frame's packed blocks read into numpy arrays (UX.12)."""

from __future__ import annotations

import numpy as np

from evolution_simulator.session.snapshot import Block


class Layer:
    """One block as arrays: ``ids`` (uint32), ``values`` (float32, one row per thing, one column
    per name in ``columns``) and ``flags`` (uint8). Read-only views of the frame's bytes."""

    __slots__ = ("columns", "flags", "ids", "values")

    def __init__(self, block: Block) -> None:
        self.columns = block.columns
        self.ids = np.frombuffer(block.ids, dtype="<u4")
        self.values = np.frombuffer(block.values, dtype="<f4").reshape(-1, len(block.columns))
        self.flags = np.frombuffer(block.flags, dtype=np.uint8)

    @property
    def count(self) -> int:
        return len(self.ids)

    def col(self, name: str) -> np.ndarray:
        return self.values[:, self.columns.index(name)]

    def flag(self, bit: int) -> np.ndarray:
        """Boolean per row: is this flag bit set."""
        return (self.flags & bit) != 0
