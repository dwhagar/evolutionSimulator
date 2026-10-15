"""Genome distance as one integer (DNA.17): the same numbers as comparing digit by digit, much faster."""

import random
from operator import ne

import pytest
from world_support import hourly_world

from evolution_simulator.diploid import DiploidDNA
from evolution_simulator.dna import DNA, GeneSpec, GenomeLayout, differing_digits
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT


def reference_distance(a: DNA, b: DNA) -> float:
    """What ``DNA.distance`` was before DNA.17: compare the digits one by one."""
    return sum(map(ne, a.sequence, b.sequence)) / a.length


def reference_diploid_distance(a: DiploidDNA, b: DiploidDNA) -> float:
    a1, a2 = a.strands
    b1, b2 = b.strands
    straight = reference_distance(a1, b1) + reference_distance(a2, b2)
    crossed = reference_distance(a1, b2) + reference_distance(a2, b1)
    return min(straight, crossed) / 2


def layout_of(length: int) -> GenomeLayout:
    return GenomeLayout(f"len{length}", 1, [GeneSpec("g", length)])


ODD_LENGTHS = (1, 2, 3, 5, 7, 31, 32, 33, 63, 64, 65, 100, 127, 128, 129, 1001)
LAYOUTS = (ANIMAL_LAYOUT, PLANT_LAYOUT, *(layout_of(n) for n in ODD_LENGTHS))


def partner_of(dna: DNA, rng: random.Random) -> DNA:
    """A genome to compare ``dna`` with, of one of the shapes distances see in a world."""
    kind = rng.randrange(6)
    digits = list(dna.sequence)
    if kind == 0:  # a stranger
        return DNA.random(dna.layout, rng)
    if kind == 1:  # identical
        return DNA(dna.layout, digits)
    if kind == 2:  # every digit different
        return DNA(dna.layout, [(d + rng.randrange(1, 4)) % 4 for d in digits])
    if kind == 3:  # a few digits changed
        for _ in range(rng.randrange(1, 6)):
            at = rng.randrange(len(digits))
            digits[at] = (digits[at] + rng.randrange(1, 4)) % 4
        return DNA(dna.layout, digits)
    if kind == 4:  # the first and last digits only
        digits[0] = (digits[0] + 1) % 4
        digits[-1] = (digits[-1] + 2) % 4
        return DNA(dna.layout, digits)
    cut = rng.randrange(len(digits) + 1)  # one end of a stranger's
    return DNA(dna.layout, digits[:cut] + list(DNA.random(dna.layout, rng).sequence)[cut:])


@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda layout: f"{layout.name}-{layout.length}")
def test_the_packed_distance_equals_the_digit_by_digit_one_on_thousands_of_pairs(layout):
    rng = random.Random(layout.length * 7919 + 1)
    pairs = 1500 if layout.length < 300 else 400
    for _ in range(pairs):
        a = DNA.random(layout, rng)
        b = partner_of(a, rng)
        assert a.distance(b) == reference_distance(a, b)  # exact: same count, same division
        assert b.distance(a) == a.distance(b)


def test_identical_and_opposite_genomes_are_zero_and_one():
    for layout in LAYOUTS:
        zero = DNA(layout, [0] * layout.length)
        three = DNA(layout, [3] * layout.length)
        assert zero.distance(zero) == 0.0 and zero.distance(three) == 1.0
        assert DNA(layout, [1] * layout.length).distance(DNA(layout, [2] * layout.length)) == 1.0


@pytest.mark.parametrize("layout", [ANIMAL_LAYOUT, PLANT_LAYOUT, layout_of(7), layout_of(65)])
def test_diploid_distance_equals_the_old_one_with_either_pairing_of_strands(layout):
    rng = random.Random(layout.length + 5)
    for _ in range(600):
        a1, a2 = DNA.random(layout, rng), DNA.random(layout, rng)
        b1 = partner_of(a1, rng)
        b2 = partner_of(a2, rng) if rng.random() < 0.5 else partner_of(a1, rng)
        a, b = DiploidDNA(a1, a2), DiploidDNA(b1, b2)
        expected = reference_diploid_distance(a, b)
        assert a.distance(b) == expected
        assert a.distance(DiploidDNA(b2, b1)) == expected  # the strand order means nothing
        assert b.distance(a) == expected


