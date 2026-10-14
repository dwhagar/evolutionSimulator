"""The species tracker (``SPECIES.1``): who has drifted away from whom, as a tree of species.

``SpeciesTracker(world)`` listens to the end of every step and, every ``period_days`` simulated days,
takes a bounded sample of the living animals and, separately, of the plants. It groups the sampled
genomes and keeps a record of each group: a species. The record says when it was first and last seen,
how big it was at each sample, where its centre (the digit-wise most common genome) is and how far that
is from where the world started. Plain data, no window code, no numpy.

What counts as a species
------------------------
A genome's distance to another is the fraction of digits that differ (``DNA.distance``). A species is a
group whose centre is clearly farther from its neighbours' centres than its own members are from it:

- **Split.** Each sample every species is cut in two (two-means on the distance, from its two
  most distant members). The two halves are *separate* when the distance between their centres is over
  ``separation`` times the spread inside them (the mean distance of members to their centre, the larger
  of the two) and never under ``min_gap`` of the digits. When that holds for ``confirm`` samples in a
  row the species splits: the larger half keeps the id, the smaller becomes a new species whose
  ``parent`` is the old one, so the species form a tree. Neither half may be under ``min_members``
  genomes or ``min_share`` of the species.
- **Merge.** Two species whose centres stay closer than ``merge_ratio`` (half) of that same separation
  for ``confirm`` samples are one again: the smaller is marked ``merged_into`` the larger. The gap
  between "split" and "merge" is the hysteresis that stops a borderline pair flickering.
- **Fade.** A species missing from the sample is gone at once when the sample was the whole
  population, and after ``confirm`` misses when the population was larger than the sample.

Genomes are assigned to the species with the nearest centre, and each centre moves to the consensus of
its members every sample, so a line that drifts keeps its id and its divergence grows. The founding
consensus is the consensus of the first sample of each kind.

The tracker only reads. It draws nothing from the world's random generator and changes nothing, so a
run gives the same ``state_digest`` with or without one. Its own state is bounded (the sample, a
decimated series per species, and at most ``extinct_kept`` extinct species) and can be saved and
restored (``to_dict`` / ``SpeciesTracker.restore``; ``save_species`` and ``load_species_data`` write the
file a run keeps beside its history, format ``SPECIES_FORMAT``).

Cost: a genome is turned into one big integer so that the distance of two genomes is a few C-speed
operations (an XOR and a popcount), whatever the genome's length. See ``docs/design/species.md``.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

SPECIES_FORMAT = 1
"""The layout of the saved tracker. Bump it when the layout changes and add the step that turns
version ``n`` into ``n + 1`` to ``_MIGRATIONS``, so an old file still loads."""

KINDS = ("animal", "plant")
DAY_SECONDS = 86400.0
RANKINGS = ("divergence", "relative", "size")
"""How ``ranking`` orders species: by distance from the founding consensus (the default of issue
207), by distance from the largest species of the kind, or by size."""

_MASK64 = (1 << 64) - 1


@dataclass(frozen=True)
class SpeciesRules:
    """The tracker's settings. The defaults are the clear-gap option (A) of issue 206 and the
    top five most divergent of issue 207, both confirmed by the owner."""

    period_days: float = 7.0
    """Simulated days between samples."""
    sample_size: int = 300
    """Most genomes taken of each kind each time."""
    separation: float = 2.0
    """Two groups are separate when the gap between their centres is over this many times the spread
    inside them."""
    min_gap: float = 0.04
    """... and never less than this fraction of the digits."""
    confirm: int = 3
    """Samples in a row a split, a merge or a miss has to hold."""
    merge_ratio: float = 0.5
    """Two species merge when their gap stays under this share of the separation they would need."""
    min_members: int = 5
    """Fewest genomes in a group that splits off."""
    min_share: float = 0.05
    """... and it must be at least this share of the species being split."""
    two_means_rounds: int = 4
    top_count: int = 5
    """How many lines per kind ``top`` gives (the lines a chart draws)."""
    history_points: int = 520
    """Samples kept in a species' own series (10 years of weekly ones); past that the older half is
    thinned to every second point."""
    extinct_kept: int = 200
    """Extinct species kept (the oldest are dropped first)."""
    seed: int = 0
    """Salt of the choice of which genomes make a sample."""

    def __post_init__(self) -> None:
        for name in ("period_days", "separation", "min_gap", "merge_ratio", "min_share"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value > 0.0):
                raise ValueError(f"{name} must be above zero, got {value}.")
        if self.min_gap >= 1.0 or self.min_share >= 0.5:
            raise ValueError("min_gap must be under 1 and min_share under 0.5.")
        if self.merge_ratio >= 1.0:
            raise ValueError("merge_ratio must be under 1, or a species would merge as it splits.")
        if self.sample_size < 2 * self.min_members:
            raise ValueError("sample_size must be at least twice min_members.")
        for name in ("confirm", "min_members", "two_means_rounds", "extinct_kept", "top_count"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1.")
        if self.history_points < 4:
            raise ValueError("history_points must be at least 4.")

    @property
    def period_seconds(self) -> float:
        return self.period_days * DAY_SECONDS

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SpeciesRules:
        defaults = cls()
        values = {
            name: type(getattr(defaults, name))(data[name])
            for name in cls.__dataclass_fields__
            if name in data
        }
        return cls(**values)


# --- genomes as integers -----------------------------------------------------------


def digits_of(genome: Any) -> str:
    """A genome's digits: a ``DNA`` as it is, a ``DiploidDNA`` as its two strands one after the
    other (so the distance counts both)."""
    strands = getattr(genome, "strands", None)
    if strands is None:
        return str(genome)
    return "".join(str(strand) for strand in strands)


class _Genome:
    """One sampled genome: its id, digits and the digits read as a base-4 integer."""

    __slots__ = ("digits", "id", "value")

    def __init__(self, organism_id: int, digits: str) -> None:
        self.id = organism_id
        self.digits = digits
        self.value = int(digits, 4)


class _Space:
    """The distance between genomes of one length: ``(x | x >> 1) & 0101...`` marks each differing
    digit of ``a ^ b`` and ``bit_count`` counts them."""

    __slots__ = ("length", "mask")

    def __init__(self, length: int) -> None:
        self.length = length
        self.mask = (4**length - 1) // 3

    def distance(self, a: int, b: int) -> float:
        x = a ^ b
        return ((x | (x >> 1)) & self.mask).bit_count() / self.length


def consensus(digit_strings: Sequence[str]) -> str:
    """The digit-wise most common genome of equally long strings (a tie goes to the lower digit)."""
    if not digit_strings:
        raise ValueError("There is no genome to take a consensus of.")
    if len(digit_strings) == 1:
        return digit_strings[0]
    out: list[str] = []
    for column in zip(*digit_strings, strict=True):
        text = "".join(column)
        out.append(max("0123", key=text.count))
    return "".join(out)


def _mix(value: int) -> int:
    """splitmix64: a fixed scramble, so which genomes are sampled never depends on the Python build."""
    value = (value + 0x9E3779B97F4A7C15) & _MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
    return value ^ (value >> 31)


def choose_sample(ids: Sequence[int], size: int, salt: int) -> list[int]:
    """Indexes (into ``ids``) of at most ``size`` of them, chosen by a hash of id and ``salt``, in
    index order. The same ids and salt give the same choice."""
    if len(ids) <= size:
        return list(range(len(ids)))
    keyed = sorted(range(len(ids)), key=lambda i: _mix(ids[i] * 0x10001 + salt))
    return sorted(keyed[:size])


# --- the records -------------------------------------------------------------------


@dataclass(frozen=True)
class SpeciesPoint:
    """One sample of one species."""

    day: float
    size: int
    """Estimated living members: those in the sample scaled up to the whole population."""
    divergence: float
    """Distance of its centre from the founding consensus, as a fraction of the digits."""


@dataclass(frozen=True)
class SpeciesInfo:
    """A species as the world last saw it (an immutable copy for readers)."""

    id: int
    kind: str
    parent: int | None
    first_day: float
    last_day: float
    """The day of the last sample it was in."""
    size: int
    peak: int
    divergence: float
    """From the founding consensus of its kind."""
    relative_divergence: float
    """From the centre of the largest living species of its kind (0 for that one)."""
    spread: float
    centre: str
    alive: bool
    extinct_day: float | None
    merged_into: int | None
    points: tuple[SpeciesPoint, ...]


@dataclass
class _Species:
    id: int
    kind: str
    parent: int | None
    first_day: float
    last_day: float
    centre: str
    size: int = 0
    peak: int = 0
    divergence: float = 0.0
    relative: float = 0.0
    spread: float = 0.0
    split_streak: int = 0
    missed: int = 0
    extinct_day: float | None = None
    merged_into: int | None = None
    points: list[tuple[float, int, float]] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.extinct_day is None

    def info(self) -> SpeciesInfo:
        return SpeciesInfo(
            id=self.id,
            kind=self.kind,
            parent=self.parent,
            first_day=self.first_day,
            last_day=self.last_day,
            size=self.size,
            peak=self.peak,
            divergence=self.divergence,
            relative_divergence=self.relative,
            spread=self.spread,
            centre=self.centre,
            alive=self.alive,
            extinct_day=self.extinct_day,
            merged_into=self.merged_into,
            points=tuple(SpeciesPoint(*p) for p in self.points),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "parent": self.parent,
            "first_day": self.first_day,
            "last_day": self.last_day,
            "centre": self.centre,
            "size": self.size,
            "peak": self.peak,
            "divergence": self.divergence,
            "relative": self.relative,
            "spread": self.spread,
            "split_streak": self.split_streak,
            "missed": self.missed,
            "extinct_day": self.extinct_day,
            "merged_into": self.merged_into,
            "points": [list(p) for p in self.points],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> _Species:
        return cls(
            id=int(data["id"]),
            kind=str(data["kind"]),
            parent=None if data["parent"] is None else int(data["parent"]),
            first_day=float(data["first_day"]),
            last_day=float(data["last_day"]),
            centre=str(data["centre"]),
            size=int(data["size"]),
            peak=int(data["peak"]),
            divergence=float(data["divergence"]),
            relative=float(data["relative"]),
            spread=float(data["spread"]),
            split_streak=int(data["split_streak"]),
            missed=int(data["missed"]),
            extinct_day=None if data["extinct_day"] is None else float(data["extinct_day"]),
            merged_into=None if data["merged_into"] is None else int(data["merged_into"]),
            points=[(float(d), int(s), float(v)) for d, s, v in data["points"]],
        )


class Observable(Protocol):
    """What the tracker reads. ``World`` has all of it; ``add_step_listener`` is optional (without
    it, call ``SpeciesTracker.observe`` after each step yourself)."""

    @property
    def tick(self) -> int: ...

    @property
    def simulated_seconds(self) -> float: ...

    @property
    def animals(self) -> list[Any]: ...

    @property
    def plants(self) -> list[Any]: ...


# --- the tracker -------------------------------------------------------------------


class SpeciesTracker:
    def __init__(
        self, source: Observable, rules: SpeciesRules | None = None, attach: bool = True
    ) -> None:
        self.rules = rules if rules is not None else SpeciesRules()
        self._source = source
        self._species: dict[int, _Species] = {}
        self._founders: dict[str, str] = {}
        self._merge_streaks: dict[tuple[int, int], int] = {}
        self._next_id = 1
        self._next_due: float | None = None
        self._taken = 0
        self.last_day: float | None = None
        """The day of the latest sample (``None`` before the first)."""
        self.last_seconds: float = 0.0
        """Real time the latest sample took, for measuring; not part of the saved state."""
        self._attached = False
        self._sample_listeners: list[Callable[[SpeciesTracker], None]] = []
        if attach:
            self.attach()

    # ---- listening

    def attach(self) -> None:
        if self._attached:
            return
        adder = getattr(self._source, "add_step_listener", None)
        if adder is not None:
            adder(self._on_step)
        self._attached = True

    def close(self) -> None:
        """Stop listening (what was tracked stays readable)."""
        if not self._attached:
            return
        remover = getattr(self._source, "remove_step_listener", None)
        if remover is not None:
            remover(self._on_step)
        self._attached = False

    def add_sample_listener(self, listener: Callable[[SpeciesTracker], None]) -> None:
        """Call ``listener(tracker)`` after each sample (the recorder of ``SPECIES.2`` uses it)."""
        self._sample_listeners.append(listener)

    def remove_sample_listener(self, listener: Callable[[SpeciesTracker], None]) -> None:
        if listener in self._sample_listeners:
            self._sample_listeners.remove(listener)

    def _on_step(self, report: object) -> None:
        self.observe()

    # ---- sampling

    @property
    def samples_taken(self) -> int:
        return self._taken

    def observe(self) -> bool:
        """Take a sample if one is due (the first as soon as there is something to sample). Returns
        whether it did. The step listener calls this after every step."""
        now = self._source.simulated_seconds
        if self._next_due is not None and now < self._next_due:
            return False
        animals = [(a.id, a.traits.dna) for a in self._source.animals]
        plants = [(p.id, p.traits.dna) for p in self._source.plants]
        if not animals and not plants and not self._species:
            return False  # nothing yet: try again after the next step
        self.observe_genomes(now / DAY_SECONDS, animals, plants)
        return True

    def observe_genomes(
        self,
        day: float,
        animals: Sequence[tuple[int, Any]],
        plants: Sequence[tuple[int, Any]] = (),
    ) -> None:
        """Take a sample from genomes handed in as ``(organism id, genome)``, a genome being its
        digits or a ``DNA``. Only the sampled genomes are turned into digits. ``observe`` does this
        with the source's; tests and other sources can call it directly."""
        started = time.perf_counter()
        salt = self.rules.seed * 1_000_003 + self._taken
        for kind, organisms in (("animal", animals), ("plant", plants)):
            self._update_kind(kind, day, list(organisms), salt)
        self._prune_extinct()
        self._taken += 1
        self.last_day = day
        self._next_due = day * DAY_SECONDS + self.rules.period_seconds
        self.last_seconds = time.perf_counter() - started
        for listener in tuple(self._sample_listeners):
            listener(self)

    # ---- one kind, one sample

    def _live(self, kind: str) -> list[_Species]:
        return sorted(
            (s for s in self._species.values() if s.kind == kind and s.alive), key=lambda s: s.id
        )

    def _new_id(self) -> int:
        found = self._next_id
        self._next_id += 1
        return found

    def _update_kind(
        self, kind: str, day: float, organisms: list[tuple[int, Any]], salt: int
    ) -> None:
        rules = self.rules
        total = len(organisms)
        live = self._live(kind)
        if total == 0:
            for species in live:
                self._miss(species, day, exhaustive=True)
            return
        chosen = choose_sample([i for i, _ in organisms], rules.sample_size, salt)
        texts = [(organisms[k][0], digits_of(organisms[k][1])) for k in chosen]
        lengths: dict[int, int] = {}
        for _, digits in texts:
            lengths[len(digits)] = lengths.get(len(digits), 0) + 1
        length = max(lengths, key=lambda n: (lengths[n], n))  # the usual length wins
        genomes = [_Genome(i, d) for i, d in texts if len(d) == length]
        scale = total / len(genomes)
        exhaustive = total <= rules.sample_size
        space = _Space(length)

        text = consensus([g.digits for g in genomes])
        if kind in self._founders and len(self._founders[kind]) != length:
            # A genome of another length (a new layout): start the kind over.
            for species in live:
                self._end(species, day, None)
            del self._founders[kind]
            live = []
        self._founders.setdefault(kind, text)
        if not live:
            first = _Species(self._new_id(), kind, None, day, day, text)
            self._species[first.id] = first
            live = [first]

        centres = {s.id: int(s.centre, 4) for s in live}
        members: dict[int, list[_Genome]] = {s.id: [] for s in live}
        for genome in genomes:
            best = min(live, key=lambda s: (space.distance(genome.value, centres[s.id]), s.id))
            members[best.id].append(genome)

        # Centres move to the consensus of their members; the rest read from there.
        for species in live:
            group = members[species.id]
            if not group:
                self._miss(species, day, exhaustive)
                continue
            species.missed = 0
            species.centre = consensus([g.digits for g in group])
            species.last_day = day
            centre = int(species.centre, 4)
            species.spread = math.fsum(space.distance(g.value, centre) for g in group) / len(group)
            species.size = max(1, round(len(group) * scale))
            species.peak = max(species.peak, species.size)

        alive = [s for s in live if s.alive]
        fresh: set[int] = set()
        for species in alive:
            made = self._maybe_split(species, members[species.id], space, day, scale)
            if made is not None:
                fresh.add(made.id)
        alive = self._live(kind)
        self._maybe_merge(alive, space, day, fresh)
        alive = self._live(kind)
        self._measure(kind, alive, space, day)

    def _miss(self, species: _Species, day: float, exhaustive: bool) -> None:
        species.missed += 1
        species.size = 0
        if exhaustive or species.missed >= self.rules.confirm:
            self._end(species, day, None)

    def _end(self, species: _Species, day: float, merged_into: int | None) -> None:
        species.extinct_day = day
        species.merged_into = merged_into
        species.size = 0
        species.split_streak = 0
        for pair in [p for p in self._merge_streaks if species.id in p]:
            del self._merge_streaks[pair]

    # ---- splitting

    def _two_means(
        self, group: list[_Genome], space: _Space
    ) -> tuple[list[_Genome], list[_Genome], str, str]:
        rules = self.rules
        first = group[0]
        a = max(group, key=lambda g: (space.distance(g.value, first.value), -g.id))
        b = max(group, key=lambda g: (space.distance(g.value, a.value), -g.id))
        centre_a, centre_b = a.value, b.value
        left: list[_Genome] = []
        right: list[_Genome] = []
        text_a, text_b = a.digits, b.digits
        for _ in range(rules.two_means_rounds):
            left, right = [], []
            for g in group:
                if space.distance(g.value, centre_a) <= space.distance(g.value, centre_b):
                    left.append(g)
                else:
                    right.append(g)
            if not left or not right:
                break
            text_a = consensus([g.digits for g in left])
            text_b = consensus([g.digits for g in right])
            new_a, new_b = int(text_a, 4), int(text_b, 4)
            if (new_a, new_b) == (centre_a, centre_b):
                break
            centre_a, centre_b = new_a, new_b
        return left, right, text_a, text_b

    def required_gap(self, spread: float) -> float:
        """The gap two groups with this spread need between their centres to count as separate."""
        rules = self.rules
        return max(rules.separation * spread, rules.min_gap)

    def _maybe_split(
        self,
        species: _Species,
        group: list[_Genome],
        space: _Space,
        day: float,
        scale: float,
    ) -> _Species | None:
        rules = self.rules
        smallest = max(rules.min_members, math.ceil(rules.min_share * len(group)))
        if len(group) < 2 * smallest:
            species.split_streak = 0
            return None
        left, right, text_a, text_b = self._two_means(group, space)
        if len(left) < smallest or len(right) < smallest:
            species.split_streak = 0
            return None
        centre_a, centre_b = int(text_a, 4), int(text_b, 4)
        spread = max(
            math.fsum(space.distance(g.value, centre_a) for g in left) / len(left),
            math.fsum(space.distance(g.value, centre_b) for g in right) / len(right),
        )
        gap = space.distance(centre_a, centre_b)
        if gap <= self.required_gap(spread):
            species.split_streak = 0
            return None
        species.split_streak += 1
        if species.split_streak < rules.confirm:
            return None
        # The larger half keeps the id (and the older record); the smaller is a new species.
        big, small = (left, right) if len(left) >= len(right) else (right, left)
        big_text, small_text = (text_a, text_b) if big is left else (text_b, text_a)
        species.centre = big_text
        species.size = max(1, round(len(big) * scale))
        species.spread = math.fsum(space.distance(g.value, int(big_text, 4)) for g in big) / len(
            big
        )
        species.split_streak = 0
        child = _Species(self._new_id(), species.kind, species.id, day, day, small_text)
        child.size = max(1, round(len(small) * scale))
        child.peak = child.size
        child.spread = math.fsum(space.distance(g.value, int(small_text, 4)) for g in small) / len(
            small
        )
        self._species[child.id] = child
        return child

    # ---- merging

    def _maybe_merge(
        self, alive: list[_Species], space: _Space, day: float, fresh: set[int]
    ) -> None:
        rules = self.rules
        seen: set[tuple[int, int]] = set()
        ordered = sorted(alive, key=lambda s: s.id)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                if a.id in fresh or b.id in fresh or not (a.alive and b.alive):
                    continue
                pair = (a.id, b.id)
                gap = space.distance(int(a.centre, 4), int(b.centre, 4))
                near = gap < rules.merge_ratio * self.required_gap(max(a.spread, b.spread))
                if not near:
                    self._merge_streaks.pop(pair, None)
                    continue
                seen.add(pair)
                streak = self._merge_streaks.get(pair, 0) + 1
                self._merge_streaks[pair] = streak
                if streak >= rules.confirm:
                    keep, gone = (a, b) if (a.size, -a.id) >= (b.size, -b.id) else (b, a)
                    keep.size += gone.size
                    keep.peak = max(keep.peak, keep.size)
                    self._end(gone, day, keep.id)
        for pair in [p for p in self._merge_streaks if p not in seen]:
            del self._merge_streaks[pair]

    # ---- the numbers each sample records

    def _measure(self, kind: str, alive: list[_Species], space: _Space, day: float) -> None:
        if not alive:
            return
        founder = int(self._founders[kind], 4)
        largest = max(alive, key=lambda s: (s.size, -s.id))
        largest_value = int(largest.centre, 4)
        for species in alive:
            value = int(species.centre, 4)
            species.divergence = space.distance(value, founder)
            species.relative = space.distance(value, largest_value)
            species.points.append((day, species.size, species.divergence))
            if len(species.points) > self.rules.history_points:
                species.points = _thin(species.points)

    def _prune_extinct(self) -> None:
        extinct = sorted(
            (s for s in self._species.values() if not s.alive),
            key=lambda s: (s.extinct_day or 0.0, s.id),
        )
        for species in extinct[: max(0, len(extinct) - self.rules.extinct_kept)]:
            del self._species[species.id]

    # ---- reading

    def species(self, kind: str | None = None, alive: bool | None = None) -> list[SpeciesInfo]:
        """Species by id, optionally only one kind and only the living (``True``) or extinct
        (``False``) ones."""
        found = [
            s.info()
            for s in sorted(self._species.values(), key=lambda s: s.id)
            if (kind is None or s.kind == kind) and (alive is None or s.alive == alive)
        ]
        return found

    def get(self, species_id: int) -> SpeciesInfo | None:
        species = self._species.get(species_id)
        return None if species is None else species.info()

    def founder(self, kind: str) -> str | None:
        """The founding consensus genome of a kind, as digits."""
        return self._founders.get(kind)

    def ranking(
        self, kind: str, by: str = "divergence", count: int | None = None
    ) -> list[SpeciesInfo]:
        """The living species of a kind, first the one furthest from the founding consensus
        (``"divergence"``), furthest from the largest species (``"relative"``) or biggest
        (``"size"``); ties by id."""
        if by not in RANKINGS:
            raise ValueError(f"Rank by one of {RANKINGS}, got {by!r}.")
        key = {
            "divergence": lambda s: (-s.divergence, s.id),
            "relative": lambda s: (-s.relative_divergence, s.id),
            "size": lambda s: (-s.size, s.id),
        }[by]
        found = sorted(self.species(kind, alive=True), key=key)
        return found if count is None else found[:count]

    def top(self, kind: str, by: str = "divergence") -> list[SpeciesInfo]:
        """The first ``top_count`` of ``ranking``: by default the five living species furthest from
        the founding genome."""
        return self.ranking(kind, by, self.rules.top_count)

    # ---- saving

    def to_dict(self) -> dict[str, Any]:
        """Everything needed to go on tracking after a restart."""
        return {
            "format": SPECIES_FORMAT,
            "kind": "species",
            "rules": self.rules.to_dict(),
            "next_id": self._next_id,
            "next_due": self._next_due,
            "taken": self._taken,
            "last_day": self.last_day,
            "founders": dict(self._founders),
            "merge_streaks": [[a, b, n] for (a, b), n in sorted(self._merge_streaks.items())],
            "species": [s.to_dict() for s in sorted(self._species.values(), key=lambda s: s.id)],
        }

    @classmethod
    def restore(
        cls, source: Observable, data: Mapping[str, Any], attach: bool = True
    ) -> SpeciesTracker:
        """A tracker that carries on from ``to_dict`` output (an older format is migrated first)."""
        document = migrate(dict(data))
        tracker = cls(source, SpeciesRules.from_dict(document["rules"]), attach=False)
        tracker._next_id = int(document["next_id"])
        tracker._next_due = None if document["next_due"] is None else float(document["next_due"])
        tracker._taken = int(document["taken"])
        tracker.last_day = None if document["last_day"] is None else float(document["last_day"])
        tracker._founders = {str(k): str(v) for k, v in document["founders"].items()}
        tracker._merge_streaks = {(int(a), int(b)): int(n) for a, b, n in document["merge_streaks"]}
        tracker._species = {
            s.id: s for s in (_Species.from_dict(entry) for entry in document["species"])
        }
        if attach:
            tracker.attach()
        return tracker


