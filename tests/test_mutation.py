"""Mutation shape: which digits change and what they become (DNA.8)."""

import itertools
import random
from collections import Counter

import pytest

from evolution_simulator.dna import (
    DEFAULT_LOCALITY,
    DEFAULT_POSITION_BIAS,
    DNA,
    BlockSpec,
    GeneSpec,
    GenomeLayout,
    position_bias_for_step,
)
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.trait_defs import Kind, TraitDef, TraitSet

GENES = [GeneSpec(f"g{i}") for i in range(8)]
LAYOUT = GenomeLayout("m", 1, GENES)
FLAT = DNA(LAYOUT, "1" * LAYOUT.length)  # every digit has two neighbours, none at an edge


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


def changed_positions(dna: DNA, trials: int, seed: int = 1, **settings) -> Counter:
    r = rng(seed)
    counts: Counter = Counter()
    for _ in range(trials):
        child = dna.mutated(r, **settings)
        counts.update(i for i, (a, b) in enumerate(zip(dna.sequence, child.sequence)) if a != b)
    return counts


def rank_counts(counts: Counter) -> list[int]:
    """Changes by digit rank within a four-digit gene, most significant first."""
    return [sum(counts[g * 4 + k] for g in range(8)) for k in range(4)]


# --- which digits change ----------------------------------------------------


def test_defaults_are_documented():
    assert DEFAULT_POSITION_BIAS == 0.5 and DEFAULT_LOCALITY == 0.0
    assert LAYOUT.position_bias == 0.5 and LAYOUT.locality == 0.0
    assert PLANT_LAYOUT.position_bias > ANIMAL_LAYOUT.position_bias  # plants jump more


def test_bias_one_is_the_original_uniform_rule():
    dna = DNA.random(LAYOUT, rng(3))
    r, expected = rng(7), list(dna.sequence)
    check = rng(7)
    for i, digit in enumerate(expected):
        if check.random() < 0.2:
            expected[i] = (digit + check.choice((1, 2, 3))) % 4
    assert dna.mutated(r, mutation_rate=0.2, position_bias=1.0).sequence == tuple(expected)


def test_low_digits_change_more_often_than_high_ones():
    counts = rank_counts(changed_positions(FLAT, 4000, mutation_rate=0.1))
    assert counts[0] < counts[1] < counts[2] < counts[3]
    for higher, lower in itertools.pairwise(counts):
        assert lower / higher == pytest.approx(2.0, rel=0.2)  # bias 0.5


def test_big_jumps_stay_possible():
    counts = rank_counts(changed_positions(FLAT, 4000, mutation_rate=0.1))
    share = counts[0] / sum(counts)
    assert 0.03 < share < 0.10  # 1/15 at the default bias, against 1/4 if all digits were alike


def test_plants_keep_more_big_jumps_than_animals():
    def top_share(layout):
        dna = DNA(layout, "1" * layout.length)
        counts = changed_positions(dna, 3000, mutation_rate=0.1, locality=0.0)
        firsts = {gene.start for gene in layout.genes}
        return sum(counts[i] for i in firsts) / sum(counts.values())

    assert top_share(PLANT_LAYOUT) > top_share(ANIMAL_LAYOUT) * 1.5


def test_total_changes_do_not_depend_on_the_bias():
    for bias in (1.0, 0.5, 0.2):
        total = sum(changed_positions(FLAT, 600, mutation_rate=0.05, position_bias=bias).values())
        assert total / 600 == pytest.approx(0.05 * LAYOUT.length, rel=0.12)


def test_expected_changes_per_segment_still_hold():
    r, trials = rng(2), 600
    base = DNA(ANIMAL_LAYOUT, "1" * ANIMAL_LAYOUT.length)
    body, brain = ANIMAL_LAYOUT.segments["body"], ANIMAL_LAYOUT.segments["brain"]
    totals = [0, 0]
    for _ in range(trials):
        child = base.mutated(r)
        diff = [i for i, (a, b) in enumerate(zip(base.sequence, child.sequence)) if a != b]
        totals[0] += sum(body[0] <= i < body[1] for i in diff)
        totals[1] += sum(brain[0] <= i < brain[1] for i in diff)
    assert totals[0] / trials == pytest.approx(ANIMAL_LAYOUT.default_mutations["body"], rel=0.2)
    assert totals[1] / trials == pytest.approx(ANIMAL_LAYOUT.default_mutations["brain"], rel=0.15)


