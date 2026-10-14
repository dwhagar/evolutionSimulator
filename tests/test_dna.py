import json
import random

import pytest

from evolution_simulator.dna import AnimalDNA, BaseDNA, Gene, Locus, PlantDNA


class TinyDNA(BaseDNA):
    """Two 2-digit genes and a locus, 5 digits."""

    low = Gene(2)
    high = Gene(2)
    kind = Locus()


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


# --- layout -----------------------------------------------------------------


def test_layout_lengths_match_prototype():
    assert AnimalDNA.STANDARD_LENGTH == 65
    assert PlantDNA.STANDARD_LENGTH == 24
    assert TinyDNA.STANDARD_LENGTH == 5


@pytest.mark.parametrize("cls", [AnimalDNA, PlantDNA, TinyDNA])
def test_genes_are_contiguous_and_cover_the_genome(cls):
    position = 0
    for gene in cls.GENES:
        assert gene.start == position
        position = gene.end
    assert position == cls.STANDARD_LENGTH


def test_animal_gene_positions_match_prototype():
    assert (AnimalDNA.speed.start, AnimalDNA.speed.end) == (0, 4)
    assert (AnimalDNA.size.start, AnimalDNA.size.end) == (8, 12)
    assert (AnimalDNA.encoder_fidelity.start, AnimalDNA.encoder_fidelity.end) == (60, 64)
    assert (AnimalDNA.sex_strategy.start, AnimalDNA.sex_strategy.end) == (64, 65)
    assert (PlantDNA.root_reach.start, PlantDNA.root_reach.end) == (20, 24)


def test_gene_width_must_be_positive():
    with pytest.raises(ValueError):
        Gene(0)


def test_base_class_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseDNA("0123")


# --- construction and validation --------------------------------------------


def test_accepts_string_and_iterables():
    assert TinyDNA("01230") == TinyDNA([0, 1, 2, 3, 0]) == TinyDNA((0, 1, 2, 3, 0))


def test_rejects_wrong_length_and_bad_digits():
    with pytest.raises(ValueError):
        TinyDNA("0123")
    with pytest.raises(ValueError):
        TinyDNA("012345")
    with pytest.raises(ValueError):
        TinyDNA("01240")
    with pytest.raises(ValueError):
        TinyDNA([0, 1, 2, 3, -1])


def test_random_is_seeded_and_valid():
    a = AnimalDNA.random(rng(7))
    assert a == AnimalDNA.random(rng(7))
    assert a != AnimalDNA.random(rng(8))
    assert a.length == len(a) == 65
    assert set(a.sequence) <= {0, 1, 2, 3}


def test_immutable():
    dna = TinyDNA("01230")
    with pytest.raises(AttributeError):
        dna.low = 0.5
    with pytest.raises(AttributeError):
        dna._sequence = (0, 0, 0, 0, 0)
    with pytest.raises(AttributeError):
        del dna._sequence
    assert isinstance(dna.sequence, tuple)


def test_equality_and_hash():
    assert TinyDNA("01230") == TinyDNA("01230")
    assert hash(TinyDNA("01230")) == hash(TinyDNA("01230"))
    assert TinyDNA("01230") != TinyDNA("01231")
    assert TinyDNA("00000") != PlantDNA("0" * 24)
    assert len({TinyDNA("01230"), TinyDNA("01230"), TinyDNA("11230")}) == 2


def test_str_and_repr():
    dna = TinyDNA("01230")
    assert str(dna) == "01230"
    assert "TinyDNA" in repr(dna) and "01230" in repr(dna)


# --- decoding ---------------------------------------------------------------


def test_decode_int_is_big_endian_base_4():
    dna = TinyDNA("01230")
    assert dna.decode_int(0, 2) == 1  # "01"
    assert dna.decode_int(1, 4) == 1 * 16 + 2 * 4 + 3  # "123"
    assert dna.decode_int(0, 4) == 27


def test_decode_normalized_range():
    assert TinyDNA("00000").low == 0.0
    assert TinyDNA("33333").low == 1.0
    assert TinyDNA("01230").low == pytest.approx(1 / 15)
    assert TinyDNA("01230").high == pytest.approx(11 / 15)  # "23" = 11 of 15


