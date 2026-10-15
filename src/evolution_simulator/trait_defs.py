"""Traits as data: what each trait reads from DNA and how it becomes a number.

A ``TraitDef`` says which gene IDs a trait depends on, the range it maps onto, whether that mapping
is linear or logarithmic, and a mutation step. A ``TraitSet`` is the table for one species. Expressing
a genome through a set gives the phenotype's primary values; DNA never sees trait names, and adding
a trait is one new row.

Several traits may read the same gene (pleiotropy: ``size`` already feeds ``mass``) and one trait
may read several genes (a cluster, ``DNA.15``). A cluster is read by its ``Combine`` rule: the
weighted mean of the genes (polygeny), or one main gene whose effect modifier genes strengthen or
weaken (epistasis). Each gene is read through dominance first, then the cluster combines them.
Derived quantities that combine traits, such as speed damped by size, stay as functions in
``traits.py``. A ``TraitSet`` can also list which traits drive which cost, so trade-offs can be read
and audited (``TraitSet.explain``).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum

from evolution_simulator.dna import Genome, GenomeLayout, position_bias_for_step
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.sense_genes import (
    FOV_HALF_DEGREES,
    HEARING_RANGE,
    SIGHT_REACH,
    SMELL_RANGE,
    TACTILE_FACTOR,
)

CARE_FRACTION_RANGE: tuple[float, float] = (0.10, 0.80)
"""A newborn's starting energy as a share of its own energy store (``parenting``)."""
COOLDOWN_DAYS_RANGE: tuple[float, float] = (2.0, 90.0)
"""Gap between matings in simulated days (``repro_cooldown``, log scale)."""
LIFESPAN_DAYS_RANGE: tuple[float, float] = (7.0, 365.0)
"""How long a plant lives, in simulated days (``longevity``, log scale). A month, 30.4 days, is gene
value 0.371."""
SEEDING_DAYS_RANGE: tuple[float, float] = (2.0, 60.0)
"""Shortest gap between seed bursts, in simulated days (``seeding_interval``, log scale)."""

SEED_PROVISION_RANGE: tuple[float, float] = (0.05, 0.50)
"""A seed's starting biomass as a share of its own full size (``seed_provision``, log scale). The
prototype's fixed 15% sits inside it. A starting range to tune."""

DEFAULT_MUTATION_STEP: float = 0.05
"""Typical size of one mutation as a fraction of a trait's range (the research note's 5%)."""

MODIFIER_SWING: float = 2.0
"""A ``MODIFIED`` cluster scales its main gene by ``1 + MODIFIER_SWING * sum(w * (g - 0.5))`` over the
modifier genes, so a modifier at its middle value changes nothing and one at an end changes the
effect by up to its weight."""
DEFAULT_MODIFIER_WEIGHT: float = 0.2
"""A modifier gene's weight when a cluster row gives none."""


class Scale(Enum):
    """How a gene value from 0 to 1 maps onto a trait's range."""

    LINEAR = "linear"
    LOG = "log"


class Kind(Enum):
    """The type of the expressed value."""

    CONTINUOUS = "continuous"  # a float in [lo, hi]
    INTEGER = "integer"  # lo + int(g * (hi - lo)), an int in [lo, hi]
    CATEGORY = "category"  # the raw digit of a single-digit gene, ignoring range and scale


class Role(Enum):
    """What a gene does in a cluster."""

    MAIN = "main"
    MODIFIER = "modifier"


class Combine(Enum):
    """How a trait reads the genes of its cluster."""

    MEAN = "mean"  # the weighted mean of the genes (polygeny)
    MODIFIED = "modified"  # the main gene, scaled by the modifier genes (epistasis)


@dataclass(frozen=True)
class GeneTerm:
    """One gene in a trait's cluster, with its role and weight.

    A plain gene ID in ``TraitDef.genes`` is a term with the main role and the default weight. A
    weight left out is 1 in a ``MEAN`` cluster and ``DEFAULT_MODIFIER_WEIGHT`` for a modifier in a
    ``MODIFIED`` one; a modifier's weight may be negative to weaken the main gene's effect as it
    rises. The main gene of a ``MODIFIED`` cluster has no weight.
    """

    gene: str
    role: Role = Role.MAIN
    weight: float | None = None

    def __post_init__(self) -> None:
        if not self.gene:
            raise ValueError("A gene term needs a gene ID.")
        object.__setattr__(self, "role", Role(self.role))
        if self.weight is not None and not math.isfinite(self.weight):
            raise ValueError(f"Gene term {self.gene!r} needs a finite weight, got {self.weight}.")


