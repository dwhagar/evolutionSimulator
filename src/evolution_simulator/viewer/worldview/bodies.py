"""What an animal looks like (UX.43): a round body with two eyes and, on one sex, spots.

The drawing itself is in ``canvas``; the rules that say *what* to draw are here, as small functions
of the frame's columns, so they can be read and tested on their own:

- the body is a circle the size of the animal's body radius, never under ``MIN_BODY_PX`` across;
- two eyes sit at the front and their pupils point where the animal is looking: ``look`` (the
  frame's column, radians from straight ahead, positive to the left) added to its heading;
- the spotted sex has a few ladybug spots on the back half (owner's answer on issue #129; which sex is
  one constant, ``SPOTTED_SEX``, issue #246);
- the eyes and the spots are dropped when the body is too small on screen to hold them, and an
  animal asleep shuts its eyes.

Colour is in ``palette`` (``body_colours``); this module only says where things go.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np

from evolution_simulator.session.snapshot import ANIMAL_FLAGS
from evolution_simulator.viewer.worldview.layers import Layer

MIN_BODY_PX = 5.0
"""A body is never drawn smaller than this across, so a zoomed-out world stays readable."""
EYES_MIN_RADIUS_PX = 6.0
"""Bodies with a smaller radius on screen are drawn without eyes."""
SPOTS_MIN_RADIUS_PX = 5.0
"""Bodies with a smaller radius on screen are drawn without spots."""
SPOTTED_SEX = "female"
"""The sex that carries the spots: ``"female"`` or ``"male"`` (owner question 4, issue #246)."""

EYE_FORWARD = 0.45
EYE_SIDE = 0.38
EYE_RADIUS = 0.3
PUPIL_RADIUS = 0.16
PUPIL_REACH = 0.13
"""Eye places and sizes as fractions of the body radius: how far forward and to each side the eye
sits, its white, its pupil, and how far the pupil moves toward where the animal looks."""
SPOTS: tuple[tuple[float, float], ...] = ((-0.5, 0.0), (-0.1, 0.5), (-0.1, -0.5))
"""Spot places (forward, left) as fractions of the body radius, and their size."""
SPOT_RADIUS = 0.2


class Eye(NamedTuple):
    """One eye on screen: where, how big, and where its pupil sits."""

    x: float
    y: float
    white: float
    pupil_x: float
    pupil_y: float
    pupil: float


def body_radius_px(radius: np.ndarray, scale: float) -> np.ndarray:
    """On-screen body radius of each animal (``radius`` in world units, ``scale`` pixels per unit)."""
    return np.maximum(radius * scale, MIN_BODY_PX / 2.0)


def has_eyes(radius_px: float) -> bool:
    return radius_px >= EYES_MIN_RADIUS_PX


def has_spots(radius_px: float) -> bool:
    return radius_px >= SPOTS_MIN_RADIUS_PX


def spotted(layer: Layer, sex: str = SPOTTED_SEX) -> np.ndarray:
    """Boolean per animal: does it carry spots."""
    if sex not in ("female", "male"):
        raise ValueError(f"No such sex {sex!r}.")
    female = layer.flag(ANIMAL_FLAGS["female"])
    return female if sex == "female" else ~female


def looks(layer: Layer) -> np.ndarray:
    """Where each animal's eyes point, radians from straight ahead (0 from a frame that has no
    ``look`` column, an older format)."""
    if "look" not in layer.columns:
        return np.zeros(layer.count)
    return np.nan_to_num(layer.col("look").astype(np.float64))


def screen_axes(heading: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Unit vectors on screen for forward and for left, from a heading in world radians (world y is
    up, screen y is down)."""
    forward = (math.cos(heading), -math.sin(heading))
    return forward, (forward[1], -forward[0])


def eyes(x: float, y: float, radius_px: float, heading: float, look: float) -> tuple[Eye, Eye]:
    """The two eyes of an animal at screen ``(x, y)`` facing ``heading`` and looking ``look`` away
    from straight ahead."""
    (fx, fy), (lx, ly) = screen_axes(heading)
    gaze_x, gaze_y = math.cos(heading + look), -math.sin(heading + look)
    found = []
    for side in (1.0, -1.0):
        ex = x + radius_px * (fx * EYE_FORWARD + lx * EYE_SIDE * side)
        ey = y + radius_px * (fy * EYE_FORWARD + ly * EYE_SIDE * side)
        reach = radius_px * PUPIL_REACH
        found.append(
            Eye(
                ex,
                ey,
                radius_px * EYE_RADIUS,
                ex + gaze_x * reach,
                ey + gaze_y * reach,
                radius_px * PUPIL_RADIUS,
            )
        )
    return found[0], found[1]


def spot_places(
    x: float, y: float, radius_px: float, heading: float
) -> list[tuple[float, float, float]]:
    """``(x, y, radius)`` of each spot on the back of the body."""
    (fx, fy), (lx, ly) = screen_axes(heading)
    return [
        (
            x + radius_px * (fx * ahead + lx * left),
            y + radius_px * (fy * ahead + ly * left),
            radius_px * SPOT_RADIUS,
        )
        for ahead, left in SPOTS
    ]
