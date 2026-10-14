"""The day-night cycle (WORLD.5): how light changes with simulated time.

A day is ``length_seconds`` of simulated time, 24 simulated hours by default (``WORLD.7``). It was ten
minutes when a tick was a second and animals lived minutes; now animals live about a simulated year,
so a real day gives them hundreds of nights to learn in, and at the default one-hour tick a day is 24
ticks. Daylight runs smoothly from 0 at midnight to 1 at noon:
``0.5 - 0.5 * cos(2 * pi * phase)`` where ``phase`` is the fraction of the day gone (0 midnight,
0.25 dawn, 0.5 noon, 0.75 dusk). It counts as night while daylight is below ``night_below``
(0.3 by default, which is a little over a third of the day).

The world starts at noon so a new run begins in full light. All of it is a pure function of the
simulated time, so it needs no state and runs stay repeatable.
"""

from __future__ import annotations

from evolution_simulator.config import DayCycle

__all__ = ["DayCycle"]
