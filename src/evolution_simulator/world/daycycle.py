"""The day-night cycle (WORLD.5): how light changes with simulated time.

A day is ``length_seconds`` of simulated time (600 by default, ten simulated minutes: animals live
from about 22 minutes to 3.3 hours, so a real 24-hour day would give most of them less than one
night to learn in). Daylight runs smoothly from 0 at midnight to 1 at noon:
``0.5 - 0.5 * cos(2 * pi * phase)`` where ``phase`` is the fraction of the day gone (0 midnight,
0.25 dawn, 0.5 noon, 0.75 dusk). It counts as night while daylight is below ``night_below``
(0.3 by default, which is a little over a third of the day).

The world starts at noon so a new run begins in full light. All of it is a pure function of the
simulated time, so it needs no state and runs stay repeatable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DayCycle:
    length_seconds: float = 600.0
    start_phase: float = 0.5
    night_below: float = 0.3

    def __post_init__(self) -> None:
        if not (math.isfinite(self.length_seconds) and self.length_seconds > 0.0):
            raise ValueError(f"length_seconds must be positive, got {self.length_seconds}.")
        if not (math.isfinite(self.start_phase) and 0.0 <= self.start_phase < 1.0):
            raise ValueError(f"start_phase must be from 0 up to 1, got {self.start_phase}.")
        if not 0.0 <= self.night_below <= 1.0:
            raise ValueError(f"night_below must be between 0 and 1, got {self.night_below}.")

    def phase(self, simulated_seconds: float) -> float:
        """Fraction of the day gone, from 0 up to 1 (0 is midnight, 0.5 noon)."""
        return (self.start_phase + simulated_seconds / self.length_seconds) % 1.0

    def daylight(self, simulated_seconds: float) -> float:
        """Light from 0 (midnight) to 1 (noon)."""
        return 0.5 - 0.5 * math.cos(math.tau * self.phase(simulated_seconds))

    def is_night(self, simulated_seconds: float) -> bool:
        return self.daylight(simulated_seconds) < self.night_below

    def day_number(self, simulated_seconds: float) -> int:
        """Whole midnights passed since the start, counting from 0."""
        return math.floor(self.start_phase + simulated_seconds / self.length_seconds)

    @property
    def night_fraction(self) -> float:
        """The share of each day that counts as night."""
        return math.acos(1.0 - 2.0 * self.night_below) / math.pi
