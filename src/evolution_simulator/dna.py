"""DNA: fixed-length quaternary (base-4) genomes.

A genome is an immutable string of digits 0-3. Its shape comes from a ``GenomeLayout``, an ordered
table of genes; a gene is a run of consecutive digits decoded as a big-endian base-4 number. DNA
only knows gene IDs and positions. It has no idea what any gene means: traits declare which gene
IDs they read (see ``trait_defs``), and the layouts in ``layouts`` are plain data.

Every random operation takes a ``random.Random`` so runs can be seeded and tests are repeatable.
Operations return new DNA and never change the parent.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Self

BASES: tuple[int, ...] = (0, 1, 2, 3)
BASE_COUNT: int = len(BASES)

DEFAULT_MUTATION_RATE: float = 0.01
"""Chance that any one digit changes per reproduction (per digit, not per organism)."""


@dataclass(frozen=True)
class GeneSpec:
    """One row of a layout table: a gene ID and how many digits it occupies."""

    id: str
    length: int = 4

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("A gene needs a non-empty ID.")
        if self.length < 1:
            raise ValueError(f"Gene {self.id!r} must be at least 1 digit long.")


@dataclass(frozen=True)
class Gene:
    """A gene placed in a layout: its digits are ``[start, end)``."""

    id: str
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class GenomeLayout:
    """An ordered gene table. Order fixes positions; the sum of lengths is the genome length.

    Bump ``version`` whenever genes are added, removed, resized or reordered: saved genomes carry
    the version and refuse to load against a different one.
    """

    name: str
    version: int
    specs: tuple[GeneSpec, ...]
    genes: tuple[Gene, ...] = field(init=False, repr=False, compare=False)
    length: int = field(init=False, compare=False)

    def __init__(self, name: str, version: int, specs: Iterable[GeneSpec]) -> None:
        specs = tuple(specs)
        if not specs:
            raise ValueError("A layout needs at least one gene.")
        ids = [spec.id for spec in specs]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate gene IDs in layout {name!r}.")
        placed: list[Gene] = []
        position = 0
        for spec in specs:
            placed.append(Gene(spec.id, position, position + spec.length))
            position += spec.length
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "specs", specs)
        object.__setattr__(self, "genes", tuple(placed))
        object.__setattr__(self, "length", position)

    def gene(self, gene_id: str) -> Gene:
        for gene in self.genes:
            if gene.id == gene_id:
                return gene
        raise KeyError(f"Layout {self.name!r} has no gene {gene_id!r}.")

    def __contains__(self, gene_id: object) -> bool:
        return any(gene.id == gene_id for gene in self.genes)

    @property
    def gene_ids(self) -> tuple[str, ...]:
        return tuple(gene.id for gene in self.genes)


Crossover = Callable[["DNA", "DNA", random.Random], "DNA"]
"""A crossover strategy: (parent_a, parent_b, rng) -> child."""


class DNA:
    """Immutable fixed-length quaternary genome shaped by a ``GenomeLayout``."""

    __slots__ = ("_layout", "_sequence")

    def __init__(self, layout: GenomeLayout, sequence: Iterable[int] | str) -> None:
        if isinstance(sequence, str):
            digits = tuple(int(char) for char in sequence.strip())
        else:
            digits = tuple(int(value) for value in sequence)
        if len(digits) != layout.length:
            raise ValueError(
                f"Sequence length mismatch: expected {layout.length}, got {len(digits)}"
            )
        for digit in digits:
            if digit not in BASES:
                raise ValueError(f"Invalid quaternary digit: {digit}. Must be 0, 1, 2, or 3.")
        object.__setattr__(self, "_layout", layout)
        object.__setattr__(self, "_sequence", digits)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("DNA is immutable.")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("DNA is immutable.")

    # -------------------------------------------------------------------------
    # Construction
    # -------------------------------------------------------------------------

    @classmethod
    def random(cls, layout: GenomeLayout, rng: random.Random) -> Self:
        """A genome with every digit drawn uniformly at random."""
        return cls(layout, (rng.choice(BASES) for _ in range(layout.length)))

    @classmethod
    def from_string(cls, layout: GenomeLayout, text: str) -> Self:
        return cls(layout, text)

    # -------------------------------------------------------------------------
    # Value semantics
    # -------------------------------------------------------------------------

    @property
    def layout(self) -> GenomeLayout:
        return self._layout

    @property
    def sequence(self) -> tuple[int, ...]:
        return self._sequence

    @property
    def length(self) -> int:
        return len(self._sequence)

    def __len__(self) -> int:
        return len(self._sequence)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DNA):
            return NotImplemented
        return self._layout == other._layout and self._sequence == other._sequence

    def __hash__(self) -> int:
        return hash((self._layout, self._sequence))

    def __str__(self) -> str:
        return "".join(str(digit) for digit in self._sequence)

    def __repr__(self) -> str:
        return f"DNA(layout={self._layout.name!r}, sequence='{self}')"

    def distance(self, other: DNA) -> float:
        """Fraction of digits that differ (0.0 identical, 1.0 every digit differs)."""
        self._require_compatible(other)
        differing = sum(1 for a, b in zip(self._sequence, other._sequence) if a != b)
        return differing / self.length

    # -------------------------------------------------------------------------
    # Serialisation
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly form; restore with ``DNA.from_dict``."""
        return {
            "layout": self._layout.name,
            "layout_version": self._layout.version,
            "sequence": str(self),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], layouts: Iterable[GenomeLayout]) -> Self:
        """Restore a genome, looking its layout up by name among ``layouts``."""
        for layout in layouts:
            if layout.name == data["layout"]:
                if data.get("layout_version") != layout.version:
                    raise ValueError(
                        f"Layout {layout.name!r} version {data.get('layout_version')!r} does not "
                        f"match the current version {layout.version}."
                    )
                return cls(layout, data["sequence"])
        raise ValueError(f"Unknown layout: {data['layout']!r}")

    # -------------------------------------------------------------------------
    # Reading genes (the only way anything reads DNA)
    # -------------------------------------------------------------------------

    def slice_of(self, gene_id: str) -> tuple[int, ...]:
        """The raw digits of a gene."""
        gene = self._layout.gene(gene_id)
        return self._sequence[gene.start : gene.end]

    def raw(self, gene_id: str) -> int:
        """A gene's digits as a big-endian base-4 integer."""
        gene = self._layout.gene(gene_id)
        return self.decode_int(gene.start, gene.end)

    def value(self, gene_id: str) -> float:
        """A gene as a float between 0.0 and 1.0."""
        gene = self._layout.gene(gene_id)
        return self.decode_normalized(gene.start, gene.end)

    def digit(self, gene_id: str) -> int:
        """The raw category (0-3) of a single-digit gene."""
        gene = self._layout.gene(gene_id)
        if gene.length != 1:
            raise ValueError(f"Gene {gene_id!r} is {gene.length} digits long, not a single digit.")
        return self._sequence[gene.start]

    def get_slice(self, start: int, end: int) -> tuple[int, ...]:
        """Digits in [start, end)."""
        if start < 0 or end > self.length or start >= end:
            raise IndexError(
                f"Invalid slice bounds: [{start}:{end}] for genome length {self.length}"
            )
        return self._sequence[start:end]

    def decode_int(self, start: int, end: int) -> int:
        """Digits in [start, end) as a big-endian base-4 integer."""
        value = 0
        for digit in self.get_slice(start, end):
            value = (value * BASE_COUNT) + digit
        return value

    def decode_normalized(self, start: int, end: int) -> float:
        """Digits in [start, end) as a float between 0.0 and 1.0."""
        max_possible = (BASE_COUNT ** (end - start)) - 1
        return self.decode_int(start, end) / max_possible

    def get_digit(self, index: int) -> int:
        """The raw digit at ``index``."""
        if index < 0 or index >= self.length:
            raise IndexError(f"Index {index} out of bounds for genome length {self.length}")
        return self._sequence[index]

    # -------------------------------------------------------------------------
    # Genetic operations
    # -------------------------------------------------------------------------

    def mutated(self, rng: random.Random, mutation_rate: float = DEFAULT_MUTATION_RATE) -> Self:
        """Point mutation: each digit changes with probability ``mutation_rate``.

        A changed digit moves to one of the other three digits with equal chance. Returns a new
        genome; this one is unchanged.
        """
        if not 0.0 <= mutation_rate <= 1.0:
            raise ValueError(f"Mutation rate must be between 0 and 1, got {mutation_rate}.")
        digits = list(self._sequence)
        for i, digit in enumerate(digits):
            if rng.random() < mutation_rate:
                digits[i] = (digit + rng.choice((1, 2, 3))) % BASE_COUNT
        return type(self)(self._layout, digits)

    def crossover(self, partner: DNA, rng: random.Random) -> Self:
        """Uniform per-digit crossover: each digit comes from either parent with equal chance."""
        self._require_compatible(partner)
        digits = [a if rng.random() < 0.5 else b for a, b in zip(self._sequence, partner._sequence)]
        return type(self)(self._layout, digits)

    def crossover_one_point(self, partner: DNA, rng: random.Random) -> Self:
        """One-point crossover: digits before a random cut from this parent, the rest from the
        partner. The parent that supplies the front is fixed (this one); callers wanting a random
        choice can swap the operands."""
        self._require_compatible(partner)
        if self.length < 2:
            raise ValueError("One-point crossover needs a genome of at least 2 digits.")
        cut = rng.randint(1, self.length - 1)
        return type(self)(self._layout, self._sequence[:cut] + partner._sequence[cut:])

    def crossover_by_gene(self, partner: DNA, rng: random.Random) -> Self:
        """Gene-level crossover: each whole gene comes from either parent with equal chance.

        Keeps every gene's value intact, so offspring genes are always one of the parents'
        versions rather than a digit-level blend.
        """
        self._require_compatible(partner)
        digits: list[int] = []
        for gene in self._layout.genes:
            source = self._sequence if rng.random() < 0.5 else partner._sequence
            digits.extend(source[gene.start : gene.end])
        return type(self)(self._layout, digits)

    def clone_with_mutation(
        self, rng: random.Random, mutation_rate: float = DEFAULT_MUTATION_RATE
    ) -> Self:
        """Asexual reproduction: a copy of this genome subject only to point mutation."""
        return self.mutated(rng, mutation_rate)

    def reproduce(
        self,
        partner: DNA | None,
        rng: random.Random,
        mutation_rate: float = DEFAULT_MUTATION_RATE,
        crossover: Crossover | None = None,
    ) -> Self:
        """Single reproduction entry point.

        With no partner this clones and mutates. With a partner it crosses over (uniform per-digit
        unless ``crossover`` supplies another strategy) and then mutates.
        """
        if partner is None:
            return self.clone_with_mutation(rng, mutation_rate)
        strategy = crossover if crossover is not None else type(self).crossover
        child = strategy(self, partner, rng)
        return child.mutated(rng, mutation_rate)

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    def _require_compatible(self, other: DNA) -> None:
        if self._layout != other._layout:
            raise TypeError(
                f"Cannot combine distinct DNA species: {self._layout.name!r} vs "
                f"{other._layout.name!r}"
            )
