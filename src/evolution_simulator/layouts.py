"""Gene layouts for each species, as plain data.

Gene IDs are the stable names that traits refer to. Positions follow from the order of the table,
so reordering, resizing, adding or removing a row changes every later position: bump the layout's
``version`` when you do, since saved genomes carry it.

The body is grouped into clusters of genes that feed one system, so the order is not the prototype's
any more (layout version 6, ``DNA.15``); the brain block follows the body.
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
    version=6,
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
    # The body keeps the prototype's 0.01 per digit (0.92 changes per child over its 92 digits). The
    # brain is about one change per child however long it is, about 0.0011 per brain digit.
    segment_mutations={"body": 0.01 * 92, "brain": 1.0},
)

PLANT_LAYOUT = GenomeLayout(
    name="plant",
    version=2,
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
    ),
    # Plants mutate more slowly than animals: half the animals' 0.01 per digit. They evolve slowly,
    # so the changes they do get keep big jumps likelier than the animals' position bias of 0.5.
    segment_mutations={"body": PLANT_MUTATION_PER_DIGIT * 30},
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


def founder_animal_dna(rng: random.Random) -> DNA:
    """A random animal genome with the reproduction genes set to ``FOUNDER_LEVELS``."""
    dna = DNA.random(ANIMAL_LAYOUT, rng)
    for gene_id, level in FOUNDER_LEVELS.items():
        dna = dna.with_value(gene_id, level)
    return dna


def dna_from_dict(data: Mapping[str, Any]) -> DNA:
    """Restore a genome saved with ``DNA.to_dict()``."""
    return DNA.from_dict(data, LAYOUTS)
