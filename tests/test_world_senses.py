"""BasicSenses: what an animal perceives, and that the senses can be swapped."""

import math

import pytest
from world_support import animal_dna, plant_dna

from evolution_simulator.brain_adapter import Percepts
from evolution_simulator.world import BasicSenses, Vec, World, WorldConfig
from evolution_simulator.world.senses import relative_direction, wrap_angle

LONG_SIGHT = "3333"
NARROW = {"sight_range": LONG_SIGHT, "sight_fov": "0000"}  # 60 units, 40 degrees
WIDE = {"sight_range": LONG_SIGHT, "sight_fov": "3333"}  # 33 units, all round
MASS_1 = "0000"
MASS_2 = "1111"
MASS_4 = "3333"
HERE = Vec.of(500, 500)


def seen_by(world, animal):
    return BasicSenses().perceive(world, animal)


def test_wrap_angle_and_relative_direction():
    assert abs(wrap_angle(3 * math.pi)) == pytest.approx(math.pi)
    assert wrap_angle(2.5 * math.pi) == pytest.approx(0.5 * math.pi)
    assert relative_direction(0.0, HERE, Vec.of(600, 500)) == pytest.approx(0.0)
    assert relative_direction(0.0, HERE, Vec.of(500, 600)) == pytest.approx(-0.5)  # to the left
    assert relative_direction(0.0, HERE, Vec.of(500, 400)) == pytest.approx(0.5)  # to the right
    assert abs(relative_direction(0.0, HERE, Vec.of(400, 500))) == pytest.approx(1.0)  # behind


def test_a_plant_ahead_is_in_the_middle_and_closeness_follows_distance():
    world = World()
    animal = world.add_animal(animal_dna(**NARROW), HERE, heading=0.0)
    world.add_plant(plant_dna(), Vec.of(520, 500))
    seen = seen_by(world, animal)
    sight = animal.traits.current_sight_range
    assert seen.plant_direction == pytest.approx(0.0)
    assert seen.plant_closeness == pytest.approx(1.0 - 20.0 / sight)


def test_left_is_negative_and_right_is_positive_when_the_view_is_wide():
    world = World()
    animal = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    world.add_plant(plant_dna(), Vec.of(500, 510))
    assert seen_by(world, animal).plant_direction == pytest.approx(-0.5)
    world = World()
    animal = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    world.add_plant(plant_dna(), Vec.of(500, 490))
    assert seen_by(world, animal).plant_direction == pytest.approx(0.5)


def test_turning_toward_what_it_sees_uses_the_same_sign_as_the_direction():
    # Facing +x with food to the right (direction +): a positive turn reduces the bearing gap.
    world = World()
    animal = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    plant = world.add_plant(plant_dna(), Vec.of(500, 490))
    assert seen_by(world, animal).plant_direction > 0
    animal.heading = wrap_angle(animal.heading - 0.3)  # what turn=+1 does at turn rate 0.3
    assert relative_direction(animal.heading, animal.position, plant.position) < 0.5


def test_things_out_of_range_or_outside_the_field_of_view_are_not_seen():
    world = World()
    animal = world.add_animal(animal_dna(**NARROW), HERE, heading=0.0)
    world.add_plant(plant_dna(), Vec.of(500 + 100, 500))  # beyond 60 units
    world.add_plant(plant_dna(), Vec.of(480, 500))  # behind, outside 40 degrees
    world.add_plant(plant_dna(), Vec.of(510, 540))  # ahead-ish but far off to the side
    seen = seen_by(world, animal)
    assert seen.plant_closeness == 0.0
    assert seen.plant_direction == 0.0


def test_the_nearest_plant_wins_ties_by_id():
    world = World()
    animal = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    far = world.add_plant(plant_dna(), Vec.of(520, 500))
    near = world.add_plant(plant_dna(), Vec.of(505, 505))
    seen = seen_by(world, animal)
    assert seen.plant_closeness == pytest.approx(
        1.0 - animal.position.distance_to(near.position) / animal.traits.current_sight_range
    )
    assert far.id < near.id


