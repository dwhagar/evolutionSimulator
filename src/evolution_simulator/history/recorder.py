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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from evolution_simulator.deaths import DeathCause
from evolution_simulator.history.samples import (
    HISTORY_FORMAT,
    READABLE_FORMATS,
    HistorySamples,
    Sample,
    Stat,
    Tier,
)
from evolution_simulator.species import SpeciesTracker
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
    track_species: bool = True
    """Keep a ``SpeciesTracker`` beside the recorder (when the source has animals and plants to read)
    and add its series to every sample (``SPECIES.2``)."""

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
            "track_species": self.track_species,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RecorderRules:
        return cls(
            period_seconds=float(data["period_seconds"]),
            tiers=tuple(TierRule(str(n), int(p), int(c)) for n, p, c in data["tiers"]),
            bins=int(data["bins"]),
            histogram_every=int(data["histogram_every"]),
            track_species=bool(data.get("track_species", True)),
        )


@dataclass(frozen=True, slots=True)
class TierChange:
    """One step of how a sample reached the ring buffers: a sample ``put`` into tier ``level`` or
    ``drop``ped from it (a merge is a drop of the sample merged into and a put of the result). A run
    store applies these to its rows, so the stored tiers stay equal to the recorder's."""

    kind: Literal["put", "drop"]
    level: int
    sample: Sample


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
        self,
        source: Observable,
        rules: RecorderRules | None = None,
        attach: bool = True,
        species: SpeciesTracker | None = None,
    ) -> None:
        self.rules = rules if rules is not None else RecorderRules()
        self._source = source
        self.species: SpeciesTracker | None = species
        """The species tracker whose series go in every sample, or ``None``. The recorder makes one
        when the rules ask and the source has animals and plants, and it drives it: the tracker
        is looked at just before each sample, so a resumed run takes the same samples as an
        uninterrupted one (a checkpoint's own ``observe`` does not sample it out of step). A tracker
        handed in stops listening to the source by itself."""
        if species is not None:
            species.close()
        elif self.rules.track_species and hasattr(source, "animals") and hasattr(source, "plants"):
            self.species = SpeciesTracker(source, attach=False)  # type: ignore[arg-type]
        self._tiers: list[list[Sample]] = [[] for _ in self.rules.tiers]
        self._last_period = self._period_now()
        """The period the last sample ended at (or the period the recorder started in)."""
        self._taken = 0
        self._births = dict.fromkeys(KINDS, 0)
        self._deaths = {f"{kind}.{cause}": 0 for kind in KINDS for cause in CAUSES}
        self._ages: dict[str, list[float]] = {kind: [] for kind in KINDS}
        """Ages (in periods) of those who died since the last sample."""
        self._roots: dict[str, dict[int, int]] = {kind: {} for kind in KINDS}
        """For each living organism born while recording: the founder its line of descent (through
        the mother, or the seeding plant) goes back to. A founder, and anyone born before recording
        began, is its own root and has no entry."""
        self._attached = False
        self._sample_listeners: list[Callable[[Sample], None]] = []
        self._tier_listeners: list[Callable[[Sequence[TierChange]], None]] = []
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

    def add_sample_listener(self, listener: Callable[[Sample], None]) -> None:
        """Call ``listener(sample)`` with each new single-period sample as it is taken, before it
        is merged into any coarser one (the process host sends these to the viewer, whose
        ``HistoryMirror`` merges them the same way)."""
        self._sample_listeners.append(listener)

    def remove_sample_listener(self, listener: Callable[[Sample], None]) -> None:
        if listener in self._sample_listeners:
            self._sample_listeners.remove(listener)

    def add_tier_listener(self, listener: Callable[[Sequence[TierChange]], None]) -> None:
        """Call ``listener(changes)`` with the ``TierChange`` list each new sample made in the ring
        buffers, after it is made (a run store keeps its history rows by these)."""
        self._tier_listeners.append(listener)

    def remove_tier_listener(self, listener: Callable[[Sequence[TierChange]], None]) -> None:
        if listener in self._tier_listeners:
            self._tier_listeners.remove(listener)

    def _on_event(self, event: WorldEvent) -> None:
        if isinstance(event, Born):
            if event.parents:
                self._births[event.kind] += 1
                roots = self._roots[event.kind]
                line = event.parents[-1]
                roots[event.id] = roots.get(line, line)
        elif isinstance(event, Died):
            self._roots[event.kind].pop(event.id, None)
            self._deaths[f"{event.kind}.{event.cause.value}"] += 1
            seconds = self._source.time_scale.seconds_per_tick
            self._ages[event.kind].append(event.age_ticks * seconds / self.rules.period_seconds)

    def _on_step(self, report: object) -> None:
        if self.species is not None:
            self.species.observe()
        self.observe()

    # ---- sampling ----------------------------------------------------------

    def _period_now(self) -> int:
        return int(self._source.simulated_seconds // self.rules.period_seconds)

    def observe(self) -> bool:
        """Take a sample if a period has passed since the last one. Returns whether it did. The
        step listener calls this after every step; call it yourself for a source without one."""
        if self.species is not None and not self._attached:
            self.species.observe()  # a recorder that listens drives it from its step listener
        now = self._period_now()
        if now <= self._last_period:
            return False
        sample = self._take(now, now - self._last_period)
        self._last_period = now
        self._taken += 1
        changes: list[TierChange] | None = [] if self._tier_listeners else None
        self._push(0, sample, changes)
        for listener in tuple(self._sample_listeners):
            listener(sample)
        if changes:
            for tier_listener in tuple(self._tier_listeners):
                tier_listener(changes)
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
        if self.species is not None:
            values.update(self.species.series_values())
        values["lineages.animal"] = float(self._lineages("animal", animals))
        values["lineages.plant"] = float(self._lineages("plant", plants))
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

    def _lineages(self, kind: str, living: Sequence[Any]) -> int:
        """How many founders still have a line of descent alive among the ``living`` organisms."""
        roots = self._roots[kind]
        return len({roots.get(organism.id, organism.id) for organism in living})

    def _histogram(self, numbers: list[float] | tuple[float, ...]) -> tuple[int, ...]:
        bins = self.rules.bins
        counts = [0] * bins
        for value in numbers:
            counts[min(bins - 1, max(0, int(value * bins)))] += 1
        return tuple(counts)

    # ---- the ring buffers --------------------------------------------------

    def _push(self, level: int, sample: Sample, changes: list[TierChange] | None = None) -> None:
        push_sample(self._tiers, self.rules.tiers, level, sample, changes)

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
            "roots": {
                kind: sorted(map(list, roots.items())) for kind, roots in self._roots.items()
            },
            "tiers": [[s.to_dict() for s in tier] for tier in self._tiers],
            "species": None if self.species is None else self.species.to_dict(),
        }

    @classmethod
    def restore(
        cls,
        source: Observable,
        data: Mapping[str, Any],
        attach: bool = True,
        species: SpeciesTracker | None = None,
    ) -> Recorder:
        """A recorder that carries on from ``to_dict`` output, listening to ``source`` (normally the
        world restored from the save made at the same moment). The species tracker comes back from the
        state saved with the recorder (format 3); for older data, or to use another one, give the
        restored tracker as ``species``, else the recorder starts a new one."""
        if data.get("format") not in READABLE_FORMATS or data.get("kind") != "recorder":
            raise ValueError("This is not a saved statistics recorder of a format I can read.")
        saved = data.get("species")
        if species is None and saved is not None:
            species = SpeciesTracker.restore(source, saved, attach=False)  # type: ignore[arg-type]
        recorder = cls(
            source, RecorderRules.from_dict(data["rules"]), attach=False, species=species
        )
        recorder._last_period = int(data["last_period"])
        recorder._taken = int(data["taken"])
        recorder._births = {kind: int(data["births"][kind]) for kind in KINDS}
        recorder._deaths = {key: int(data["deaths"][key]) for key in recorder._deaths}
        recorder._ages = {kind: [float(a) for a in data["ages"][kind]] for kind in KINDS}
        # Format 1 kept no lineage roots: the living start as their own founders.
        saved_roots = data.get("roots", {})
        recorder._roots = {
            kind: {int(i): int(root) for i, root in saved_roots.get(kind, ())} for kind in KINDS
        }
        if len(data["tiers"]) != len(recorder._tiers):
            raise ValueError("The saved tiers do not match the saved rules.")
        recorder._tiers = [[Sample.from_dict(s) for s in tier] for tier in data["tiers"]]
        if attach:
            recorder.attach()
        return recorder


