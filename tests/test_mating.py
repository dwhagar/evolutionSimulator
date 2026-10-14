"""Who mates with whom: closest genome first, cross-breeding as the last choice (REPRO.4)."""

import pytest
from world_support import animal_dna, grown

from evolution_simulator.diploid import DiploidDNA
from evolution_simulator.dna import DNA
from evolution_simulator.world import Vec, World, WorldConfig
from evolution_simulator.world.mating import choose_mate, mate_rank, may_mate

HERE = Vec.of(500, 500)
STILL = {"speed": -2.0}
LOVER = {"mate": 2.0}


def lover(**genes: str) -> DNA:
    return animal_dna(brain={**STILL, **LOVER}, **genes)


def differ(dna: DNA, digits: int) -> DNA:
    """The same genome with its first ``digits`` body digits changed."""
    changed = [(d + 1) % 4 if i < digits else d for i, d in enumerate(dna.sequence)]
    return DNA(dna.layout, changed)


@pytest.fixture
def world() -> World:
    return World(WorldConfig(seed=0, mating_reach=10.0))


def put(world: World, dna: DNA, x: float):
    animal = world.add_animal(dna, Vec.of(x, 500), heading=0.0)
    grown(animal)
    return animal


# --- the rules --------------------------------------------------------------


def test_any_two_animals_of_one_kind_may_mate_but_not_an_animal_with_itself(world):
    a, b = put(world, lover(), 500), put(world, lover(), 501)
    assert may_mate(a, b) and may_mate(b, a)
    assert not may_mate(a, a)


def test_animals_with_different_kinds_of_genome_cannot_mate(world):
    a = put(world, lover(), 500)
    b = put(world, lover(), 501)
    b.traits.dna = DiploidDNA.from_haploid(b.traits.dna)  # same layout, other ploidy
    assert not may_mate(a, b) and not may_mate(b, a)


def test_the_closest_genome_is_chosen_even_when_a_stranger_is_nearer(world):
    me = put(world, lover(), 500)
    kin = put(world, differ(lover(), 3), 508)
    stranger = put(world, differ(lover(), 40), 501)
    assert choose_mate(me, [stranger, kin]) is kin
    assert choose_mate(me, [kin, stranger]) is kin
    assert mate_rank(me, kin)[0] < mate_rank(me, stranger)[0]


def test_a_distant_genome_is_still_chosen_when_nothing_closer_is_in_reach(world):
    me = put(world, lover(), 500)
    stranger = put(world, differ(lover(), 60), 501)
    assert (
        choose_mate(me, [stranger]) is stranger
    )  # cross-breeding is allowed, just least preferred


def test_ties_go_to_the_nearer_animal_then_the_lower_id(world):
    me = put(world, lover(), 500)
    near = put(world, lover(), 502)
    far = put(world, lover(), 506)
    assert choose_mate(me, [far, near]) is near
    twin_a, twin_b = put(world, lover(), 504), put(world, lover(), 496)
    assert choose_mate(me, [twin_b, twin_a]) is twin_a  # same genome, same distance: lower id


def test_nobody_in_reach_means_no_choice(world):
    me = put(world, lover(), 500)
    assert choose_mate(me, []) is None
    assert choose_mate(me, [me]) is None


# --- in the world -----------------------------------------------------------


def test_a_pair_forms_with_the_closer_relative_not_the_nearer_stranger():
    world = World(WorldConfig(seed=0, mating_reach=10.0))
    me = put(world, lover(), 500)
    stranger = put(world, differ(lover(), 40), 501)
    kin = put(world, differ(lover(), 2), 507)
    report = world.step()
    # Id order: `me` chooses first and picks its relative; the stranger then has nobody left.
    assert report.animal_births == 1
    child = world.animals[-1]
    assert set(child.parents) == {me.id, kin.id}
    assert stranger.traits.mating_cooldown == 0 and kin.traits.mating_cooldown > 0


def test_cross_breeding_happens_when_it_is_the_only_option():
    world = World(WorldConfig(seed=0, mating_reach=10.0))
    a = put(world, lover(), 500)
    b = put(world, differ(lover(), 60), 501)
    assert world.step().animal_births == 1
    assert set(world.animals[-1].parents) == {a.id, b.id}


def test_the_mate_rule_is_one_function_the_world_calls(monkeypatch):
    from evolution_simulator.world import mating

    world = World(WorldConfig(seed=0, mating_reach=10.0))
    put(world, lover(), 500)
    put(world, lover(), 501)
    monkeypatch.setattr(mating, "may_mate", lambda a, b: False)
    assert world.step().animal_births == 0