def test_homozygous_and_heterozygous_diploids_agree_with_the_old_distance():
    rng = random.Random(3)
    one, other = DNA.random(ANIMAL_LAYOUT, rng), DNA.random(ANIMAL_LAYOUT, rng)
    homozygous, mixed = DiploidDNA(one, one), DiploidDNA(one, other)
    for a, b in (
        (homozygous, mixed),
        (mixed, homozygous),
        (mixed, mixed),
        (homozygous, homozygous),
    ):
        assert a.distance(b) == reference_diploid_distance(a, b)
    assert homozygous.distance(homozygous) == 0.0


def test_the_errors_are_the_same_as_before():
    rng = random.Random(4)
    with pytest.raises(TypeError, match="distinct DNA species"):
        DNA.random(ANIMAL_LAYOUT, rng).distance(DNA.random(PLANT_LAYOUT, rng))
    with pytest.raises(TypeError, match="another diploid genome"):
        DiploidDNA(*(DNA.random(ANIMAL_LAYOUT, rng) for _ in range(2))).distance(
            DNA.random(ANIMAL_LAYOUT, rng)
        )


def test_layouts_that_are_equal_but_not_the_same_object_still_compare():
    first, second = layout_of(9), layout_of(9)
    assert first is not second and first == second
    a, b = DNA(first, "012301230"), DNA(second, "012301231")
    assert a.distance(b) == pytest.approx(1 / 9)


# --- the packed integer ----------------------------------------------------------------------------


def test_packed_is_the_digits_read_as_a_base_4_number_and_is_made_once():
    dna = DNA(layout_of(8), "01230123")
    assert dna.packed == int("01230123", 4)
    assert DNA(layout_of(3), "000").packed == 0
    assert DNA(ANIMAL_LAYOUT, "3" * ANIMAL_LAYOUT.length).packed == 4**ANIMAL_LAYOUT.length - 1
    first = dna.packed
    assert dna.packed is first  # the same object: kept, not rebuilt


def test_differing_digits_counts_digits_not_bits():
    # 0 and 3 differ in both bits, 1 and 2 in both, 0 and 1 in one: each is one digit
    assert differing_digits(int("0123", 4), int("3210", 4), 4) == 4
    assert differing_digits(int("0000", 4), int("1111", 4), 4) == 4
    assert differing_digits(int("0123", 4), int("0123", 4), 4) == 0
    assert differing_digits(int("0123", 4), int("0133", 4), 4) == 1


def test_the_cache_is_not_part_of_the_genome():
    cached, fresh = DNA(layout_of(6), "012012"), DNA(layout_of(6), "012012")
    cached.distance(fresh)  # fills the cache of both
    assert cached.packed == fresh.packed
    clean = DNA(layout_of(6), "012012")
    assert cached == clean and hash(cached) == hash(clean)
    assert cached.to_dict() == clean.to_dict()
    assert set(cached.to_dict()) == {"layout", "layout_version", "sequence"}
    assert str(cached) == str(clean) and repr(cached) == repr(clean)
    with pytest.raises(AttributeError, match="immutable"):
        cached._packed = 0
    diploid_a, diploid_b = DiploidDNA(cached, clean), DiploidDNA(clean, clean)
    assert diploid_a == diploid_b and hash(diploid_a) == hash(diploid_b)


# --- the world does not move -----------------------------------------------------------------------


def run_world(monkeypatch=None, reference=None):
    calls = []
    if reference is not None:

        def counting(self, other):
            calls.append(1)
            return reference(self, other)

        monkeypatch.setattr(DNA, "distance", counting)
    world = hourly_world(seed=11)
    world.populate(animals=60, plants=80)
    for _ in range(24 * 6):
        world.step()
    return world.state_digest(), calls


def test_a_world_run_gives_the_same_digest_with_the_old_distance_and_the_new(monkeypatch):
    new_digest, _ = run_world()
    old_digest, calls = run_world(monkeypatch, reference_distance)
    assert calls  # mate choice and the senses really do ask for distances here
    assert new_digest == old_digest
