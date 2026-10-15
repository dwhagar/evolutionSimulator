"""Body colour: the colour line, the diet colour and how well a coat matches its background.

The pure functions of the colour design note (``docs/design/colour.md``, ``TRAIT.20``), shared by
the simulator (``TRAIT.21``: hiding in foliage) and the viewer (``UX.43``: drawing), so what the
owner sees is what the animals "see". Nothing here depends on the world, numpy or Qt.

An animal's colour is a *position* from 0 to 1 on a line of five anchors, rust red (the carnivore
colour) at 0, purple (omnivores) at 0.25, blue (herbivores) at 0.5, teal at 0.75 and leaf green
(the nearest thing to foliage) at 1, with straight-line interpolation of RGB between neighbours.
Until the colour gene exists (``TRAIT.21``) the position comes from the diet (``diet_colour``), and
the gene's founders start from the same function, so nothing changes colour when the gene lands.

Colours are RGB triples of floats from 0 to 1.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

RGB = tuple[float, float, float]

POSITIONS: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
"""Where the anchors sit on the colour line."""
ANCHORS: tuple[RGB, ...] = (
    (0.70, 0.30, 0.22),  # rust red: the carnivore colour
    (0.55, 0.20, 0.60),  # purple: the omnivore colour
    (0.20, 0.30, 0.85),  # blue: the herbivore colour
    (0.15, 0.60, 0.60),  # teal
    (0.20, 0.65, 0.20),  # leaf green
)
"""The colour at each of ``POSITIONS``."""

GROUND: RGB = (0.55, 0.45, 0.30)
"""Bare earth, a dull brown."""
PLANT_GREEN: RGB = (0.20, 0.55, 0.20)
"""The foliage of a soft plant (toughness 0)."""
FOLIAGE_DARKENING: float = 0.5
"""A plant of toughness 1 is this much darker (the owner's "tougher plants are darker")."""
MATCH_RADIUS: float = 0.6
"""A coat farther than this (RGB distance) from the background gets no benefit from matching it."""


def _clamp01(value: float) -> float:
    return min(max(value, 0.0), 1.0) if math.isfinite(value) else 0.0


def rgb(position: float) -> RGB:
    """The colour at ``position`` on the line (0 to 1; outside is clamped)."""
    at = _clamp01(position)
    for i in range(1, len(POSITIONS)):
        if at <= POSITIONS[i]:
            span = POSITIONS[i] - POSITIONS[i - 1]
            t = (at - POSITIONS[i - 1]) / span
            low, high = ANCHORS[i - 1], ANCHORS[i]
            return (
                low[0] + (high[0] - low[0]) * t,
                low[1] + (high[1] - low[1]) * t,
                low[2] + (high[2] - low[2]) * t,
            )
    return ANCHORS[-1]


def chroma(position: float) -> float:
    """How vivid the colour at ``position`` is: the spread between its largest and smallest
    channel (0 for a grey; the pigment upkeep of ``TRAIT.21`` grows with its square)."""
    colour = rgb(position)
    return max(colour) - min(colour)


def diet_colour(carnivore_eff: float, herbivore_eff: float) -> float:
    """The position of the coat an animal with these diet genes would have: 0.5 (blue) for a
    plant eater, 0 (rust red) for a meat eater and 0.25 (purple) for a balanced diet.

    ``tilt`` is the meat efficiency less the plant efficiency, from -1 (all plants) to +1 (all
    meat); the position is ``0.25 * (1 - tilt)``. (The design note writes the factor as 0.5, which
    would put plant eaters on green; 0.25 is what its own table and prose describe.)"""
    tilt = max(-1.0, min(1.0, carnivore_eff - herbivore_eff))
    return 0.25 * (1.0 - tilt)


def share_colour(meat_share: float) -> float:
    """The same position from a meat share (the part of what it can digest that is meat, 0 to 1,
    the ``diet`` of a frame): 0.5 for all plants, 0.25 for half and half, 0 for all meat."""
    return 0.5 * (1.0 - _clamp01(meat_share))


def foliage(toughness: float = 0.0) -> RGB:
    """The colour of a plant's foliage, darker the tougher it is (0 to 1)."""
    keep = 1.0 - FOLIAGE_DARKENING * _clamp01(toughness)
    return (PLANT_GREEN[0] * keep, PLANT_GREEN[1] * keep, PLANT_GREEN[2] * keep)


def background(cover: float, toughness: float = 0.0) -> RGB:
    """What an animal sits against: bare ground blended toward foliage by how much of the ground
    nearby is under plant canopy (``cover``, 0 to 1; ``toughness`` darkens the foliage)."""
    share = _clamp01(cover)
    leaves = foliage(toughness)
    return (
        GROUND[0] + share * (leaves[0] - GROUND[0]),
        GROUND[1] + share * (leaves[1] - GROUND[1]),
        GROUND[2] + share * (leaves[2] - GROUND[2]),
    )


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    """The straight-line distance between two RGB colours (at most 1.73)."""
    return math.dist(a, b)


def match(position: float, background_rgb: Sequence[float], radius: float = MATCH_RADIUS) -> float:
    """How well the coat at ``position`` matches ``background_rgb``: 1 for a perfect match, falling
    to 0 at ``radius`` away and beyond."""
    return max(0.0, 1.0 - distance(rgb(position), background_rgb) / radius)
