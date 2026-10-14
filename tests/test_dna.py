import json
import random

import pytest

from evolution_simulator.dna import DNA, Gene, GeneSpec, GenomeLayout
from evolution_simulator.layouts import ANIMAL_LAYOUT, LAYOUTS, PLANT_LAYOUT, dna_from_dict

TINY = GenomeLayout("tiny", 1, [GeneSpec("low", 2), GeneSpec("high", 2), GeneSpec("kind", 1)])
N = ANIMAL_LAYOUT.length


def tiny(sequence) -> DNA:
    return DNA(TINY, sequence)


def animal(sequence) -> DNA:
    return DNA(ANIMAL_LAYOUT, sequence)


def plant(sequence) -> DNA:
    return DNA(PLANT_LAYOUT, sequence)


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


# --- layout -----------------------------------------------------------------


def test_layout_lengths_match_prototype():
    assert ANIMAL_LAYOUT.length == 461  # 65 body digits plus a 396-digit brain
    assert PLANT_LAYOUT.length == 24
    assert TINY.length == 5


@pytest.mark.parametrize("layout", [ANIMAL_LAYOUT, PLANT_LAYOUT, TINY])
def test_genes_are_contiguous_and_cover_the_genome(layout):
    position = 0
    for gene in layout.genes:
        assert gene.start == position
        position = gene.end
    assert position == layout.length


def test_animal_gene_positions_match_prototype():
    def span(layout, gene_id):
        gene = layout.gene(gene_id)
        return gene.start, gene.end

    assert span(ANIMAL_LAYOUT, "speed") == (0, 4)
    assert span(ANIMAL_LAYOUT, "size") == (8, 12)
    assert span(ANIMAL_LAYOUT, "fertility") == (56, 60)
    assert span(ANIMAL_LAYOUT, "encoder_fidelity") == (60, 64)
    assert span(ANIMAL_LAYOUT, "sex_strategy") == (64, 65)
    assert span(ANIMAL_LAYOUT, "brain") == (65, 461)
    assert span(PLANT_LAYOUT, "root_reach") == (20, 24)


def test_layout_lookup():
    assert "size" in ANIMAL_LAYOUT and "nope" not in ANIMAL_LAYOUT
    assert ANIMAL_LAYOUT.gene_ids[0] == "speed"
    with pytest.raises(KeyError):
        ANIMAL_LAYOUT.gene("nope")


def test_layout_validation():
    with pytest.raises(ValueError):
        GeneSpec("x", 0)
    with pytest.raises(ValueError):
        GeneSpec("", 4)
    with pytest.raises(ValueError):
        GenomeLayout("empty", 1, [])
    with pytest.raises(ValueError):
        GenomeLayout("dupe", 1, [GeneSpec("a"), GeneSpec("a")])


def test_layout_equality_is_by_content():
    same = GenomeLayout("tiny", 1, [GeneSpec("low", 2), GeneSpec("high", 2), GeneSpec("kind", 1)])
    other_version = GenomeLayout(
        "tiny", 2, [GeneSpec("low", 2), GeneSpec("high", 2), GeneSpec("kind", 1)]
    )
    assert same == TINY and hash(same) == hash(TINY)
    assert other_version != TINY
    assert isinstance(ANIMAL_LAYOUT.genes[0], Gene)


# --- construction and validation --------------------------------------------


def test_accepts_string_and_iterables():
    assert tiny("01230") == tiny([0, 1, 2, 3, 0]) == tiny((0, 1, 2, 3, 0))


def test_rejects_wrong_length_and_bad_digits():
    with pytest.raises(ValueError):
        tiny("0123")
    with pytest.raises(ValueError):
        tiny("012345")
    with pytest.raises(ValueError):
        tiny("01240")
    with pytest.raises(ValueError):
        tiny([0, 1, 2, 3, -1])


def test_random_is_seeded_and_valid():
    a = DNA.random(ANIMAL_LAYOUT, rng(7))
    assert a == DNA.random(ANIMAL_LAYOUT, rng(7))
    assert a != DNA.random(ANIMAL_LAYOUT, rng(8))
    assert a.length == len(a) == 461
    assert a.layout is ANIMAL_LAYOUT
    assert set(a.sequence) <= {0, 1, 2, 3}


def test_immutable():
    dna = tiny("01230")
    with pytest.raises(AttributeError):
        dna.anything = 0.5
    with pytest.raises(AttributeError):
        dna._sequence = (0, 0, 0, 0, 0)
    with pytest.raises(AttributeError):
        del dna._sequence
    assert isinstance(dna.sequence, tuple)


