"""The statistics recorder (``UX.8``): samples a running world once per simulated day.

``Recorder(world)`` listens to the world's events (births and deaths with their causes) and to the end
of every step; once a period of simulated time has passed (a day, by default) it takes a ``Sample``:
population levels from the world's read-only views, the births and deaths since the last sample, and a
``Stat`` for every trait and gene of the animals and the plants (plus a histogram per gene now and
then). Old samples are merged into coarser ones so memory stays bounded however long the run: a ring
buffer per tier (days, weeks, months, years), where what falls off the end of one tier is merged into
the next, and the last tier merges its two oldest samples when it is full.

It only reads. Nothing it does touches the world's state or random generator, so a run gives the same
``state_digest`` with or without a recorder, and a world with none pays nothing: the world builds
events and calls step listeners only while someone has asked. It is deterministic, has no dependencies
and can be saved and restored (``to_dict`` / ``Recorder.restore``), so a run store can put the history
beside a world's checkpoints and a resumed run goes on exactly as an uninterrupted one would.

Births counted are real births: organisms put in by hand (founders) have no parents and are left out.
"""

from __future__ import annotations

import gzip
import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from evolution_simulator.deaths import DeathCause
from evolution_simulator.history.samples import (
    HISTORY_FORMAT,
    HistorySamples,
    Sample,
    Stat,
    Tier,
)
from evolution_simulator.world.events import Born, Died, EventListener, WorldEvent
from evolution_simulator.world.timescale import TimeScale
from evolution_simulator.world.views import AnimalView, CorpseView, PlantView

DAY_SECONDS = 86400.0


@dataclass(frozen=True)
class TierRule:
    """One resolution: a full sample covers ``periods`` periods and the tier holds ``capacity``."""

    name: str
    periods: int
    capacity: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A tier needs a name.")
        if self.periods < 1 or self.capacity < 1:
            raise ValueError(f"Tier {self.name!r} needs periods and capacity of at least 1.")


DEFAULT_TIERS: tuple[TierRule, ...] = (
    TierRule("day", 1, 90),
    TierRule("week", 7, 52),
    TierRule("month", 30, 60),
    TierRule("year", 365, 128),
)
"""A quarter of daily points, a year of weekly, five years of monthly, then yearly (and after 128
years the oldest yearly samples start merging in pairs). At most 330 samples are ever held. A
coarser sample is built from the finer ones, so its length varies around the nominal one (a "month" is
four or five whole weeks; every sample says how many periods it covers in ``span``)."""


