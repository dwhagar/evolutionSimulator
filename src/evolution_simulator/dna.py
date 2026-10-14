"""DNA: fixed-length quaternary (base-4) genomes.

A genome is an immutable string of digits 0-3. Its shape comes from a ``GenomeLayout``, an ordered
table of genes; a gene is a run of consecutive digits decoded as a big-endian base-4 number. DNA
only knows gene IDs and positions. It has no idea what any gene means: traits declare which gene
IDs they read (see ``trait_defs``), and the layouts in ``layouts`` are plain data.

A ``BlockSpec`` is a gene that holds an array of numbers (the brain's weights) instead of one value.
Genes belong to named segments (body, brain) so mutation can be set per segment, and recombination can
treat every gene, and every group of values inside a block, as one unit.

Every random operation takes a ``random.Random`` so runs can be seeded and tests are repeatable.
Operations return new DNA and never change the parent.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, Self

BASES: tuple[int, ...] = (0, 1, 2, 3)
BASE_COUNT: int = len(BASES)

DEFAULT_MUTATION_RATE: float = 0.01
"""Chance that any one digit changes per reproduction (per digit, not per organism)."""

DEFAULT_POSITION_BIAS: float = 0.5
"""How much less often each more significant digit of a value mutates than the one below it.
1.0 treats every digit alike (the original behaviour); 0.5 makes the last digit of a four-digit gene
twice as likely to change as the one before it, so most mutations are small and a few are big jumps."""

MIN_POSITION_BIAS: float = 0.1
"""Lowest bias ``position_bias_for_step`` returns, so the top digit always keeps a chance to jump."""

DEFAULT_LOCALITY: float = 0.0
"""Chance that a changed digit moves to a neighbouring digit (+-1) instead of a random other digit.
0.0 is fully random (the original behaviour); 1.0 always takes a neighbour."""

DEFAULT_SEGMENT: str = "body"
"""Segment a gene belongs to unless it names another."""

DEFAULT_MEAN_CUTS: float = 1.0
"""Expected crossover cut points per genome (``crossover_linked``)."""

DEFAULT_GENE_FIDELITY: float = 0.9
"""How closely crossover follows whole genes: the chance that a cut falls exactly between genes.
1.0 always cuts between genes; 0.0 always cuts somewhere inside a gene."""


@dataclass(frozen=True)
class GeneSpec:
    """One row of a layout table: a gene ID and how many digits it occupies."""

    id: str
    length: int = 4
    segment: str = DEFAULT_SEGMENT
    """The part of the genome this gene belongs to; the genes of a segment must be consecutive."""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("A gene needs a non-empty ID.")
        if self.length < 1:
            raise ValueError(f"Gene {self.id!r} must be at least 1 digit long.")
        if not self.segment:
            raise ValueError(f"Gene {self.id!r} needs a non-empty segment name.")


@dataclass(frozen=True)
class BlockSpec:
    """A gene that is an array of ``count`` numbers, each ``digits_per_value`` digits long.

    Each value decodes onto ``low``..``high``: with ``levels`` possible values the level ``n`` maps to
    ``low + (high - low) * n / (levels - 1)``, so the end points are exactly ``low`` and ``high``.
    Two digits over -2 to 2 gives 16 levels and no exact zero (the closest are about +-0.13).

    ``groups`` splits the values into consecutive blocks of the given sizes that recombination keeps
    together (the brain uses one block per hidden neuron). The default is one block.
    """

    id: str
    count: int
    digits_per_value: int = 2
    low: float = 0.0
    high: float = 1.0
    groups: tuple[int, ...] = ()
    segment: str = DEFAULT_SEGMENT

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("A gene block needs a non-empty ID.")
        if self.count < 1:
            raise ValueError(f"Gene block {self.id!r} needs at least one value.")
        if self.digits_per_value < 1:
            raise ValueError(f"Gene block {self.id!r} needs at least one digit per value.")
        if not self.low < self.high:
            raise ValueError(
                f"Gene block {self.id!r} needs low < high, got {self.low}, {self.high}."
            )
        if not self.segment:
            raise ValueError(f"Gene block {self.id!r} needs a non-empty segment name.")
        groups = tuple(self.groups) or (self.count,)
        if any(size < 1 for size in groups) or sum(groups) != self.count:
            raise ValueError(
                f"Gene block {self.id!r}: group sizes {groups} must be positive and add up to "
                f"{self.count}."
            )
        object.__setattr__(self, "groups", groups)

    @property
    def length(self) -> int:
        """Digits the block occupies."""
        return self.count * self.digits_per_value

    @property
    def levels(self) -> int:
        """Distinct values one entry can take."""
        return BASE_COUNT**self.digits_per_value

    def decode(self, digits: Sequence[int]) -> tuple[float, ...]:
        """Decode this block's digits (``length`` of them) into its values."""
        if len(digits) != self.length:
            raise ValueError(
                f"Gene block {self.id!r} takes {self.length} digits, got {len(digits)}."
            )
        step = (self.high - self.low) / (self.levels - 1)
        size = self.digits_per_value
        values: list[float] = []
        for i in range(0, self.length, size):
            level = 0
            for digit in digits[i : i + size]:
                level = level * BASE_COUNT + digit
            values.append(self.low + step * level)
        return tuple(values)

    def encode(self, values: Sequence[float]) -> tuple[int, ...]:
        """The digits that decode closest to ``values`` (each clamped to the range)."""
        if len(values) != self.count:
            raise ValueError(
                f"Gene block {self.id!r} takes {self.count} values, got {len(values)}."
            )
        top = self.levels - 1
        step = (self.high - self.low) / top
        digits: list[int] = []
        for value in values:
            level = min(top, max(0, round((value - self.low) / step)))
            chunk: list[int] = []
            for _ in range(self.digits_per_value):
                level, digit = divmod(level, BASE_COUNT)
                chunk.append(digit)
            digits.extend(reversed(chunk))
        return tuple(digits)


