"""Gene layouts for each species, as plain data.

Gene IDs are the stable names that traits refer to. Positions follow from the order of the table,
so reordering, resizing, adding or removing a row changes every later position: bump the layout's
``version`` when you do, since saved genomes carry it.

Body positions match the original prototype digit for digit; the brain block follows them.
"""

from __future__ import annotations

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
    version=4,
    specs=(
        # body
        GeneSpec("speed"),
        GeneSpec("agility"),
        GeneSpec("size"),
        GeneSpec("somatic_maint"),
        # senses
        GeneSpec("sight_range"),
        GeneSpec("sight_fov"),
        GeneSpec("hearing"),
        GeneSpec("smell"),
        GeneSpec("touch"),
        GeneSpec("taste"),
        # feeding and behaviour
        GeneSpec("herbivore_eff"),
        GeneSpec("carnivore_eff"),
        GeneSpec("aggression"),
        GeneSpec("fear"),
        # reproduction (REPRO.5): energy per offspring, the gap between births, the urge to mate
        GeneSpec("caregiving", length=3),
        GeneSpec("repro_interval", length=3),
        GeneSpec("repro_drive", length=3),
        GeneSpec("encoder_fidelity"),
        # one digit read as a category
        GeneSpec("sex_strategy", length=1),
        # how the brain operates (BRAIN.23); the learning ones are read once learning exists
        GeneSpec("brain_gain"),
        GeneSpec("reaction_time"),
        GeneSpec("curiosity"),
        GeneSpec("learning_rate"),
        # the brain: read by the Brain object, not by the trait table
        BRAIN_GENE,
    ),
    # The body keeps the prototype's 0.01 per digit (0.86 changes per child over its 86 digits). The
    # brain is about one change per child however long it is, about 0.0011 per brain digit.
    segment_mutations={"body": 0.01 * 86, "brain": 1.0},
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


def dna_from_dict(data: Mapping[str, Any]) -> DNA:
    """Restore a genome saved with ``DNA.to_dict()``."""
    return DNA.from_dict(data, LAYOUTS)
