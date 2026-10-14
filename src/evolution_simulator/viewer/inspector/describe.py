"""What the inspector says about a creature, as plain data (UX.14).

Everything here takes an ``AnimalDetail`` (and a frame or the history where it needs one) and
returns text or small records, so it is tested without a window. ``panel.py`` and the ``tab_*``
modules only put the results on the screen.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from evolution_simulator.brain_adapter import BrainDecision
from evolution_simulator.catalogue import (
    GENES,
    Description,
    describe_gene,
    describe_trait,
)
from evolution_simulator.deaths import DeathCause
from evolution_simulator.dna import DNA, GenomeLayout
from evolution_simulator.history import HistorySamples
from evolution_simulator.layouts import ANIMAL_LAYOUT
from evolution_simulator.session import ANIMAL_FLAGS, Frame
from evolution_simulator.viewer.worldview.layers import Layer
from evolution_simulator.world.views import AnimalDetail

LEVEL_UNIT = "level 0 to 1"
DIGIT_UNIT_PREFIX = "digit"
DAY_SECONDS = 86400.0

STAGES: tuple[tuple[float, str], ...] = ((0.12, "young"), (0.75, "in its prime"), (1.01, "old"))
"""Where a creature is in its life, by the share of its lifespan it has used up: the upper bound of
each stage. Only a way of saying it; nothing in the simulation depends on it."""

DEATH_WORDS: dict[DeathCause, str] = {
    DeathCause.STARVATION: "starved",
    DeathCause.OLD_AGE: "died of old age",
    DeathCause.PREDATION: "was killed by another animal",
    DeathCause.POISON: "was poisoned by its food",
    DeathCause.EATEN: "was eaten",
    DeathCause.DAMAGE: "died of its injuries",
}

SENSE_TRAITS: tuple[str, ...] = (
    "sight_reach",
    "fov_half_degrees",
    "hearing_range",
    "smell_range",
    "tactile_factor",
    "call_radius",
)
"""The derived traits that are the senses' ranges, shown as their own group."""

CLUSTER_TITLES: dict[str, str] = {
    "frame": "Frame",
    "repair": "Repair",
    "sight": "Sight",
    "hearing": "Hearing and calls",
    "chemical": "Smell and taste",
    "diet": "Diet",
    "temperament": "Temperament",
    "reproduction": "Reproduction",
}
OTHER_TITLE = "Other genes"


# --- the body and its state -----------------------------------------------------------------


def sex_name(sex: int) -> str:
    """0 impregnates, 1 bears the young (``AnimalView.sex``)."""
    return "female" if sex == 1 else "male"


def life_stage(age_ratio: float) -> str:
    for bound, name in STAGES:
        if age_ratio < bound:
            return name
    return STAGES[-1][1]


def seconds_per_tick(frame: Frame | None) -> float | None:
    """The length of a tick, read from a frame (simulated time over ticks); ``None`` before the
    world has run at all."""
    if frame is None or frame.tick <= 0 or frame.simulated_seconds <= 0.0:
        return None
    return frame.simulated_seconds / frame.tick


def age_text(detail: AnimalDetail, tick_seconds: float | None) -> str:
    """ "3 days old, in its prime (41% of its life)" - or ticks while the tick length is unknown."""
    share = f"{detail.age_ratio * 100:.0f}% of its life"
    if tick_seconds is None:
        return f"{detail.age_ticks} ticks old, {life_stage(detail.age_ratio)} ({share})"
    days = detail.age_ticks * tick_seconds / DAY_SECONDS
    if days >= 365.0:
        age = f"{days / 365.0:.1f} years"
    elif days >= 1.0:
        age = "1 day" if round(days) == 1 else f"{days:.0f} days"
    else:
        age = f"{days * 24.0:.0f} hours"
    return f"{age} old, {life_stage(detail.age_ratio)} ({share})"


def diet_text(diet: float) -> str:
    """The meat share of what it can digest, in words."""
    if diet < 0.05:
        return "eats plants only"
    if diet < 0.35:
        return "mostly plants"
    if diet <= 0.65:
        return "plants and meat"
    if diet <= 0.95:
        return "mostly meat"
    return "eats meat only"


