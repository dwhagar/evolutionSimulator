"""Gene layouts for each species, as plain data.

Gene IDs are the stable names that traits refer to. Positions follow from the order of the table,
so reordering, resizing, adding or removing a row changes every later position: bump the layout's
``version`` when you do, since saved genomes carry it.

Body positions match the original prototype digit for digit; the brain block follows them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from evolution_simulator.brain import DEFAULT_SHAPE
from evolution_simulator.dna import DNA, BlockSpec, GeneSpec, GenomeLayout

BRAIN_GENE = BlockSpec(
    "brain",
    count=DEFAULT_SHAPE.weight_count,
    digits_per_value=2,
    low=-2.0,
    high=2.0,
    groups=DEFAULT_SHAPE.group_sizes,
    segment="brain",
)
"""The brain's 198 weights and biases, two digits each (396 digits), one group per hidden neuron."""

ANIMAL_LAYOUT = GenomeLayout(
    name="animal",
    version=2,
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
        GeneSpec("fertility"),
        GeneSpec("encoder_fidelity"),
        # one digit read as a category
        GeneSpec("sex_strategy", length=1),
        # the brain: read by the Brain object, not by the trait table
        BRAIN_GENE,
    ),
    # The body keeps the prototype's 0.01 per digit (0.65 changes per child). The brain is about
    # one change per child however long it is, about 0.0025 per brain digit.
    segment_mutations={"body": 0.01 * 65, "brain": 1.0},
)

PLANT_LAYOUT = GenomeLayout(
    name="plant",
    version=1,
    specs=(
        GeneSpec("max_biomass"),
        GeneSpec("growth_rate"),
        GeneSpec("toxicity"),
        GeneSpec("dispersal_radius"),
        GeneSpec("seed_clutch"),
        GeneSpec("root_reach"),
    ),
    # Plants evolve slowly, so keep big jumps likelier than the animals' default of 0.5.
    position_bias=0.75,
)

LAYOUTS: tuple[GenomeLayout, ...] = (ANIMAL_LAYOUT, PLANT_LAYOUT)
"""Every known layout, for restoring saved genomes."""


def dna_from_dict(data: Mapping[str, Any]) -> DNA:
    """Restore a genome saved with ``DNA.to_dict()``."""
    return DNA.from_dict(data, LAYOUTS)