def push_sample(
    tiers: list[list[Sample]],
    rules: Sequence[TierRule],
    level: int,
    sample: Sample,
    changes: list[TierChange] | None = None,
) -> None:
    """Add a sample to a tier, merging it into the newest one when they belong to the same stretch
    of that tier, and pass the oldest on when the tier is over its capacity. The ring buffers of a
    ``Recorder`` and of a ``HistoryMirror`` are both kept by this. Given a list, it is filled with
    the ``TierChange`` steps taken, in order."""
    tier = tiers[level]
    rule = rules[level]
    if tier and _bucket(tier[-1], rule) == _bucket(sample, rule):
        if changes is not None:
            changes.append(TierChange("drop", level, tier[-1]))
        tier[-1] = tier[-1].merge(sample)
        if changes is not None:
            changes.append(TierChange("put", level, tier[-1]))
    else:
        tier.append(sample)
        if changes is not None:
            changes.append(TierChange("put", level, sample))
    while len(tier) > rule.capacity:
        oldest = tier.pop(0)
        if changes is not None:
            changes.append(TierChange("drop", level, oldest))
        if level + 1 < len(tiers):
            push_sample(tiers, rules, level + 1, oldest, changes)
        else:
            if changes is not None:
                changes.append(TierChange("drop", level, tier[0]))
            tier[0] = oldest.merge(tier[0])
            if changes is not None:
                changes.append(TierChange("put", level, tier[0]))


