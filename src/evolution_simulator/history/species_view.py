"""Species over time, read back from a history (``UX.41``): what to draw and how species rank.

The recorder writes, in every daily sample, the species tracker's series (``species.py``, named by
``series_name``): for each kind ``total`` and ``count``, the size of every species in the top five by
divergence or by size (``species.animal.12``) with its ``.divergence`` and ``.parent`` (-1 for none),
and what the rest add up to under each ranking (``rest_by_divergence``, ``rest_by_size``). This module
turns those into columns a chart can draw. No window code; a history recorded before species were
tracked simply gives ``None``.

A species has a size series only while it is in a top list, so a size missing from a sample is
nothing (the species was outside both lists, its members counted in the rest). A line starts at the
first sample that has the species.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from evolution_simulator.history.samples import HistorySamples
from evolution_simulator.species import SERIES_PREFIX, parse_series_name, series_name

RANKINGS: tuple[str, ...] = ("divergence", "size")
"""How species are ranked here: by distance from the founding genome (the owner's default, issue
207) or by size."""
TOP = 5
"""Species in a top list: the tracker's ``top_count`` default, confirmed by the owner."""
MAX_LINES = 10
"""The most species drawn at once, so a long run with many ups and downs stays readable."""


@dataclass(frozen=True)
class SpeciesView:
    """The species of one kind through a history, one entry per sample that has the kind's total."""

    kind: str
    days: tuple[float, ...]
    """The period at the end of each sample (a simulated day with the default recorder)."""
    total: tuple[float, ...]
    """Members of all living species."""
    count: tuple[float, ...]
    """How many living species there are."""
    rest: dict[str, tuple[float, ...]]
    """Members outside the top five of each ranking (``"divergence"`` and ``"size"``)."""
    sizes: dict[int, tuple[float | None, ...]]
    """Per species id, its size in each sample, ``None`` where it has no series."""
    divergence: dict[int, tuple[float | None, ...]]
    """Per species id, its distance from the founding genome (a fraction), ``None`` where unknown."""
    parents: dict[int, int | None]
    """Per species id, the species it split from, or ``None`` for a founder lineage."""

    def first_index(self, species_id: int) -> int:
        """The first sample that has this species."""
        sizes, divergences = self.sizes[species_id], self.divergence[species_id]
        return next(
            i for i in range(len(self.days)) if sizes[i] is not None or divergences[i] is not None
        )

    def alive_at_end(self, species_id: int) -> bool:
        """Whether the newest sample has the species with members."""
        column = self.sizes.get(species_id)
        return bool(column and column[-1])

    def last_divergence(self, species_id: int) -> float | None:
        column = self.divergence.get(species_id, ())
        return next((v for v in reversed(column) if v is not None), None)


def has_species(history: HistorySamples) -> bool:
    """Whether any sample of the history carries species series."""
    return any(name.startswith(SERIES_PREFIX) for name in history.names())


def species_view(history: HistorySamples, kind: str) -> SpeciesView | None:
    """The species of ``kind`` in ``history``, or ``None`` when it has no species series for it."""
    total_name = series_name(kind, field="total")
    parsed: dict[str, tuple[int | None, str | None] | None] = {}
    rows = []
    for sample in history.samples():
        values = sample.values
        if total_name not in values:
            continue
        sizes: dict[int, float] = {}
        divergences: dict[int, float] = {}
        parents: dict[int, float] = {}
        for name, value in values.items():
            if not name.startswith(SERIES_PREFIX):
                continue
            if name not in parsed:
                found = parse_series_name(name)
                parsed[name] = None if found is None or found[0] != kind else found[1:]
            entry = parsed[name]
            if entry is None or entry[0] is None:
                continue
            species_id, field = entry
            if field is None:
                sizes[species_id] = value
            elif field == "divergence":
                divergences[species_id] = value
            elif field == "parent":
                parents[species_id] = value
        rows.append((sample, sizes, divergences, parents))
    if not rows:
        return None

    def level(sample, field: str) -> float:
        return sample.values.get(series_name(kind, field=field), 0.0)

    ids = sorted({i for _, sizes, divs, _ in rows for i in (*sizes, *divs)})
    parent_of: dict[int, int | None] = {}
    for _, _, _, parents in rows:
        for species_id, value in parents.items():
            parent_of[species_id] = None if value < 0 else round(value)
    return SpeciesView(
        kind=kind,
        days=tuple(float(sample.day) for sample, *_ in rows),
        total=tuple(level(sample, "total") for sample, *_ in rows),
        count=tuple(level(sample, "count") for sample, *_ in rows),
        rest={by: tuple(level(sample, f"rest_by_{by}") for sample, *_ in rows) for by in RANKINGS},
        sizes={i: tuple(sizes.get(i) for _, sizes, _, _ in rows) for i in ids},
        divergence={i: tuple(divs.get(i) for _, _, divs, _ in rows) for i in ids},
        parents={i: parent_of.get(i) for i in ids},
    )


def top_at(view: SpeciesView, index: int, by: str, count: int = TOP) -> list[int]:
    """The species ranked first in one sample, the first in front (ties by the lower id, as the
    tracker orders them): the furthest from the founders, or the biggest."""
    if by not in RANKINGS:
        raise ValueError(f"Rank by one of {RANKINGS}, got {by!r}.")
    columns = view.divergence if by == "divergence" else view.sizes
    pool = [(value, i) for i, column in columns.items() if (value := column[index]) is not None]
    pool.sort(key=lambda pair: (-pair[0], pair[1]))
    return [i for _, i in pool[:count]]


def chosen_ids(view: SpeciesView, by: str, count: int = TOP, cap: int = MAX_LINES) -> list[int]:
    """The species to draw: the top ``count`` of the newest sample, first in front, then (up to
    ``cap`` in all) those that were in the top ``count`` of the most earlier samples."""
    current = top_at(view, len(view.days) - 1, by, count)
    tenure: Counter[int] = Counter()
    for index in range(len(view.days)):
        tenure.update(top_at(view, index, by, count))
    earlier = sorted((i for i in tenure if i not in current), key=lambda i: (-tenure[i], i))
    return current + earlier[: max(0, cap - len(current))]
