"""The offline fit of the seed brain (BRAIN.9, BRAIN.25) and how sturdy the seed it wrote is.

The fit tool needs numpy (the ``gui`` extra), which the simulator does not, so these tests skip
without it.
"""

import random

import pytest

np = pytest.importorskip("numpy")

from evolution_simulator import seed_brain as sb
from evolution_tools import fit_seed_brain as fit


@pytest.fixture(scope="module")
def table():
    return fit.warm_net()


@pytest.fixture(scope="module")
def held_out():
    return fit.dataset(4000, 2)


def test_the_table_reads_back_as_the_seed_in_seed_brain(table):
    x, t = fit.dataset(1500, 3)
    assert fit.score(table, x, t) >= 0.95


def test_the_batched_mutation_losses_match_rebuilding_the_net_each_time(table):
    x, t = fit.dataset(600, 7)
    base, losses = fit.mutation_losses(table, x, t)
    assert base == pytest.approx(fit.score(table, x, t))
    params = fit.parameter_list(table)
    assert losses.shape == (len(params), 2)
    rng = random.Random(1)
    for flat in rng.sample(range(len(params)), 40):
        name, index = params[flat]
        array = getattr(table, name)
        for side, step in enumerate((-1, 1)):
            kept = array[index]
            array[index] = min(sb.LEVELS - 1, max(0, kept + step))
            rebuilt = base - fit.score(table, x, t)
            array[index] = kept
            assert losses[flat, side] == pytest.approx(rebuilt, abs=1e-12), (name, index, step)


def test_every_parameter_a_founder_can_get_moved_is_in_the_list(table):
    # seeded_dna moves any weight or bias of the seeded neurons and the output biases, not a gate
    names = [name for name, _ in fit.parameter_list(table)]
    assert len(names) == sb.SEED_HIDDEN * (1 + fit.N_IN + fit.N_OUT) + fit.N_OUT
    assert set(names) == {"w1", "b1", "w2", "b2"}


def test_the_seed_does_not_fall_off_a_cliff_under_one_level_mutations(table, held_out):
    # BRAIN.25: before the robust fit 2.0% of single mutations cost a tenth of the agreement and
    # founders with three of them lost that much 6.9% of the time.
    x, t = held_out
    _, losses = fit.mutation_losses(table, x, t)
    assert (losses > 0.10).mean() <= 0.012
    assert (losses > 0.25).mean() <= 0.006


def test_few_founders_lose_much_of_their_agreement(table, held_out):
    x, t = held_out
    _, loss = fit.founder_losses(table, x, t, founders=1500)
    assert (loss > 0.10).mean() <= 0.045
    assert (loss > 0.25).mean() <= 0.02
