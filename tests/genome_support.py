"""Build genomes from digits written in the gene order before the clusters.

Layout version 7 grouped the body genes into clusters (``DNA.15``), which moved every body gene. A
few tests pin a hand-made genome digit by digit with numbers checked against a separate calculation;
this reads their digits in the order of layout version 6 (the prototype's order with the reproduction
genes, ``sight_acuity`` and the operating genes) and places each gene where it now sits, so the
pinned genome keeps the same gene values.
"""

from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT

ORDER_V6: tuple[tuple[str, int], ...] = (
    ("speed", 4),
    ("agility", 4),
    ("size", 4),
    ("somatic_maint", 4),
    ("sight_range", 4),
    ("sight_fov", 4),
    ("sight_acuity", 4),
    ("hearing", 4),
    ("smell", 4),
    ("touch", 4),
    ("taste", 4),
    ("herbivore_eff", 4),
    ("carnivore_eff", 4),
    ("aggression", 4),
    ("fear", 4),
    ("parenting", 3),
    ("repro_cooldown", 3),
    ("repro_drive", 3),
    ("fertility", 3),
    ("recovery", 3),
    ("encoder_fidelity", 4),
    ("sex_strategy", 1),
    ("brain_gain", 4),
    ("reaction_time", 4),
    ("curiosity", 4),
    ("learning_rate", 4),
)
"""Body genes of layout version 6 with their lengths (96 digits)."""

BODY_LENGTH = sum(length for _, length in ORDER_V6)


def body_from_v6(digits: str) -> str:
    """The 92 body digits in layout version 6 order, rewritten in the current gene order."""
    if len(digits) != BODY_LENGTH:
        raise ValueError(f"Expected {BODY_LENGTH} body digits, got {len(digits)}.")
    chunks: dict[str, str] = {}
    at = 0
    for gene_id, length in ORDER_V6:
        chunks[gene_id] = digits[at : at + length]
        at += length
    return "".join(chunks[gene.id] for gene in ANIMAL_LAYOUT.genes if gene.block is None)


def dna_from_v6(body: str, brain: str) -> DNA:
    """A genome from version 6 body digits and the brain digits."""
    return DNA(ANIMAL_LAYOUT, body_from_v6(body) + brain)