def state_words(detail: AnimalDetail) -> list[str]:
    """What it is doing in its body: asleep, carrying young, ready to mate, how often it mated."""
    if not detail.alive:
        return [f"dead: {death_text(detail.death_cause)}"]
    words = []
    if detail.asleep:
        words.append("asleep")
    if detail.pregnant:
        young = "1 young" if detail.litter == 1 else f"{detail.litter} young"
        words.append(f"carrying {young}")
    if detail.ready_to_mate:
        words.append("ready to mate")
    if not words:
        words.append("awake")
    return words


def death_text(cause: DeathCause | None) -> str:
    return "cause unknown" if cause is None else DEATH_WORDS.get(cause, str(cause))


def decision_words(detail: AnimalDetail) -> str:
    """ "turning left, fast, eating" for what it decided on its latest tick."""
    if not detail.alive:
        return "none (dead)"
    if detail.asleep:
        return "asleep"
    decision = detail.decision
    if decision is None:
        return "nothing decided yet"
    parts = [turn_word(decision.turn), speed_word(decision.speed), *action_words(decision)]
    if decision.wandering:
        parts.append("wandering (its brain could not decide)")
    return ", ".join(parts)


def turn_word(turn: float) -> str:
    if abs(turn) < 0.1:
        return "straight ahead"
    side = "left" if turn > 0 else "right"  # the world is y-up and headings turn counterclockwise
    return f"turning {side}" if abs(turn) < 0.6 else f"turning hard {side}"


def speed_word(speed: float) -> str:
    if speed < 0.1:
        return "standing still"
    if speed < 0.4:
        return "slowly"
    if speed < 0.7:
        return "at a walk"
    return "fast"


def action_words(decision: BrainDecision) -> list[str]:
    chosen = []
    if decision.eats_or_attacks:
        chosen.append("eating or attacking")
    if decision.seeks_mating:
        chosen.append("looking for a mate")
    if decision.calls_alarm:
        chosen.append("calling an alarm")
    if decision.calls_for_mate:
        chosen.append("calling for a mate")
    return chosen


# --- traits ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class TraitRow:
    id: str
    name: str
    text: str
    """The value with its unit."""
    meaning: str


@dataclass(frozen=True)
class TraitGroup:
    title: str
    rows: tuple[TraitRow, ...]


def number_text(value: float) -> str:
    """A number as a person reads it: few digits, no needless zeros."""
    if not math.isfinite(value):
        return str(value)
    if value != 0.0 and abs(value) < 0.01:
        return f"{value:.2g}"
    if abs(value) >= 1000.0:
        return f"{value:,.0f}"
    return f"{value:.3g}" if abs(value) < 100.0 else f"{value:.0f}"


def describe_trait_or_name(name: str) -> Description:
    """The catalogue entry, or a readable stand-in for a trait the catalogue does not know."""
    try:
        return describe_trait(name)
    except KeyError:
        return Description(name.replace("_", " ").capitalize(), "", "")


def value_text(value: float, unit: str) -> str:
    if unit.startswith(DIGIT_UNIT_PREFIX):
        return f"{round(value)}"
    if unit in ("", LEVEL_UNIT):
        return number_text(value)
    return f"{number_text(value)} {unit}"


def trait_groups(traits: Mapping[str, float]) -> list[TraitGroup]:
    """The traits in the simulation's units, in a group for the senses and a group for the rest.
    Traits that only restate a gene's level are left out: the Genes tab shows those."""
    senses: list[TraitRow] = []
    rest: list[TraitRow] = []
    for name, value in traits.items():
        info = describe_trait_or_name(name)
        if info.unit in (LEVEL_UNIT,) or info.unit.startswith(DIGIT_UNIT_PREFIX):
            continue
        row = TraitRow(name, info.name, value_text(value, info.unit), info.meaning)
        (senses if name in SENSE_TRAITS else rest).append(row)
    senses.sort(key=lambda r: SENSE_TRAITS.index(r.id))
    groups = []
    if senses:
        groups.append(TraitGroup("Senses", tuple(senses)))
    if rest:
        groups.append(TraitGroup("Traits", tuple(rest)))
    return groups


# --- genes ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneRow:
    id: str
    name: str
    meaning: str
    level: float
    """0 to 1, where the bar sits."""
    text: str
    digits: str
    population: float | None
    """The living population's mean for this gene, 0 to 1, when the history has one."""
    unusual: bool
    """Far from the population's mean (more than two standard deviations)."""


