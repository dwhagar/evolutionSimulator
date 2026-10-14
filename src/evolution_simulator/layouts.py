"""Gene layouts for each species, as plain data.

Gene IDs are the stable names that traits refer to. Positions follow from the order of the table,
so reordering, resizing, adding or removing a row changes every later position: bump the layout's
``version`` when you do, since saved genomes carry it.

The body is grouped into clusters of genes that feed one system, so the order is not the prototype's
any more (layout version 7, ``DNA.15``); the brain block follows the body.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import Any

from evolution_simulator.brain import DEFAULT_BLUEPRINT
from evolution_simulator.dna import DNA, BlockSpec, GeneSpec, GenomeLayout

BRAIN_GENE = BlockSpec(
    "brain",
    count=DEFAULT_BLUEPRINT.value_count,
    digits_per_value=2,
    low=-2.0,
    high=2.0,
    groups=DEFAULT_BLUEPRINT.group_sizes,
    segment="brain",
)
"""The brain: 16 slots of 28 values (gate, bias, 20 incoming and 6 outgoing weights) and the 6
output biases, 454 values of two digits each (908 digits), one group per slot."""

PLANT_MUTATION_PER_DIGIT: float = 0.005
"""Chance a plant digit changes per child: half the animal body's 0.01, so plants evolve slower."""

ANIMAL_LAYOUT = GenomeLayout(
    name="animal",
    version=7,
    specs=(
        # Genes that feed one trait or one system sit together, tagged as a cluster (DNA.15), so
        # crossover tends to inherit them together (see docs/design/gene-clusters.md).
        # frame: mass, energy store, speed, turning
        GeneSpec("size", cluster="frame"),
        GeneSpec("speed", cluster="frame"),
        GeneSpec("agility", cluster="frame"),
        # repair: wear, healing, upkeep
        GeneSpec("somatic_maint", cluster="repair"),
        GeneSpec("recovery", length=3, cluster="repair"),
        # senses
        GeneSpec("sight_range", cluster="sight"),
        GeneSpec("sight_fov", cluster="sight"),
        GeneSpec("sight_acuity", cluster="sight"),
        GeneSpec("hearing", cluster="hearing"),
        GeneSpec("encoder_fidelity", cluster="hearing"),
        GeneSpec("smell", cluster="chemical"),
        GeneSpec("taste", cluster="chemical"),
        GeneSpec("touch"),
        # feeding and behaviour
        GeneSpec("herbivore_eff", cluster="diet"),
        GeneSpec("carnivore_eff", cluster="diet"),
        GeneSpec("aggression", cluster="temperament"),
        GeneSpec("fear", cluster="temperament"),
        # reproduction (REPRO.8): the urge to mate, the gap between matings, litter size and
        # gestation, how much each parent gives a newborn, and the sex digit read as a category
        GeneSpec("repro_drive", length=3, cluster="reproduction"),
        GeneSpec("repro_cooldown", length=3, cluster="reproduction"),
        GeneSpec("fertility", length=3, cluster="reproduction"),
        GeneSpec("parenting", length=3, cluster="reproduction"),
        GeneSpec("sex_strategy", length=1, cluster="reproduction"),
        # how the brain operates (BRAIN.23); the learning ones are read once learning exists
        GeneSpec("brain_gain"),
        GeneSpec("reaction_time"),
        GeneSpec("curiosity"),
        GeneSpec("learning_rate"),
        # the brain: read by the Brain object, not by the trait table
        BRAIN_GENE,
    ),
    # The body keeps the prototype's 0.01 per digit (0.96 changes per child over its 96 digits). The
    # brain is about one change per child however long it is, about 0.0011 per brain digit.
    segment_mutations={"body": 0.01 * 96, "brain": 1.0},
)

PLANT_LAYOUT = GenomeLayout(
    name="plant",
    version=3,
    specs=(
        GeneSpec("max_biomass"),
        GeneSpec("growth_rate"),
        GeneSpec("toxicity"),
        GeneSpec("dispersal_radius"),
        GeneSpec("seed_clutch"),
        GeneSpec("root_reach"),
        # reproduction (REPRO.3): energy per seed and the gap between seed bursts
        GeneSpec("seed_provision", length=3),
        GeneSpec("seeding_interval", length=3),
        # how long the plant lives; trades against its growth and seed budget (TRAIT.8)
        GeneSpec("longevity", length=3),
    ),
    # Plants mutate more slowly than animals: half the animals' 0.01 per digit. They evolve slowly,
    # so the changes they do get keep big jumps likelier than the animals' position bias of 0.5.
    segment_mutations={"body": PLANT_MUTATION_PER_DIGIT * 33},
    position_bias=0.75,
)

