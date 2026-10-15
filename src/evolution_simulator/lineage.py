"""A cheap family colour key for a genome (UX.30).

The world view can colour animals by family so that lineages and species show up as groups. That needs
a number per animal that stays close for relatives and far for strangers, and that costs almost
nothing for a thousand animals every frame. Comparing every genome with every other would not.

``family_key(genome)`` gives two numbers: the genome's digits (centred on the middle of 0 to 3)
projected on two fixed random directions. A projection is the same for the same genome, changes a
little for a few changed digits (a child of two parents sits between them, a mutant next to its
original) and spreads unrelated genomes about it by one unit (the standard deviation over random
genomes is 1 on each). It is a pure function of the genome, so it is nothing to save: a loaded world
recomputes the same keys. Each animal works it out once, when it is made.

The keys of a real population are far closer together than one unit, since its members share most of
their genes: a viewer should stretch the range it finds in the frame over its colour scale (for
example by percentiles) and not use the numbers as they are.
"""

from __future__ import annotations

import math
import random
from typing import Any

_SEED = 0xFA3117
"""Fixes the two directions for good: changing it recolours every run."""

_directions: dict[int, tuple[tuple[float, ...], float, tuple[float, ...], float, float]] = {}
"""Per genome length: the two weight vectors, their sums, and the scale to unit spread."""

_MIDDLE = 49.5
"""The character code of the digit 1.5, the middle of '0' (48) to '3' (51)."""


def _unit_length(weights: tuple[float, ...]) -> tuple[float, ...]:
    """The weights scaled so their squares add up to the number of weights, which makes the spread of
    a random genome exactly 1 whatever draw the direction was (a chance direction can be off by 20%)."""
    norm = math.sqrt(math.sumprod(weights, weights) / len(weights))
    return tuple(w / norm for w in weights)


def _weights(length: int) -> tuple[tuple[float, ...], float, tuple[float, ...], float, float]:
    found = _directions.get(length)
    if found is None:
        rng = random.Random(_SEED + length)
        first = _unit_length(tuple(rng.gauss(0.0, 1.0) for _ in range(length)))
        second = _unit_length(tuple(rng.gauss(0.0, 1.0) for _ in range(length)))
        # A uniform digit of 0 to 3 has variance 1.25; the weights of one projection add up in
        # squares, so this scale gives a random genome a spread of 1 on each key.
        scale = 1.0 / math.sqrt(1.25 * length)
        found = (first, sum(first), second, sum(second), scale)
        _directions[length] = found
    return found


def _strand_key(digits: str) -> tuple[float, float]:
    first, first_sum, second, second_sum, scale = _weights(len(digits))
    codes = digits.encode("ascii")
    return (
        (math.sumprod(first, codes) - _MIDDLE * first_sum) * scale,
        (math.sumprod(second, codes) - _MIDDLE * second_sum) * scale,
    )


def family_key(genome: Any) -> tuple[float, float]:
    """The two family numbers of a genome (a ``DNA``, or a ``DiploidDNA`` as the mean of its two
    strands). Close genomes give close numbers."""
    strands = getattr(genome, "strands", None)
    if strands is None:
        return _strand_key(str(genome))
    keys = [_strand_key(str(strand)) for strand in strands]
    return (sum(k[0] for k in keys) / len(keys), sum(k[1] for k in keys) / len(keys))