def test_equality_and_hash():
    assert tiny("01230") == tiny("01230")
    assert hash(tiny("01230")) == hash(tiny("01230"))
    assert tiny("01230") != tiny("01231")
    assert tiny("00000") != plant("0" * 24)
    assert len({tiny("01230"), tiny("01230"), tiny("11230")}) == 2


def test_str_and_repr():
    dna = tiny("01230")
    assert str(dna) == "01230"
    assert "tiny" in repr(dna) and "01230" in repr(dna)


# --- decoding ---------------------------------------------------------------


def test_decode_int_is_big_endian_base_4():
    dna = tiny("01230")
    assert dna.decode_int(0, 2) == 1  # "01"
    assert dna.decode_int(1, 4) == 1 * 16 + 2 * 4 + 3  # "123"
    assert dna.decode_int(0, 4) == 27


def test_decode_normalized_range():
    assert tiny("00000").value("low") == 0.0
    assert tiny("33333").value("low") == 1.0
    assert tiny("01230").value("low") == pytest.approx(1 / 15)
    assert tiny("01230").value("high") == pytest.approx(11 / 15)  # "23" = 11 of 15


def test_reading_genes_by_id():
    dna = tiny("01230")
    assert dna.slice_of("high") == (2, 3)
    assert dna.raw("high") == 11
    assert dna.digit("kind") == 0
    assert tiny("00003").digit("kind") == 3
    with pytest.raises(ValueError):
        dna.digit("low")  # two digits, not a category
    with pytest.raises(KeyError):
        dna.value("nope")


def test_every_gene_stays_in_unit_interval():
    for seed in range(50):
        dna = DNA.random(ANIMAL_LAYOUT, rng(seed))
        for gene in ANIMAL_LAYOUT.genes:
            assert 0.0 <= dna.value(gene.id) <= 1.0


def test_dna_has_no_trait_names():
    dna = animal("0" * N)
    for name in ("size", "speed", "fear", "sex_strategy", "aggression"):
        assert not hasattr(dna, name)


def test_slice_and_digit_bounds():
    dna = tiny("01230")
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
    a = tiny("00000")
    assert a.distance(a) == 0.0
    assert a.distance(tiny("10000")) == pytest.approx(0.2)
    assert a.distance(tiny("11111")) == 1.0
    assert a.distance(tiny("01230")) == tiny("01230").distance(a)
    with pytest.raises(TypeError):
        a.distance(plant("0" * 24))


def test_dict_round_trip_through_json():
    for layout in LAYOUTS:
        original = DNA.random(layout, rng(3))
        restored = dna_from_dict(json.loads(json.dumps(original.to_dict())))
        assert restored == original
        assert restored.layout is layout


def test_dict_carries_layout_name_and_version():
    data = DNA.random(PLANT_LAYOUT, rng(3)).to_dict()
    assert data["layout"] == "plant"
    assert data["layout_version"] == PLANT_LAYOUT.version


def test_from_dict_checks_layout_and_version():
    data = DNA.random(PLANT_LAYOUT, rng(3)).to_dict()
    with pytest.raises(ValueError):
        dna_from_dict({**data, "layout_version": PLANT_LAYOUT.version + 1})
    with pytest.raises(ValueError):
        dna_from_dict({"layout": "plant", "sequence": data["sequence"]})
    with pytest.raises(ValueError):
        dna_from_dict({"layout": "nope", "layout_version": 1, "sequence": "0"})


def test_from_string():
    assert DNA.from_string(PLANT_LAYOUT, "0" * 24) == plant("0" * 24)


# --- mutation ---------------------------------------------------------------


def test_zero_rate_is_identity():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    assert dna.mutated(rng(2), 0.0) == dna
    assert dna.clone_with_mutation(rng(2), 0.0) == dna


def test_rate_one_changes_every_digit():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    child = dna.mutated(rng(2), 1.0)
    assert all(a != b for a, b in zip(dna.sequence, child.sequence))
    assert dna.distance(child) == 1.0


def test_mutation_does_not_touch_parent_and_keeps_length():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    before = str(dna)
    child = dna.mutated(rng(2), 0.5)
    assert str(dna) == before
    assert child.length == dna.length
    assert child.layout is ANIMAL_LAYOUT


def test_mutation_is_deterministic_for_a_seed():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    assert dna.mutated(rng(9), 0.2) == dna.mutated(rng(9), 0.2)
    assert dna.mutated(rng(9), 0.2) != dna.mutated(rng(10), 0.2)


