"""History samples (``UX.8``): what the statistics recorder keeps and the charts read.

One ``Sample`` describes a stretch of simulated time (one day when it is first taken): the
population levels (counts, mean energy and so on), the flows over the stretch (births and deaths by
cause), a ``Stat`` (count, mean, spread, minimum, maximum) for every trait and gene of the animals
and the plants, and, now and then, a histogram of each gene. Older samples are merged into coarser
ones (days into weeks, weeks into months, months into years) and the merge is exact for what it
keeps: a merged ``Stat`` is the statistic of all the individuals of the samples that went into it,
counts and flows add up, and levels are averaged by the time they cover.

Plain values only, no dependencies: a viewer reads ``HistorySamples`` and nothing else, and it round
trips through ``to_dict`` and ``from_dict`` (JSON-ready) for the run store.

Series names are dotted: ``animals``, ``plants``, ``corpses``, ``animal.energy``, ``births.animal``,
``deaths.animal.starvation``, and for the stats ``animal.trait.mass`` and ``animal.gene.size``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

HISTORY_FORMAT = 2
"""The layout of ``HistorySamples.to_dict`` (and of a saved recorder); bump it when that layout
changes and add the old number to ``READABLE_FORMATS`` with a migration.

- 1: a ``Stat`` is ``[n, mean, std, lo, hi]``; no lineage counts.
- 2: a ``Stat`` may carry the 10th and 90th percentile (``[n, mean, std, lo, hi, p10, p90]``), the
  samples have ``lineages.*`` levels and a saved recorder carries the lineage roots of the living."""

READABLE_FORMATS: tuple[int, ...] = (1, 2)
"""The formats that load. A format-1 history loads with no percentiles (the charts fall back to
mean plus or minus a deviation for those samples); saving it again writes format 2."""

SUM_PREFIXES: tuple[str, ...] = ("births.", "deaths.")
"""Values whose names start with these are flows, added up when samples merge. Every other value is
a level, averaged by the time each sample covers."""


def is_flow(name: str) -> bool:
    return name.startswith(SUM_PREFIXES)


def percentile(ordered: Sequence[float], q: float) -> float:
    """The ``q`` (0 to 1) quantile of numbers already in order, by linear interpolation between the
    two nearest ranks (the usual default)."""
    position = q * (len(ordered) - 1)
    below = int(position)
    above = min(below + 1, len(ordered) - 1)
    return ordered[below] + (ordered[above] - ordered[below]) * (position - below)


@dataclass(frozen=True, slots=True)
class Stat:
    """Count, mean, spread (population standard deviation), minimum and maximum of some numbers,
    and the 10th and 90th percentile (``None`` in history recorded before format 2)."""

    n: int
    mean: float
    std: float
    lo: float
    hi: float
    p10: float | None = None
    p90: float | None = None

    @classmethod
    def of(cls, values: Iterable[float]) -> Stat | None:
        """The statistic of ``values``, or ``None`` when there are none."""
        data = sorted(values)
        if not data:
            return None
        n = len(data)
        mean = math.fsum(data) / n
        variance = math.fsum((v - mean) ** 2 for v in data) / n
        return cls(
            n,
            mean,
            math.sqrt(variance),
            data[0],
            data[-1],
            percentile(data, 0.1),
            percentile(data, 0.9),
        )

    def merge(self, other: Stat) -> Stat:
        """The statistic of both sets of numbers together."""
        n = self.n + other.n
        mean = (self.n * self.mean + other.n * other.mean) / n
        variance = (
            self.n * (self.std**2 + (self.mean - mean) ** 2)
            + other.n * (other.std**2 + (other.mean - mean) ** 2)
        ) / n
        # Percentiles cannot be merged exactly without the numbers; the count-weighted average of
        # the two is close for samples of one population and exact for equal ones. It is absent
        # when either side has none (older history).
        p10 = p90 = None
        if self.p10 is not None and other.p10 is not None:
            p10 = (self.n * self.p10 + other.n * other.p10) / n
        if self.p90 is not None and other.p90 is not None:
            p90 = (self.n * self.p90 + other.n * other.p90) / n
        return Stat(
            n, mean, math.sqrt(variance), min(self.lo, other.lo), max(self.hi, other.hi), p10, p90
        )

    def to_list(self) -> list[float]:
        """``[n, mean, std, lo, hi]``, with ``p10, p90`` after them when it has them."""
        row: list[float] = [self.n, self.mean, self.std, self.lo, self.hi]
        if self.p10 is not None and self.p90 is not None:
            row += [self.p10, self.p90]
        return row

    @classmethod
    def from_list(cls, row: Sequence[float]) -> Stat:
        """The inverse of ``to_list``; a five-number row (format 1) has no percentiles."""
        n, mean, std, lo, hi, *rest = row
        if len(rest) not in (0, 2):
            raise ValueError(f"A saved statistic has 5 or 7 numbers, not {len(row)}.")
        p10, p90 = (float(rest[0]), float(rest[1])) if rest else (None, None)
        return cls(int(n), float(mean), float(std), float(lo), float(hi), p10, p90)


@dataclass(frozen=True, slots=True)
class Sample:
    """Statistics for ``span`` periods (days, by default) ending at period ``day``.

    ``day`` counts periods of simulated time since the world began, so with the default period it is
    the simulated day. ``tick`` is the world's tick at the end of the stretch.
    """

    day: int
    span: int
    tick: int
    values: Mapping[str, float] = field(default_factory=dict)
    stats: Mapping[str, Stat] = field(default_factory=dict)
    histograms: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    """Gene distributions, in equal bins over the gene's 0 to 1; only some samples have them."""

    def __post_init__(self) -> None:
        if self.span < 1:
            raise ValueError(f"A sample covers at least one period, got {self.span}.")

    @property
    def start(self) -> int:
        """The period the stretch began at (``day - span``)."""
        return self.day - self.span

    def rate(self, name: str) -> float | None:
        """A value per period: a flow divided by the periods covered, a level as it is."""
        value = self.values.get(name)
        if value is None:
            return None
        return value / self.span if is_flow(name) else value

    def merge(self, later: Sample) -> Sample:
        """This sample and one that follows it, as a single sample covering both stretches."""
        values: dict[str, float] = {}
        for name in self.values.keys() | later.values.keys():
            a, b = self.values.get(name), later.values.get(name)
            if is_flow(name):
                values[name] = (a or 0.0) + (b or 0.0)
            elif a is None:
                values[name] = b  # type: ignore[assignment]
            elif b is None:
                values[name] = a
            else:
                values[name] = (a * self.span + b * later.span) / (self.span + later.span)
        stats: dict[str, Stat] = dict(self.stats)
        for name, stat in later.stats.items():
            stats[name] = stats[name].merge(stat) if name in stats else stat
        histograms: dict[str, tuple[int, ...]] = dict(self.histograms)
        for name, bins in later.histograms.items():
            mine = histograms.get(name)
            histograms[name] = (
                bins if mine is None else tuple(x + y for x, y in zip(mine, bins, strict=True))
            )
        return Sample(
            day=later.day,
            span=self.span + later.span,
            tick=later.tick,
            values=dict(sorted(values.items())),
            stats=dict(sorted(stats.items())),
            histograms=dict(sorted(histograms.items())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "span": self.span,
            "tick": self.tick,
            "values": dict(self.values),
            "stats": {name: s.to_list() for name, s in self.stats.items()},
            "histograms": {name: list(bins) for name, bins in self.histograms.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Sample:
        return cls(
            day=int(data["day"]),
            span=int(data["span"]),
            tick=int(data["tick"]),
            values={name: float(v) for name, v in data["values"].items()},
            stats={name: Stat.from_list(row) for name, row in data["stats"].items()},
            histograms={
                name: tuple(int(c) for c in bins) for name, bins in data["histograms"].items()
            },
        )


@dataclass(frozen=True, slots=True)
class Tier:
    """The samples of one resolution, oldest first. ``periods`` is how many periods a full sample of
    this tier covers (1 for days, 7 for weeks and so on; the newest may cover fewer)."""

    name: str
    periods: int
    samples: tuple[Sample, ...]


@dataclass(frozen=True, slots=True)
class HistorySamples:
    """Everything the recorder has kept, as an immutable value a viewer can hold and read.

    ``tiers`` run from the finest (recent days) to the coarsest (years); every period of simulated
    time since the recorder started is in exactly one sample. ``period_seconds`` is the length of a
    period in simulated seconds.
    """

    period_seconds: float
    tiers: tuple[Tier, ...]
    format: int = HISTORY_FORMAT

    def samples(self) -> tuple[Sample, ...]:
        """Every sample, oldest first (the coarsest tier comes first)."""
        return tuple(s for tier in reversed(self.tiers) for s in tier.samples)

    def __len__(self) -> int:
        return sum(len(tier.samples) for tier in self.tiers)

    @property
    def latest(self) -> Sample | None:
        for tier in self.tiers:
            if tier.samples:
                return tier.samples[-1]
        return None

    def names(self) -> tuple[str, ...]:
        """The names of every value that appears in any sample, sorted."""
        found: set[str] = set()
        for sample in self.samples():
            found.update(sample.values)
        return tuple(sorted(found))

    def stat_names(self) -> tuple[str, ...]:
        found: set[str] = set()
        for sample in self.samples():
            found.update(sample.stats)
        return tuple(sorted(found))

    def series(self, name: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """``(days, values)`` for one value, oldest first, one point per sample that has it.

        ``days`` is the period at the end of each sample's stretch. Flows are per period (a week's
        births are divided by 7) so points from different tiers sit on one scale.
        """
        days: list[float] = []
        values: list[float] = []
        for sample in self.samples():
            value = sample.rate(name)
            if value is not None:
                days.append(float(sample.day))
                values.append(value)
        return tuple(days), tuple(values)

    def stat_series(self, name: str) -> tuple[tuple[float, ...], tuple[Stat, ...]]:
        """``(days, stats)`` for one trait or gene, oldest first."""
        days: list[float] = []
        stats: list[Stat] = []
        for sample in self.samples():
            stat = sample.stats.get(name)
            if stat is not None:
                days.append(float(sample.day))
                stats.append(stat)
        return tuple(days), tuple(stats)

    def histogram_at(self, name: str, day: float) -> tuple[int, ...] | None:
        """The gene histogram nearest to ``day`` (a period number), for scrubbing through time."""
        best: tuple[float, tuple[int, ...]] | None = None
        for sample in self.samples():
            bins = sample.histograms.get(name)
            if bins is None:
                continue
            gap = abs(sample.day - day)
            if best is None or gap < best[0]:
                best = (gap, bins)
        return None if best is None else best[1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "period_seconds": self.period_seconds,
            "tiers": [
                {
                    "name": tier.name,
                    "periods": tier.periods,
                    "samples": [s.to_dict() for s in tier.samples],
                }
                for tier in self.tiers
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HistorySamples:
        if data.get("format") not in READABLE_FORMATS:
            raise ValueError(f"Cannot read history format {data.get('format')!r}.")
        return cls(
            period_seconds=float(data["period_seconds"]),
            tiers=tuple(
                Tier(
                    str(t["name"]),
                    int(t["periods"]),
                    tuple(Sample.from_dict(s) for s in t["samples"]),
                )
                for t in data["tiers"]
            ),
        )
