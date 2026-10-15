"""Gene blocks (DNA.11) and per-segment mutation and per-unit crossover (DNA.12)."""

import random

import pytest

from evolution_simulator.brain import DEFAULT_BLUEPRINT
from evolution_simulator.dna import DNA, BlockSpec, GeneSpec, GenomeLayout
from evolution_simulator.layouts import (
    ANIMAL_LAYOUT,
    BRAIN_GENE,
    LAYOUTS,
    PLANT_LAYOUT,
    dna_from_dict,
)

BODY = ANIMAL_LAYOUT.segments["body"]
BRAIN = ANIMAL_LAYOUT.segments["brain"]
N = ANIMAL_LAYOUT.length

# 2-digit values over -2..2, two groups of two values, a gene before and a segment after
BLOCKY = GenomeLayout(
    "blocky",
    1,
    [
        GeneSpec("head", 2),
        BlockSpec("weights", count=4, low=-2.0, high=2.0, groups=(2, 2), segment="brain"),
        GeneSpec("tail", 1, segment="tail"),
    ],
    segment_mutations={"brain": 2.0},
)


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


def animal(sequence) -> DNA:
    return DNA(ANIMAL_LAYOUT, sequence)


def changed_per_segment(parent: DNA, child: DNA) -> dict[str, int]:
    return {
        name: sum(1 for i in range(start, end) if parent.sequence[i] != child.sequence[i])
        for name, (start, end) in parent.layout.segments.items()
    }


# --- BlockSpec (DNA.11) ------------------------------------------------------


def test_block_length_and_levels():
    block = BlockSpec("w", count=5, digits_per_value=2)
    assert block.length == 10
    assert block.levels == 16
    assert BlockSpec("w", count=2, digits_per_value=3).levels == 64


def test_block_validation():
    with pytest.raises(ValueError):
        BlockSpec("", 3)
    with pytest.raises(ValueError):
        BlockSpec("w", 0)
    with pytest.raises(ValueError):
        BlockSpec("w", 3, digits_per_value=0)
    with pytest.raises(ValueError):
        BlockSpec("w", 3, low=1.0, high=1.0)
    with pytest.raises(ValueError):
        BlockSpec("w", 3, groups=(1, 1))  # does not add up
    with pytest.raises(ValueError):
        BlockSpec("w", 3, groups=(3, 0))
    with pytest.raises(ValueError):
        BlockSpec("w", 3, segment="")


def test_block_decode_end_points_and_steps():
    block = BlockSpec("w", count=3, digits_per_value=2, low=-2.0, high=2.0)
    assert block.decode([0, 0, 3, 3, 0, 1]) == pytest.approx((-2.0, 2.0, -2.0 + 4.0 / 15))
    with pytest.raises(ValueError):
        block.decode([0, 0])


def test_block_decode_is_big_endian_like_a_plain_gene():
    block = BlockSpec("w", count=1, digits_per_value=2)
    assert block.decode([1, 0])[0] == pytest.approx(4 / 15)
    assert block.decode([0, 1])[0] == pytest.approx(1 / 15)


def test_block_encode_round_trips_every_level():
    block = BlockSpec("w", count=16, digits_per_value=2, low=-2.0, high=2.0)
    levels = [-2.0 + 4.0 * n / 15 for n in range(16)]
    digits = block.encode(levels)
    assert block.decode(digits) == pytest.approx(levels)
    assert digits[:4] == (0, 0, 0, 1)


def test_block_encode_rounds_and_clamps():
    block = BlockSpec("w", count=3, digits_per_value=2, low=-2.0, high=2.0)
    decoded = block.decode(block.encode([0.0, 99.0, -99.0]))
    assert decoded[1] == 2.0 and decoded[2] == -2.0
    assert abs(decoded[0]) < 0.14  # no exact zero with 16 levels; the nearest is +-0.133
    with pytest.raises(ValueError):
        block.encode([0.0])


def test_block_units_follow_the_groups():
    gene = BLOCKY.gene("weights")
    assert gene.units == ((2, 6), (6, 10))
    assert BLOCKY.gene("head").units == ((0, 2),)


# --- layout with blocks and segments ----------------------------------------


