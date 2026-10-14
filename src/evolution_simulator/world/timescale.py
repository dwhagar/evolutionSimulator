"""Time scale (WORLD.3): how simulated time relates to ticks and to real time.

A tick is a fixed length of simulated time, 1 second by default. The *speed* says how many
simulated seconds pass for each real second, so it sets how many ticks should run per real second.
The presets are the owner's list (issue 10): 1 real second equals 1 minute, 1 hour, 1 day, 7 days,
1 month, 1 year, 10 years, 100 years or 1000 years. A year is 365.25 days and a month a twelfth of
that. How fast the computer can actually step is a separate limit; ``Pacer`` caps the ticks it asks
for and the run is then slower than the preset.

Nothing here reads a clock. Callers pass in the real time that has passed, so runs stay repeatable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MINUTE: float = 60.0
HOUR: float = 60.0 * MINUTE
DAY: float = 24.0 * HOUR
YEAR: float = 365.25 * DAY
MONTH: float = YEAR / 12.0

SPEED_PRESETS: dict[str, float] = {
    "real-time": 1.0,
    "minute": MINUTE,
    "hour": HOUR,
    "day": DAY,
    "week": 7.0 * DAY,
    "month": MONTH,
    "year": YEAR,
    "decade": 10.0 * YEAR,
    "century": 100.0 * YEAR,
    "millennium": 1000.0 * YEAR,
}
"""Preset name to simulated seconds per real second."""


@dataclass(frozen=True)
class TimeScale:
    """Seconds of simulated time in one tick, and simulated seconds per real second."""

    seconds_per_tick: float = 1.0
    speed: float = 1.0

    def __post_init__(self) -> None:
        for name, value in (("seconds_per_tick", self.seconds_per_tick), ("speed", self.speed)):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be a positive finite number, got {value}.")

    @classmethod
    def from_preset(cls, name: str, seconds_per_tick: float = 1.0) -> TimeScale:
        if name not in SPEED_PRESETS:
            raise ValueError(f"Unknown speed preset {name!r}; choose from {sorted(SPEED_PRESETS)}.")
        return cls(seconds_per_tick=seconds_per_tick, speed=SPEED_PRESETS[name])

    @property
    def ticks_per_real_second(self) -> float:
        return self.speed / self.seconds_per_tick

    def ticks_for(self, real_seconds: float) -> float:
        """Ticks that should run in ``real_seconds`` of real time (not rounded)."""
        return real_seconds * self.ticks_per_real_second

    def simulated_seconds(self, ticks: int) -> float:
        return ticks * self.seconds_per_tick


class Pacer:
    """Turns elapsed real time into whole ticks to run, carrying the fraction over.

    Each call to ``advance`` returns how many ticks to step now. ``max_ticks`` caps one call, for
    speeds the computer cannot keep up with; the ticks over the cap are dropped, not queued, so a
    slow machine falls behind the preset rather than spiralling.
    """

    def __init__(self, time_scale: TimeScale) -> None:
        self.time_scale = time_scale
        self._carry: float = 0.0

    def advance(self, real_seconds: float, max_ticks: int | None = None) -> int:
        if not math.isfinite(real_seconds) or real_seconds < 0.0:
            raise ValueError(f"Elapsed real time must be zero or more, got {real_seconds}.")
        owed = self._carry + self.time_scale.ticks_for(real_seconds)
        ticks = math.floor(owed)
        self._carry = owed - ticks
        if max_ticks is not None and ticks > max_ticks:
            ticks = max_ticks
            self._carry = 0.0
        return ticks


def format_duration(seconds: float) -> str:
    """Simulated time as years, days and clock time, for example ``2y 41d 05:12:09``."""
    if not math.isfinite(seconds) or seconds < 0.0:
        raise ValueError(f"A duration must be zero or more, got {seconds}.")
    total = int(seconds)
    years, rest = divmod(total, int(YEAR))
    days, rest = divmod(rest, int(DAY))
    hours, rest = divmod(rest, int(HOUR))
    minutes, secs = divmod(rest, int(MINUTE))
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    if years:
        return f"{years}y {days}d {clock}"
    if days:
        return f"{days}d {clock}"
    return clock