def test_locus_is_raw_digit():
    assert TinyDNA("00003").kind == 3
    assert TinyDNA("00000").kind == 0
    assert isinstance(TinyDNA("00002").kind, int)


def test_every_gene_stays_in_unit_interval():
    for seed in range(50):
        dna = AnimalDNA.random(rng(seed))
        for gene in AnimalDNA.GENES:
            if not isinstance(gene, Locus):
                assert 0.0 <= getattr(dna, gene.name) <= 1.0


def test_class_access_returns_the_descriptor():
    assert isinstance(AnimalDNA.size, Gene)
    assert isinstance(AnimalDNA.sex_strategy, Locus)


def test_slice_and_digit_bounds():
    dna = TinyDNA("01230")
    assert dna.get_slice(1, 3) == (1, 2)
    assert dna.get_digit(4) == 0
    for bad in [(-1, 2), (0, 6), (3, 3), (4, 2)]:
        with pytest.raises(IndexError):
            dna.get_slice(*bad)
    for bad_index in (-1, 5):
        with pytest.raises(IndexError):
            dna.get_digit(bad_index)


# --- distance and serialisation ---------------------------------------------


def test_distance():
    a = TinyDNA("00000")
    assert a.distance(a) == 0.0
    assert a.distance(TinyDNA("10000")) == pytest.approx(0.2)
    assert a.distance(TinyDNA("11111")) == 1.0
    assert a.distance(TinyDNA("01230")) == TinyDNA("01230").distance(a)
    with pytest.raises(TypeError):
        a.distance(PlantDNA("0" * 24))


def test_dict_round_trip_through_json():
    original = AnimalDNA.random(rng(3))
    restored = BaseDNA.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original
    assert type(restored) is AnimalDNA
    assert BaseDNA.from_dict(PlantDNA.random(rng(3)).to_dict()).length == 24


def test_from_dict_unknown_type():
    with pytest.raises(ValueError):
        BaseDNA.from_dict({"type": "NopeDNA", "sequence": "0"})


def test_from_string():
    assert PlantDNA.from_string("0" * 24) == PlantDNA("0" * 24)


# --- mutation ---------------------------------------------------------------


def test_zero_rate_is_identity():
    dna = AnimalDNA.random(rng(1))
    assert dna.mutated(rng(2), 0.0) == dna
    assert dna.clone_with_mutation(rng(2), 0.0) == dna


def test_rate_one_changes_every_digit():
    dna = AnimalDNA.random(rng(1))
    child = dna.mutated(rng(2), 1.0)
    assert all(a != b for a, b in zip(dna.sequence, child.sequence))
    assert dna.distance(child) == 1.0


def test_mutation_does_not_touch_parent_and_keeps_length():
    dna = AnimalDNA.random(rng(1))
    before = str(dna)
    child = dna.mutated(rng(2), 0.5)
    assert str(dna) == before
    assert child.length == dna.length
    assert type(child) is AnimalDNA


def test_mutation_is_deterministic_for_a_seed():
    dna = AnimalDNA.random(rng(1))
    assert dna.mutated(rng(9), 0.2) == dna.mutated(rng(9), 0.2)
    assert dna.mutated(rng(9), 0.2) != dna.mutated(rng(10), 0.2)


def test_mutation_rate_matches_expectation():
    dna = AnimalDNA.random(rng(1))
    r = rng(5)
    trials = 400
    changed = sum(round(dna.mutated(r, 0.05).distance(dna) * dna.length) for _ in range(trials))
    expected = trials * dna.length * 0.05
    assert abs(changed - expected) < 0.15 * expected


def test_changed_digits_land_on_the_other_three_digits_evenly():
    dna = TinyDNA("00000")
    r = rng(11)
    counts = {1: 0, 2: 0, 3: 0}
    for _ in range(3000):
        for digit in dna.mutated(r, 1.0).sequence:
            counts[digit] += 1
    total = sum(counts.values())
    assert all(abs(count / total - 1 / 3) < 0.03 for count in counts.values())


@pytest.mark.parametrize("rate", [-0.1, 1.1])
def test_invalid_rate_rejected(rate):
    with pytest.raises(ValueError):
        TinyDNA("00000").mutated(rng(), rate)


