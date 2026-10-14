"""Traits as data: what each trait reads from DNA and how it becomes a number.

A ``TraitDef`` says which gene IDs a trait depends on, the range it maps onto, whether that mapping
is linear or logarithmic, and a mutation step. A ``TraitSet`` is the table for one species. Expressing
a genome through a set gives the phenotype's primary values; DNA never sees trait names, and adding
a trait is one new row.

Several traits may read the same gene (pleiotropy: ``size`` already feeds ``mass``) and one trait
may read several genes (polygeny: the mean of the genes' values). Derived quantities that combine
traits, such as speed damped by size, stay as functions in ``traits.py``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum

from evolution_simulator.dna import DNA, GenomeLayout
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT

DEFAULT_MUTATION_STEP: float = 0.05
"""Typical size of one mutation as a fraction of a trait's range (the research note's 5%)."""


class Scale(Enum):
    """How a gene value from 0 to 1 maps onto a trait's range."""

    LINEAR = "linear"
    LOG = "log"


class Kind(Enum):
    """The type of the expressed value."""

    CONTINUOUS = "continuous"  # a float in [lo, hi]
    INTEGER = "integer"  # lo + int(g * (hi - lo)), an int in [lo, hi]
    CATEGORY = "category"  # the raw digit of a single-digit gene, ignoring range and scale


@dataclass(frozen=True)
class TraitDef:
    """One trait.

    ``genes`` lists the gene IDs it reads; with more than one, the mean of their values is used.
    ``mutation_step`` is the typical mutation size as a fraction of the range. It is data for the
    mutation operator to use when it supports per-trait steps; no operator reads it yet.
    """

    name: str
    genes: tuple[str, ...]
    lo: float = 0.0
    hi: float = 1.0
    scale: Scale = Scale.LINEAR
    kind: Kind = Kind.CONTINUOUS
    mutation_step: float = DEFAULT_MUTATION_STEP
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A trait needs a name.")
        if not self.genes:
            raise ValueError(f"Trait {self.name!r} must read at least one gene.")
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

    def from_unit(self, unit: float) -> float:
        """Map a gene value in [0, 1] onto this trait's range and scale."""
        unit = min(1.0, max(0.0, unit))
        if self.scale is Scale.LOG:
            return self.lo * (self.hi / self.lo) ** unit
        return self.lo + unit * (self.hi - self.lo)

    def express(self, dna: DNA) -> float | int:
        """This trait's value for a genome."""
        if self.kind is Kind.CATEGORY:
            return dna.digit(self.genes[0])
        unit = sum(dna.value(gene_id) for gene_id in self.genes) / len(self.genes)
        if self.kind is Kind.INTEGER:
            if self.scale is Scale.LOG:
                return int(self.from_unit(unit))
            return int(self.lo) + int(min(1.0, max(0.0, unit)) * (self.hi - self.lo))
        return self.from_unit(unit)


class TraitSet:
    """The trait table for one species, checked against that species' layout."""

    def __init__(self, name: str, layout: GenomeLayout, defs: Iterable[TraitDef]) -> None:
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
        self._by_name: dict[str, TraitDef] = {d.name: d for d in self.defs}

    def __getitem__(self, trait_name: str) -> TraitDef:
        return self._by_name[trait_name]

    def __contains__(self, trait_name: object) -> bool:
        return trait_name in self._by_name

    def __iter__(self) -> Iterator[TraitDef]:
        return iter(self.defs)

    def __len__(self) -> int:
        return len(self.defs)

    def express(self, dna: DNA) -> Mapping[str, float | int]:
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

    def unread_genes(self) -> tuple[str, ...]:
        """Layout genes that no trait reads."""
        read = {gene_id for trait in self.defs for gene_id in trait.genes}
        return tuple(gene_id for gene_id in self.layout.gene_ids if gene_id not in read)


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
        _level("hearing"),
        _level("smell"),
        _level("touch"),
        _level("taste"),
        _level("herbivore_eff"),
        _level("carnivore_eff"),
        _level("aggression"),
        _level("fear"),
        _level("encoder_fidelity"),
        # Ranged traits.
        TraitDef("mass", ("size",), 1.0, 4.0, description="Body mass in simulation units."),
        TraitDef("sight_reach", ("sight_range",), 10.0, 60.0, description="Before FOV narrowing."),
        TraitDef("fov_degrees", ("sight_fov",), 40.0, 360.0),
        TraitDef("hearing_range", ("hearing",), 15.0, 85.0),
        TraitDef("smell_range", ("smell",), 20.0, 100.0),
        TraitDef("tactile_factor", ("touch",), 1.1, 2.6, description="Times body radius."),
        TraitDef("call_radius", ("encoder_fidelity",), 0.0, 60.0),
        TraitDef("call_energy_cost", ("encoder_fidelity",), 1.5, 7.5),
        TraitDef("sex_strategy", ("sex_strategy",), kind=Kind.CATEGORY),
    ),
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
    ),
)