def _weight(term: GeneTerm) -> float:
    """A term's weight; a trait fills every weight in when it is built, so this is its value there."""
    return 1.0 if term.weight is None else term.weight


@dataclass(frozen=True)
class TraitDef:
    """One trait.

    ``genes`` lists the genes it reads, as IDs or ``GeneTerm`` rows (after construction it holds just
    the IDs and ``terms`` holds the resolved rows). With more than one, ``combine`` says how they
    are read: ``MEAN`` (the default) is the weighted mean, ``MODIFIED`` is one main gene scaled by
    the others. ``cluster`` optionally names the layout cluster all of them must belong to.
    ``mutation_step`` is the typical mutation size as a fraction of the range. It is data for the
    mutation operator: ``TraitSet.position_biases()`` turns it into the per-gene bias that
    ``DNA.mutated(gene_biases=...)`` reads, so a trait with a small step changes mostly in its low digits.
    """

    name: str
    genes: tuple[str | GeneTerm, ...]
    lo: float = 0.0
    hi: float = 1.0
    scale: Scale = Scale.LINEAR
    kind: Kind = Kind.CONTINUOUS
    mutation_step: float = DEFAULT_MUTATION_STEP
    description: str = ""
    combine: Combine = Combine.MEAN
    cluster: str | None = None
    terms: tuple[GeneTerm, ...] = field(init=False, repr=False, compare=False)
    """The cluster as resolved rows, with every weight filled in."""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A trait needs a name.")
        if not self.genes:
            raise ValueError(f"Trait {self.name!r} must read at least one gene.")
        rows = tuple(g if isinstance(g, GeneTerm) else GeneTerm(g) for g in self.genes)
        object.__setattr__(self, "combine", Combine(self.combine))
        object.__setattr__(self, "terms", self._resolve(rows))
        object.__setattr__(self, "genes", tuple(term.gene for term in self.terms))
        if self.kind is Kind.CATEGORY:
            if len(self.genes) != 1:
                raise ValueError(f"Category trait {self.name!r} must read exactly one gene.")
            return
        if not self.lo < self.hi:
            raise ValueError(f"Trait {self.name!r} needs lo < hi, got {self.lo} and {self.hi}.")
        if self.scale is Scale.LOG and self.lo <= 0:
            raise ValueError(f"Log-scale trait {self.name!r} needs lo > 0, got {self.lo}.")
        if not 0.0 < self.mutation_step <= 1.0:
            raise ValueError(f"Trait {self.name!r} needs a mutation step in (0, 1].")
        if self.kind is Kind.INTEGER and (self.lo != int(self.lo) or self.hi != int(self.hi)):
            raise ValueError(f"Integer trait {self.name!r} needs whole-number bounds.")

    def _resolve(self, rows: tuple[GeneTerm, ...]) -> tuple[GeneTerm, ...]:
        """Check the cluster's rows and fill in every weight."""
        if len({row.gene for row in rows}) != len(rows):
            raise ValueError(f"Trait {self.name!r} reads the same gene twice.")
        if self.combine is Combine.MEAN:
            resolved = tuple(GeneTerm(r.gene, r.role, _weight(r)) for r in rows)
            if any(_weight(r) <= 0 for r in resolved):
                raise ValueError(f"Trait {self.name!r} needs positive weights for a mean.")
            return resolved
        mains = [r for r in rows if r.role is Role.MAIN]
        if len(mains) != 1 or len(rows) < 2:
            raise ValueError(
                f"Modified trait {self.name!r} needs one main gene and at least one modifier."
            )
        resolved_rows = []
        for row in rows:
            if row.role is Role.MAIN:
                weight = 1.0
            else:
                weight = DEFAULT_MODIFIER_WEIGHT if row.weight is None else row.weight
                if weight == 0.0:
                    raise ValueError(f"Modifier {row.gene!r} of {self.name!r} needs a weight.")
            resolved_rows.append(GeneTerm(row.gene, row.role, weight))
        return tuple(resolved_rows)

    @property
    def main_gene(self) -> str:
        """The gene a ``MODIFIED`` cluster scales (the first gene of a ``MEAN`` one)."""
        if self.combine is Combine.MODIFIED:
            return next(t.gene for t in self.terms if t.role is Role.MAIN)
        return self.terms[0].gene

    def step_multiplier(self, gene_id: str) -> float:
        """How much larger a change in this gene must be to move the trait by one mutation step: the
        reciprocal of the share of the trait that gene controls. In a mean that is its share of the
        total weight; a modifier moves the trait by at most ``MODIFIER_SWING * |weight|`` of its own
        change, and the main gene fully."""
        term = next(t for t in self.terms if t.gene == gene_id)
        if self.combine is Combine.MEAN:
            return sum(_weight(t) for t in self.terms) / _weight(term)
        if term.role is Role.MAIN:
            return 1.0
        return 1.0 / min(1.0, MODIFIER_SWING * abs(_weight(term)))

    def unit(self, dna: Genome) -> float:
        """The cluster's value from 0 to 1, before it is mapped onto the trait's range. Each gene is
        read through the genome, so dominance acts first, inside each gene; then the cluster
        combines the genes."""
        if self.combine is Combine.MEAN:
            total = sum(_weight(t) for t in self.terms)
            return sum(_weight(t) * dna.value(t.gene) for t in self.terms) / total
        swing = 0.0
        for t in self.terms:
            if t.role is Role.MODIFIER:
                swing += _weight(t) * (dna.value(t.gene) - 0.5)
        main = dna.value(self.main_gene)
        return min(1.0, max(0.0, main * (1.0 + MODIFIER_SWING * swing)))

    def from_unit(self, unit: float) -> float:
        """Map a gene value in [0, 1] onto this trait's range and scale."""
        unit = min(1.0, max(0.0, unit))
        if self.scale is Scale.LOG:
            return self.lo * (self.hi / self.lo) ** unit
        return self.lo + unit * (self.hi - self.lo)

    def express(self, dna: Genome) -> float | int:
        """This trait's value for a genome."""
        if self.kind is Kind.CATEGORY:
            return dna.digit(self.genes[0])
        unit = self.unit(dna)
        if self.kind is Kind.INTEGER:
            if self.scale is Scale.LOG:
                return int(self.from_unit(unit))
            return int(self.lo) + int(min(1.0, max(0.0, unit)) * (self.hi - self.lo))
        return self.from_unit(unit)


