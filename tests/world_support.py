"""Helpers for the world tests: genomes with chosen genes and brains with fixed behaviour."""

from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, BRAIN_GENE, PLANT_LAYOUT

BRAIN_SIZE = BRAIN_GENE.count
ANIMAL_BASE = DNA(ANIMAL_LAYOUT, "1" * ANIMAL_LAYOUT.length)
PLANT_BASE = DNA(PLANT_LAYOUT, "1" * PLANT_LAYOUT.length)


def animal_dna(brain: dict[str, float] | None = None, **genes: str) -> DNA:
    """An animal genome of all 1s with the named genes set to the given digit strings.

    ``brain`` sets the six output biases (turn, speed, eat, mate, alarm, call) of an otherwise flat
    brain: use +-2 for "always" and "never". Without it the brain is left as the base genome's.
    """
    dna = ANIMAL_BASE
    for gene_id, digits in genes.items():
        dna = dna.replaced(gene_id, digits)
    if brain is not None:
        biases = [
            brain.get(name, -2.0) for name in ("turn", "speed", "eat", "mate", "alarm", "call")
        ]
        values = [0.0] * (BRAIN_SIZE - 6) + biases
        dna = dna.replaced("brain", BRAIN_GENE.encode(values))
    return dna


def plant_dna(**genes: str) -> DNA:
    dna = PLANT_BASE
    for gene_id, digits in genes.items():
        dna = dna.replaced(gene_id, digits)
    return dna
