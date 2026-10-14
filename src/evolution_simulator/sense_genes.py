"""What the sense genes mean: ranges, noise and energy cost (``SENSE.11``, ``SENSE.16``).

The gene levels (0 to 1) come from the trait table; this module holds the numbers that turn them
into sense organs and the formulas for what an organ costs. They are plain constants for now and
move into the constants config with ``TRAIT.3``. The values are the starting rules of
``docs/design/senses.md`` ("Sense range, cost and noise"), to be calibrated against a running world
(``SENSE.13``).

- **Range.** Vision, hearing and smell can reach 0 (the sense is lost: no cost, no report). Touch is
  always on: contact is always felt, the gene only sets how far past the body it reaches.
- **Noise.** The error on a direction report falls linearly as the gene rises, so a better organ is
  more accurate as well as longer.
- **Cost.** An organ costs in proportion to the area it covers: the cone of vision, the circles of
  hearing and smell. Touch and taste keep the old cost of 0.08 times the gene level squared.
- **Vision** (``SENSE.16``, ``docs/design/sense-genes.md``) has two genes besides its level. The field
  gene ``f`` is the half-angle either side of the direction of movement, 15 to 180 degrees on a log
  scale; the acuity gene ``a`` is how sharp the eye tries to be. A wide field spreads the eye thin, so
  the working acuity is ``min(a, 1 - f)``. Working acuity lengthens the reach, shrinks the errors in
  direction, closeness and relative size, and adds to the cost, which keeps the whole frontier about
  equally dear: you choose what to see, not how much to pay.
"""

from __future__ import annotations

import math

SIGHT_REACH: tuple[float, float] = (0.0, 60.0)
"""Vision range at gene 0 and 1, before the field of view narrows it. 0 is blind."""
FOV_HALF_DEGREES: tuple[float, float] = (15.0, 180.0)
"""Half-angle of the field of vision at gene 0 and 1, on a log scale (``15 * 12 ** f``), so 30 to
360 degrees across and 52 degrees (104 across) in the middle."""
ACUITY_REACH: tuple[float, float] = (0.6, 1.4)
"""Vision reach as a multiple of the base reach at working acuity 0 and 1."""
ACUITY_DIRECTION_NOISE: tuple[float, float] = (0.02, 0.005)
"""Vision direction error, and relative-size error, at working acuity 0 and 1."""
ACUITY_CLOSENESS_NOISE: tuple[float, float] = (0.05, 0.01)
"""Vision closeness error at working acuity 0 and 1."""
HEARING_RANGE: tuple[float, float] = (0.0, 85.0)
SMELL_RANGE: tuple[float, float] = (0.0, 100.0)
TACTILE_FACTOR: tuple[float, float] = (1.1, 2.6)
"""Touch reach as a multiple of the body radius; touch is always on."""

NOISE_AT_GENE: dict[str, tuple[float, float]] = {
    "hearing": (0.30, 0.15),
    "smell": (0.50, 0.25),
}
"""Standard deviation of the direction error, in input units, at gene 0 and at gene 1. Vision's
depends on its working acuity instead (``vision_direction_noise``)."""

COST_PER_AREA: dict[str, float] = {
    "vision": 8e-6,
    "hearing": 2.5e-6,
    "smell": 2.5e-6,
}
"""Energy per tick per square unit covered; vision costs the most per area, and is multiplied by
``1 + working acuity``, so a mid-range eye (reach 30 over 104 degrees, acuity 0.5) pays 0.0098.
Placeholders: ``SENSE.13`` calibrates them against a running world."""
TOUCH_COST: float = 0.08
TASTE_COST: float = 0.08
"""Energy per tick times the gene level squared (unchanged from the original rule)."""


def _between(low_high: tuple[float, float], level: float) -> float:
    low, high = low_high
    return low + (high - low) * min(1.0, max(0.0, level))


def direction_noise(sense: str, gene_level: float) -> float:
    """The direction error of a hearing or smell organ whose gene is at ``gene_level`` (0 to 1).
    Vision's error comes from its acuity: see ``vision_direction_noise``."""
    return _between(NOISE_AT_GENE[sense], gene_level)


def half_angle(field_level: float) -> float:
    """Degrees either side of the direction of movement for a field gene of ``field_level``."""
    low, high = FOV_HALF_DEGREES
    level = min(1.0, max(0.0, field_level))
    return low * (high / low) ** level


def working_acuity(field_level: float, acuity_level: float) -> float:
    """How sharply the eye actually sees: its acuity gene, but never above ``1 - field``, because
    the same light-sensing cells spread over a wider field resolve less of it."""
    field = min(1.0, max(0.0, field_level))
    return min(min(1.0, max(0.0, acuity_level)), 1.0 - field)


def vision_reach(base_reach: float, acuity: float) -> float:
    """Reach of the eye in units: the base reach (the range gene) times 0.6 to 1.4 by working acuity."""
    return base_reach * _between(ACUITY_REACH, acuity)


def vision_direction_noise(acuity: float) -> float:
    """The direction error of the eye (and of the relative size it reports) at working ``acuity``."""
    return _between(ACUITY_DIRECTION_NOISE, acuity)


def vision_closeness_noise(acuity: float) -> float:
    """The error on how close the eye says a thing is, at working ``acuity``."""
    return _between(ACUITY_CLOSENESS_NOISE, acuity)


def circle_area(sense_range: float) -> float:
    return math.pi * sense_range * sense_range


def cone_area(sense_range: float, fov_degrees: float) -> float:
    """Area of the slice of a circle that a field of view of ``fov_degrees`` (across) covers."""
    return fov_degrees / 360.0 * circle_area(sense_range)


def sense_cost(
    sight_range: float,
    fov_degrees: float,
    hearing_range: float,
    smell_range: float,
    touch_level: float,
    taste_level: float,
    acuity: float = 0.0,
) -> float:
    """Energy per tick the sense organs cost: ranges are the effective ranges in world units, the
    field of view is the total angle across, and ``acuity`` is the eye's working acuity."""
    return (
        COST_PER_AREA["vision"] * (1.0 + acuity) * cone_area(sight_range, fov_degrees)
        + COST_PER_AREA["hearing"] * circle_area(hearing_range)
        + COST_PER_AREA["smell"] * circle_area(smell_range)
        + TOUCH_COST * touch_level**2
        + TASTE_COST * taste_level**2
    )
