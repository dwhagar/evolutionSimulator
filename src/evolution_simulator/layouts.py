"""Gene layouts for each species, as plain data.

Gene IDs are the stable names that traits refer to. Positions follow from the order of the table,
so reordering, resizing, adding or removing a row changes every later position: bump the layout's
``version`` when you do, since saved genomes carry it.

Positions match the original prototype digit for digit.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from evolution_simulator.dna import DNA, GeneSpec, GenomeLayout

ANIMAL_LAYOUT = GenomeLayout(
    name="animal",
    version=1,
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
    ),
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
)

LAYOUTS: tuple[GenomeLayout, ...] = (ANIMAL_LAYOUT, PLANT_LAYOUT)
"""Every known layout, for restoring saved genomes."""


def dna_from_dict(data: Mapping[str, Any]) -> DNA:
    """Restore a genome saved with ``DNA.to_dict()``."""
    return DNA.from_dict(data, LAYOUTS)
