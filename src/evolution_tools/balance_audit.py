"""The gene balance audit (``TRAIT.17``).

The owner's rule is that every gene needs two balancers: a link to another gene or trait that grows
as the gene rises, and a direct cost. ``docs/design/gene-balance.md`` (Proposal 1) turns that into
a standard: a gene is balanced when raising it to its maximum, or dropping it to its minimum, leaves
the organism worse off in at least one realistic world, and the reason is written down. This script
checks the standard. For each gene of each layout it

1. holds every other gene at the reference (founder) values,
2. steps the gene through a grid (nine points, 0 to 1; ``--fast`` uses three),
3. computes a fitness proxy in each reference environment, and
4. reports the best value in each environment, whether the proxy rises, falls, peaks or stays flat,
   and a verdict for the gene.

**Plants.** The proxy is the expected number of *established* seedlings over a lifetime: one real
``PlantTraits`` grows, pays its upkeep, is grazed and seeds as the real code does (growth, defence
upkeep, the seed budget, ``launch_seeds``), and each seed is then grown as a seedling, which counts
as established if it survives to half its full size, discounted by a background hazard per tick
(rot, trampling) for as long as that takes. The stand around the plant is a stand-in for the world:
its neighbours shade and take soil as ``PlantRules`` says, and the seedlings of a plant that
disperses far escape the crowding near their parent.

**Animals.** The proxy is lifetime offspring, counted at the birth and weighted by whether the
newborn lives off its parents' gift through its first hours (the chemostat's fast), for one real
``AnimalTraits`` that eats, ages, is hurt, mates with a fresh reference partner and gives birth
through the same ``AnimalTraits.feed``, ``mate`` and ``give_birth`` that ``evolution_tools.reproduction_check``
uses (its injury and newborn settings are imported, and its pressures for ``speed``, ``agility``,
``aggression`` and ``fear`` are kept). Unlike that chemostat food is not shared: each animal has an
income of its own, so one value of one gene can be compared with another at a fixed budget. The
habitats are rich and poor plants, poor plants with toxic ones, poor plants with prey, and poor
plants with a predator that finds an animal in proportion to how visible it is.

**What it cannot see.** The animal habitats have no space and no brain, so the senses and the
brain's own genes show their cost and none of their benefit. Those genes are recorded in
``RECORDED`` as blind, with the reason, and not as balanced: their benefit has to be audited in a
real world (a follow-up item). Every benefit that *is* modelled is a stand-in and a guess (see the
module constants); the audit shows where the costs bite, not where the genes will settle.

Verdicts, per gene:

- ``ok``: the proxy peaks inside the range in some environment, or is best at the top in one and not
  in another (a world-dependent gene);
- ``top``: best at the top in every environment where it matters (runs to the maximum, so the gene
  is free or has no cost that bites);
- ``bottom``: best at the bottom in every environment where it matters (sinks, so it has a cost and
  no benefit);
- ``dead``: the sweep changes nothing anywhere.

Run ``python -m evolution_tools.balance_audit [--fast] [--layout plant|animal] [--markdown FILE]``. It exits
1 if a gene fails without a recorded reason (``RECORDED``) or a recorded failure has been fixed.
The balancer table (``docs/design/gene-balancers.md``) is read and checked at the same time.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from evolution_simulator.config import DEFAULT_RULES, SensingRules, TraitRules
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import (
    ANIMAL_LAYOUT,
    FOUNDER_CAMOUFLAGE,
    FOUNDER_LEVELS,
    FOUNDER_PLANT_LONGEVITY,
    PLANT_LAYOUT,
)
from evolution_simulator.trait_defs import ANIMAL_TRAITS, PLANT_TRAITS
from evolution_simulator.traits import AnimalTraits, MatingResult, PlantTraits
from evolution_tools.reproduction_check import Ecology  # settings shared with the chemostat

ROOT = Path(__file__).resolve().parents[2]

GRID_FULL: tuple[float, ...] = tuple(i / 8 for i in range(9))
GRID_FAST: tuple[float, ...] = (0.0, 0.5, 1.0)
FLAT = 0.01
"""A sweep whose proxy varies by less than this share of its largest value is flat."""
TIE = 0.05
"""A value within this share of the spread of the best counts as best (a tie)."""

BALANCERS_PATH = ROOT / "docs" / "design" / "gene-balancers.md"
SRC = ROOT / "src" / "evolution_simulator"


# --------------------------------------------------------------------------------------------------
# Reference genomes
# --------------------------------------------------------------------------------------------------


def reference_animal(**genes: float) -> DNA:
    """The animal every sweep starts from: the middle (0.5) of every gene, the reproduction genes at
    ``FOUNDER_LEVELS``, no camouflage and sex 0 (the brain is left as drawn, since nothing here has
    a brain). Named genes are set to the given 0 to 1 value."""
    dna = DNA.random(ANIMAL_LAYOUT, random.Random(0))
    for gene in ANIMAL_LAYOUT.genes:
        if gene.block is None:
            dna = dna.with_value(gene.id, 0.5)
    for gene_id, level in FOUNDER_LEVELS.items():
        dna = dna.with_value(gene_id, level)
    dna = dna.with_value("camouflage", FOUNDER_CAMOUFLAGE).with_value("sex_strategy", 0.0)
    for gene_id, value in genes.items():
        dna = dna.with_value(gene_id, value)
    return dna


REFERENCE_PLANT_GROWTH = 0.65
"""A little above the middle: at 0.5 the reference plant sits on the edge of paying its upkeep as a
seedling (``upkeep_share`` 0.31 against the founders' 0.3), so any crowding at all would kill it
and a sweep would show a cliff instead of a slope."""


def reference_plant(**genes: float) -> DNA:
    """The plant every sweep starts from: the middle of every gene, the founder lifespan and a little
    more growth (``REFERENCE_PLANT_GROWTH``)."""
    dna = DNA(PLANT_LAYOUT, "0" * PLANT_LAYOUT.length)
    for gene in PLANT_LAYOUT.genes:
        dna = dna.with_value(gene.id, 0.5)
    dna = dna.with_value("longevity", FOUNDER_PLANT_LONGEVITY)
    dna = dna.with_value("growth_rate", REFERENCE_PLANT_GROWTH)
    for gene_id, value in genes.items():
        dna = dna.with_value(gene_id, value)
    return dna


# --------------------------------------------------------------------------------------------------
# Fitness: the growth rate of a lineage
# --------------------------------------------------------------------------------------------------

R_FLOOR = -0.5
"""Growth rate per day reported for a lineage that leaves nothing (and the floor of the solver)."""
R_CEILING = 2.0


def growth_rate(births: Iterable[tuple[float, float]], founders: float = 1.0) -> float:
    """The intrinsic growth rate per day ``r`` of a lineage whose ``founders`` individuals left the
    given ``(tick, weight)`` offspring (weight 1 is one established young): the ``r`` that solves
    ``sum(weight * exp(-r * day)) = founders`` (the Euler-Lotka equation, with ``founders`` the
    cohort size). It prices *when* the young come, not only how many, which the lifetime total
    (``R0``) does not: a gene that delays the first seed for a longer life, or a longer life of
    small litters, is not credited for the extra seeds it never needs. A lineage that leaves
    nothing gets ``R_FLOOR``."""
    days = [(tick / 24.0, weight) for tick, weight in births if weight > 0.0]
    if not days:
        return R_FLOOR

    def surplus(rate: float) -> float:
        return sum(weight * math.exp(-rate * day) for day, weight in days) - founders

    low, high = R_FLOOR, R_CEILING
    if surplus(low) <= 0.0:
        return R_FLOOR
    if surplus(high) >= 0.0:
        return R_CEILING
    for _ in range(60):
        middle = 0.5 * (low + high)
        if surplus(middle) > 0.0:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


# --------------------------------------------------------------------------------------------------
# Plants
# --------------------------------------------------------------------------------------------------

PLANT_HORIZON_DAYS = 400
"""A plant is followed for its lifespan, at most this many days (the gene runs to 365)."""
SEEDLING_WINDOW_TICKS = 24 * 90
"""A seedling that is not half grown in this many ticks has not established."""
BITE_TICKS = 2.0
"""A grazer's visit lasts this many ticks of ``WorldRules.graze_amount``."""
SEED_COMPETITION = 0.3
"""Each other seed of the same burst lowers a seedling's chance by this share, less so the farther
the seeds are scattered (``1 / (1 + 0.3 * (n - 1) * (1 - escape))``): the seeds that fall together
share the soil and the light. Without it a bigger clutch is always better, which only the stand
limits in the world. A guess."""
ESCAPE_DISTANCE = 25.0
"""Seeds dispersed this far are, on average, out of the crowding near their parent (the soil
neighbourhood of ``PlantRules``)."""


@dataclass(frozen=True)
class Neighbour:
    """A plant of the stand around the one being audited: how heavy and wide it is, and how far."""

    biomass: float
    canopy: float
    distance: float


@dataclass(frozen=True)
class Stand:
    """A reference environment for plants. The numbers are stand-ins chosen to put each pressure
    on and to leave the reference plant just able to hold its own, not measurements; ``PlantRules``
    says how the soil and the shade are worked out."""

    name: str
    soil: float = 1.0
    """Share of the soil access left by the neighbours' roots (1 is a lone plant)."""
    neighbours: tuple[Neighbour, ...] = ()
    """Heavier plants shade a smaller one; once it outgrows them they stop."""
    visits_per_day: float = 0.0
    """How often a grazer comes by."""
    avoids_toxin: bool = True
    """Whether the grazers stay away from a toxic plant in proportion to its toxicity; one adapted
    to the toxin (``False``) takes no notice."""
    hazard: float = 0.002
    """Chance per tick that a seedling is lost to rot, trampling or a passing grazer."""
    adult_hazard: float = 0.0005
    """Chance per tick that a grown plant is lost to storm, rot or disease (1.2% a day), which is what
    keeps a long life from being worth more than it earns."""


STANDS: tuple[Stand, ...] = (
    Stand("sparse"),
    Stand("dense", soil=0.9, neighbours=(Neighbour(40.0, 7.0, 5.0),)),
    Stand("grazed", visits_per_day=0.5, hazard=0.004),
    Stand("adapted grazer", visits_per_day=0.25, avoids_toxin=False, hazard=0.004),
)


def _conditions(plant: PlantTraits, stand: Stand, escape: float) -> tuple[float, float]:
    """The sunlight and soil factors for a plant in ``stand``; ``escape`` (0 to 1) is how far a
    seedling is from its parent's crowding, which takes the crowding away in that share."""
    load = sum(
        1.0 - n.distance / n.canopy
        for n in stand.neighbours
        if n.distance < n.canopy and n.biomass > plant.current_biomass
    )
    shade = 1.0 / (1.0 + plant.rules.plant_limits.shade_strength * load * (1.0 - escape))
    soil = 1.0 - (1.0 - stand.soil) * (1.0 - escape)
    return shade, soil


def _seedling_established(
    dna: DNA, start: float, stand: Stand, rules: TraitRules, escape: float
) -> float:
    """The chance that a seed with ``start`` biomass becomes an established plant: it must reach half
    its full size within ``SEEDLING_WINDOW_TICKS`` and survives each tick it takes with chance
    ``1 - hazard``."""
    seedling = PlantTraits(dna, rules)
    seedling.set_starting_biomass(start)
    for tick in range(SEEDLING_WINDOW_TICKS + 1):
        if seedling.current_biomass >= 0.5 * seedling.max_biomass:
            return (1.0 - stand.hazard) ** tick
        shade, soil = _conditions(seedling, stand, escape)
        seedling.set_environmental_conditions(shade, soil)
        seedling.update_growth_and_metabolism()
        if not seedling.is_alive:
            return 0.0
    return 0.0


def plant_births(
    dna: DNA, stand: Stand, rules: TraitRules = DEFAULT_RULES, days: int = PLANT_HORIZON_DAYS
) -> list[tuple[float, float]]:
    """The ``(tick, established seedlings)`` a plant of this genome leaves in ``stand``, each burst
    weighted by the chance that the plant is still alive to make it (``adult_hazard``).

    The plant grows, pays upkeep, is grazed and seeds through the real ``PlantTraits``. A burst
    pays for whole seeds with ``launch_seeds``; the part of a seed that the budget could also
    afford is counted as that share of one more, so a gene that raises the budget by a little moves
    the proxy by a little (the real code floors it)."""
    plant = PlantTraits(dna, rules)
    escape = 1.0 - math.exp(-plant.dispersal_radius / ESCAPE_DISTANCE)
    bite = BITE_TICKS * rules.world.graze_amount
    visit_chance = stand.visits_per_day / 24.0
    if stand.avoids_toxin:
        visit_chance *= 1.0 - plant.toxicity
    owed = 0.0
    births: list[tuple[float, float]] = []
    cache: dict[int, float] = {}
    for tick in range(min(days * 24, int(plant.lifespan_ticks) + 1)):
        shade, soil = _conditions(plant, stand, 0.0)
        plant.set_environmental_conditions(shade, soil)
        plant.update_growth_and_metabolism()
        if not plant.is_alive:
            break
        owed += visit_chance
        if owed >= 1.0:
            owed -= 1.0
            plant.graze(bite)
            if not plant.is_alive:
                break
        if not plant.flag_ready_to_seed:
            continue
        per_seed = plant.seed_provision * plant.max_biomass
        affordable = min(plant.seed_count, plant.seed_budget / per_seed)
        part = affordable - int(affordable)
        seeds = [PlantTraits(dna, rules) for _ in range(plant.seed_capacity())]
        plant.launch_seeds(seeds)
        weighted = [(seed, 1.0) for seed in seeds]
        if part > 0.0:
            share = PlantTraits(dna, rules)
            share.set_starting_biomass(per_seed)
            weighted.append((share, part))
        total = 0.0
        for seed, weight in weighted:
            key = round(seed.current_biomass * 10)
            if key not in cache:
                cache[key] = _seedling_established(dna, seed.current_biomass, stand, rules, escape)
            total += weight * cache[key]
        count = sum(weight for _, weight in weighted)
        crowding = 1.0 + SEED_COMPETITION * max(0.0, count - 1.0) * (1.0 - escape)
        births.append((float(tick), total / crowding * (1.0 - stand.adult_hazard) ** tick))
    return births


def plant_fitness(
    dna: DNA, stand: Stand, rules: TraitRules = DEFAULT_RULES, days: int = PLANT_HORIZON_DAYS
) -> float:
    """The growth rate per day of a lineage of this plant in ``stand`` (see ``growth_rate``)."""
    return growth_rate(plant_births(dna, stand, rules, days))


# --------------------------------------------------------------------------------------------------
# Animals
# --------------------------------------------------------------------------------------------------

ANIMAL_HORIZON_TICKS = 5000
"""An animal is followed for its lifespan, at most this many ticks (about 210 days)."""
MEETING_CHANCE = 0.05
"""Chance per tick that a willing animal meets a reference partner of the other sex (the
chemostat's value)."""
FORAGE_WEIGHT = (0.5, 0.2, 0.3)
"""What ``speed``, ``agility`` and ``aggression`` buy: the food found each tick is
``1 + 0.5 speed + 0.2 agility + 0.3 aggression`` times the habitat's (``reproduction_check.py``'s
stand-in, divided by the reference animal's so it keeps the habitat's units). A guess."""
FEAR_INJURY = 0.5
"""``fear`` cuts the chance of being hurt by up to this share (the chemostat's stand-in)."""
FORAGE_SPEED_RATIO = 0.5
"""Share of top speed an animal moves at while it forages (the chemostat's)."""
ESCAPE_BASE, ESCAPE_SPEED, ESCAPE_AGILITY, ESCAPE_FEAR = 0.2, 0.4, 0.2, 0.2
"""Chance of getting away from a predator that has found it: a base plus what ``speed``,
``agility`` and ``fear`` add. A guess."""
SIBLING_COMPETITION = 0.15
"""Each extra young in a litter lowers the chance that each of them lives by this share
(``1 / (1 + 0.15 * (n - 1))``): siblings share the food and the nest. Without it the proxy has no
crowding at all and a bigger litter is always better, which only the real world's shared food limits
(the chemostat shares its food for this reason). A guess."""
PREDATOR_DAMAGE = 80.0
"""Health lost to a predator that does not miss (a body holds 100 to 300)."""


@dataclass(frozen=True)
class Habitat:
    """A reference environment for animals: the income of one animal per tick and what else is out
    there. Stand-ins, with no space and no other animals, tuned so that the reference animal just
    breeds (a gene that costs more than it earns then shows)."""

    name: str
    plant: float = 0.0
    """Plant biomass an animal of reference foraging skill can graze in a tick."""
    toxic_share: float = 0.0
    """Share of the bites that come from a toxic plant."""
    toxicity: float = 0.0
    meat: float = 0.0
    """Meat biomass it can take in a tick."""
    predator: float = 0.0
    """Chance per tick that a predator finds an animal as visible as the reference one."""


HABITATS: tuple[Habitat, ...] = (
    Habitat("rich plants", plant=4.0),
    Habitat("poor plants", plant=2.8),
    Habitat("toxic plants", plant=3.2, toxic_share=0.06, toxicity=0.5),
    Habitat("prey", plant=0.6, meat=3.0),
    Habitat("predator", plant=3.0, predator=0.006),
)


class _Partners:
    """The reference mates an animal meets. Building an animal builds its brain, so the male is
    built once and refilled for every mating, and a female is built afresh only after she has
    conceived (a mating that misses leaves her unchanged)."""

    def __init__(self, rules: TraitRules) -> None:
        self._rules = rules
        self._male = self._make(0)
        self._female = self._make(1)

    def _make(self, sex: int) -> AnimalTraits:
        partner = AnimalTraits(reference_animal(sex_strategy=sex / 3.0), rules=self._rules)
        self.refill(partner)
        return partner

    @staticmethod
    def refill(partner: AnimalTraits) -> AnimalTraits:
        partner.current_energy = partner.max_energy
        partner.mating_cooldown = 0.0
        partner.age_ticks = int(partner.lifespan_ticks)
        return partner

    def male(self) -> AnimalTraits:
        return self.refill(self._male)

    def female(self) -> AnimalTraits:
        return self.refill(self._female)

    def bear(self) -> None:
        """The current female is pregnant: the next one is a new animal."""
        self._female = self._make(1)


@dataclass
class Cohort:
    """What a group of animals of one genome did in a habitat."""

    births: list[tuple[float, float]] = field(default_factory=list)
    founders: int = 0

    @property
    def fitness(self) -> float:
        return growth_rate(self.births, float(self.founders))


class _Draw:
    """A random generator that has already drawn its number: ``inspect_food`` asks for one."""

    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


def live_animal(
    dna: DNA,
    habitat: Habitat,
    seed: int,
    rules: TraitRules = DEFAULT_RULES,
    ticks: int = ANIMAL_HORIZON_TICKS,
) -> list[tuple[float, float]]:
    """One animal's life in ``habitat``: the ``(tick, weight)`` of every birth it fathers or bears,
    weight 1 for a young that is born with enough energy to last its first hours without eating
    (less for one that is not), until it dies or ``ticks`` have passed.

    Chance comes from separate streams for hurts, meetings, food, predators and matings, and every
    stream but the last draws the same numbers each tick whatever happens, so two genomes given the
    same ``seed`` meet the same weather and differ only in what their genes do with it (common
    random numbers: a gene's effect is not buried in the luck of the draw)."""
    eco = Ecology()
    animal = AnimalTraits(dna, rules=rules)
    reference = _reference_animal(rules)
    skill = _forage_skill(animal) / _forage_skill(reference)
    visible = SENSING.visibility(
        animal.body_radius, FORAGE_SPEED_RATIO, animal.camouflage
    ) / SENSING.visibility(reference.body_radius, FORAGE_SPEED_RATIO, 0.0)
    fear, agility, speed = animal.phenotype["fear"], animal.phenotype["agility"], _quickness(animal)
    escape = min(
        1.0, ESCAPE_BASE + ESCAPE_SPEED * speed + ESCAPE_AGILITY * agility + ESCAPE_FEAR * fear
    )
    hurt = eco.injury_chance * (1.0 - FEAR_INJURY * fear)
    hurts, meetings, foods, predators, matings = (
        random.Random(f"{seed}/{name}") for name in ("hurt", "meet", "food", "predator", "mate")
    )
    births: list[tuple[float, float]] = []
    partners = _Partners(rules)
    litters: dict[int, tuple[object, list[AnimalTraits]]] = {}
    bearing: list[AnimalTraits] = []  # partners carrying this animal's young
    for tick in range(min(ticks, int(animal.lifespan_ticks))):
        injury, damage = hurts.random(), hurts.uniform(eco.injury_low, eco.injury_high)
        _eat(animal, habitat, skill, foods.random(), _Draw(foods.random()))
        if injury < hurt:
            animal.apply_damage(damage)
        found, got_away = predators.random(), predators.random()
        if found < habitat.predator * visible and got_away >= escape:
            animal.apply_damage(PREDATOR_DAMAGE)
        animal.update_metabolism_and_aging(FORAGE_SPEED_RATIO)
        if not animal.is_alive:
            break
        meets = meetings.random() < MEETING_CHANCE
        if meets and animal.wants_mate:
            if animal.sex == 1:
                AnimalTraits.mate(partners.male(), animal, matings)
            else:
                mother = partners.female()
                if AnimalTraits.mate(animal, mother, matings) is MatingResult.CONCEIVED:
                    bearing.append(mother)
                    partners.bear()
        for mother in (animal, *bearing):
            pregnancy = mother.pregnancy
            if pregnancy is None:
                continue
            if mother is not animal:
                pregnancy.remaining -= 1.0
            if not pregnancy.due:
                continue
            held = litters.get(id(pregnancy))
            if held is None or held[0] is not pregnancy:
                # A due birth that cannot be paid for waits, so build the litter only once.
                held = litters[id(pregnancy)] = (
                    pregnancy,
                    [AnimalTraits(genome, rules=rules) for genome in pregnancy.children],
                )
            litter = held[1]
            if pregnancy.father is not None and pregnancy.father is not animal:
                partners.refill(pregnancy.father)
            if AnimalTraits.give_birth(mother, litter):
                births.append(
                    (float(tick), sum(_newborn_weight(young, eco, len(litter)) for young in litter))
                )
        bearing = [m for m in bearing if m.pregnancy is not None]
    return births


_REFERENCES: dict[int, AnimalTraits] = {}


def _reference_animal(rules: TraitRules) -> AnimalTraits:
    if id(rules) not in _REFERENCES:
        _REFERENCES[id(rules)] = AnimalTraits(reference_animal(), rules=rules)
    return _REFERENCES[id(rules)]


def _quickness(animal: AnimalTraits) -> float:
    """The ``speed`` gene as the body delivers it: a hidden animal is slower (``camouflage``)."""
    slowing = animal.rules.body.camouflage_slowing * animal.camouflage
    return animal.phenotype["speed"] * (1.0 - slowing)


def _forage_skill(animal: AnimalTraits) -> float:
    t = animal.phenotype
    return (
        1.0
        + FORAGE_WEIGHT[0] * _quickness(animal)
        + FORAGE_WEIGHT[1] * t["agility"]
        + FORAGE_WEIGHT[2] * t["aggression"]
    )


def _eat(
    animal: AnimalTraits, habitat: Habitat, skill: float, toxic: float, noticed: _Draw
) -> None:
    """One tick of eating: a bite of plant (a toxic one now and then, which the animal refuses if its
    taste notices) and a bite of meat."""
    if habitat.plant > 0.0:
        if toxic < habitat.toxic_share:
            if not animal.inspect_food(habitat.toxicity, noticed):  # type: ignore[arg-type]
                animal.feed(habitat.plant * skill, False, habitat.toxicity)
        else:
            animal.feed(habitat.plant * skill, False)
    if habitat.meat > 0.0:
        animal.feed(habitat.meat * skill, True)


def _newborn_weight(young: AnimalTraits, eco: Ecology, litter: int) -> float:
    """1 for a newborn whose gift of energy lasts its first fasting hours, less for one that would
    starve first (the chemostat's newborn who cannot eat for ``newborn_fast_ticks``), and less for
    each sibling it shares a litter with (``SIBLING_COMPETITION``)."""
    need = young.basal_metabolism * eco.newborn_fast_ticks
    fed = min(1.0, young.current_energy / need) if need > 0.0 else 1.0
    return fed / (1.0 + SIBLING_COMPETITION * (litter - 1))


def animal_fitness(
    dna: DNA,
    habitat: Habitat,
    animals: int = 8,
    ticks: int = ANIMAL_HORIZON_TICKS,
    rules: TraitRules = DEFAULT_RULES,
    seed: int = 1,
) -> float:
    """The growth rate per day of a lineage founded by ``animals`` animals of this genome in
    ``habitat`` (see ``growth_rate``). Each animal lives apart, with its own income."""
    births: list[tuple[float, float]] = []
    for index in range(animals):
        births.extend(live_animal(dna, habitat, seed * 1000 + index, rules, ticks))
    return growth_rate(births, float(animals))


SENSING = SensingRules()


# --------------------------------------------------------------------------------------------------
# Shapes and verdicts
# --------------------------------------------------------------------------------------------------

FLAT_SPREAD = 0.002
"""A sweep whose growth rates (per day) differ by no more than this is flat: the noise floor of the
animal runs, about a tenth of the effect of a gene that matters."""
TIE_SPREAD = 0.001
"""A value within this of the best (growth rate per day) is a tie for best."""


@dataclass(frozen=True)
class Shape:
    """What one gene's sweep did in one environment."""

    kind: str
    """``flat``, ``rises``, ``falls``, ``peaks`` or ``dips`` (best at both ends)."""
    best: float
    """The grid value with the highest proxy (the lowest value among ties)."""
    at_top: bool
    """The top of the range is among the best."""
    at_bottom: bool


def shape_of(values: Sequence[float], grid: Sequence[float]) -> Shape:
    """Classify a sweep. Values within ``TIE_SPREAD`` of the best tie for best."""
    top, bottom = max(values), min(values)
    best = grid[values.index(top)]
    if top - bottom <= FLAT_SPREAD:
        return Shape("flat", best, False, False)
    winners = [i for i, value in enumerate(values) if value >= top - TIE_SPREAD]
    at_top, at_bottom = len(values) - 1 in winners, 0 in winners
    if at_top and at_bottom:
        kind = "dips"
    elif at_top:
        kind = "rises"
    elif at_bottom:
        kind = "falls"
    else:
        kind = "peaks"
    return Shape(kind, best, at_top, at_bottom)


def judge(shapes: Iterable[Shape], category: bool = False) -> str:
    """The verdict on a gene from its shapes in every environment: ``dead`` (flat everywhere),
    ``top`` (best at the top wherever it matters), ``bottom`` (best at the bottom wherever it
    matters) or ``ok``. A gene that is a category (the sex digit) has no top or bottom: it is ``ok``
    if its sweep changes anything."""
    live = [shape for shape in shapes if shape.kind != "flat"]
    if not live:
        return "dead"
    if category:
        return "ok"
    if all(shape.at_top for shape in live):
        return "top"
    if all(shape.at_bottom for shape in live):
        return "bottom"
    return "ok"


@dataclass(frozen=True)
class Recorded:
    """A gene that is allowed to fail the standard, and why."""

    verdicts: tuple[str, ...]
    reason: str
    task: str
    """The TODO item that is to fix it (or ``-`` when it is not a defect)."""
    fast: tuple[str, ...] = ()
    """More verdicts allowed in the fast sweep, whose three points and two environments can see less
    (a gene whose cost shows only in a habitat the fast sweep leaves out looks free there)."""


# --------------------------------------------------------------------------------------------------
# Dead traits: a trait row that nothing reads
# --------------------------------------------------------------------------------------------------

_DEFINITION = re.compile(r'^\s*self\.(\w+)(?:\s*:[^=]+)?\s*=\s*(?:\w+\()?t\["(\w+)"\]')


def _source_lines() -> list[str]:
    skip = {"trait_defs.py", "catalogue.py"}
    lines: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name not in skip and "viewer" not in path.parts:
            lines.extend(path.read_text().splitlines())
    return lines


def unread_traits(traits: object) -> list[str]:
    """The traits of a ``TraitSet`` that no code reads: not the trait tables, not the catalogue and
    not the viewer, but the world, the traits classes, the brain or the senses. ``TraitSet.unread_genes``
    only asks whether a trait row reads the gene; this asks whether anyone reads the trait, which is
    how ``root_reach`` (``PlantTraits.root_radius``, read nowhere) slipped through.

    A trait counts as read when its name (or the attribute that ``traits.py`` copies it to) is used
    outside the line that copies it."""
    lines = _source_lines()
    aliases: dict[str, set[str]] = {}
    for line in lines:
        match = _DEFINITION.match(line)
        if match:
            aliases.setdefault(match.group(2), set()).add(match.group(1))
    unread = []
    for definition in traits.defs:  # type: ignore[attr-defined]
        name = definition.name
        names = {name, *aliases.get(name, ())}
        attribute = re.compile(rf"\.(?:{'|'.join(map(re.escape, names))})\b")
        subscript = re.compile(rf'\["{re.escape(name)}"\]')
        used = False
        for line in lines:
            copy = _DEFINITION.match(line)
            if copy and copy.group(2) == name:
                continue  # the line that copies this trait onto the object is not a use
            if attribute.search(line) or subscript.search(line):
                used = True
                break
        if not used:
            unread.append(name)
    return unread


def dead_genes(traits: object, gene_ids: Iterable[str]) -> list[str]:
    """The genes all of whose traits are read by nothing (see ``unread_traits``)."""
    unread = set(unread_traits(traits))
    dead = []
    for gene_id in gene_ids:
        try:
            reading = traits.traits_reading(gene_id)  # type: ignore[attr-defined]
        except KeyError:
            continue
        if reading and all(trait.name in unread for trait in reading):
            dead.append(gene_id)
    return dead


# --------------------------------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------------------------------

WILD = Habitat("wild", plant=2.0, toxic_share=0.05, toxicity=0.5, meat=2.0, predator=0.004)
"""Everything at once, for the fast audit, which has room for two environments: it holds the
benefits of taste, carnivory and camouflage that the plain ``poor plants`` habitat does not."""
ANIMAL_ENVIRONMENTS: dict[str, Habitat] = {h.name: h for h in (*HABITATS, WILD)}
PLANT_ENVIRONMENTS: dict[str, Stand] = {s.name: s for s in STANDS}
FAST_ANIMAL_ENVIRONMENTS: tuple[str, ...] = ("poor plants", "wild")
FAST_ANIMALS, FAST_TICKS = 3, 2000
FULL_ANIMALS = 16
LAYOUT_NAMES = ("plant", "animal")


def sweepable_genes(layout: str) -> tuple[str, ...]:
    """The genes that are swept: every gene but a gene block (the brain)."""
    layout_ = PLANT_LAYOUT if layout == "plant" else ANIMAL_LAYOUT
    return tuple(gene.id for gene in layout_.genes if gene.block is None)


def environments(layout: str, fast: bool = False) -> tuple[str, ...]:
    if layout == "plant":
        return tuple(PLANT_ENVIRONMENTS)  # cheap enough to run in full whatever the mode
    return FAST_ANIMAL_ENVIRONMENTS if fast else tuple(h.name for h in HABITATS)


def sweep(
    layout: str,
    gene: str,
    environment: str,
    grid: Sequence[float],
    animals: int = FULL_ANIMALS,
    ticks: int = ANIMAL_HORIZON_TICKS,
) -> tuple[float, ...]:
    """The fitness proxy of ``gene`` at each ``grid`` value in one environment."""
    if layout == "plant":
        stand = PLANT_ENVIRONMENTS[environment]
        return tuple(plant_fitness(reference_plant(**{gene: v}), stand) for v in grid)
    habitat = ANIMAL_ENVIRONMENTS[environment]
    return tuple(
        animal_fitness(reference_animal(**{gene: v}), habitat, animals=animals, ticks=ticks)
        for v in grid
    )


def price(layout: str, gene: str) -> float:
    """The direct cost of the gene: how much more the body's upkeep is per tick with the gene at its
    top than at its bottom, as a share of the reference body's whole burn (upkeep plus foraging at
    half speed; for a plant, as a share of its upkeep). Negative if raising the gene saves energy; 0
    if it is free. Costs paid in another currency (time, risk, a share of the seed budget, a slower
    body, movement) are not in it."""

    def upkeep(value: float) -> float:
        if layout == "plant":
            return PlantTraits(reference_plant(**{gene: value})).basal_metabolism
        return AnimalTraits(reference_animal(**{gene: value})).basal_metabolism

    swing = upkeep(1.0) - upkeep(0.0)
    if layout == "plant":
        return swing / upkeep(0.5)
    reference = AnimalTraits(reference_animal())
    rules = reference.rules.body
    moving = FORAGE_SPEED_RATIO * reference.current_max_speed
    whole = reference.basal_metabolism + (moving / rules.speed_reference) ** 2 * (
        rules.kinetic_burn * reference.mass
    )
    return swing / whole


@dataclass
class GeneAudit:
    """The result for one gene."""

    layout: str
    gene: str
    grid: tuple[float, ...]
    series: dict[str, tuple[float, ...]]
    shapes: dict[str, Shape]
    verdict: str
    price: float
    dead_trait: bool
    """No code reads any trait the gene feeds (see ``unread_traits``)."""
    fast: bool = False
    """Whether this came from the fast sweep (animals: three points and two environments)."""

    @property
    def recorded(self) -> Recorded | None:
        return RECORDED.get((self.layout, self.gene))

    @property
    def status(self) -> str:
        """``ok``, ``recorded`` (fails, with a reason on record), ``FAIL`` (fails without one) or
        ``STALE`` (recorded, but it no longer fails that way)."""
        failing = self.verdict != "ok" or self.dead_trait
        verdict = "dead" if self.dead_trait else self.verdict
        record = self.recorded
        if record is None:
            return "FAIL" if failing else "ok"
        allowed = (*record.verdicts, *(record.fast if self.fast else ()))
        if failing and verdict in allowed:
            return "recorded"
        if self.fast and self.layout == "animal":
            # The fast animal sweep is too coarse to say that a recorded failure has been fixed.
            return "recorded" if failing else "ok"
        if not failing and not record.verdicts:
            return "ok"  # a record that only excuses the fast sweep
        return "STALE"


def _job(
    args: tuple[str, str, str, tuple[float, ...], int, int],
) -> tuple[str, str, tuple[float, ...]]:
    layout, gene, environment, grid, animals, ticks = args
    return gene, environment, sweep(layout, gene, environment, grid, animals, ticks)


def audit(
    layout: str,
    genes: Sequence[str] | None = None,
    fast: bool = False,
    workers: int = 1,
    progress: Callable[[str], None] | None = None,
) -> list[GeneAudit]:
    """Audit the genes of one layout (all of them unless ``genes`` names some)."""
    grid = GRID_FAST if fast else GRID_FULL
    animals, ticks = (FAST_ANIMALS, FAST_TICKS) if fast else (FULL_ANIMALS, ANIMAL_HORIZON_TICKS)
    names = tuple(genes) if genes is not None else sweepable_genes(layout)
    envs = environments(layout, fast)
    jobs = [(layout, gene, env, tuple(grid), animals, ticks) for gene in names for env in envs]
    if workers > 1:
        import multiprocessing

        with multiprocessing.get_context("fork").Pool(workers) as pool:
            done = list(pool.imap(_job, jobs))
    else:
        done = []
        for job in jobs:
            done.append(_job(job))
            if progress:
                progress(f"{job[0]} {job[1]} {job[2]}")
    results: dict[str, dict[str, tuple[float, ...]]] = {}
    for gene, env, values in done:
        results.setdefault(gene, {})[env] = values
    traits = PLANT_TRAITS if layout == "plant" else ANIMAL_TRAITS
    dead = set(dead_genes(traits, names))
    categories = {
        gene
        for gene in names
        if any(t.kind.value == "category" for t in traits.traits_reading(gene))
    }
    audits = []
    for gene in names:
        series = results[gene]
        shapes = {env: shape_of(list(values), list(grid)) for env, values in series.items()}
        audits.append(
            GeneAudit(
                layout,
                gene,
                tuple(grid),
                series,
                shapes,
                judge(shapes.values(), gene in categories),
                price(layout, gene),
                gene in dead,
                fast and layout == "animal",
            )
        )
    return audits


_BLIND = "Blind: the habitats have no space, no other animals to be seen or heard and no brain."
_BLIND_TASK = "-"
"""The senses and the brain genes need a world audit (animals in a real world); until then they are
recorded as blind, not as balanced."""

RECORDED: dict[tuple[str, str], Recorded] = {
    # Plants (the baseline of 2026-10-15; TRAIT.13 is the plant trade-offs item)
    ("plant", "max_biomass"): Recorded(
        ("bottom",),
        "A lone plant gains nothing from size here (no light race for the canopy, no seed or "
        "grazing benefit). Size needs its benefit side.",
        "TRAIT.13",
    ),
    ("plant", "growth_rate"): Recorded(
        ("top",),
        "Growth is free: no growth upkeep and no softer tissue yet.",
        "TRAIT.13",
    ),
    ("plant", "dispersal_radius"): Recorded(
        ("top",),
        "Scattering seeds is free: no travel cost from the seed provision yet.",
        "TRAIT.13",
    ),
    ("plant", "seed_clutch"): Recorded(
        ("top",),
        "Free below the seed budget cap and the cap stops it, so it sits at the top.",
        "TRAIT.13",
    ),
    ("plant", "root_reach"): Recorded(
        ("dead",),
        "The roots do nothing yet.",
        "TRAIT.13",
    ),
    ("plant", "seed_provision"): Recorded(
        ("bottom",),
        "More small seeds beat fewer big ones: a big reserve has no benefit yet (no germination "
        "delay, no hazard of a waiting seed).",
        "TRAIT.13",
    ),
    ("plant", "seeding_interval"): Recorded(
        ("bottom",),
        "Seeding early and often is free: toughness does not drop with it yet.",
        "TRAIT.13",
    ),
    # Animals
    ("animal", "agility"): Recorded(
        ("top",),
        "The stand-in escape benefit is generous and agility has no real cost beyond its small "
        "upkeep. Recheck when turning matters in a real world.",
        "REPRO.9",
    ),
    ("animal", "aggression"): Recorded(
        ("top",),
        "The stand-in competition benefit has no matching injury or lost mate yet.",
        "REPRO.9",
        fast=("dead", "bottom"),
    ),
    ("animal", "somatic_maint"): Recorded(
        ("bottom",),
        "Its benefit is a longer life, which r discounts: the late-life gain does not pay for the "
        "repair upkeep in a growth rate.",
        "REPRO.9",
    ),
    ("animal", "herbivore_eff"): Recorded(
        ("top",),
        "A better gut is only held back by its upkeep and the diet penalty. Plants have no "
        "fibre or toughness yet.",
        "TRAIT.14",
        fast=("dead",),
    ),
    ("animal", "fertility"): Recorded(
        ("top",),
        "The litter and the chance of a mating are cheap at the audit scale; newborns do not "
        "compete with each other in a real world. Recheck with the long-run check.",
        "REPRO.9",
        fast=("dead",),
    ),
    ("animal", "parenting"): Recorded(
        ("bottom",),
        "Any parenting above about 0.05 stops births in these habitats: the gift to the newborn "
        "costs more than the protection gains. Needs the juvenile body.",
        "REPRO.10",
    ),
    ("animal", "camouflage"): Recorded(
        ("top",),
        "Its benefit (fewer predators) is the stand-in and its cost placeholders, so it sits at "
        "the top wherever a predator is.",
        "REPRO.9",
        fast=("dead", "ok"),
    ),
    # The fast sweep sees too little to be sure of these: they are balanced in the full sweep.
    ("animal", "carnivore_eff"): Recorded((), "Balanced in the full sweep.", "-", fast=("bottom",)),
    ("animal", "fear"): Recorded((), "Balanced in the full sweep.", "-", fast=("top", "bottom")),
    # Blind genes: the habitats cannot see what these do.
    **{
        ("animal", gene): Recorded(("dead", "bottom"), _BLIND, _BLIND_TASK, fast=("top",))
        for gene in (
            "sight_range",
            "sight_fov",
            "sight_acuity",
            "hearing",
            "encoder_fidelity",
            "smell",
            "touch",
            "brain_gain",
            "reaction_time",
            "curiosity",
            "learning_rate",
        )
    },
}
"""Genes that fail the standard with a reason on record: the baseline of the first audit. The
audit fails a gene that fails without an entry here, and fails an entry that no longer fails (a
fix takes its entry out)."""


# --------------------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------------------

ARROWS = {"flat": "=", "rises": "up", "falls": "down", "peaks": "peak", "dips": "dip"}


def report(audits: Sequence[GeneAudit], title: str = "") -> str:
    """The audit as a markdown table: per gene the best value and shape in each environment, the
    verdict, the direct cost and the reason on record."""
    if not audits:
        return ""
    envs = list(audits[0].shapes)
    lines = [title] if title else []
    head = ["Gene", *envs, "Verdict", "Direct cost", "Note"]
    lines.append("| " + " | ".join(head) + " |")
    lines.append("| " + " | ".join(["---"] * len(head)) + " |")
    for audit_ in audits:
        cells = [f"`{audit_.gene}`"]
        for env in envs:
            shape = audit_.shapes[env]
            cells.append(
                f"{ARROWS[shape.kind]}"
                if shape.kind == "flat"
                else f"{shape.best:.2f} {ARROWS[shape.kind]}"
            )
        verdict = "dead" if audit_.dead_trait else audit_.verdict
        record = audit_.recorded
        note = ""
        if audit_.dead_trait:
            note = "no code reads its trait. "
        if record is not None:
            note += f"{record.reason} ({record.task})"
        status = audit_.status
        cells.append(verdict if status == "ok" else f"{verdict} ({status})")
        cells.append(f"{audit_.price * 100:+.1f}%" if abs(audit_.price) > 1e-9 else "free")
        cells.append(note.strip())
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def failures(audits: Iterable[GeneAudit]) -> list[GeneAudit]:
    """The audits that are not ``ok`` or ``recorded``: a gene that fails with no reason on record,
    or a recorded failure that no longer fails."""
    return [a for a in audits if a.status in ("FAIL", "STALE")]


# --------------------------------------------------------------------------------------------------
# The balancer table
# --------------------------------------------------------------------------------------------------

KINDS = ("link", "cost", "world")
STATUSES = ("built", "planned")
_ROW = re.compile(r"^\|\s*`(?P<gene>\w+)`\s*\|(?P<rest>.*)\|\s*$")


@dataclass(frozen=True)
class Balancer:
    """One entry of the balancer table: something that holds a gene in check."""

    layout: str
    gene: str
    kind: str
    """``link`` (another gene or trait that changes when this one rises), ``cost`` (a direct cost: upkeep,
    a share of a budget, a delay, a risk) or ``world`` (what the world pushes back with)."""
    what: str
    status: str
    """``built`` (the code does it) or ``planned`` (a TODO item will)."""
    task: str


def load_balancers(path: Path = BALANCERS_PATH) -> list[Balancer]:
    """Read the balancer table. The file has a ``## Plants`` and a ``## Animals`` section, each a
    table with the columns ``| Gene | Kind | Balancer | Status | Task |``."""
    layout = ""
    found: list[Balancer] = []
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            title = line[3:].strip().lower()
            layout = (
                "plant"
                if title.startswith("plant")
                else "animal"
                if title.startswith("animal")
                else ""
            )
            continue
        match = _ROW.match(line)
        if not match or not layout:
            continue
        cells = [cell.strip() for cell in match.group("rest").split("|")]
        if len(cells) != 4:
            raise ValueError(f"Balancer row for {match.group('gene')} needs 5 columns: {line}")
        kind, what, status, task = cells
        found.append(Balancer(layout, match.group("gene"), kind, what, status, task.strip("`")))
    return found


def balancer_problems(
    balancers: Sequence[Balancer], layouts: Iterable[str] = LAYOUT_NAMES
) -> list[str]:
    """What is wrong with the table: a gene with fewer than two entries (the owner's rule), an entry for
    a gene no layout has, a bad kind or status, or a planned entry that names no task."""
    problems: list[str] = []
    for layout in layouts:
        genes = set(sweepable_genes(layout)) | ({"brain"} if layout == "animal" else set())
        by_gene: dict[str, list[Balancer]] = {}
        for entry in balancers:
            if entry.layout == layout:
                by_gene.setdefault(entry.gene, []).append(entry)
        for gene in sorted(genes):
            if len(by_gene.get(gene, [])) < 2:
                problems.append(
                    f"{layout} gene {gene} has {len(by_gene.get(gene, []))} balancers; two are needed"
                )
        for gene in sorted(set(by_gene) - genes - PLANNED_GENES):
            problems.append(f"{layout} balancer table has an entry for {gene}, which is not a gene")
    for entry in balancers:
        if entry.kind not in KINDS:
            problems.append(f"{entry.gene}: kind {entry.kind!r} is not one of {KINDS}")
        if entry.status not in STATUSES:
            problems.append(f"{entry.gene}: status {entry.status!r} is not one of {STATUSES}")
        if entry.status == "planned" and not re.fullmatch(
            r"[A-Z]+\.\d+(, [A-Z]+\.\d+)*", entry.task
        ):
            problems.append(
                f"{entry.gene}: a planned balancer needs a task such as TRAIT.13, got {entry.task!r}"
            )
    return problems


PLANNED_GENES = {"toughness", "resistance"}
"""Genes the design has planned but no layout has yet; they may have rows in the table already."""


def built_balancers(balancers: Sequence[Balancer], layout: str, gene: str) -> int:
    return sum(
        1 for b in balancers if b.layout == layout and b.gene == gene and b.status == "built"
    )


# --------------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--fast", action="store_true", help="three points and two animal environments"
    )
    parser.add_argument("--layout", choices=(*LAYOUT_NAMES, "both"), default="both")
    parser.add_argument("--gene", action="append", help="audit only this gene (repeatable)")
    parser.add_argument("--workers", type=int, default=0, help="processes (default: all cores)")
    parser.add_argument("--markdown", type=Path, help="write the report here as well")
    parser.add_argument("--json", type=Path, help="write the raw sweeps here as well")
    args = parser.parse_args(argv)
    import json
    import os

    workers = args.workers or (os.cpu_count() or 1)
    layouts = LAYOUT_NAMES if args.layout == "both" else (args.layout,)
    problems = balancer_problems(load_balancers(), layouts)
    sections: list[str] = []
    raw: dict[str, dict[str, dict[str, list[float]]]] = {}
    bad: list[GeneAudit] = []
    for layout in layouts:
        results = audit(layout, args.gene, args.fast, workers)
        raw[layout] = {a.gene: {env: list(v) for env, v in a.series.items()} for a in results}
        mode = "fast" if args.fast else "full"
        sections.append(report(results, f"### {layout.capitalize()} genes ({mode} sweep)"))
        bad.extend(failures(results))
    text = "\n\n".join(sections)
    print(text)
    if args.markdown:
        args.markdown.write_text(text + "\n")
    if args.json:
        args.json.write_text(json.dumps(raw, indent=1) + "\n")
    for audit_ in bad:
        print(
            f"{audit_.status}: {audit_.layout} gene {audit_.gene} is {audit_.verdict}",
            file=sys.stderr,
        )
    for problem in problems:
        print(f"balancer table: {problem}", file=sys.stderr)
    return 1 if bad or problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