def _bucket(sample: Sample, rule: TierRule) -> int:
    """Which stretch of this tier a sample falls in, by the period it ends at."""
    return (sample.day - 1) // rule.periods


def dump_history(history: HistorySamples | Recorder, gzipped: bool = True) -> bytes:
    """A history, or a recorder's whole state, as the bytes ``save_history`` writes (JSON, gzipped
    unless told not to), for a store that keeps them somewhere other than a file."""
    payload = json.dumps(history.to_dict(), separators=(",", ":"), sort_keys=True).encode("utf-8")
    return gzip.compress(payload, compresslevel=1, mtime=0) if gzipped else payload


def load_history_bytes(
    raw: bytes, gzipped: bool = True, name: str = "the history"
) -> dict[str, Any]:
    """The dict ``dump_history`` bytes hold; give it to ``HistorySamples.from_dict`` or
    ``Recorder.restore``."""
    data = json.loads((gzip.decompress(raw) if gzipped else raw).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name} is not a saved history.")  # noqa: TRY004
    return data


def save_history(history: HistorySamples | Recorder, path: str | os.PathLike[str]) -> Path:
    """Write a history, or a recorder's whole state, as JSON (gzip when the name ends in ``.gz``),
    written beside the target and moved into place."""
    target = Path(path)
    payload = dump_history(history, gzipped=target.suffix == ".gz")
    scratch = target.with_name(target.name + ".part")
    scratch.write_bytes(payload)
    os.replace(scratch, target)
    return target


def load_history_data(path: str | os.PathLike[str]) -> dict[str, Any]:
    """The dict a ``save_history`` file holds; give it to ``HistorySamples.from_dict`` (a plain
    history) or ``Recorder.restore`` (a recorder's state)."""
    source = Path(path)
    return load_history_bytes(source.read_bytes(), source.suffix == ".gz", source.name)