LAYOUTS: tuple[GenomeLayout, ...] = (ANIMAL_LAYOUT, PLANT_LAYOUT)
"""Every known layout, for restoring saved genomes."""


FOUNDER_LEVELS: Mapping[str, float] = {
    "fertility": 0.75,
    "parenting": 0.0,
    "repro_drive": 0.5,
    "repro_cooldown": 0.5,
    "recovery": 0.5,
}
"""Where the reproduction genes start in a first generation (``REPRO.7``): large litters, no
parenting, and the middle of the range for the rest. Evolution moves them from there."""


FOUNDER_SENSE_SPREAD: float = 0.07
"""How far a first generation's sense genes stray from the middle (0.5), either way, so the
population is not a set of clones (``SENSE.16``)."""
FOUNDER_DIET_TILT: float = 0.3
"""How far diet moves the starting field of vision: ``0.5 - 0.3 * tilt`` where the tilt runs from -1
(all plants) to +1 (all meat), so a pure predator starts with a narrow field and sharp eyes and a
pure plant eater with a wide field and soft ones."""
_MIDDLE_SENSES: tuple[str, ...] = ("sight_range", "hearing", "smell", "touch", "taste")


def seed_sense_genes(dna: DNA, rng: random.Random) -> DNA:
    """A copy of a first-generation genome with its sense genes at their starting levels.

    The range genes and touch and taste start in the middle, 0.5 plus or minus
    ``FOUNDER_SENSE_SPREAD``. The eye starts on its frontier (``sight_acuity = 1 - sight_fov``, so
    none of the acuity gene goes unused) with the field tilted by the genome's own diet:
    ``carnivore_eff - herbivore_eff`` from -1 to +1. After this the diet and the eye evolve
    independently (``SENSE.19``'s default). Haploid genomes only.
    """
    spread = FOUNDER_SENSE_SPREAD

    def around(level: float) -> float:
        return min(1.0, max(0.0, level + rng.uniform(-spread, spread)))

    tilt = dna.value("carnivore_eff") - dna.value("herbivore_eff")
    for gene_id in _MIDDLE_SENSES:
        dna = dna.with_value(gene_id, around(0.5))
    field = around(0.5 - FOUNDER_DIET_TILT * tilt)
    return dna.with_value("sight_fov", field).with_value("sight_acuity", 1.0 - field)


def founder_animal_dna(rng: random.Random) -> DNA:
    """A random animal genome with the reproduction genes set to ``FOUNDER_LEVELS`` and the sense
    genes at their starting levels (``seed_sense_genes``)."""
    dna = DNA.random(ANIMAL_LAYOUT, rng)
    for gene_id, level in FOUNDER_LEVELS.items():
        dna = dna.with_value(gene_id, level)
    return seed_sense_genes(dna, rng)


FOUNDER_PLANT_LONGEVITY: float = 0.371
"""Where a first generation's plant lifespan starts: the gene value that gives one simulated month
(7 to 365 days on a log scale, so 30.4 days). Evolution moves it from there (``TRAIT.8``)."""
FOUNDER_LONGEVITY_SPREAD: float = 0.1
"""How far a first generation's plant lifespans stray from the start, either way, so the founders do
not all die on the same day (a gene value of 0.1 is about 1.7 times longer or shorter)."""


def founder_plant_dna(rng: random.Random) -> DNA:
    """A random plant genome with the lifespan gene at the starting level, give or take the spread."""
    dna = DNA.random(PLANT_LAYOUT, rng)
    level = FOUNDER_PLANT_LONGEVITY + rng.uniform(
        -FOUNDER_LONGEVITY_SPREAD, FOUNDER_LONGEVITY_SPREAD
    )
    return dna.with_value("longevity", level)


def dna_from_dict(data: Mapping[str, Any]) -> DNA:
    """Restore a genome saved with ``DNA.to_dict()``."""
    return DNA.from_dict(data, LAYOUTS)