@dataclass(frozen=True)
class RecorderRules:
    period_seconds: float = DAY_SECONDS
    """Simulated seconds per sample: one day."""
    tiers: tuple[TierRule, ...] = DEFAULT_TIERS
    bins: int = 20
    """Bins of a gene histogram, over the gene's 0 to 1."""
    histogram_every: int = 30
    """A histogram of every gene goes in the first sample and every this-many-th after it."""

    def __post_init__(self) -> None:
        if not (math.isfinite(self.period_seconds) and self.period_seconds > 0.0):
            raise ValueError(f"period_seconds must be above zero, got {self.period_seconds}.")
        if not self.tiers or self.tiers[0].periods != 1:
            raise ValueError("The first tier must hold single periods.")
        for finer, coarser in zip(self.tiers, self.tiers[1:], strict=False):
            if coarser.periods <= finer.periods:
                raise ValueError("Each tier must cover more periods than the one before.")
        if self.tiers[-1].capacity < 2:
            raise ValueError("The last tier needs room for 2 samples, to merge the oldest.")
        if self.bins < 1 or self.histogram_every < 1:
            raise ValueError("bins and histogram_every must be at least 1.")

    @property
    def capacity(self) -> int:
        """The most samples the recorder ever holds."""
        return sum(tier.capacity for tier in self.tiers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_seconds": self.period_seconds,
            "tiers": [[t.name, t.periods, t.capacity] for t in self.tiers],
            "bins": self.bins,
            "histogram_every": self.histogram_every,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RecorderRules:
        return cls(
            period_seconds=float(data["period_seconds"]),
            tiers=tuple(TierRule(str(n), int(p), int(c)) for n, p, c in data["tiers"]),
            bins=int(data["bins"]),
            histogram_every=int(data["histogram_every"]),
        )


class Observable(Protocol):
    """What the recorder reads. ``World`` has all of it; ``add_step_listener`` and ``trait_columns``
    are optional (without the first, call ``Recorder.observe`` after each step yourself; without the
    second, no trait or gene statistics are kept)."""

    @property
    def tick(self) -> int: ...

    @property
    def simulated_seconds(self) -> float: ...

    @property
    def time_scale(self) -> TimeScale: ...

    def animal_views(self) -> list[AnimalView]: ...

    def plant_views(self) -> list[PlantView]: ...

    def corpse_views(self) -> list[CorpseView]: ...

    def add_event_listener(self, listener: EventListener) -> None: ...

    def remove_event_listener(self, listener: EventListener) -> None: ...


KINDS = ("animal", "plant")
CAUSES = tuple(cause.value for cause in DeathCause)


class Recorder:
    def __init__(
        self, source: Observable, rules: RecorderRules | None = None, attach: bool = True
    ) -> None:
        self.rules = rules if rules is not None else RecorderRules()
        self._source = source
        self._tiers: list[list[Sample]] = [[] for _ in self.rules.tiers]
        self._last_period = self._period_now()
        """The period the last sample ended at (or the period the recorder started in)."""
        self._taken = 0
        self._births = dict.fromkeys(KINDS, 0)
        self._deaths = {f"{kind}.{cause}": 0 for kind in KINDS for cause in CAUSES}
        self._ages: dict[str, list[float]] = {kind: [] for kind in KINDS}
        """Ages (in periods) of those who died since the last sample."""
        self._attached = False
        if attach:
            self.attach()

    # ---- listening ---------------------------------------------------------

    def attach(self) -> None:
        """Start listening to the source. Done by the constructor unless told not to."""
        if self._attached:
            return
        self._source.add_event_listener(self._on_event)
        adder = getattr(self._source, "add_step_listener", None)
        if adder is not None:
            adder(self._on_step)
        self._attached = True

    def close(self) -> None:
        """Stop listening (the history stays readable)."""
        if not self._attached:
            return
        self._source.remove_event_listener(self._on_event)
        remover = getattr(self._source, "remove_step_listener", None)
        if remover is not None:
            remover(self._on_step)
        self._attached = False

    def _on_event(self, event: WorldEvent) -> None:
        if isinstance(event, Born):
            if event.parents:
                self._births[event.kind] += 1
        elif isinstance(event, Died):
            self._deaths[f"{event.kind}.{event.cause.value}"] += 1
            seconds = self._source.time_scale.seconds_per_tick
            self._ages[event.kind].append(event.age_ticks * seconds / self.rules.period_seconds)

    def _on_step(self, report: object) -> None:
        self.observe()

    # ---- sampling ----------------------------------------------------------

    def _period_now(self) -> int:
        return int(self._source.simulated_seconds // self.rules.period_seconds)

    def observe(self) -> bool:
        """Take a sample if a period has passed since the last one. Returns whether it did. The
        step listener calls this after every step; call it yourself for a source without one."""
        now = self._period_now()
        if now <= self._last_period:
            return False
        sample = self._take(now, now - self._last_period)
        self._last_period = now
        self._taken += 1
        self._push(0, sample)
        return True

    def _take(self, period: int, span: int) -> Sample:
        source = self._source
        animals = source.animal_views()
        plants = source.plant_views()
        corpses = source.corpse_views()
        values: dict[str, float] = {
            "animals": float(len(animals)),
            "plants": float(len(plants)),
            "corpses": float(len(corpses)),
            "corpses.meat": math.fsum(c.meat for c in corpses),
        }
        if animals:
            n = len(animals)
            values["animal.energy"] = math.fsum(a.energy_ratio for a in animals) / n
            values["animal.health"] = math.fsum(a.health_ratio for a in animals) / n
            values["animal.age"] = math.fsum(a.age_ratio for a in animals) / n
            values["animal.diet"] = math.fsum(a.diet for a in animals) / n
            values["animal.asleep"] = sum(a.asleep for a in animals) / n
            values["animal.pregnant"] = sum(a.pregnant for a in animals) / n
            values["animal.ready"] = sum(a.ready_to_mate for a in animals) / n
        if plants:
            values["plant.biomass"] = math.fsum(p.biomass_ratio for p in plants) / len(plants)
        for kind in KINDS:
            values[f"births.{kind}"] = float(self._births[kind])
            values[f"deaths.{kind}"] = float(
                sum(self._deaths[f"{kind}.{cause}"] for cause in CAUSES)
            )
            for cause in CAUSES:
                values[f"deaths.{kind}.{cause}"] = float(self._deaths[f"{kind}.{cause}"])

        stats: dict[str, Stat] = {}
        for kind in KINDS:
            died = Stat.of(self._ages[kind])
            if died is not None:
                stats[f"{kind}.age_at_death"] = died
        histograms: dict[str, tuple[int, ...]] = {}
        columns_of = getattr(source, "trait_columns", None)
        if columns_of is not None:
            with_histograms = self._taken % self.rules.histogram_every == 0
            for kind in KINDS:
                for column, numbers in columns_of(kind).items():
                    stat = Stat.of(numbers)
                    if stat is None:
                        continue
                    stats[f"{kind}.{column}"] = stat
                    if with_histograms and column.startswith("gene."):
                        histograms[f"{kind}.{column}"] = self._histogram(numbers)

        self._births = dict.fromkeys(KINDS, 0)
        self._deaths = dict.fromkeys(self._deaths, 0)
        self._ages = {kind: [] for kind in KINDS}
        return Sample(
            day=period,
            span=span,
            tick=source.tick,
            values=dict(sorted(values.items())),
            stats=dict(sorted(stats.items())),
            histograms=dict(sorted(histograms.items())),
        )

    def _histogram(self, numbers: list[float] | tuple[float, ...]) -> tuple[int, ...]:
        bins = self.rules.bins
        counts = [0] * bins
        for value in numbers:
            counts[min(bins - 1, max(0, int(value * bins)))] += 1
        return tuple(counts)

    # ---- the ring buffers --------------------------------------------------

    def _push(self, level: int, sample: Sample) -> None:
        """Add a sample to a tier, merging it into the newest one when they belong to the same
        stretch of that tier, and pass the oldest on when the tier is over its capacity."""
        tier = self._tiers[level]
        rule = self.rules.tiers[level]
        if tier and _bucket(tier[-1], rule) == _bucket(sample, rule):
            tier[-1] = tier[-1].merge(sample)
        else:
            tier.append(sample)
        while len(tier) > rule.capacity:
            oldest = tier.pop(0)
            if level + 1 < len(self._tiers):
                self._push(level + 1, oldest)
            else:
                tier[0] = oldest.merge(tier[0])

    # ---- reading and saving ------------------------------------------------

    @property
    def sample_count(self) -> int:
        """Samples held now (never more than ``rules.capacity``)."""
        return sum(len(tier) for tier in self._tiers)

    def history(self) -> HistorySamples:
        """What has been recorded, as an immutable value."""
        return HistorySamples(
            self.rules.period_seconds,
            tuple(
                Tier(rule.name, rule.periods, tuple(samples))
                for rule, samples in zip(self.rules.tiers, self._tiers, strict=True)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Everything needed to go on recording after a restart: the history and the counters since
        the last sample."""
        return {
            "format": HISTORY_FORMAT,
            "kind": "recorder",
            "rules": self.rules.to_dict(),
            "last_period": self._last_period,
            "taken": self._taken,
            "births": dict(self._births),
            "deaths": dict(self._deaths),
            "ages": {kind: list(ages) for kind, ages in self._ages.items()},
            "tiers": [[s.to_dict() for s in tier] for tier in self._tiers],
        }

    @classmethod
    def restore(cls, source: Observable, data: Mapping[str, Any], attach: bool = True) -> Recorder:
        """A recorder that carries on from ``to_dict`` output, listening to ``source`` (normally the
        world restored from the save made at the same moment)."""
        if data.get("format") != HISTORY_FORMAT or data.get("kind") != "recorder":
            raise ValueError("This is not a saved statistics recorder of a format I can read.")
        recorder = cls(source, RecorderRules.from_dict(data["rules"]), attach=False)
        recorder._last_period = int(data["last_period"])
        recorder._taken = int(data["taken"])
        recorder._births = {kind: int(data["births"][kind]) for kind in KINDS}
        recorder._deaths = {key: int(data["deaths"][key]) for key in recorder._deaths}
        recorder._ages = {kind: [float(a) for a in data["ages"][kind]] for kind in KINDS}
        if len(data["tiers"]) != len(recorder._tiers):
            raise ValueError("The saved tiers do not match the saved rules.")
        recorder._tiers = [[Sample.from_dict(s) for s in tier] for tier in data["tiers"]]
        if attach:
            recorder.attach()
        return recorder


def _bucket(sample: Sample, rule: TierRule) -> int:
    """Which stretch of this tier a sample falls in, by the period it ends at."""
    return (sample.day - 1) // rule.periods


def save_history(history: HistorySamples | Recorder, path: str | os.PathLike[str]) -> Path:
    """Write a history, or a recorder's whole state, as JSON (gzip when the name ends in ``.gz``),
    written beside the target and moved into place."""
    data = history.to_dict()
    target = Path(path)
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if target.suffix == ".gz":
        payload = gzip.compress(payload, compresslevel=6, mtime=0)
    scratch = target.with_name(target.name + ".part")
    scratch.write_bytes(payload)
    os.replace(scratch, target)
    return target


def load_history_data(path: str | os.PathLike[str]) -> dict[str, Any]:
    """The dict a ``save_history`` file holds; give it to ``HistorySamples.from_dict`` (a plain
    history) or ``Recorder.restore`` (a recorder's state)."""
    source = Path(path)
    raw = source.read_bytes()
    if source.suffix == ".gz":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{source.name} is not a saved history.")  # noqa: TRY004
    return data