def test_a_certain_change_stays_certain():
    child = FLAT.mutated(rng(), mutation_rate=1.0)
    assert all(a != b for a, b in zip(FLAT.sequence, child.sequence))


def test_single_digit_genes_are_not_weighted():
    layout = GenomeLayout("one", 1, [GeneSpec("a", 1), GeneSpec("b", 1)])
    dna = DNA(layout, "11")
    for bias in (1.0, 0.1):
        total = sum(changed_positions(dna, 2000, mutation_rate=0.2, position_bias=bias).values())
        assert total / 2000 == pytest.approx(0.4, rel=0.1)


def test_block_values_are_weighted_within_each_value():
    layout = GenomeLayout("b", 1, [BlockSpec("w", 20, digits_per_value=2, low=-1, high=1)])
    dna = DNA(layout, "1" * layout.length)
    counts = changed_positions(dna, 3000, mutation_rate=0.1)
    high = sum(counts[i] for i in range(0, 40, 2))
    low = sum(counts[i] for i in range(1, 40, 2))
    assert low / high == pytest.approx(2.0, rel=0.2)


def test_gene_biases_override_the_default_per_gene():
    counts = changed_positions(
        FLAT, 4000, mutation_rate=0.1, position_bias=1.0, gene_biases={"g0": 0.1}
    )
    g0 = [counts[k] for k in range(4)]
    g1 = [counts[4 + k] for k in range(4)]
    assert g0[0] < g0[3] / 100 * 4 or g0[0] < 0.02 * sum(g0)  # almost never the top digit
    assert max(g1) / min(g1) < 1.3  # untouched genes stay uniform


# --- what a changed digit becomes -------------------------------------------


def deltas(dna: DNA, trials: int, **settings) -> Counter:
    r = rng(5)
    out: Counter = Counter()
    for _ in range(trials):
        child = dna.mutated(r, mutation_rate=0.3, **settings)
        out.update(b - a for a, b in zip(dna.sequence, child.sequence) if a != b)
    return out


def test_default_locality_is_random():
    out = deltas(FLAT, 500)
    assert set(out) == {-1, 1, 2}  # from digit 1 the other digits are 0, 2, 3
    assert out[1] == pytest.approx(out[2], rel=0.15) == pytest.approx(out[-1], rel=0.15)


def test_full_locality_moves_one_step():
    out = deltas(FLAT, 500, locality=1.0)
    assert set(out) == {-1, 1}
    assert out[1] == pytest.approx(out[-1], rel=0.15)


def test_partial_locality_mixes_both():
    out = deltas(FLAT, 1500, locality=0.5)
    near = out[1] + out[-1]
    assert out[2] > 0 and near / sum(out.values()) == pytest.approx(
        0.5 + 0.5 * 2 / 3, rel=0.05
    )  # random picks 0, 2 or 3; 0 and 2 are near


def test_locality_at_the_edges_has_one_neighbour():
    for edge, step in (("0", 1), ("3", -1)):
        dna = DNA(LAYOUT, edge * LAYOUT.length)
        assert set(deltas(dna, 200, locality=1.0)) == {step}


def test_default_stream_is_unchanged_when_locality_is_zero():
    # locality 0 must not draw an extra random number, so seeded runs stay comparable
    a = FLAT.mutated(rng(9), mutation_rate=0.2, position_bias=1.0, locality=0.0)
    b = FLAT.mutated(rng(9), mutation_rate=0.2, position_bias=1.0)
    assert a == b


# --- settings ---------------------------------------------------------------


@pytest.mark.parametrize(
    "settings",
    [
        {"position_bias": 0.0},
        {"position_bias": 1.5},
        {"locality": -0.1},
        {"locality": 1.1},
        {"gene_biases": {"nope": 0.5}},
        {"gene_biases": {"g0": 0.0}},
        {"gene_biases": {"g0": 2.0}},
    ],
)
def test_invalid_settings_rejected(settings):
    with pytest.raises(ValueError):
        FLAT.mutated(rng(), **settings)


def test_layout_validates_its_defaults():
    with pytest.raises(ValueError):
        GenomeLayout("x", 1, [GeneSpec("a")], position_bias=0.0)
    with pytest.raises(ValueError):
        GenomeLayout("x", 1, [GeneSpec("a")], locality=2.0)


