"""Gene-following cut-point crossover (DNA.7)."""

import functools
import random

import pytest

from evolution_simulator.dna import DNA, GeneSpec, GenomeLayout
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT

ZEROS = DNA(ANIMAL_LAYOUT, "0" * ANIMAL_LAYOUT.length)
THREES = DNA(ANIMAL_LAYOUT, "3" * ANIMAL_LAYOUT.length)
UNIT_STARTS = {start for start, _ in ANIMAL_LAYOUT.units}


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


def switches(child: DNA) -> list[int]:
    """Digit positions where the child changes from one parent to the other (parents 0s and 3s)."""
    seq = child.sequence
    return [i for i in range(1, len(seq)) if seq[i] != seq[i - 1]]


def test_cuts_fall_between_units_when_fidelity_is_one():
    for seed in range(100):
        child = ZEROS.crossover_linked(THREES, rng(seed), mean_cuts=3.0, gene_fidelity=1.0)
        assert set(switches(child)) <= UNIT_STARTS


def test_default_settings_are_documented_constants():
    from evolution_simulator.dna import DEFAULT_GENE_FIDELITY, DEFAULT_MEAN_CUTS

    assert DEFAULT_MEAN_CUTS == 1.0
    assert DEFAULT_GENE_FIDELITY == 0.9
    assert ZEROS.crossover_linked(THREES, rng(5)) == ZEROS.crossover_linked(
        THREES, rng(5), DEFAULT_MEAN_CUTS, DEFAULT_GENE_FIDELITY
    )


def test_a_cut_is_always_made_at_one_or_more_expected_cuts():
    for seed in range(200):
        child = ZEROS.crossover_linked(THREES, rng(seed), mean_cuts=1.0, gene_fidelity=1.0)
        assert child != ZEROS and child != THREES
        assert len(switches(child)) >= 1


@pytest.mark.parametrize("mean_cuts", [1.0, 2.0, 4.0])
def test_mean_number_of_cuts_matches_the_setting(mean_cuts):
    r = rng(8)
    trials = 1500
    total = sum(
        len(switches(ZEROS.crossover_linked(THREES, r, mean_cuts, gene_fidelity=1.0)))
        for _ in range(trials)
    )
    assert abs(total / trials - mean_cuts) < 0.12 * mean_cuts


def test_fractional_mean_cuts_is_the_chance_of_one_cut():
    r = rng(2)
    trials = 2000
    mixed = sum(
        ZEROS.crossover_linked(THREES, r, 0.3, gene_fidelity=1.0) not in (ZEROS, THREES)
        for _ in range(trials)
    )
    assert abs(mixed / trials - 0.3) < 0.04


def test_no_cuts_copies_one_whole_parent():
    seen = {str(ZEROS.crossover_linked(THREES, rng(s), mean_cuts=0.0)) for s in range(30)}
    assert seen == {str(ZEROS), str(THREES)}


def test_zero_fidelity_cuts_inside_units():
    # A one-digit unit has no inside, so a cut there still falls on its boundary.
    single = {start for start, end in ANIMAL_LAYOUT.units if end - start == 1}
    inside = 0
    for seed in range(100):
        child = ZEROS.crossover_linked(THREES, rng(seed), mean_cuts=2.0, gene_fidelity=0.0)
        for position in switches(child):
            assert position not in UNIT_STARTS - single
            inside += 1
    assert inside > 100


def test_default_fidelity_is_mostly_but_not_always_between_genes():
    r = rng(4)
    between = odd = 0
    for _ in range(1500):
        child = ZEROS.crossover_linked(THREES, r, mean_cuts=2.0)
        for position in switches(child):
            if position in UNIT_STARTS:
                between += 1
            else:
                odd += 1
    share = odd / (odd + between)
    assert 0.05 < share < 0.15  # about 1 - 0.9, a little less where units are one digit


def test_brain_neurons_stay_whole_at_full_fidelity():
    brain = ANIMAL_LAYOUT.gene("brain")
    a = DNA.random(ANIMAL_LAYOUT, rng(1))
    b = DNA.random(ANIMAL_LAYOUT, rng(2))
    for seed in range(50):
        child = a.crossover_linked(b, rng(seed), mean_cuts=3.0, gene_fidelity=1.0)
        for start, end in brain.units:
            piece = child.sequence[start:end]
            assert piece in (a.sequence[start:end], b.sequence[start:end])


def test_neighbouring_genes_travel_together_more_than_per_gene_crossover():
    r = rng(2)

    def count(op) -> int:
        return sum(len(switches(op(ZEROS, THREES, r))) for _ in range(300))

    assert count(lambda a, b, r: a.crossover_linked(b, r, 1.0, 1.0)) < count(
        lambda a, b, r: a.crossover_by_unit(b, r)
    )


def test_parents_are_unchanged_and_runs_repeat():
    a, b = DNA.random(PLANT_LAYOUT, rng(1)), DNA.random(PLANT_LAYOUT, rng(2))
    before = (str(a), str(b))
    assert a.crossover_linked(b, rng(3)) == a.crossover_linked(b, rng(3))
    assert (str(a), str(b)) == before


def test_identical_parents_give_that_genome():
    a = DNA.random(ANIMAL_LAYOUT, rng(1))
    assert a.crossover_linked(a, rng(2), mean_cuts=5.0, gene_fidelity=0.0) == a


def test_single_unit_genome_cannot_be_cut():
    one = GenomeLayout("one", 1, [GeneSpec("g", 4)])
    a, b = DNA(one, "0000"), DNA(one, "3333")
    seen = {str(a.crossover_linked(b, rng(s), mean_cuts=3.0)) for s in range(30)}
    assert seen == {"0000", "3333"}


def test_more_cuts_than_boundaries_is_capped():
    small = GenomeLayout("s", 1, [GeneSpec("a", 2), GeneSpec("b", 2), GeneSpec("c", 2)])
    a, b = DNA(small, "000000"), DNA(small, "333333")
    for seed in range(30):
        child = a.crossover_linked(b, rng(seed), mean_cuts=50.0, gene_fidelity=1.0)
        assert child.sequence in ((0, 0, 3, 3, 0, 0), (3, 3, 0, 0, 3, 3))


@pytest.mark.parametrize(
    "kwargs", [{"mean_cuts": -1.0}, {"gene_fidelity": 1.5}, {"gene_fidelity": -0.1}]
)
def test_invalid_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        ZEROS.crossover_linked(THREES, rng(), **kwargs)


def test_rejects_other_layouts():
    with pytest.raises(TypeError):
        ZEROS.crossover_linked(DNA(PLANT_LAYOUT, "0" * PLANT_LAYOUT.length), rng())


def test_reproduce_uses_it_by_default_and_accepts_other_settings():
    a, b = DNA.random(ANIMAL_LAYOUT, rng(1)), DNA.random(ANIMAL_LAYOUT, rng(2))
    frozen = {"body": 0.0, "brain": 0.0}
    assert a.reproduce(b, rng(3), mutations_per_segment=frozen) == a.crossover_linked(b, rng(3))
    tight = functools.partial(DNA.crossover_linked, mean_cuts=2.0, gene_fidelity=1.0)
    assert a.reproduce(b, rng(3), crossover=tight, mutations_per_segment=frozen) == (
        a.crossover_linked(b, rng(3), 2.0, 1.0)
    )
    assert a.reproduce(b, rng(3), crossover=DNA.crossover, mutations_per_segment=frozen) == (
        a.crossover(b, rng(3))
    )
