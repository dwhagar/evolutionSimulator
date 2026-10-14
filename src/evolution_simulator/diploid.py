"""Diploid genomes: two strands of every gene, combined by a dominance model (``DNA.13``).

A ``DiploidDNA`` holds two ordinary ``DNA`` strands with the same layout. It offers the reads the rest
of the code uses (``value``, ``digit``, ``values``), so ``TraitSet.express`` and ``AnimalTraits`` take
either kind of genome unchanged; for each gene the two strands' decoded values are blended by a
``DominanceModel``. Haploid species just keep using ``DNA``; both satisfy ``dna.Genome``.

Reproduction follows meiosis: each parent makes a **gamete** (one strand, made by recombining its own
two strands), the gamete is mutated, and the child gets one gamete from each parent. A plant that
reproduces on its own clones both strands instead (or pairs two of its own gametes, which is selfing).
Like every operation here, it takes an injected ``random.Random`` and never changes the parent.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from evolution_simulator.dna import DNA, Crossover, GenomeLayout


@dataclass(frozen=True)
class DominanceModel:
    """How the two strands' values combine into the value an organism expresses.

    For a gene with decoded values ``a`` and ``b`` the expressed value is
    ``(a + b) / 2 + c * |a - b| / 2``, where ``c`` is the gene's dominance coefficient from -1 to 1:

    * ``0`` (the default): **codominant**, the plain average of the two strands.
    * ``1``: the higher strand is fully dominant (the expressed value is ``max(a, b)``).
    * ``-1``: the lower strand is fully dominant (``min(a, b)``).
    * between: partial dominance.

    ``default`` applies to every gene; ``per_gene`` overrides it for named genes. Single-digit
    category genes blend their digits the same way and round half up. Gene blocks (the brain's
    weights) blend value by value.
    """

    default: float = 0.0
    per_gene: Mapping[str, float] | tuple[tuple[str, float], ...] = ()
    _lookup: dict[str, float] = field(init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        pairs = dict(self.per_gene)
        for name, value in (("default", self.default), *pairs.items()):
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"Dominance for {name!r} must be between -1 and 1, got {value}.")
        object.__setattr__(self, "per_gene", tuple(sorted(pairs.items())))
        object.__setattr__(self, "_lookup", pairs)

    def coefficient(self, gene_id: str) -> float:
        return self._lookup.get(gene_id, self.default)

    def blend(self, gene_id: str, a: float, b: float) -> float:
        """The expressed value of a gene from its two strands' values."""
        c = self.coefficient(gene_id)
        mixed = (a + b) / 2 + c * abs(a - b) / 2
        return min(max(a, b), max(min(a, b), mixed))  # floating error must not leave [a, b]

    def check(self, layout: GenomeLayout) -> None:
        unknown = sorted(gene_id for gene_id in self._lookup if gene_id not in layout)
        if unknown:
            raise ValueError(f"Dominance names genes layout {layout.name!r} lacks: {unknown}.")

    def to_dict(self) -> dict[str, Any]:
        return {"default": self.default, "per_gene": dict(self.per_gene)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(data.get("default", 0.0), data.get("per_gene", {}))


CODOMINANT = DominanceModel()
"""Average the two strands (the default)."""


class DiploidDNA:
    """Immutable pair of ``DNA`` strands read through a ``DominanceModel``."""

    __slots__ = ("_dominance", "_strands")

    def __init__(self, first: DNA, second: DNA, dominance: DominanceModel = CODOMINANT) -> None:
        if not isinstance(first, DNA) or not isinstance(second, DNA):
            raise TypeError("A diploid genome is made of two DNA strands.")
        if first.layout != second.layout:
            raise TypeError(
                f"Both strands need the same layout, got {first.layout.name!r} and "
                f"{second.layout.name!r}."
            )
        dominance.check(first.layout)
        object.__setattr__(self, "_strands", (first, second))
        object.__setattr__(self, "_dominance", dominance)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("DiploidDNA is immutable.")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("DiploidDNA is immutable.")

    # -------------------------------------------------------------------------
    # Construction
    # -------------------------------------------------------------------------

    @classmethod
    def random(
        cls, layout: GenomeLayout, rng: random.Random, dominance: DominanceModel = CODOMINANT
    ) -> Self:
        """Two independent random strands."""
        return cls(DNA.random(layout, rng), DNA.random(layout, rng), dominance)

    @classmethod
    def from_haploid(cls, dna: DNA, dominance: DominanceModel = CODOMINANT) -> Self:
        """Both strands the same, so every gene is homozygous and expresses exactly as ``dna`` does
        (whatever the dominance model)."""
        return cls(dna, dna, dominance)

    # -------------------------------------------------------------------------
    # Value semantics
    # -------------------------------------------------------------------------

    @property
    def layout(self) -> GenomeLayout:
        return self._strands[0].layout

    @property
    def ploidy(self) -> int:
        return 2

    @property
    def strands(self) -> tuple[DNA, DNA]:
        return self._strands

    @property
    def dominance(self) -> DominanceModel:
        return self._dominance

    def _key(self) -> tuple[Any, ...]:
        # Which strand is first carries no meaning, so compare them as a set.
        return (self.layout, tuple(sorted(s.sequence for s in self._strands)), self._dominance)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DiploidDNA):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        first, second = self._strands
        return f"DiploidDNA(layout={self.layout.name!r}, strands=('{first}', '{second}'))"

    def distance(self, other: DiploidDNA) -> float:
        """Fraction of digits that differ, using whichever pairing of strands is closest (0.0
        identical, 1.0 every digit differs). The strand order does not matter."""
        if not isinstance(other, DiploidDNA):
            raise TypeError("A diploid genome can only be compared with another diploid genome.")
        a1, a2 = self._strands
        b1, b2 = other._strands
        straight = a1.distance(b1) + a2.distance(b2)
        crossed = a1.distance(b2) + a2.distance(b1)
        return min(straight, crossed) / 2

    # -------------------------------------------------------------------------
    # Reading genes
    # -------------------------------------------------------------------------

    def value(self, gene_id: str) -> float:
        """A gene as a float from 0.0 to 1.0, with the two strands blended by the dominance model."""
        first, second = self._strands
        return self._dominance.blend(gene_id, first.value(gene_id), second.value(gene_id))

    def digit(self, gene_id: str) -> int:
        """A single-digit gene's category: the two strands' digits blended, rounded half up."""
        first, second = self._strands
        blended = self._dominance.blend(gene_id, first.digit(gene_id), second.digit(gene_id))
        return min(3, max(0, math.floor(blended + 0.5)))

    def values(self, gene_id: str) -> tuple[float, ...]:
        """A gene block's numbers (the brain's weights), blended value by value."""
        first, second = self._strands
        return tuple(
            self._dominance.blend(gene_id, a, b)
            for a, b in zip(first.values(gene_id), second.values(gene_id))
        )

    def is_homozygous(self, gene_id: str) -> bool:
        """Whether both strands carry the same digits for a gene."""
        first, second = self._strands
        return first.slice_of(gene_id) == second.slice_of(gene_id)

    # -------------------------------------------------------------------------
    # Reproduction
    # -------------------------------------------------------------------------

    def gamete(self, rng: random.Random, crossover: Crossover | None = None) -> DNA:
        """One haploid strand for a child: this genome's two strands recombined (meiosis).
        ``crossover`` is any strategy from ``DNA`` and defaults to ``DNA.crossover_linked``."""
        strategy = crossover if crossover is not None else DNA.crossover_linked
        first, second = self._strands
        return strategy(first, second, rng)

    def reproduce(
        self,
        partner: DiploidDNA | None,
        rng: random.Random,
        mutation_rate: float | None = None,
        crossover: Crossover | None = None,
        mutations_per_segment: Mapping[str, float] | None = None,
        position_bias: float | None = None,
        locality: float | None = None,
        gene_biases: Mapping[str, float] | None = None,
    ) -> Self:
        """Make a child. With a partner each parent contributes a mutated gamete; with none this
        genome's two strands are copied and mutated on their own (asexual reproduction). The child
        uses this genome's dominance model.

        ``crossover`` recombines a parent's two strands into its gamete. The mutation settings are
        those of ``DNA.mutated``, with one difference: ``mutations_per_segment`` and the layout
        defaults are expected changes **per child**, so each of the child's two strands gets half.
        A per-digit ``mutation_rate`` applies to every digit of both strands as it stands.
        """
        if mutation_rate is not None and mutations_per_segment is not None:
            raise ValueError("Set a mutation rate per digit or mutations per segment, not both.")
        if partner is not None:
            self._require_compatible(partner)
        per_child = None
        if mutation_rate is None:
            expected = self._strands[0].expected_mutations(mutations_per_segment)
            per_child = {segment: count / 2 for segment, count in expected.items()}

        def mutate(strand: DNA) -> DNA:
            return strand.mutated(
                rng, mutation_rate, per_child, position_bias, locality, gene_biases
            )

        if partner is None:
            return type(self)(*(mutate(strand) for strand in self._strands), self._dominance)
        mine = mutate(self.gamete(rng, crossover))
        theirs = mutate(partner.gamete(rng, crossover))
        return type(self)(mine, theirs, self._dominance)

    def _require_compatible(self, other: object) -> None:
        if not isinstance(other, DiploidDNA):
            raise TypeError("A diploid genome can only reproduce with another diploid genome.")
        if other.layout != self.layout:
            raise TypeError(
                f"Cannot reproduce across layouts: {self.layout.name!r} and {other.layout.name!r}."
            )

    # -------------------------------------------------------------------------
    # Serialisation
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly form; restore with ``DiploidDNA.from_dict``."""
        first, second = self._strands
        return {
            "ploidy": 2,
            "strands": [first.to_dict(), second.to_dict()],
            "dominance": self._dominance.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], layouts: Iterable[GenomeLayout]) -> Self:
        """Restore a genome; each strand checks its layout name and version."""
        if data.get("ploidy") != 2 or len(data.get("strands", ())) != 2:
            raise ValueError("Not a diploid genome: expected ploidy 2 and two strands.")
        layouts = tuple(layouts)
        first, second = (DNA.from_dict(strand, layouts) for strand in data["strands"])
        return cls(first, second, DominanceModel.from_dict(data.get("dominance", {})))
