"""Who mates with whom: closest genome first, cross-breeding as the last choice (REPRO.4)."""

import pytest
from world_support import LOVING, animal_dna, grown, hourly_world

from evolution_simulator.diploid import DiploidDNA
from evolution_simulator.dna import DNA
from evolution_simulator.world import Vec, World
from evolution_simulator.world.mating import choose_mate, mate_rank, may_mate

HERE = Vec.of(500, 500)


def lover(sex: int = 0, **genes: str) -> DNA:
    """A mate-seeking animal; the sex digit is 0 (impregnates) or 1 (bears)."""
    return animal_dna(brain=LOVING, sex_strategy=str(sex), **genes)


def differ(dna: DNA, digits: int, skip: tuple[str, ...] = ()) -> DNA:
    """The same genome with its first ``digits`` body digits changed (the genes named in ``skip``
    are left alone, for example the sex digit)."""
    kept = {
        i
        for gene_id in skip
        for i in range(dna.layout.gene(gene_id).start, dna.layout.gene(gene_id).end)
    }
    changed = [
        (d + 1) % 4 if i < digits and i not in kept else d for i, d in enumerate(dna.sequence)
    ]
    return DNA(dna.layout, changed)


@pytest.fixture
def world() -> World:
    return hourly_world(mating_reach=10.0)


def put(world: World, dna: DNA, x: float):
    animal = world.add_animal(dna, Vec.of(x, 500), heading=0.0)
    grown(animal)
    return animal


# --- the rules --------------------------------------------------------------


def test_one_of_each_sex_may_mate_but_not_an_animal_with_itself_or_two_of_a_sex(world):
    a, b = put(world, lover(0), 500), put(world, lover(1), 501)
    assert may_mate(a, b) and may_mate(b, a)
    assert not may_mate(a, a)
    c, d = put(world, lover(0), 502), put(world, lover(2), 503)  # digits 0 and 2 are both sex 0
    assert not may_mate(a, c) and not may_mate(a, d)
    e, f = put(world, lover(1), 504), put(world, lover(3), 505)  # digits 1 and 3 are both sex 1
    assert not may_mate(b, e) and not may_mate(b, f)
    assert may_mate(d, f)  # a sex digit of 2 or 3 only changes the drive


def test_animals_with_different_kinds_of_genome_cannot_mate(world):
    a = put(world, lover(0), 500)
    b = put(world, lover(1), 501)
    b.traits.dna = DiploidDNA.from_haploid(b.traits.dna)  # same layout, other ploidy
    assert not may_mate(a, b) and not may_mate(b, a)


def test_the_closest_genome_is_chosen_even_when_a_stranger_is_nearer(world):
    me = put(world, lover(0), 500)
    kin = put(world, differ(lover(1), 3, skip=("sex_strategy",)), 508)
    stranger = put(world, differ(lover(1), 40, skip=("sex_strategy",)), 501)
    assert choose_mate(me, [stranger, kin]) is kin
    assert choose_mate(me, [kin, stranger]) is kin
    assert mate_rank(me, kin)[0] < mate_rank(me, stranger)[0]


def test_a_distant_genome_is_still_chosen_when_nothing_closer_is_in_reach(world):
    me = put(world, lover(0), 500)
    stranger = put(world, differ(lover(1), 60, skip=("sex_strategy",)), 501)
    assert (
        choose_mate(me, [stranger]) is stranger
    )  # cross-breeding is allowed, just least preferred


def test_ties_go_to_the_nearer_animal_then_the_lower_id(world):
    me = put(world, lover(0), 500)
    near = put(world, lover(1), 502)
    far = put(world, lover(1), 506)
    assert choose_mate(me, [far, near]) is near
    twin_a, twin_b = put(world, lover(1), 504), put(world, lover(1), 496)
    assert choose_mate(me, [twin_b, twin_a]) is twin_a  # same genome, same distance: lower id


def test_the_other_sex_only(world):
    me = put(world, lover(0), 500)
    same = put(world, lover(0), 501)
    other = put(world, lover(1), 508)
    assert choose_mate(me, [same, other]) is other
    assert choose_mate(me, [same]) is None


def test_nobody_in_reach_means_no_choice(world):
    me = put(world, lover(0), 500)
    assert choose_mate(me, []) is None
    assert choose_mate(me, [me]) is None


# --- in the world -----------------------------------------------------------


def test_a_pair_forms_with_the_closer_relative_not_the_nearer_stranger(sure_conception):
    world = hourly_world(mating_reach=10.0)
    me = put(world, lover(0), 500)
    stranger = put(world, differ(lover(1), 40, skip=("sex_strategy",)), 501)
    kin = put(world, differ(lover(1), 2, skip=("sex_strategy",)), 507)
    world.step()
    # Id order: `me` chooses first and picks its relative; the stranger then has nobody left.
    assert kin.traits.is_pregnant and kin.partner == me.id
    assert not stranger.traits.is_pregnant
    assert stranger.traits.mating_cooldown == 0 and kin.traits.mating_cooldown == 0
    assert me.traits.mating_cooldown > 0


def test_cross_breeding_happens_when_it_is_the_only_option(sure_conception):
    world = hourly_world(mating_reach=10.0)
    a = put(world, lover(0), 500)
    b = put(world, differ(lover(1), 60, skip=("sex_strategy",)), 501)
    world.step()
    assert b.traits.is_pregnant and b.partner == a.id


def test_the_mate_rule_is_one_function_the_world_calls(monkeypatch, sure_conception):
    from evolution_simulator.world import mating

    world = hourly_world(mating_reach=10.0)
    put(world, lover(0), 500)
    mother = put(world, lover(1), 501)
    monkeypatch.setattr(mating, "may_mate", lambda a, b: False)
    world.step()
    assert not mother.traits.is_pregnant
