"""DNA: fixed-length quaternary (base-4) genomes.

A genome is an immutable string of digits 0-3. Each subclass declares an ordered layout of genes,
and a gene is a run of consecutive digits decoded as a big-endian base-4 number. DNA knows nothing
about what a gene means; traits read genes through the descriptors on the subclass.

Every random operation takes a ``random.Random`` so runs can be seeded and tests are repeatable.
Operations return new DNA and never change the parent.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from typing import Any, ClassVar, Self, overload

BASES: tuple[int, ...] = (0, 1, 2, 3)
BASE_COUNT: int = len(BASES)

DEFAULT_MUTATION_RATE: float = 0.01
"""Chance that any one digit changes per reproduction (per digit, not per organism)."""


class Gene:
    """A run of ``width`` digits decoded as a float between 0.0 and 1.0.

    Declare genes in the class body of a DNA subclass; the order of declaration fixes their
    position in the sequence. Reading the attribute on an instance returns the decoded value.
    """

    def __init__(self, width: int = 4) -> None:
        if width < 1:
            raise ValueError("Gene width must be at least 1 digit.")
        self.width = width
        self.name = ""
        self.start = 0

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @property
    def end(self) -> int:
        return self.start + self.width

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> Self: ...
    @overload
    def __get__(self, obj: BaseDNA, objtype: type | None = None) -> float: ...
    def __get__(self, obj: BaseDNA | None, objtype: type | None = None) -> Self | float:
        if obj is None:
            return self
        return obj.decode_normalized(self.start, self.end)


class Locus(Gene):
    """A single digit read as a raw category 0-3 instead of a float."""

    def __init__(self) -> None:
        super().__init__(width=1)

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> Self: ...
    @overload
    def __get__(self, obj: BaseDNA, objtype: type | None = None) -> int: ...
    def __get__(self, obj: BaseDNA | None, objtype: type | None = None) -> Self | int:
        if obj is None:
            return self
        return obj.get_digit(self.start)


Crossover = Callable[["BaseDNA", "BaseDNA", random.Random], "BaseDNA"]
"""A crossover strategy: (parent_a, parent_b, rng) -> child."""


class BaseDNA:
    """Immutable fixed-length quaternary genome.

    Subclasses declare genes as class attributes (``Gene`` or ``Locus``). The genome length is the
    sum of the gene widths, so the layout is the single source of truth.
    """

    GENES: ClassVar[tuple[Gene, ...]] = ()
    STANDARD_LENGTH: ClassVar[int] = 0

    __slots__ = ("_sequence",)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        genes = tuple(value for value in vars(cls).values() if isinstance(value, Gene))
        if not genes:
            return  # an intermediate abstract class with no layout of its own
        position = 0
        for gene in genes:
            gene.start = position
            position += gene.width
        cls.GENES = genes
        cls.STANDARD_LENGTH = position

    def __init__(self, sequence: Iterable[int] | str) -> None:
        if self.STANDARD_LENGTH <= 0:
            raise TypeError(f"{type(self).__name__} declares no genes and cannot be instantiated.")
        if isinstance(sequence, str):
            digits = tuple(int(char) for char in sequence.strip())
        else:
            digits = tuple(int(value) for value in sequence)
        if len(digits) != self.STANDARD_LENGTH:
            raise ValueError(
                f"Sequence length mismatch: expected {self.STANDARD_LENGTH}, got {len(digits)}"
            )
        for digit in digits:
            if digit not in BASES:
                raise ValueError(f"Invalid quaternary digit: {digit}. Must be 0, 1, 2, or 3.")
        object.__setattr__(self, "_sequence", digits)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable.")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable.")

    # -------------------------------------------------------------------------
    # Construction
    # -------------------------------------------------------------------------

    @classmethod
    def random(cls, rng: random.Random) -> Self:
        """A genome with every digit drawn uniformly at random."""
        return cls(rng.choice(BASES) for _ in range(cls.STANDARD_LENGTH))

    @classmethod
    def from_string(cls, text: str) -> Self:
        return cls(text)

    # -------------------------------------------------------------------------
    # Value semantics
    # -------------------------------------------------------------------------

    @property
    def sequence(self) -> tuple[int, ...]:
        return self._sequence

    @property
    def length(self) -> int:
        return len(self._sequence)

    def __len__(self) -> int:
        return len(self._sequence)

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return NotImplemented
        assert isinstance(other, BaseDNA)
        return self._sequence == other._sequence

    def __hash__(self) -> int:
        return hash((type(self), self._sequence))

    def __str__(self) -> str:
        return "".join(str(digit) for digit in self._sequence)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(length={self.length}, sequence='{self}')"

    def distance(self, other: BaseDNA) -> float:
        """Fraction of digits that differ (0.0 identical, 1.0 every digit differs)."""
        self._require_compatible(other)
        differing = sum(1 for a, b in zip(self._sequence, other._sequence) if a != b)
        return differing / self.length

    # -------------------------------------------------------------------------
    # Serialisation
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, str]:
        """JSON-friendly form; restore with ``BaseDNA.from_dict``."""
        return {"type": type(self).__name__, "sequence": str(self)}

    @staticmethod
    def from_dict(data: dict[str, str]) -> BaseDNA:
        kind = data["type"]
        for subclass in _all_subclasses(BaseDNA):
            if subclass.__name__ == kind and subclass.STANDARD_LENGTH > 0:
                return subclass(data["sequence"])
        raise ValueError(f"Unknown DNA type: {kind!r}")

    # -------------------------------------------------------------------------
    # Genetic operations
    # -------------------------------------------------------------------------

    def mutated(self, rng: random.Random, mutation_rate: float = DEFAULT_MUTATION_RATE) -> Self:
        """Point mutation: each digit changes with probability ``mutation_rate``.

        A changed digit moves to one of the other three digits with equal chance. Returns a new
        genome; this one is unchanged.
        """
        _check_rate(mutation_rate)
        digits = list(self._sequence)
        for i, digit in enumerate(digits):
            if rng.random() < mutation_rate:
                digits[i] = (digit + rng.choice((1, 2, 3))) % BASE_COUNT
        return type(self)(digits)

    def crossover(self, partner: BaseDNA, rng: random.Random) -> Self:
        """Uniform per-digit crossover: each digit comes from either parent with equal chance."""
        self._require_compatible(partner)
        digits = [a if rng.random() < 0.5 else b for a, b in zip(self._sequence, partner._sequence)]
        return type(self)(digits)

    def crossover_one_point(self, partner: BaseDNA, rng: random.Random) -> Self:
        """One-point crossover: digits before a random cut from this parent, the rest from the
        partner. The parent that supplies the front is fixed (this one); callers wanting a random
        choice can swap the operands."""
        self._require_compatible(partner)
        if self.length < 2:
            raise ValueError("One-point crossover needs a genome of at least 2 digits.")
        cut = rng.randint(1, self.length - 1)
        return type(self)(self._sequence[:cut] + partner._sequence[cut:])

    def crossover_by_gene(self, partner: BaseDNA, rng: random.Random) -> Self:
        """Gene-level crossover: each whole gene comes from either parent with equal chance.

        Keeps every gene's value intact, so offspring genes are always one of the parents'
        versions rather than a digit-level blend.
        """
        self._require_compatible(partner)
        digits: list[int] = []
        for gene in self.GENES:
            source = self._sequence if rng.random() < 0.5 else partner._sequence
            digits.extend(source[gene.start : gene.end])
        return type(self)(digits)

    def clone_with_mutation(
        self, rng: random.Random, mutation_rate: float = DEFAULT_MUTATION_RATE
    ) -> Self:
        """Asexual reproduction: a copy of this genome subject only to point mutation."""
        return self.mutated(rng, mutation_rate)

    def reproduce(
        self,
        partner: BaseDNA | None,
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
        assert isinstance(child, type(self))
        return child.mutated(rng, mutation_rate)

    # -------------------------------------------------------------------------
    # Decoding
    # -------------------------------------------------------------------------

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
    # Internals
    # -------------------------------------------------------------------------

    def _require_compatible(self, other: BaseDNA) -> None:
        if type(self) is not type(other):
            raise TypeError(
                f"Cannot combine distinct DNA species: {type(self).__name__} vs "
                f"{type(other).__name__}"
            )


def _check_rate(rate: float) -> None:
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"Mutation rate must be between 0 and 1, got {rate}.")


def _all_subclasses(cls: type[BaseDNA]) -> list[type[BaseDNA]]:
    found: list[type[BaseDNA]] = []
    for sub in cls.__subclasses__():
        found.append(sub)
        found.extend(_all_subclasses(sub))
    return found


# =============================================================================
# Animal DNA (65 quaternary digits)
# =============================================================================


class AnimalDNA(BaseDNA):
    """Physical, five-sense, metabolic and behavioural genes for mobile organisms.

    Gene order (and so digit positions) matches the original prototype: 16 four-digit genes
    followed by one sex-strategy digit, 65 digits in all.
    """

    speed = Gene()
    agility = Gene()
    size = Gene()
    somatic_maint = Gene()

    sight_range = Gene()
    sight_fov = Gene()
    hearing = Gene()
    smell = Gene()
    touch = Gene()
    taste = Gene()

    herbivore_eff = Gene()
    carnivore_eff = Gene()
    aggression = Gene()
    fear = Gene()
    fertility = Gene()
    encoder_fidelity = Gene()

    sex_strategy = Locus()


# =============================================================================
# Plant DNA (24 quaternary digits)
# =============================================================================


class PlantDNA(BaseDNA):
    """Structural, metabolic, defensive and reproductive genes for sessile organisms."""

    max_biomass = Gene()
    growth_rate = Gene()
    toxicity = Gene()
    dispersal_radius = Gene()
    seed_clutch = Gene()
    root_reach = Gene()