@dataclass(frozen=True)
class Gene:
    """A gene placed in a layout: its digits are ``[start, end)``."""

    id: str
    start: int
    end: int
    segment: str = DEFAULT_SEGMENT
    block: BlockSpec | None = None
    """Set when the gene is an array of values rather than one value."""

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def value_spans(self) -> tuple[tuple[int, int], ...]:
        """Digit ranges (start, end) that each decode to one number: the gene itself, or for a
        block each of its values. Within a span the first digit is the most significant."""
        if self.block is None:
            return ((self.start, self.end),)
        width = self.block.digits_per_value
        return tuple((at, at + width) for at in range(self.start, self.end, width))

    @property
    def units(self) -> tuple[tuple[int, int], ...]:
        """Digit ranges (start, end) that recombination keeps whole: the gene itself, or for a
        block each of its groups."""
        if self.block is None:
            return ((self.start, self.end),)
        bounds: list[tuple[int, int]] = []
        position = self.start
        for size in self.block.groups:
            width = size * self.block.digits_per_value
            bounds.append((position, position + width))
            position += width
        return tuple(bounds)


@dataclass(frozen=True)
class GenomeLayout:
    """An ordered gene table. Order fixes positions; the sum of lengths is the genome length.

    Bump ``version`` whenever genes are added, removed, resized or reordered: saved genomes carry
    the version and refuse to load against a different one.
    """

    name: str
    version: int
    specs: tuple[GeneSpec | BlockSpec, ...]
    genes: tuple[Gene, ...] = field(init=False, repr=False, compare=False)
    length: int = field(init=False, compare=False)
    segments: Mapping[str, tuple[int, int]] = field(init=False, repr=False, compare=False)
    """Digit range (start, end) of each segment, in layout order."""
    units: tuple[tuple[int, int], ...] = field(init=False, repr=False, compare=False)
    """Digit ranges recombination keeps whole: every gene, or every group inside a block."""
    default_mutations: Mapping[str, float] = field(init=False, repr=False, compare=False)
    """Expected changed digits per child for each segment, used when a caller sets no rate."""
    position_bias: float = field(init=False, repr=False, compare=False)
    """Default for ``DNA.mutated``: how much rarer each more significant digit is to change."""
    locality: float = field(init=False, repr=False, compare=False)
    """Default for ``DNA.mutated``: chance a changed digit moves to a neighbouring digit."""

    def __init__(
        self,
        name: str,
        version: int,
        specs: Iterable[GeneSpec | BlockSpec],
        segment_mutations: Mapping[str, float] | None = None,
        position_bias: float = DEFAULT_POSITION_BIAS,
        locality: float = DEFAULT_LOCALITY,
    ) -> None:
        """``segment_mutations`` sets the expected changed digits per child for the segments it
        names (a segment left out gets ``DEFAULT_MUTATION_RATE`` per digit). ``position_bias`` and
        ``locality`` are the layout's default mutation shape (see ``DNA.mutated``). All three are
        defaults for callers, not part of the layout's identity."""
        _check_bias(position_bias)
        _check_locality(locality)
        specs = tuple(specs)
        if not specs:
            raise ValueError("A layout needs at least one gene.")
        ids = [spec.id for spec in specs]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate gene IDs in layout {name!r}.")
        placed: list[Gene] = []
        segments: dict[str, tuple[int, int]] = {}
        position = 0
        previous = ""
        for spec in specs:
            block = spec if isinstance(spec, BlockSpec) else None
            gene = Gene(spec.id, position, position + spec.length, spec.segment, block)
            placed.append(gene)
            position = gene.end
            if spec.segment != previous and spec.segment in segments:
                raise ValueError(
                    f"Layout {name!r}: genes of segment {spec.segment!r} must be consecutive."
                )
            first = segments.get(spec.segment, (gene.start, gene.start))[0]
            segments[spec.segment] = (first, gene.end)
            previous = spec.segment
        wanted = dict(segment_mutations or {})
        unknown = set(wanted) - set(segments)
        if unknown:
            raise ValueError(
                f"Layout {name!r} sets mutation for unknown segments {sorted(unknown)}."
            )
        if any(value < 0 for value in wanted.values()):
            raise ValueError(f"Layout {name!r} sets a negative mutation count.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "specs", specs)
        object.__setattr__(self, "genes", tuple(placed))
        object.__setattr__(self, "length", position)
        object.__setattr__(self, "segments", segments)
        object.__setattr__(self, "units", tuple(unit for gene in placed for unit in gene.units))
        object.__setattr__(self, "position_bias", position_bias)
        object.__setattr__(self, "locality", locality)
        object.__setattr__(
            self,
            "default_mutations",
            {
                segment: wanted.get(segment, DEFAULT_MUTATION_RATE * (end - start))
                for segment, (start, end) in segments.items()
            },
        )

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


def _check_bias(bias: float) -> None:
    if not 0.0 < bias <= 1.0:
        raise ValueError(f"Position bias must be above 0 and at most 1, got {bias}.")


def _check_locality(locality: float) -> None:
    if not 0.0 <= locality <= 1.0:
        raise ValueError(f"Locality must be between 0 and 1, got {locality}.")


def _digit_weights(width: int, bias: float) -> tuple[float, ...]:
    """Relative chance of each digit of a ``width``-digit value changing, most significant first.
    Each digit is ``bias`` times as likely as the one below it, scaled to a mean of 1 so a value's
    total mutation chance does not depend on the bias."""
    raw = [bias ** (width - 1 - i) for i in range(width)]
    mean = sum(raw) / width
    return tuple(weight / mean for weight in raw)


def position_bias_for_step(width: int, step: float) -> float:
    """The position bias at which a mutation in a ``width``-digit value moves it by ``step`` of its
    range on average (a changed digit becomes a random other digit; a trait's ``mutation_step``).

    Returns 1.0 when even evenly spread mutations are smaller than ``step`` and
    ``MIN_POSITION_BIAS`` when even the strongest bias is larger.
    """
    if width < 1:
        raise ValueError(f"A value needs at least one digit, got {width}.")
    if not 0.0 < step <= 1.0:
        raise ValueError(f"Mutation step must be above 0 and at most 1, got {step}.")
    if width == 1:
        return 1.0  # nothing to weight
    # Replacing a digit by a random other one moves it 5/3 places on average (0.. 3 apart).
    size = [5 / 3 * BASE_COUNT**rank / (BASE_COUNT**width - 1) for rank in range(width)]

    def typical(bias: float) -> float:
        weights = [bias**rank for rank in range(width)]
        return sum(w * s for w, s in zip(weights, size)) / sum(weights)

    if typical(1.0) <= step:
        return 1.0
    if typical(MIN_POSITION_BIAS) >= step:
        return MIN_POSITION_BIAS
    low, high = MIN_POSITION_BIAS, 1.0
    for _ in range(40):
        middle = (low + high) / 2
        if typical(middle) < step:
            low = middle
        else:
            high = middle
    return (low + high) / 2


class Genome(Protocol):
    """What the rest of the code needs from a genome: the reads traits and the brain use, plus
    reproduction. ``DNA`` (one strand, haploid) and ``DiploidDNA`` (two strands, in ``diploid.py``)
    both provide it, so an organism is built from either without knowing which."""

    @property
    def layout(self) -> GenomeLayout: ...

    @property
    def ploidy(self) -> int: ...

    def value(self, gene_id: str) -> float: ...

    def digit(self, gene_id: str) -> int: ...

    def values(self, gene_id: str) -> tuple[float, ...]: ...

    def distance(self, other: Any) -> float: ...

    def reproduce(self, partner: Any, rng: random.Random, *args: Any, **kwargs: Any) -> Any: ...


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
    def ploidy(self) -> int:
        """Copies of each gene: 1 for a plain ``DNA`` (haploid)."""
        return 1

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

    def values(self, gene_id: str) -> tuple[float, ...]:
        """The numbers in a gene block (the brain's weights), decoded onto the block's range."""
        gene = self._layout.gene(gene_id)
        if gene.block is None:
            raise ValueError(f"Gene {gene_id!r} is not a gene block; use value() or digit().")
        return gene.block.decode(self._sequence[gene.start : gene.end])

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

    def mutated(
        self,
        rng: random.Random,
        mutation_rate: float | None = None,
        mutations_per_segment: Mapping[str, float] | None = None,
        position_bias: float | None = None,
        locality: float | None = None,
        gene_biases: Mapping[str, float] | None = None,
    ) -> Self:
        """Point mutation. Returns a new genome; this one is unchanged.

        *How many digits change.* With ``mutation_rate`` every digit changes with that probability,
        whatever segment it is in. With ``mutations_per_segment`` each named segment gets that
        expected number of changed digits per child, and segments left out keep the layout's
        ``default_mutations``. This stops a long segment (the brain's hundreds of digits) from
        swamping the mutation count. With neither, the layout's ``default_mutations`` apply (0.01
        per digit unless the layout says otherwise). The two settings cannot be combined.

        *Which digits change.* The first digit of a gene carries most of its range, so a change
        there is a big jump and a change in the last digit is a tiny nudge. ``position_bias`` is how
        much rarer each more significant digit is to change than the one below it: 1.0 treats all
        digits alike, 0.5 (the default, the layout's ``position_bias``) makes most mutations small
        and keeps a few big jumps, and smaller values favour the low digits more. It reshapes the
        chances inside each value without changing how many digits change in total.
        ``gene_biases`` sets it per gene ID (for example from ``TraitSet.position_biases()``); a
        gene left out uses ``position_bias``.

        *What a changed digit becomes.* With chance ``locality`` (default the layout's ``locality``,
        0.0) it moves to a neighbouring digit (+-1, so the value stays close in sequence); otherwise
        it becomes one of the other three digits with equal chance.
        """
        if mutation_rate is not None and mutations_per_segment is not None:
            raise ValueError("Set a mutation rate per digit or mutations per segment, not both.")
        bias = self._layout.position_bias if position_bias is None else position_bias
        near = self._layout.locality if locality is None else locality
        _check_bias(bias)
        _check_locality(near)
        probabilities = [0.0] * self.length
        if mutation_rate is not None:
            if not 0.0 <= mutation_rate <= 1.0:
                raise ValueError(f"Mutation rate must be between 0 and 1, got {mutation_rate}.")
            probabilities = [mutation_rate] * self.length
        else:
            expected = self.expected_mutations(mutations_per_segment)
            for name, (start, end) in self._layout.segments.items():
                probabilities[start:end] = [min(1.0, expected[name] / (end - start))] * (
                    end - start
                )
        self._apply_position_bias(probabilities, bias, gene_biases)
        digits = list(self._sequence)
        for i, digit in enumerate(digits):
            if rng.random() < probabilities[i]:
                if near > 0.0 and rng.random() < near:
                    digits[i] = rng.choice(
                        [d for d in (digit - 1, digit + 1) if 0 <= d < BASE_COUNT]
                    )
                else:
                    digits[i] = (digit + rng.choice((1, 2, 3))) % BASE_COUNT
        return type(self)(self._layout, digits)

    def expected_mutations(
        self, mutations_per_segment: Mapping[str, float] | None = None
    ) -> dict[str, float]:
        """Expected changed digits per child for each segment: the layout's defaults, with any
        segments named in ``mutations_per_segment`` replaced."""
        expected = dict(self._layout.default_mutations)
        for name, value in (mutations_per_segment or {}).items():
            if name not in self._layout.segments:
                raise ValueError(
                    f"Unknown segment {name!r}; layout {self._layout.name!r} has "
                    f"{sorted(self._layout.segments)}."
                )
            if value < 0:
                raise ValueError(
                    f"Mutations for segment {name!r} must not be negative, got {value}."
                )
            expected[name] = value
        return expected

    def _apply_position_bias(
        self, probabilities: list[float], bias: float, gene_biases: Mapping[str, float] | None
    ) -> None:
        """Redistribute each value's mutation chance over its digits (see ``mutated``)."""
        per_gene = dict(gene_biases or {})
        for gene_id, value in per_gene.items():
            if gene_id not in self._layout:
                raise ValueError(f"Layout {self._layout.name!r} has no gene {gene_id!r}.")
            _check_bias(value)
        for gene in self._layout.genes:
            gene_bias = per_gene.get(gene.id, bias)
            if gene_bias == 1.0:
                continue
            for start, end in gene.value_spans:
                if end - start < 2:
                    continue
                for offset, weight in enumerate(_digit_weights(end - start, gene_bias)):
                    if probabilities[start + offset] < 1.0:  # a certain change stays certain
                        probabilities[start + offset] = min(
                            1.0, probabilities[start + offset] * weight
                        )

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

    def crossover_linked(
        self,
        partner: DNA,
        rng: random.Random,
        mean_cuts: float = DEFAULT_MEAN_CUTS,
        gene_fidelity: float = DEFAULT_GENE_FIDELITY,
    ) -> Self:
        """Cut-point crossover that follows genes, the default for reproduction (``DNA.7``).

        The genome is read start to finish, taking digits from one parent until a cut point, then
        from the other, and so on. The first parent is chosen at random.

        * ``mean_cuts`` is the expected number of cut points in the whole genome. A value of 1 or
          more always makes at least one cut (as meiosis does) and averages ``mean_cuts``; below 1 it
          is the chance of making a single cut.
        * Cuts normally fall between units: between genes, or between groups inside a gene block (a
          hidden neuron stays whole). ``gene_fidelity`` is the chance that a cut does so. With the
          remaining chance the cut lands at a random digit inside the unit that follows it, so that
          one unit is a digit-level mix of both parents, which is the slightly odd crossover the
          owner asked for. 1.0 keeps every unit whole; 0.0 makes every cut inside a unit.

        Neighbouring genes tend to travel together, so the settings also set how strong linkage is.
        """
        self._require_compatible(partner)
        if mean_cuts < 0:
            raise ValueError(f"Mean cuts must not be negative, got {mean_cuts}.")
        if not 0.0 <= gene_fidelity <= 1.0:
            raise ValueError(f"Gene fidelity must be between 0 and 1, got {gene_fidelity}.")
        units = self._layout.units
        boundaries = len(units) - 1
        count = min(boundaries, _cut_count(rng, mean_cuts))
        positions: list[int] = []
        for index in rng.sample(range(1, boundaries + 1), count):
            start, end = units[index]
            if end - start > 1 and rng.random() >= gene_fidelity:
                positions.append(rng.randint(start + 1, end - 1))
            else:
                positions.append(start)
        positions.sort()
        source, other = (self._sequence, partner._sequence)
        if rng.random() < 0.5:
            source, other = other, source
        digits: list[int] = []
        previous = 0
        for position in [*positions, self.length]:
            digits.extend(source[previous:position])
            source, other = other, source
            previous = position
        return type(self)(self._layout, digits)

    def crossover_by_unit(self, partner: DNA, rng: random.Random) -> Self:
        """Block-aware crossover: each whole unit comes from either parent with equal chance.

        A unit is a gene, or one group of values inside a gene block. For the brain that is one hidden
        neuron with its incoming and outgoing weights, so a child gets whole neurons from either
        parent and never a blend inside one (the "competing conventions" problem in the brain
        design note). On a layout with no blocks this is the same as ``crossover_by_gene``.
        """
        self._require_compatible(partner)
        digits: list[int] = []
        for start, end in self._layout.units:
            source = self._sequence if rng.random() < 0.5 else partner._sequence
            digits.extend(source[start:end])
        return type(self)(self._layout, digits)

    def clone_with_mutation(
        self,
        rng: random.Random,
        mutation_rate: float | None = None,
        mutations_per_segment: Mapping[str, float] | None = None,
        position_bias: float | None = None,
        locality: float | None = None,
        gene_biases: Mapping[str, float] | None = None,
    ) -> Self:
        """Asexual reproduction: a copy of this genome subject only to point mutation."""
        return self.mutated(
            rng, mutation_rate, mutations_per_segment, position_bias, locality, gene_biases
        )

    def reproduce(
        self,
        partner: DNA | None,
        rng: random.Random,
        mutation_rate: float | None = None,
        crossover: Crossover | None = None,
        mutations_per_segment: Mapping[str, float] | None = None,
        position_bias: float | None = None,
        locality: float | None = None,
        gene_biases: Mapping[str, float] | None = None,
    ) -> Self:
        """Single reproduction entry point.

        With no partner this clones and mutates. With a partner it crosses over (``crossover_linked``
        with its default settings, unless ``crossover`` supplies another strategy, for example
        ``functools.partial(DNA.crossover_linked, mean_cuts=2, gene_fidelity=1.0)`` or
        ``DNA.crossover``) and then mutates. Mutation settings are as for ``mutated``.
        """
        if partner is None:
            return self.clone_with_mutation(
                rng, mutation_rate, mutations_per_segment, position_bias, locality, gene_biases
            )
        strategy = crossover if crossover is not None else type(self).crossover_linked
        child = strategy(self, partner, rng)
        return child.mutated(
            rng, mutation_rate, mutations_per_segment, position_bias, locality, gene_biases
        )

    def replaced(self, gene_id: str, digits: Iterable[int] | str) -> Self:
        """A copy with the digits of one gene replaced (for example with ``BlockSpec.encode``)."""
        gene = self._layout.gene(gene_id)
        new = tuple(int(d) for d in digits)
        if len(new) != gene.length:
            raise ValueError(f"Gene {gene_id!r} takes {gene.length} digits, got {len(new)}.")
        return type(self)(
            self._layout, self._sequence[: gene.start] + new + self._sequence[gene.end :]
        )

    def with_value(self, gene_id: str, value: float) -> Self:
        """A copy with a gene set to the digits nearest ``value`` (0.0 to 1.0, as ``value`` reads it)."""
        gene = self._layout.gene(gene_id)
        top = 4**gene.length - 1
        number = round(min(1.0, max(0.0, value)) * top)
        digits = []
        for _ in range(gene.length):
            number, digit = divmod(number, 4)
            digits.append(digit)
        return self.replaced(gene_id, reversed(digits))

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    def _require_compatible(self, other: DNA) -> None:
        if self._layout != other._layout:
            raise TypeError(
                f"Cannot combine distinct DNA species: {self._layout.name!r} vs "
                f"{other._layout.name!r}"
            )


def _cut_count(rng: random.Random, mean_cuts: float) -> int:
    """Number of cut points. At least one when ``mean_cuts`` >= 1, averaging ``mean_cuts``."""
    if mean_cuts <= 0:
        return 0
    if mean_cuts < 1:
        return 1 if rng.random() < mean_cuts else 0
    extra = mean_cuts - 1.0
    count = 1
    if extra > 0:
        t = rng.expovariate(extra)
        while t < 1.0:
            count += 1
            t += rng.expovariate(extra)
    return count