def _thin(points: list[tuple[float, int, float]]) -> list[tuple[float, int, float]]:
    """Keep every second point of the older half (the newest half stays whole)."""
    half = len(points) // 2
    return points[:half:2] + points[half:]


# --- the file ----------------------------------------------------------------------

_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}
"""``{n: f}``: ``f`` takes a document of format ``n`` and returns it as format ``n + 1``."""


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """A saved tracker brought up to ``SPECIES_FORMAT`` (``ValueError`` if it cannot be read)."""
    if data.get("kind") != "species":
        raise ValueError("This is not a saved species tracker.")
    version = data.get("format")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError(f"The saved species tracker has no usable format: {version!r}.")
    if version > SPECIES_FORMAT:
        raise ValueError(
            f"The saved species tracker is format {version}, newer than this program reads "
            f"({SPECIES_FORMAT})."
        )
    while version < SPECIES_FORMAT:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise ValueError(
                f"The saved species tracker is format {version} and cannot be upgraded."
            )
        data = step(data)
        version += 1
        data["format"] = version
    return data


def save_species(tracker: SpeciesTracker, path: str | os.PathLike[str]) -> Path:
    """Write the tracker's state as JSON (gzip when the name ends in ``.gz``), written beside the
    target and moved into place. The same state gives the same bytes."""
    target = Path(path)
    payload = json.dumps(tracker.to_dict(), separators=(",", ":"), sort_keys=True).encode("utf-8")
    if target.suffix == ".gz":
        payload = gzip.compress(payload, compresslevel=6, mtime=0)
    scratch = target.with_name(target.name + ".part")
    scratch.write_bytes(payload)
    os.replace(scratch, target)
    return target


def load_species_data(path: str | os.PathLike[str]) -> dict[str, Any]:
    """The dict a ``save_species`` file holds; give it to ``SpeciesTracker.restore``."""
    source = Path(path)
    raw = source.read_bytes()
    if source.suffix == ".gz":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{source.name} is not a saved species tracker.")  # noqa: TRY004
    return data