# --- crossover and reproduction ----------------------------------------------


def test_uniform_crossover_digits_come_from_parents():
    a, b = AnimalDNA("0" * 65), AnimalDNA("3" * 65)
    child = a.crossover(b, rng(4))
    assert set(child.sequence) <= {0, 3}
    assert set(child.sequence) == {0, 3}  # 65 coin flips: both parents contribute


def test_crossover_of_identical_parents_is_that_genome():
    a = AnimalDNA.random(rng(1))
    assert a.crossover(a, rng(2)) == a
    assert a.crossover_one_point(a, rng(2)) == a
    assert a.crossover_by_gene(a, rng(2)) == a


def test_crossover_is_deterministic_and_leaves_parents_alone():
    a, b = AnimalDNA.random(rng(1)), AnimalDNA.random(rng(2))
    before = (str(a), str(b))
    assert a.crossover(b, rng(3)) == a.crossover(b, rng(3))
    assert (str(a), str(b)) == before


def test_one_point_crossover_has_one_cut():
    a, b = AnimalDNA("0" * 65), AnimalDNA("3" * 65)
    for seed in range(20):
        child = a.crossover_one_point(b, rng(seed))
        cut = child.sequence.index(3)
        assert child.sequence[:cut] == (0,) * cut
        assert child.sequence[cut:] == (3,) * (65 - cut)
        assert 1 <= cut <= 64


def test_gene_crossover_keeps_genes_whole():
    a = AnimalDNA.random(rng(1))
    b = AnimalDNA.random(rng(2))
    for seed in range(20):
        child = a.crossover_by_gene(b, rng(seed))
        for gene in AnimalDNA.GENES:
            piece = child.get_slice(gene.start, gene.end)
            assert piece in (a.get_slice(gene.start, gene.end), b.get_slice(gene.start, gene.end))


def test_gene_crossover_mixes_both_parents():
    a, b = AnimalDNA("0" * 65), AnimalDNA("3" * 65)
    child = a.crossover_by_gene(b, rng(6))
    assert set(child.sequence) == {0, 3}


def test_crossover_rejects_mismatched_species():
    animal, plant = AnimalDNA("0" * 65), PlantDNA("0" * 24)
    for op in (animal.crossover, animal.crossover_one_point, animal.crossover_by_gene):
        with pytest.raises(TypeError):
            op(plant, rng())
    with pytest.raises(TypeError):
        animal.reproduce(plant, rng())


def test_one_point_needs_two_digits():
    class OneDigit(BaseDNA):
        only = Locus()

    with pytest.raises(ValueError):
        OneDigit("0").crossover_one_point(OneDigit("1"), rng())


def test_reproduce_without_partner_clones_with_mutation():
    dna = AnimalDNA.random(rng(1))
    assert dna.reproduce(None, rng(2), mutation_rate=0.0) == dna
    assert dna.reproduce(None, rng(2), 0.1) == dna.clone_with_mutation(rng(2), 0.1)


def test_reproduce_with_partner_crosses_then_mutates():
    a, b = AnimalDNA.random(rng(1)), AnimalDNA.random(rng(2))
    child = a.reproduce(b, rng(3), mutation_rate=0.0)
    assert child == a.crossover(b, rng(3))
    assert a.reproduce(b, rng(3), 0.2) == a.reproduce(b, rng(3), 0.2)
    assert type(a.reproduce(b, rng(3))) is AnimalDNA


def test_reproduce_accepts_other_crossover_strategies():
    a, b = AnimalDNA("0" * 65), AnimalDNA("3" * 65)
    child = a.reproduce(b, rng(3), mutation_rate=0.0, crossover=AnimalDNA.crossover_one_point)
    assert child == a.crossover_one_point(b, rng(3))
    child = a.reproduce(b, rng(3), mutation_rate=0.0, crossover=BaseDNA.crossover_by_gene)
    assert child == a.crossover_by_gene(b, rng(3))


def test_zero_mutation_asexual_child_equals_parent():
    for seed in range(10):
        dna = PlantDNA.random(rng(seed))
        assert dna.reproduce(None, rng(seed), 0.0) == dna