def test_mutation_rate_matches_expectation():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    r = rng(5)
    trials = 400
    changed = sum(round(dna.mutated(r, 0.05).distance(dna) * dna.length) for _ in range(trials))
    expected = trials * dna.length * 0.05
    assert abs(changed - expected) < 0.15 * expected


def test_changed_digits_land_on_the_other_three_digits_evenly():
    dna = tiny("00000")
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
        tiny("00000").mutated(rng(), rate)


# --- crossover and reproduction ----------------------------------------------


def test_uniform_crossover_digits_come_from_parents():
    a, b = animal("0" * N), animal("3" * N)
    child = a.crossover(b, rng(4))
    assert set(child.sequence) <= {0, 3}
    assert set(child.sequence) == {0, 3}  # one coin flip per digit: both parents contribute


def test_crossover_of_identical_parents_is_that_genome():
    a = DNA.random(ANIMAL_LAYOUT, rng(1))
    assert a.crossover(a, rng(2)) == a
    assert a.crossover_one_point(a, rng(2)) == a
    assert a.crossover_by_gene(a, rng(2)) == a


def test_crossover_is_deterministic_and_leaves_parents_alone():
    a, b = DNA.random(ANIMAL_LAYOUT, rng(1)), DNA.random(ANIMAL_LAYOUT, rng(2))
    before = (str(a), str(b))
    assert a.crossover(b, rng(3)) == a.crossover(b, rng(3))
    assert (str(a), str(b)) == before


def test_one_point_crossover_has_one_cut():
    a, b = animal("0" * N), animal("3" * N)
    for seed in range(20):
        child = a.crossover_one_point(b, rng(seed))
        cut = child.sequence.index(3)
        assert child.sequence[:cut] == (0,) * cut
        assert child.sequence[cut:] == (3,) * (N - cut)
        assert 1 <= cut <= N - 1


def test_gene_crossover_keeps_genes_whole():
    a = DNA.random(ANIMAL_LAYOUT, rng(1))
    b = DNA.random(ANIMAL_LAYOUT, rng(2))
    for seed in range(20):
        child = a.crossover_by_gene(b, rng(seed))
        for gene in ANIMAL_LAYOUT.genes:
            piece = child.get_slice(gene.start, gene.end)
            assert piece in (a.get_slice(gene.start, gene.end), b.get_slice(gene.start, gene.end))


def test_gene_crossover_mixes_both_parents():
    a, b = animal("0" * N), animal("3" * N)
    child = a.crossover_by_gene(b, rng(6))
    assert set(child.sequence) == {0, 3}


def test_crossover_rejects_mismatched_species():
    a, p = animal("0" * N), plant("0" * 24)
    for op in (a.crossover, a.crossover_one_point, a.crossover_by_gene):
        with pytest.raises(TypeError):
            op(p, rng())
    with pytest.raises(TypeError):
        a.reproduce(p, rng())


def test_one_point_needs_two_digits():
    one = GenomeLayout("one", 1, [GeneSpec("only", 1)])

    with pytest.raises(ValueError):
        DNA(one, "0").crossover_one_point(DNA(one, "1"), rng())


def test_reproduce_without_partner_clones_with_mutation():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    assert dna.reproduce(None, rng(2), mutation_rate=0.0) == dna
    assert dna.reproduce(None, rng(2), 0.1) == dna.clone_with_mutation(rng(2), 0.1)


def test_reproduce_with_partner_crosses_then_mutates():
    a, b = DNA.random(ANIMAL_LAYOUT, rng(1)), DNA.random(ANIMAL_LAYOUT, rng(2))
    child = a.reproduce(b, rng(3), mutation_rate=0.0)
    assert child == a.crossover_linked(b, rng(3))
    assert a.reproduce(b, rng(3), 0.2) == a.reproduce(b, rng(3), 0.2)
    assert a.reproduce(b, rng(3)).layout is ANIMAL_LAYOUT


def test_reproduce_accepts_other_crossover_strategies():
    a, b = animal("0" * N), animal("3" * N)
    child = a.reproduce(b, rng(3), mutation_rate=0.0, crossover=DNA.crossover_one_point)
    assert child == a.crossover_one_point(b, rng(3))
    child = a.reproduce(b, rng(3), mutation_rate=0.0, crossover=DNA.crossover_by_gene)
    assert child == a.crossover_by_gene(b, rng(3))


def test_zero_mutation_asexual_child_equals_parent():
    for seed in range(10):
        dna = DNA.random(PLANT_LAYOUT, rng(seed))
        assert dna.reproduce(None, rng(seed), 0.0) == dna