def test_animal_layout_has_the_brain_after_the_body():
    assert BRAIN_GENE.count == DEFAULT_BLUEPRINT.value_count == 582
    assert BRAIN_GENE.length == 1164
    assert ANIMAL_LAYOUT.gene("brain").block is BRAIN_GENE
    assert BODY == (0, 100)
    assert BRAIN == (100, 1264)
    assert ANIMAL_LAYOUT.gene("camouflage").end == BODY[1]


def test_plant_layout_has_one_body_segment_and_no_blocks():
    assert dict(PLANT_LAYOUT.segments) == {"body": (0, 33)}
    assert all(gene.block is None for gene in PLANT_LAYOUT.genes)


def test_units_tile_the_genome_with_one_per_gene_and_one_per_brain_group():
    position = 0
    for start, end in ANIMAL_LAYOUT.units:
        assert start == position
        position = end
    assert position == N
    assert len(ANIMAL_LAYOUT.units) == 27 + 17  # 27 body genes, 16 slots and the output biases
    brain_units = [u for u in ANIMAL_LAYOUT.units if u[0] >= BRAIN[0]]
    assert [(end - start) // 2 for start, end in brain_units] == list(DEFAULT_BLUEPRINT.group_sizes)


def test_segments_must_be_consecutive_and_named():
    with pytest.raises(ValueError):
        GenomeLayout("bad", 1, [GeneSpec("a"), GeneSpec("b", segment="x"), GeneSpec("c")])
    with pytest.raises(ValueError):
        GeneSpec("a", segment="")
    assert GenomeLayout("ok", 1, [GeneSpec("a"), GeneSpec("b"), GeneSpec("c", segment="x")])


def test_layout_mutation_defaults():
    assert ANIMAL_LAYOUT.default_mutations["body"] == pytest.approx(1.0)
    assert ANIMAL_LAYOUT.default_mutations["brain"] == 1.0
    assert PLANT_LAYOUT.default_mutations["body"] == pytest.approx(0.165)  # 0.005 per digit
    assert BLOCKY.default_mutations["brain"] == 2.0
    assert BLOCKY.default_mutations["body"] == pytest.approx(0.02)  # unlisted: 0.01 per digit
    with pytest.raises(ValueError):
        GenomeLayout("bad", 1, [GeneSpec("a")], segment_mutations={"nope": 1.0})
    with pytest.raises(ValueError):
        GenomeLayout("bad", 1, [GeneSpec("a")], segment_mutations={"body": -1.0})


def test_mutation_defaults_do_not_change_layout_identity():
    plain = GenomeLayout("p", 1, [GeneSpec("a")])
    tuned = GenomeLayout("p", 1, [GeneSpec("a")], segment_mutations={"body": 0.0})
    assert plain == tuned and hash(plain) == hash(tuned)


def test_animal_layout_version_covers_the_brain():
    assert ANIMAL_LAYOUT.version == 9
    old = {"layout": "animal", "layout_version": 1, "sequence": "0" * 65}
    with pytest.raises(ValueError):
        dna_from_dict(old)
    dna = DNA.random(ANIMAL_LAYOUT, rng(3))
    assert dna_from_dict(dna.to_dict()) == dna
    assert ANIMAL_LAYOUT in LAYOUTS


# --- reading a block ---------------------------------------------------------


def test_values_reads_a_block_onto_its_range():
    dna = DNA(BLOCKY, "00" + "0033" + "1200" + "0" + "")
    assert dna.values("weights") == pytest.approx(
        (-2.0, 2.0, -2.0 + 4.0 * 6 / 15, -2.0)
    )  # "12" = 6 of 15


def test_values_of_the_brain_cover_the_range():
    low = animal("0" * N).values("brain")
    high = animal("3" * N).values("brain")
    assert len(low) == len(high) == 582
    assert set(low) == {-2.0} and set(high) == {2.0}
    for seed in range(5):
        values = DNA.random(ANIMAL_LAYOUT, rng(seed)).values("brain")
        assert all(-2.0 <= v <= 2.0 for v in values)


def test_values_rejects_plain_genes():
    with pytest.raises(ValueError):
        DNA.random(ANIMAL_LAYOUT, rng(1)).values("size")


def test_a_block_is_also_readable_as_a_plain_gene_slice():
    dna = DNA.random(ANIMAL_LAYOUT, rng(2))
    assert len(dna.slice_of("brain")) == 1164


def test_replaced_swaps_one_gene_only():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    digits = BRAIN_GENE.encode([1.0] * 582)
    child = dna.replaced("brain", digits)
    assert child.values("brain") == pytest.approx((1.0 + 0.0,) * 582, abs=0.14)
    assert child.sequence[: BRAIN[0]] == dna.sequence[: BRAIN[0]]
    with pytest.raises(ValueError):
        dna.replaced("brain", (0, 1))


# --- mutation per segment (DNA.12) ------------------------------------------


def test_default_animal_mutation_does_not_let_the_brain_swamp_the_body():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    r = rng(5)
    trials = 1500
    body = brain = 0
    for _ in range(trials):
        counts = changed_per_segment(dna, dna.mutated(r))
        body += counts["body"]
        brain += counts["brain"]
    assert body / trials == pytest.approx(1.0, abs=0.1)
    assert brain / trials == pytest.approx(1.0, abs=0.15)
    # per-digit 0.01 everywhere would have given about 9 brain changes per child


def test_plant_default_is_half_a_percent_per_digit():
    dna = DNA.random(PLANT_LAYOUT, rng(1))
    r = rng(2)
    trials = 2000
    changed = sum(round(dna.mutated(r).distance(dna) * dna.length) for _ in range(trials))
    assert changed / trials == pytest.approx(0.15, abs=0.04)


def test_mutations_per_segment_set_the_expected_count_of_each_segment():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    r = rng(7)
    trials = 1200
    totals = {"body": 0, "brain": 0}
    for _ in range(trials):
        for name, count in changed_per_segment(
            dna, dna.mutated(r, mutations_per_segment={"body": 3.0, "brain": 6.0})
        ).items():
            totals[name] += count
    assert totals["body"] / trials == pytest.approx(3.0, abs=0.2)
    assert totals["brain"] / trials == pytest.approx(6.0, abs=0.3)


def test_a_segment_left_out_keeps_its_layout_default():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    r = rng(8)
    trials = 1200
    body = sum(
        changed_per_segment(dna, dna.mutated(r, mutations_per_segment={"brain": 0.0}))["body"]
        for _ in range(trials)
    )
    assert body / trials == pytest.approx(1.0, abs=0.1)


def test_zero_in_one_segment_freezes_it():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    for seed in range(30):
        child = dna.mutated(rng(seed), mutations_per_segment={"brain": 0.0, "body": 20.0})
        counts = changed_per_segment(dna, child)
        assert counts["brain"] == 0 and counts["body"] > 0
        child = dna.mutated(rng(seed), mutations_per_segment={"brain": 20.0, "body": 0.0})
        counts = changed_per_segment(dna, child)
        assert counts["body"] == 0 and counts["brain"] > 0


def test_segment_mutation_is_deterministic_and_leaves_the_parent_alone():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    before = str(dna)
    settings = {"brain": 5.0}
    assert dna.mutated(rng(4), mutations_per_segment=settings) == dna.mutated(
        rng(4), mutations_per_segment=settings
    )
    assert dna.mutated(rng(4), mutations_per_segment=settings) != dna.mutated(
        rng(5), mutations_per_segment=settings
    )
    assert str(dna) == before


def test_a_count_above_the_segment_length_caps_at_every_digit_changing():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    child = dna.mutated(rng(2), mutations_per_segment={"body": 1e6, "brain": 0.0})
    assert changed_per_segment(dna, child) == {"body": 100, "brain": 0}


def test_per_digit_rate_still_means_the_same_thing_everywhere():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    assert dna.mutated(rng(2), 0.0) == dna
    assert dna.mutated(rng(2), 1.0).distance(dna) == 1.0


def test_rate_and_segment_settings_cannot_be_combined_or_be_invalid():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    with pytest.raises(ValueError):
        dna.mutated(rng(), 0.1, {"brain": 1.0})
    with pytest.raises(ValueError):
        dna.mutated(rng(), mutations_per_segment={"legs": 1.0})
    with pytest.raises(ValueError):
        dna.mutated(rng(), mutations_per_segment={"brain": -1.0})
    with pytest.raises(ValueError):
        dna.mutated(rng(), 1.5)


def test_reproduce_and_clone_pass_segment_settings_through():
    a, b = DNA.random(ANIMAL_LAYOUT, rng(1)), DNA.random(ANIMAL_LAYOUT, rng(2))
    frozen = {"body": 0.0, "brain": 0.0}
    assert a.reproduce(None, rng(3), mutations_per_segment=frozen) == a
    assert a.clone_with_mutation(rng(3), mutations_per_segment=frozen) == a
    child = a.reproduce(b, rng(3), crossover=DNA.crossover_by_unit, mutations_per_segment=frozen)
    assert child == a.crossover_by_unit(b, rng(3))
    mutated = a.reproduce(None, rng(3), mutations_per_segment={"body": 0.0, "brain": 30.0})
    assert changed_per_segment(a, mutated)["body"] == 0
    assert changed_per_segment(a, mutated)["brain"] > 0


# --- crossover by unit (DNA.12) ----------------------------------------------


def test_unit_crossover_keeps_every_unit_whole():
    a, b = DNA.random(ANIMAL_LAYOUT, rng(1)), DNA.random(ANIMAL_LAYOUT, rng(2))
    for seed in range(30):
        child = a.crossover_by_unit(b, rng(seed))
        for start, end in ANIMAL_LAYOUT.units:
            piece = child.get_slice(start, end)
            assert piece in (a.get_slice(start, end), b.get_slice(start, end))


def test_unit_crossover_never_blends_inside_a_neuron_but_uniform_does():
    a, b = DNA(ANIMAL_LAYOUT, "0" * N), DNA(ANIMAL_LAYOUT, "3" * N)
    neurons = [u for u in ANIMAL_LAYOUT.units if u[0] >= BRAIN[0]]
    mixed_by_uniform = 0
    for seed in range(20):
        child = a.crossover_by_unit(b, rng(seed))
        for start, end in neurons:
            assert len(set(child.get_slice(start, end))) == 1
        uniform = a.crossover(b, rng(seed))
        mixed_by_uniform += sum(1 for s, e in neurons if len(set(uniform.get_slice(s, e))) > 1)
    assert mixed_by_uniform > 0


def test_unit_crossover_takes_whole_neurons_from_both_parents():
    a, b = DNA(ANIMAL_LAYOUT, "0" * N), DNA(ANIMAL_LAYOUT, "3" * N)
    neurons = [u for u in ANIMAL_LAYOUT.units if u[0] >= BRAIN[0]]
    donors = set()
    for seed in range(10):
        child = a.crossover_by_unit(b, rng(seed))
        donors |= {child.sequence[start] for start, _ in neurons}
    assert donors == {0, 3}


def test_unit_crossover_is_deterministic_and_leaves_parents_alone():
    a, b = DNA.random(ANIMAL_LAYOUT, rng(1)), DNA.random(ANIMAL_LAYOUT, rng(2))
    before = (str(a), str(b))
    assert a.crossover_by_unit(b, rng(3)) == a.crossover_by_unit(b, rng(3))
    assert (str(a), str(b)) == before
    assert a.crossover_by_unit(a, rng(3)) == a


def test_unit_crossover_matches_gene_crossover_when_there_are_no_blocks():
    a, b = DNA.random(PLANT_LAYOUT, rng(1)), DNA.random(PLANT_LAYOUT, rng(2))
    for seed in range(10):
        assert a.crossover_by_unit(b, rng(seed)) == a.crossover_by_gene(b, rng(seed))


def test_unit_crossover_rejects_other_layouts():
    with pytest.raises(TypeError):
        DNA.random(ANIMAL_LAYOUT, rng(1)).crossover_by_unit(DNA.random(PLANT_LAYOUT, rng(1)), rng())


def test_small_blocky_layout_end_to_end():
    a, b = DNA(BLOCKY, "00" + "00000000" + "0"), DNA(BLOCKY, "33" + "33333333" + "3")
    seen = set()
    for seed in range(40):
        child = a.crossover_by_unit(b, rng(seed))
        assert len(set(child.get_slice(2, 6))) == 1 and len(set(child.get_slice(6, 10))) == 1
        seen.add((child.sequence[2], child.sequence[6]))
    assert seen == {(0, 0), (0, 3), (3, 0), (3, 3)}


def test_trait_sets_do_not_report_gene_blocks_as_unread():
    from evolution_simulator.trait_defs import ANIMAL_TRAITS, TraitDef, TraitSet

    assert "brain" in ANIMAL_LAYOUT
    assert "brain" not in ANIMAL_TRAITS.unread_genes()
    traits = TraitSet("t", BLOCKY, [TraitDef("h", ("head",))])
    assert traits.unread_genes() == ("tail",)
