import json
import random

import pytest

from evolution_simulator.dna import AnimalDNA, BaseDNA, Gene, Locus, PlantDNA


class TinyDNA(BaseDNA):
    """Two 2-digit genes and a locus, 5 digits."""

    low = Gene(2)
    high = Gene(2)
    kind = Locus()


N = AnimalDNA.STANDARD_LENGTH


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


# --- layout -----------------------------------------------------------------


def test_layout_lengths_match_prototype():
    assert AnimalDNA.STANDARD_LENGTH == 61
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
    assert (AnimalDNA.encoder_fidelity.start, AnimalDNA.encoder_fidelity.end) == (56, 60)
    assert (AnimalDNA.sex_strategy.start, AnimalDNA.sex_strategy.end) == (60, 61)
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
    assert a.length == len(a) == 61
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


def test_layout_version_is_saved_and_checked():
    data = PlantDNA.random(rng(3)).to_dict()
    assert data["layout_version"] == PlantDNA.LAYOUT_VERSION
    with pytest.raises(ValueError):
        BaseDNA.from_dict({**data, "layout_version": PlantDNA.LAYOUT_VERSION + 1})
    with pytest.raises(ValueError):
        BaseDNA.from_dict({"type": "PlantDNA", "sequence": "0" * 24})


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


def test_full_rate_changes_every_digit():
    dna = AnimalDNA.random(rng(1))
    child = dna.mutated(rng(2), dna.length)
    assert all(a != b for a, b in zip(dna.sequence, child.sequence))
    assert dna.distance(child) == 1.0


def test_mutation_does_not_touch_parent_and_keeps_length():
    dna = AnimalDNA.random(rng(1))
    before = str(dna)
    child = dna.mutated(rng(2), 20.0)
    assert str(dna) == before
    assert child.length == dna.length
    assert type(child) is AnimalDNA


def test_mutation_is_deterministic_for_a_seed():
    dna = AnimalDNA.random(rng(1))
    assert dna.mutated(rng(9), 8.0) == dna.mutated(rng(9), 8.0)
    assert dna.mutated(rng(9), 8.0) != dna.mutated(rng(10), 8.0)


def test_mean_mutations_per_child_matches_the_setting():
    dna = AnimalDNA.random(rng(1))
    r = rng(5)
    trials = 600
    for wanted in (0.5, 3.0):
        changed = sum(
            round(dna.mutated(r, wanted).distance(dna) * dna.length) for _ in range(trials)
        )
        assert abs(changed / trials - wanted) < 0.15 * wanted + 0.05


def test_default_mutations_keep_the_prototype_per_digit_rate():
    assert AnimalDNA.DEFAULT_MUTATIONS == pytest.approx(0.01 * 61)
    assert PlantDNA.DEFAULT_MUTATIONS == pytest.approx(0.01 * 24)
    dna = PlantDNA.random(rng(1))
    r = rng(2)
    trials = 2000
    changed = sum(round(dna.mutated(r).distance(dna) * dna.length) for _ in range(trials))
    assert abs(changed / trials - PlantDNA.DEFAULT_MUTATIONS) < 0.05


def test_position_weights_steer_where_changes_land():
    dna = TinyDNA("00000")
    r = rng(3)
    hits = [0] * 5
    for _ in range(2000):
        for i, digit in enumerate(dna.mutated(r, 1.0, [0, 0, 0, 1, 3]).sequence):
            hits[i] += digit != 0
    assert hits[:3] == [0, 0, 0]
    # one expected change per child, split 1:3 between the last two digits
    assert 400 < hits[3] < 600
    assert 1400 < hits[4] < 1600
    # uniform weights are the same as no weights
    assert dna.mutated(rng(4), 2.0, [1] * 5) == dna.mutated(rng(4), 2.0)


@pytest.mark.parametrize("weights", [[1, 1, 1], [0] * 5, [1, 1, 1, 1, -1]])
def test_bad_position_weights_rejected(weights):
    with pytest.raises(ValueError):
        TinyDNA("00000").mutated(rng(), 1.0, weights)


def test_changed_digits_land_on_the_other_three_digits_evenly():
    dna = TinyDNA("00000")
    r = rng(11)
    counts = {1: 0, 2: 0, 3: 0}
    for _ in range(3000):
        for digit in dna.mutated(r, 5.0).sequence:
            counts[digit] += 1
    total = sum(counts.values())
    assert all(abs(count / total - 1 / 3) < 0.03 for count in counts.values())


def test_negative_mutations_rejected():
    with pytest.raises(ValueError):
        TinyDNA("00000").mutated(rng(), -0.1)


# --- crossover and reproduction ----------------------------------------------


def test_uniform_crossover_digits_come_from_parents():
    a, b = AnimalDNA("0" * N), AnimalDNA("3" * N)
    child = a.crossover(b, rng(4))
    assert set(child.sequence) <= {0, 3}
    assert set(child.sequence) == {0, 3}  # coin flips per digit: both parents contribute


def test_crossover_of_identical_parents_is_that_genome():
    a = AnimalDNA.random(rng(1))
    assert a.crossover(a, rng(2)) == a
    assert a.crossover_one_point(a, rng(2)) == a
    assert a.crossover_by_gene(a, rng(2)) == a
    assert a.crossover_linked(a, rng(2)) == a