@dataclass(frozen=True)
class GeneGroup:
    cluster: str
    title: str
    rows: tuple[GeneRow, ...]


@dataclass(frozen=True)
class Genes:
    groups: tuple[GeneGroup, ...]
    brain_digits: str
    """The digits of the brain block (not drawn as bars: it is hundreds of numbers)."""


UNUSUAL_SIGMAS = 2.0


def population_genes(history: HistorySamples | None) -> dict[str, tuple[float, float]]:
    """The mean and standard deviation of each animal gene in the newest sample."""
    latest = None if history is None else history.latest
    if latest is None:
        return {}
    prefix = "animal.gene."
    return {
        name[len(prefix) :]: (stat.mean, stat.std)
        for name, stat in latest.stats.items()
        if name.startswith(prefix)
    }


def read_genes(
    genome: str,
    population: Mapping[str, tuple[float, float]] | None = None,
    layout: GenomeLayout = ANIMAL_LAYOUT,
) -> Genes | None:
    """The genome as named genes grouped by cluster, or ``None`` when the string is not a genome of
    this layout (a stand-in simulation has short ones)."""
    if len(genome) != layout.length:
        return None
    try:
        dna = DNA.from_string(layout, genome)
    except ValueError:
        return None
    population = population or {}
    order: list[str] = []
    rows: dict[str, list[GeneRow]] = {}
    brain = ""
    for gene in layout.genes:
        if gene.block is not None:
            brain = genome[gene.start : gene.end]
            continue
        if gene.id not in GENES:
            continue
        info = describe_gene(gene.id)
        level = dna.value(gene.id)
        digits = genome[gene.start : gene.end]
        if info.unit.startswith(DIGIT_UNIT_PREFIX):
            text = digits
        else:
            text = number_text(level)
        mean = population.get(gene.id)
        unusual = (
            mean is not None and mean[1] > 0.0 and abs(level - mean[0]) > UNUSUAL_SIGMAS * mean[1]
        )
        row = GeneRow(
            gene.id,
            info.name,
            info.meaning,
            level,
            text,
            digits,
            None if mean is None else mean[0],
            unusual,
        )
        cluster = gene.cluster or ""
        if cluster not in rows:
            order.append(cluster)
            rows[cluster] = []
        rows[cluster].append(row)
    others = rows.pop("", [])
    groups = [
        GeneGroup(name, CLUSTER_TITLES.get(name, name.capitalize()), tuple(rows[name]))
        for name in order
        if name
    ]
    if others:
        groups.append(GeneGroup("", OTHER_TITLE, tuple(others)))
    return Genes(tuple(groups), brain)


# --- family ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Relative:
    id: int
    sex: int
    age_ratio: float
    distance: float
    """In family-key units; smaller is closer."""


def animal_ids(frame: Frame | None) -> frozenset[int]:
    """The living animals of a frame, for deciding whether an id can be selected."""
    if frame is None:
        return frozenset()
    return frozenset(int(i) for i in Layer(frame.animals).ids)


def closest_relatives(frame: Frame | None, animal_id: int, limit: int = 8) -> list[Relative] | None:
    """The living animals whose family key is nearest this one's (``None`` if the frame has no key
    or does not hold the animal). Close keys mean close genomes: parents, children, siblings."""
    if frame is None:
        return None
    layer = Layer(frame.animals)
    if "family_a" not in layer.columns or "family_b" not in layer.columns:
        return None
    mine = [i for i, found in enumerate(layer.ids) if int(found) == animal_id]
    if not mine:
        return None
    a, b = layer.col("family_a"), layer.col("family_b")
    me = mine[0]
    distance = np.hypot(a - a[me], b - b[me])
    female = layer.flag(ANIMAL_FLAGS["female"])
    age = layer.col("age_ratio")
    order = [int(i) for i in np.argsort(distance, kind="stable") if int(i) != me][:limit]
    return [
        Relative(int(layer.ids[i]), 1 if female[i] else 0, float(age[i]), float(distance[i]))
        for i in order
    ]


def relative_text(relative: Relative) -> str:
    return f"#{relative.id}: {sex_name(relative.sex)}, {life_stage(relative.age_ratio)}"


def ids_text(ids: Sequence[int]) -> str:
    return ", ".join(f"#{i}" for i in ids) if ids else "none"