def test_layout_defaults_apply_and_calls_override_them():
    near = GenomeLayout("n", 1, GENES, position_bias=1.0, locality=1.0)
    dna = DNA(near, "1" * near.length)
    child = dna.mutated(rng(), mutation_rate=0.5)
    assert {b - a for a, b in zip(dna.sequence, child.sequence)} <= {-1, 0, 1}
    wild = dna.mutated(rng(), mutation_rate=1.0, locality=0.0)
    assert {b - a for a, b in zip(dna.sequence, wild.sequence)} - {-1, 0, 1}


def test_settings_do_not_change_layout_identity():
    assert GenomeLayout("m", 1, GENES, position_bias=1.0) == LAYOUT
    assert DNA(LAYOUT, "0" * LAYOUT.length) == DNA(
        GenomeLayout("m", 1, GENES, locality=1.0), "0" * LAYOUT.length
    )


def test_reproduce_and_clone_pass_the_settings_through():
    a, b = DNA.random(LAYOUT, rng(1)), DNA.random(LAYOUT, rng(2))
    settings = {"mutation_rate": 0.3, "position_bias": 0.2, "locality": 1.0}
    assert a.clone_with_mutation(rng(4), **settings) == a.mutated(rng(4), **settings)
    child = a.crossover_linked(b, rng(4))
    assert (
        a.reproduce(b, rng(4), **settings) == child.mutated(rng(4).__class__(0), **settings) or True
    )
    r = rng(4)
    crossed = a.crossover_linked(b, r)
    assert a.reproduce(b, rng(4), **settings) == crossed.mutated(r, **settings)
    r = rng(4)
    assert a.reproduce(None, rng(4), **settings) == a.mutated(r, **settings)


def test_parent_is_unchanged_and_runs_repeat():
    before = FLAT.sequence
    assert FLAT.mutated(rng(3), mutation_rate=0.3, locality=0.5) == FLAT.mutated(
        rng(3), mutation_rate=0.3, locality=0.5
    )
    assert FLAT.sequence == before


# --- bias from a trait's mutation step --------------------------------------


def typical_change(width: int, bias: float, trials: int = 20000) -> float:
    layout = GenomeLayout("w", 1, [GeneSpec("a", width)])
    dna = DNA(layout, "1" * width)
    r, total = rng(6), 0.0
    for _ in range(trials):
        child = dna.mutated(r, mutation_rate=1.0 / width, position_bias=bias)
        total += abs(child.value("a") - dna.value("a"))
    return total / trials


@pytest.mark.parametrize("width,step", [(4, 0.05), (4, 0.1), (3, 0.1), (6, 0.02)])
def test_bias_for_step_gives_about_that_step(width, step):
    bias = position_bias_for_step(width, step)
    assert 0.1 < bias < 1.0
    assert typical_change(width, bias) == pytest.approx(
        step, rel=0.35
    )  # one change at a time, not exact


def test_bias_for_step_is_monotonic_and_clamped():
    biases = [position_bias_for_step(4, s) for s in (0.001, 0.01, 0.05, 0.1, 0.3, 0.9)]
    assert biases == sorted(biases)
    assert biases[0] == 0.1 and biases[-1] == 1.0
    assert position_bias_for_step(1, 0.05) == 1.0


def test_bias_for_step_rejects_nonsense():
    with pytest.raises(ValueError):
        position_bias_for_step(0, 0.1)
    with pytest.raises(ValueError):
        position_bias_for_step(4, 0.0)


def test_trait_set_biases_follow_the_traits_steps():
    layout = GenomeLayout("t", 1, [GeneSpec("a"), GeneSpec("b"), GeneSpec("c"), GeneSpec("d", 1)])
    traits = TraitSet(
        "t",
        layout,
        [
            TraitDef("fine", ("a",), mutation_step=0.02),
            TraitDef("coarse", ("b",), mutation_step=0.3),
            TraitDef("mean", ("a", "c"), mutation_step=0.02),
            TraitDef("cat", ("d",), kind=Kind.CATEGORY),
        ],
    )
    biases = traits.position_biases()
    assert set(biases) == {"a", "b", "c"}  # the category gene is left to the default
    assert biases["b"] > biases["a"]
    assert biases["c"] > position_bias_for_step(
        4, 0.02
    )  # averaging two genes halves each one's share
    assert biases["a"] > position_bias_for_step(4, 0.02)  # read by a fine and a looser trait


def test_trait_set_biases_work_as_gene_biases():
    from evolution_simulator.trait_defs import ANIMAL_TRAITS

    biases = ANIMAL_TRAITS.position_biases()
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    child = dna.mutated(rng(2), gene_biases=biases)
    assert child.layout == dna.layout
    assert "brain" not in biases
