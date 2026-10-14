"""What the sense genes mean: ranges, noise and energy cost (``SENSE.11``).

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
"""

from __future__ import annotations

import math

SIGHT_REACH: tuple[float, float] = (0.0, 60.0)
"""Vision range at gene 0 and 1, before the field of view narrows it. 0 is blind."""
FOV_DEGREES: tuple[float, float] = (40.0, 360.0)
FOV_RANGE_PENALTY: float = 0.45
"""A field of view at gene 1 shortens the range by this fraction: ``reach * (1 - 0.45 * fov_gene)``."""
HEARING_RANGE: tuple[float, float] = (0.0, 85.0)
SMELL_RANGE: tuple[float, float] = (0.0, 100.0)
TACTILE_FACTOR: tuple[float, float] = (1.1, 2.6)
"""Touch reach as a multiple of the body radius; touch is always on."""

NOISE_AT_GENE: dict[str, tuple[float, float]] = {
    "vision": (0.02, 0.01),
    "hearing": (0.30, 0.15),
    "smell": (0.50, 0.25),
}
"""Standard deviation of the direction error, in input units, at gene 0 and at gene 1."""

COST_PER_AREA: dict[str, float] = {
    "vision": 1.2e-5,
    "hearing": 2.5e-6,
    "smell": 2.5e-6,
}
"""Energy per tick per square unit covered; vision costs the most per area. Placeholders: a random
animal's sense bill comes to about 19% of its basal metabolism (10% to 29% for the middle 80%), and
with every other gene at 0 a smell specialist pays about 28%, a hearing one 22%, a wide-eyed one 17%
and a narrow-eyed one 7%. ``SENSE.13`` calibrates them against a running world."""
TOUCH_COST: float = 0.08
TASTE_COST: float = 0.08
"""Energy per tick times the gene level squared (unchanged from the original rule)."""


def direction_noise(sense: str, gene_level: float) -> float:
    """The direction error of an organ whose gene is at ``gene_level`` (0 to 1)."""
    worst, best = NOISE_AT_GENE[sense]
    level = min(1.0, max(0.0, gene_level))
    return worst + (best - worst) * level


def circle_area(sense_range: float) -> float:
    return math.pi * sense_range * sense_range


def cone_area(sense_range: float, fov_degrees: float) -> float:
    """Area of the slice of a circle that a field of view of ``fov_degrees`` covers."""
    return fov_degrees / 360.0 * circle_area(sense_range)


def sense_cost(
    sight_range: float,
    fov_degrees: float,
    hearing_range: float,
    smell_range: float,
    touch_level: float,
    taste_level: float,
) -> float:
    """Energy per tick the sense organs cost: ranges are the effective ranges in world units."""
    return (
        COST_PER_AREA["vision"] * cone_area(sight_range, fov_degrees)
        + COST_PER_AREA["hearing"] * circle_area(hearing_range)
        + COST_PER_AREA["smell"] * circle_area(smell_range)
        + TOUCH_COST * touch_level**2
        + TASTE_COST * taste_level**2
    )
