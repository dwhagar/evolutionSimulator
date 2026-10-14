"""The family colour key (UX.30): two numbers that stay close for relatives."""

import math
import random
import statistics

import pytest
from world_support import animal_dna

from evolution_simulator.diploid import DiploidDNA
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.lineage import family_key
from evolution_simulator.session.snapshot import ANIMAL_COLUMNS, FRAME_FORMAT, pack_animals
from evolution_simulator.world import ANIMAL_FIELDS, Vec, World, WorldConfig


def spread(a, b) -> float:
    return math.dist(a, b)


def test_the_same_genome_gives_the_same_key_and_it_is_a_pair_of_numbers():
    dna = DNA.random(ANIMAL_LAYOUT, random.Random(1))
    assert family_key(dna) == family_key(DNA(ANIMAL_LAYOUT, str(dna)))
    a, b = family_key(dna)
    assert math.isfinite(a) and math.isfinite(b)


def test_random_genomes_spread_about_one_unit_on_each_number():
    rng = random.Random(2)
    keys = [family_key(DNA.random(ANIMAL_LAYOUT, rng)) for _ in range(400)]
    for column in (0, 1):
        values = [k[column] for k in keys]
        assert statistics.pstdev(values) == pytest.approx(1.0, abs=0.12)
        assert statistics.mean(values) == pytest.approx(0.0, abs=0.15)
    plants = [family_key(DNA.random(PLANT_LAYOUT, rng)) for _ in range(200)]
    assert statistics.pstdev(k[0] for k in plants) == pytest.approx(1.0, abs=0.2)


def test_a_few_changed_digits_move_the_key_a_little_and_many_move_it_far():
    rng = random.Random(3)
    base = DNA.random(ANIMAL_LAYOUT, rng)
    near = [spread(family_key(base), family_key(base.mutated(rng, 0.005))) for _ in range(40)]
    far = [spread(family_key(base), family_key(base.mutated(rng, 0.5))) for _ in range(40)]
    strangers = [
        spread(family_key(base), family_key(DNA.random(ANIMAL_LAYOUT, rng))) for _ in range(40)
    ]
    assert statistics.mean(near) < 0.25 * statistics.mean(strangers)
    assert statistics.mean(near) < statistics.mean(far) < statistics.mean(strangers) * 1.1


def test_a_child_sits_closer_to_its_parents_than_a_stranger_does():
    rng = random.Random(4)
    wins = 0
    for _ in range(40):
        mother, father = (DNA.random(ANIMAL_LAYOUT, rng) for _ in range(2))
        stranger = family_key(DNA.random(ANIMAL_LAYOUT, rng))
        child = family_key(mother.reproduce(father, rng))
        parents = min(spread(child, family_key(mother)), spread(child, family_key(father)))
        wins += parents < spread(child, stranger)
    assert wins >= 32  # a child of two strangers sits between them, not on either


def test_a_diploid_genome_is_the_mean_of_its_strands():
    rng = random.Random(5)
    first, second = DNA.random(ANIMAL_LAYOUT, rng), DNA.random(ANIMAL_LAYOUT, rng)
    key = family_key(DiploidDNA(first, second))
    a, b = family_key(first), family_key(second)
    assert key == pytest.approx(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    assert family_key(DiploidDNA.from_haploid(first)) == pytest.approx(family_key(first))


def test_an_animal_works_its_key_out_once_and_the_view_and_frame_carry_it():
    world = World(WorldConfig(seed=1))
    animal = world.add_animal(animal_dna(), Vec.of(500, 500))
    key = animal.traits.family_key
    assert key == family_key(animal.traits.dna)
    assert animal.traits.family_key is key  # cached
    view = world.animal_views()[0]
    assert (view.family_a, view.family_b) == key
    assert ANIMAL_FIELDS[-2:] == ("family_a", "family_b")
    block = pack_animals([view])
    assert block.columns == ANIMAL_COLUMNS and FRAME_FORMAT >= 2
    assert block.column("family_a")[0] == pytest.approx(key[0])
    assert block.column("family_b")[0] == pytest.approx(key[1])