def test_other_animals_are_prey_threat_or_possible_mate_by_mass():
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2, **WIDE), HERE, heading=0.0)
    world.add_animal(animal_dna(size=MASS_1), Vec.of(510, 500))  # lighter
    world.add_animal(animal_dna(size=MASS_4), Vec.of(500, 510))  # heavier
    world.add_animal(animal_dna(size=MASS_2), Vec.of(490, 500))  # similar
    seen = seen_by(world, me)
    assert seen.prey_closeness > 0 and seen.prey_direction == pytest.approx(0.0)
    assert seen.threat_closeness > 0 and seen.threat_direction == pytest.approx(-0.5)
    assert seen.mate_closeness > 0 and abs(seen.mate_direction) == pytest.approx(1.0)
    assert seen.crowding == pytest.approx(0.3)


def test_relative_size_is_that_of_the_nearer_of_prey_and_threat():
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2, **WIDE), HERE, heading=0.0)
    world.add_animal(animal_dna(size=MASS_1), Vec.of(510, 500))  # lighter: half the mass
    world.add_animal(animal_dna(size=MASS_4), Vec.of(500, 520))  # heavier: twice the mass, further
    assert seen_by(world, me).relative_size == pytest.approx(-0.5)  # log2(1/2) / 2
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2, **WIDE), HERE, heading=0.0)
    world.add_animal(animal_dna(size=MASS_1), Vec.of(520, 500))
    world.add_animal(animal_dna(size=MASS_4), Vec.of(500, 510))  # now the nearer one
    assert seen_by(world, me).relative_size == pytest.approx(0.5)  # log2(2) / 2
    world = World()
    alone = world.add_animal(animal_dna(size=MASS_2, **WIDE), HERE, heading=0.0)
    world.add_animal(animal_dna(size=MASS_2), Vec.of(510, 500))  # a possible mate is not sized
    assert seen_by(world, alone).relative_size == 0.0


def test_the_time_of_day_is_reported():
    world = World()
    me = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    assert seen_by(world, me).daylight == 1.0  # no day cycle: always full daylight
    assert seen_by(world, me).senses_nothing  # and that is not a sense


def test_an_animal_does_not_sense_itself():
    world = World()
    me = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    seen = seen_by(world, me)
    assert seen == Percepts(daylight=1.0)  # daylight is reported even when nothing else is


def test_touch_needs_the_touch_gene_and_something_close():
    world = World()
    toucher = world.add_animal(animal_dna(touch="3333", **WIDE), HERE, heading=0.0)
    numb = world.add_animal(animal_dna(touch="0000", **WIDE), Vec.of(502, 500), heading=0.0)
    assert seen_by(world, toucher).touching
    assert not seen_by(world, numb).touching
    world.add_plant(plant_dna(), Vec.of(600, 600))
    far_toucher = world.add_animal(animal_dna(touch="3333", **WIDE), Vec.of(900, 100))
    assert not seen_by(world, far_toucher).touching


def test_perceiving_changes_nothing():
    world = World(WorldConfig(seed=3))
    world.populate(animals=10, plants=40)
    before = world.state_digest()
    for animal in world.animals:
        seen_by(world, animal)
    assert world.state_digest() == before


def test_the_step_loop_uses_whatever_senses_it_is_given():
    class AlwaysFoodAhead:
        def __init__(self):
            self.asked = []

        def perceive(self, world, animal):
            self.asked.append(animal.id)
            return Percepts(plant_closeness=0.7)

    senses = AlwaysFoodAhead()
    world = World(WorldConfig(), senses=senses)
    first = world.add_animal(animal_dna(), HERE, heading=0.0)
    second = world.add_animal(animal_dna(), Vec.of(100, 100), heading=1.0)
    world.step()
    assert senses.asked == [first.id, second.id]
    assert first.last_decision is not None
