"""Drawing one tick behind (UX.12): sliding creatures from where they were to where they are.

At slow speeds the world changes only a few times a second or less (at the hourly tick, "hour" is one
tick a second, "real-time" one tick an hour), so a view that shows each frame as it arrives would
jump. The view keeps the last two frames and shows the position a fraction ``t`` of the way from the
earlier to the later one, with ``t`` growing over the real time one tick takes (``duration``).
Above about ten ticks a second the steps are too small to see and ``duration`` says no glide.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np

from evolution_simulator.viewer.worldview.layers import Layer

GLIDE_MIN_SECONDS = 0.1
"""Real time per frame under which sliding is not worth it (above ten steps a second)."""


def duration(simulated_seconds: float, speed: float | None, *, running: bool) -> float | None:
    """Real seconds the step between two frames takes, or ``None`` when the view should show the
    newest frame as it is (paused, stepping, as fast as possible, or too fast to see).

    ``simulated_seconds`` is the simulated time between the two frames and ``speed`` the simulated
    seconds per real second the session is actually managing."""
    if not running or speed is None or not speed > 0.0 or not simulated_seconds > 0.0:
        return None
    seconds = simulated_seconds / speed
    return seconds if seconds >= GLIDE_MIN_SECONDS and math.isfinite(seconds) else None


class Pose(NamedTuple):
    """Where each animal was drawn: the start of the next slide, so a frame that arrives mid-slide
    carries on from where the picture is and nothing jumps."""

    ids: np.ndarray
    x: np.ndarray
    y: np.ndarray
    heading: np.ndarray

    @property
    def count(self) -> int:
        return len(self.ids)


def pose_of(layer: Layer) -> Pose:
    return Pose(layer.ids, layer.col("x"), layer.col("y"), layer.col("heading"))


def blend(prev: Pose | None, cur: Layer, t: float) -> Pose:
    """The pose of each row of ``cur``, ``t`` of the way from where the same animal was in ``prev``.
    An animal that is new in ``cur`` stays where it is; the heading turns the short way round."""
    x, y, heading = cur.col("x"), cur.col("y"), cur.col("heading")
    if prev is None or t >= 1.0 or prev.count == 0 or cur.count == 0:
        return Pose(cur.ids, x, y, heading)
    order = np.argsort(prev.ids)
    ids = prev.ids[order]
    at = np.minimum(np.searchsorted(ids, cur.ids), len(ids) - 1)
    known = ids[at] == cur.ids
    source = order[at]
    px, py, ph = prev.x[source], prev.y[source], prev.heading[source]
    turn = (heading - ph + np.pi) % (2.0 * np.pi) - np.pi
    t = max(t, 0.0)
    return Pose(
        cur.ids,
        np.where(known, px + (x - px) * t, x),
        np.where(known, py + (y - py) * t, y),
        np.where(known, ph + turn * t, heading),
    )