@dataclass(frozen=True)
class TraitExplanation:
    """What is behind one trait, for reading and tests (``TraitSet.explain``)."""

    trait: str
    combine: Combine
    terms: tuple[GeneTerm, ...]
    """The genes it reads, with role and weight."""
    clusters: tuple[str, ...]
    """The layout clusters those genes belong to."""
    shared: Mapping[str, tuple[str, ...]]
    """For each gene it reads that other traits read too (pleiotropy), those other traits."""
    costs: tuple[str, ...]
    """The cost terms that this trait drives."""


class TraitSet:
    """The trait table for one species, checked against that species' layout.

    ``costs`` optionally maps each shared cost (upkeep, wear, a birth) to the traits that drive it, so
    the trade-offs can be listed and audited. The formulas themselves stay in ``traits.py``.
    ``free`` maps the genes that deliberately pay nothing to the reason, so ``unpaid_genes`` only
    lists genes nobody has decided about (``TRAIT.9``).
    """

    def __init__(
        self,
        name: str,
        layout: GenomeLayout,
        defs: Iterable[TraitDef],
        costs: Mapping[str, Iterable[str]] | None = None,
        free: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        self.layout = layout
        self.defs: tuple[TraitDef, ...] = tuple(defs)
        names = [d.name for d in self.defs]
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate trait names in trait set {name!r}.")
        for trait in self.defs:
            for gene_id in trait.genes:
                if gene_id not in layout:
                    raise ValueError(
                        f"Trait {trait.name!r} reads gene {gene_id!r}, which layout "
                        f"{layout.name!r} does not have."
                    )
            if trait.kind is Kind.CATEGORY and layout.gene(trait.genes[0]).length != 1:
                raise ValueError(f"Category trait {trait.name!r} needs a single-digit gene.")
            if trait.cluster is not None:
                members = layout.clusters.get(trait.cluster)
                if members is None:
                    raise ValueError(
                        f"Trait {trait.name!r} names cluster {trait.cluster!r}, which layout "
                        f"{layout.name!r} does not have."
                    )
                outside = [g for g in trait.genes if g not in members]
                if outside:
                    raise ValueError(
                        f"Trait {trait.name!r} reads {outside} outside cluster {trait.cluster!r}."
                    )
        self._by_name: dict[str, TraitDef] = {d.name: d for d in self.defs}
        self.costs: Mapping[str, tuple[str, ...]] = {
            term: tuple(drivers) for term, drivers in (costs or {}).items()
        }
        for term, drivers in self.costs.items():
            unknown = [d for d in drivers if d not in self._by_name]
            if unknown:
                raise ValueError(f"Cost {term!r} names unknown traits {unknown}.")
        self.free: Mapping[str, str] = dict(free or {})
        """Genes that need no cost, with the reason."""
        for gene_id, reason in self.free.items():
            if gene_id not in layout:
                raise ValueError(f"Free gene {gene_id!r} is not in layout {layout.name!r}.")
            if not reason.strip():
                raise ValueError(f"Free gene {gene_id!r} needs a reason.")

    def __getitem__(self, trait_name: str) -> TraitDef:
        return self._by_name[trait_name]

    def __contains__(self, trait_name: object) -> bool:
        return trait_name in self._by_name

    def __iter__(self) -> Iterator[TraitDef]:
        return iter(self.defs)

    def __len__(self) -> int:
        return len(self.defs)

    def express(self, dna: Genome) -> Mapping[str, float | int]:
        """Every trait's value for a genome, by trait name."""
        if dna.layout != self.layout:
            raise TypeError(
                f"Trait set {self.name!r} expects layout {self.layout.name!r}, "
                f"got {dna.layout.name!r}."
            )
        return {trait.name: trait.express(dna) for trait in self.defs}

    def traits_reading(self, gene_id: str) -> tuple[TraitDef, ...]:
        """Which traits depend on a gene (what a mutation there can change)."""
        return tuple(trait for trait in self.defs if gene_id in trait.genes)

    def position_biases(self) -> Mapping[str, float]:
        """Per-gene position bias for ``DNA.mutated(gene_biases=...)``, from the traits' steps.

        For each single-value gene a trait reads, the bias at which a typical mutation moves the
        gene by about the trait's ``mutation_step`` (see ``position_bias_for_step``). A cluster
        moves only a share of one gene's change, so the step is scaled up by the reciprocal of that
        share (``TraitDef.step_multiplier``: the number of genes in an equal mean); a gene read by
        several traits uses their mean step. Genes no trait reads (and gene blocks) are left out and
        use the caller's default.
        """
        steps: dict[str, list[float]] = {}
        for trait in self.defs:
            if trait.kind is Kind.CATEGORY:
                continue
            for gene_id in trait.genes:
                steps.setdefault(gene_id, []).append(
                    min(1.0, trait.mutation_step * trait.step_multiplier(gene_id))
                )
        return {
            gene_id: position_bias_for_step(
                self.layout.gene(gene_id).length, sum(wanted) / len(wanted)
            )
            for gene_id, wanted in steps.items()
        }

    def explain(self, trait_name: str) -> TraitExplanation:
        """The genes, weights and clusters behind a trait, the other traits that read the same genes
        and the costs it drives. For reading and tests, not for the simulation."""
        trait = self._by_name[trait_name]
        shared = {
            gene_id: others
            for gene_id in trait.genes
            if (others := tuple(t.name for t in self.traits_reading(gene_id) if t is not trait))
        }
        clusters: list[str] = []
        for gene_id in trait.genes:
            cluster = self.layout.gene(gene_id).cluster
            if cluster is not None and cluster not in clusters:
                clusters.append(cluster)
        return TraitExplanation(
            trait=trait.name,
            combine=trait.combine,
            terms=trait.terms,
            clusters=tuple(clusters),
            shared=shared,
            costs=tuple(term for term, drivers in self.costs.items() if trait.name in drivers),
        )

    def unpaid_genes(self) -> tuple[str, ...]:
        """Genes read by traits that drive no cost and are not recorded in ``free``: what nobody has
        decided about. Only useful when the set was given ``costs``. Gene blocks are left out."""
        paid = {name for drivers in self.costs.values() for name in drivers}
        return tuple(
            gene.id
            for gene in self.layout.genes
            if gene.block is None
            and (readers := self.traits_reading(gene.id))
            and gene.id not in self.free
            and not any(t.name in paid for t in readers)
        )

    def unread_genes(self) -> tuple[str, ...]:
        """Layout genes that no trait reads. Gene blocks are left out: the brain reads those."""
        read = {gene_id for trait in self.defs for gene_id in trait.genes}
        return tuple(
            gene.id for gene in self.layout.genes if gene.id not in read and gene.block is None
        )


def _level(gene_id: str, description: str = "") -> TraitDef:
    """A gene's own value, 0 to 1, as a trait named after the gene."""
    return TraitDef(gene_id, (gene_id,), description=description)


# =============================================================================
# Animal traits
# =============================================================================

ANIMAL_TRAITS = TraitSet(
    "animal",
    ANIMAL_LAYOUT,
    (
        # Gene levels, 0 to 1, used by the formulas in traits.py.
        _level("speed"),
        _level("agility"),
        _level("size"),
        _level("somatic_maint", "Repair: slows wear, costs upkeep."),
        _level("sight_range"),
        _level("sight_fov"),
        _level("sight_acuity"),
        _level(
            "camouflage",
            "How hard the body is to see: others see it from less far, at a cost in upkeep and speed.",
        ),
        _level("hearing"),
        _level("smell"),
        _level("touch"),
        _level("taste"),
        _level("herbivore_eff"),
        _level("carnivore_eff"),
        _level("aggression"),
        _level("fear"),
        _level("encoder_fidelity"),
        _level("repro_drive", "Urge to find a mate: lowers the energy needed to start looking."),
        _level("fertility", "Chance a mating takes, litter size, gestation; costs upkeep."),
        _level("recovery", "How fast the body heals and regains energy at rest; costs upkeep."),
        # Ranged traits.
        TraitDef("mass", ("size",), 1.0, 4.0, description="Body mass in simulation units."),
        TraitDef(
            "sight_reach", ("sight_range",), *SIGHT_REACH, description="Before acuity lengthens it."
        ),
        TraitDef(
            "fov_half_degrees",
            ("sight_fov",),
            *FOV_HALF_DEGREES,
            scale=Scale.LOG,
            description="Field of vision either side of the direction of movement.",
        ),
        TraitDef("hearing_range", ("hearing",), *HEARING_RANGE),
        TraitDef("smell_range", ("smell",), *SMELL_RANGE),
        TraitDef("tactile_factor", ("touch",), *TACTILE_FACTOR, description="Times body radius."),
        TraitDef("call_radius", ("encoder_fidelity",), 0.0, 60.0),
        TraitDef("call_energy_cost", ("encoder_fidelity",), 1.5, 7.5),
        TraitDef("sex_strategy", ("sex_strategy",), kind=Kind.CATEGORY),
        # Reproduction (REPRO.8).
        TraitDef(
            "care_fraction",
            ("parenting",),
            *CARE_FRACTION_RANGE,
            description="A newborn starts with the mean of its parents' share of its energy store.",
        ),
        TraitDef(
            "cooldown_days",
            ("repro_cooldown",),
            *COOLDOWN_DAYS_RANGE,
            scale=Scale.LOG,
            description="Simulated days between matings, before the repair stretch.",
        ),
        TraitDef(
            "litter_capacity",
            (
                GeneTerm("fertility"),
                GeneTerm("size", Role.MODIFIER),
                GeneTerm("recovery", Role.MODIFIER),
            ),
            combine=Combine.MODIFIED,
            description=(
                "Fertility sets the litter, a big or quick-healing body carries more (0 to 1; "
                "DNA.14's example)."
            ),
        ),
        # How the brain operates (BRAIN.23). Curiosity and the learning rate wait for BRAIN.24.
        TraitDef(
            "brain_gain",
            ("brain_gain",),
            0.5,
            2.0,
            scale=Scale.LOG,
            description="Multiplies every neuron's input sum: high is sharp, low is gradual.",
        ),
        TraitDef(
            "decision_interval",
            ("reaction_time",),
            1,
            4,
            kind=Kind.INTEGER,
            description="Reference ticks (hours) between brain decisions; a slower thinker is cheaper (BRAIN.11, WORLD.16).",
        ),
        TraitDef("curiosity", ("curiosity",), 0.0, 0.5, description="Size of random output nudge."),
        TraitDef(
            "learning_rate", ("learning_rate",), 0.0, 2.0, description="Strength of learning."
        ),
    ),
    costs={
        "body upkeep": ("mass",),
        "movement burn": ("mass", "speed"),
        "size slows movement": ("size",),
        "repair upkeep": ("somatic_maint",),
        "readiness upkeep": ("cooldown_days",),
        "drive upkeep and wear": ("repro_drive", "sex_strategy"),
        "agility upkeep": ("agility",),
        "temperament upkeep": ("aggression", "fear"),
        "learning upkeep": ("learning_rate",),
        "camouflage upkeep and slowing": ("camouflage",),
        "fertility upkeep": ("fertility",),
        "recovery upkeep": ("recovery",),
        "sensing upkeep": (
            "sight_reach",
            "sight_fov",
            "sight_acuity",
            "fov_half_degrees",
            "hearing_range",
            "smell_range",
            "touch",
            "taste",
        ),
        "gut upkeep": ("herbivore_eff", "carnivore_eff"),
        "brain upkeep": ("decision_interval",),
        "calling": ("call_radius", "call_energy_cost"),
        "gestation": ("fertility", "litter_capacity"),
        "cooldown stretch": ("somatic_maint", "cooldown_days"),
        "birth cost": ("care_fraction", "size", "somatic_maint"),
    },
    free={
        "brain_gain": (
            "A scale on the brain's own weights, which evolve too: any gain can be matched by "
            "weights, so selection has no direction to push it. The weights above the dead zone "
            "are what cost."
        ),
        "curiosity": (
            "Pays for itself: it nudges every output at random, so the animal moves, eats and "
            "mates less reliably, and a noisy speed costs more than a steady one because the "
            "burn grows with the square of the speed."
        ),
    },
)

# =============================================================================
# Plant traits
# =============================================================================

PLANT_TRAITS = TraitSet(
    "plant",
    PLANT_LAYOUT,
    (
        _level("toxicity"),
        TraitDef("max_biomass", ("max_biomass",), 20.0, 200.0),
        TraitDef("canopy_radius", ("max_biomass",), 2.0, 12.0),
        TraitDef("base_growth_rate", ("growth_rate",), 0.2, 1.0),
        TraitDef("dispersal_radius", ("dispersal_radius",), 10.0, 70.0),
        TraitDef("seed_count", ("seed_clutch",), 1, 8, kind=Kind.INTEGER),
        TraitDef("root_radius", ("root_reach",), 3.0, 15.0),
        # Reproduction (REPRO.3).
        TraitDef(
            "seed_provision",
            ("seed_provision",),
            *SEED_PROVISION_RANGE,
            scale=Scale.LOG,
            description="A seed starts with this share of its own full size.",
        ),
        TraitDef(
            "seeding_days",
            ("seeding_interval",),
            *SEEDING_DAYS_RANGE,
            scale=Scale.LOG,
            description="Shortest gap between seed bursts, in simulated days.",
        ),
        # Lifespan (TRAIT.8).
        _level("longevity", "Long life slows growth and shrinks the seed budget."),
        TraitDef(
            "lifespan_days",
            ("longevity",),
            *LIFESPAN_DAYS_RANGE,
            scale=Scale.LOG,
            description="Simulated days until an uneaten plant dies of old age.",
        ),
    ),
)
