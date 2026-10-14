"""Who mates with whom (``REPRO.4``).

Two rules, each in one function so they can change without touching the step loop:

* ``may_mate`` says whether two animals can have a child at all. Today any two animals with the same
  kind of genome may. The sex rule (``DNA.9``: is one of each needed?) belongs here.
* ``choose_mate`` picks among the willing animals within reach: the one whose genome is closest
  (``distance``). The closest genome is the same species or the nearest relative, so animals prefer
  their own kind. Cross-breeding between distant genomes is allowed but is the last choice: it
  happens only when nothing closer is in reach. Ties go to the nearer animal, then the lower id.
"""

from __future__ import annotations

from collections.abc import Iterable

from evolution_simulator.world.organisms import Animal


def may_mate(a: Animal, b: Animal) -> bool:
    """Whether ``a`` and ``b`` can have a child together (the one place that decides)."""
    if a is b:
        return False
    genome_a, genome_b = a.traits.dna, b.traits.dna
    return genome_a.layout == genome_b.layout and genome_a.ploidy == genome_b.ploidy


def mate_rank(chooser: Animal, candidate: Animal) -> tuple[float, float, int]:
    """How much ``chooser`` prefers ``candidate``; lower is better: genetic distance, then how far
    apart they are standing, then id."""
    return (
        chooser.traits.dna.distance(candidate.traits.dna),
        chooser.position.distance_to(candidate.position),
        candidate.id,
    )


def choose_mate(chooser: Animal, candidates: Iterable[Animal]) -> Animal | None:
    """The preferred animal among ``candidates`` that ``chooser`` may mate with, or ``None``."""
    allowed = [c for c in candidates if may_mate(chooser, c)]
    return min(allowed, key=lambda c: mate_rank(chooser, c), default=None)