def test_crossover_is_deterministic_and_leaves_parents_alone():
    a, b = AnimalDNA.random(rng(1)), AnimalDNA.random(rng(2))
    before = (str(a), str(b))
    assert a.crossover(b, rng(3)) == a.crossover(b, rng(3))
    assert (str(a), str(b)) == before


def test_one_point_crossover_has_one_cut():
    a, b = AnimalDNA("0" * N), AnimalDNA("3" * N)
    for seed in range(20):
        child = a.crossover_one_point(b, rng(seed))
        cut = child.sequence.index(3)
        assert child.sequence[:cut] == (0,) * cut
        assert child.sequence[cut:] == (3,) * (N - cut)
        assert 1 <= cut <= N - 1


def test_gene_crossover_keeps_genes_whole():
    a = AnimalDNA.random(rng(1))
    b = AnimalDNA.random(rng(2))
    for seed in range(20):
        child = a.crossover_by_gene(b, rng(seed))
        for gene in AnimalDNA.GENES:
            piece = child.get_slice(gene.start, gene.end)
            assert piece in (a.get_slice(gene.start, gene.end), b.get_slice(gene.start, gene.end))


def test_gene_crossover_mixes_both_parents():
    a, b = AnimalDNA("0" * N), AnimalDNA("3" * N)
    child = a.crossover_by_gene(b, rng(6))
    assert set(child.sequence) == {0, 3}


def test_linked_crossover_never_cuts_inside_a_gene():
    a, b = AnimalDNA.random(rng(1)), AnimalDNA.random(rng(2))
    for seed in range(100):
        child = a.crossover_linked(b, rng(seed), mean_cuts=3.0)
        for gene in AnimalDNA.GENES:
            piece = child.get_slice(gene.start, gene.end)
            assert piece in (a.get_slice(gene.start, gene.end), b.get_slice(gene.start, gene.end))


def test_linked_crossover_mean_cut_count():
    a, b = AnimalDNA("0" * N), AnimalDNA("3" * N)
    r = rng(8)
    trials = 1500
    for mean_cuts in (1.0, 2.0):
        switches = 0
        for _ in range(trials):
            child = a.crossover_linked(b, r, mean_cuts)
            switches += sum(1 for x, y in zip(child.sequence, child.sequence[1:]) if x != y)
        # Cuts landing on the same boundary cancel, so the mean sits slightly below the setting.
        assert 0.8 * mean_cuts < switches / trials <= mean_cuts + 0.1


def test_linked_crossover_with_no_cuts_copies_one_parent():
    a, b = AnimalDNA.random(rng(1)), AnimalDNA.random(rng(2))
    seen = {str(a.crossover_linked(b, rng(seed), mean_cuts=0.0)) for seed in range(30)}
    assert seen == {str(a), str(b)}


def test_linked_crossover_keeps_neighbouring_genes_together_more_than_per_gene():
    a, b = AnimalDNA("0" * N), AnimalDNA("3" * N)
    r = rng(2)

    def switches(op) -> int:
        total = 0
        for _ in range(300):
            child = op(a, b, r)
            total += sum(1 for x, y in zip(child.sequence, child.sequence[1:]) if x != y)
        return total

    assert switches(AnimalDNA.crossover_linked) < switches(AnimalDNA.crossover_by_gene)


def test_negative_cuts_rejected():
    a = AnimalDNA.random(rng(1))
    with pytest.raises(ValueError):
        a.crossover_linked(a, rng(), mean_cuts=-1.0)


def test_crossover_rejects_mismatched_species():
    animal, plant = AnimalDNA("0" * N), PlantDNA("0" * 24)
    for op in (
        animal.crossover,
        animal.crossover_one_point,
        animal.crossover_by_gene,
        animal.crossover_linked,
    ):
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
    assert dna.reproduce(None, rng(2), mutations_per_genome=0.0) == dna
    assert dna.reproduce(None, rng(2), 2.0) == dna.clone_with_mutation(rng(2), 2.0)


def test_reproduce_with_partner_crosses_then_mutates():
    a, b = AnimalDNA.random(rng(1)), AnimalDNA.random(rng(2))
    child = a.reproduce(b, rng(3), mutations_per_genome=0.0)
    assert child == a.crossover_linked(b, rng(3))
    assert a.reproduce(b, rng(3), 2.0) == a.reproduce(b, rng(3), 2.0)
    assert type(a.reproduce(b, rng(3))) is AnimalDNA
    assert a.reproduce(b, rng(3), 0.0, crossover=AnimalDNA.crossover) == a.crossover(b, rng(3))


def test_reproduce_accepts_other_crossover_strategies():
    a, b = AnimalDNA("0" * N), AnimalDNA("3" * N)
    child = a.reproduce(
        b, rng(3), mutations_per_genome=0.0, crossover=AnimalDNA.crossover_one_point
    )
    assert child == a.crossover_one_point(b, rng(3))
    child = a.reproduce(b, rng(3), mutations_per_genome=0.0, crossover=BaseDNA.crossover_by_gene)
    assert child == a.crossover_by_gene(b, rng(3))


def test_zero_mutation_asexual_child_equals_parent():
    for seed in range(10):
        dna = PlantDNA.random(rng(seed))
        assert dna.reproduce(None, rng(seed), 0.0) == dna
