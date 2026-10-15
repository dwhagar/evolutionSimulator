"""Where an animal's eyes point (UX.43): the core side of the round creatures with eyes."""

import math

import pytest
from world_support import animal_dna, hourly_world, plant_dna

from evolution_simulator.brain_adapter import BrainDecision
from evolution_simulator.session import ANIMAL_COLUMNS, FRAME_FORMAT, Session
from evolution_simulator.world import Vec
from evolution_simulator.world.focus import choose_focus, look_angle


def decision(**kw):
    fields = {
        "turn": 0.0,
        "speed": 0.0,
        "eat_or_attack": 0.0,
        "seek_mating": 0.0,
        "alarm_call": 0.0,
        "mating_call": 0.0,
    }
    fields.update(kw)
    return BrainDecision(**fields)


TARGETS = [("plant", 1), ("prey", 2), ("mate", 3), ("threat", 4), ("young", 5)]


def test_danger_takes_the_eyes_first_then_what_it_is_doing():
    assert choose_focus(TARGETS, decision()) == 4
    without_threat = [t for t in TARGETS if t[0] != "threat"]
    assert choose_focus(without_threat, decision(seek_mating=1.0)) == 3
    assert choose_focus(without_threat, decision(eat_or_attack=1.0)) == 2
    assert choose_focus([("plant", 1)], decision(eat_or_attack=1.0)) == 1
    assert choose_focus(without_threat, decision()) == 5  # idle: its young, then the rest
    assert choose_focus([("plant", 1), ("prey", 2)], decision()) == 2
    assert choose_focus([], decision()) is None


def test_the_eyes_turn_toward_the_target_inside_the_field_of_vision():
    half = math.radians(60.0)
    here = Vec.of(0, 0)
    assert look_angle(0.0, here, Vec.of(10, 10), half) == pytest.approx(math.pi / 4)  # to the left
    assert look_angle(0.0, here, Vec.of(10, -10), half) == pytest.approx(-math.pi / 4)
    assert look_angle(math.pi / 2, here, Vec.of(0, 5), half) == pytest.approx(0.0)  # dead ahead
    assert look_angle(0.0, here, here, half) == 0.0  # on the same spot: straight ahead


def test_the_eyes_never_turn_past_the_edge_of_the_field_of_vision():
    half = math.radians(60.0)
    here = Vec.of(0, 0)
    assert look_angle(0.0, here, Vec.of(-10, 1), half) == pytest.approx(half)  # behind, left side
    assert look_angle(0.0, here, Vec.of(-10, -1), half) == pytest.approx(-half)
    assert look_angle(0.0, here, Vec.of(0, 10), half) == pytest.approx(half)  # square to the left


def test_an_animal_looks_at_a_plant_it_senses_and_the_frame_carries_the_angle():
    world = hourly_world(seed=4)
    animal = world.add_animal(animal_dna(), Vec.of(500, 500), heading=0.0)
    plant = world.add_plant(plant_dna(), Vec.of(503, 502))
    world.step()
    assert animal.focus == plant.id
    half = math.radians(animal.traits.fov_degrees) / 2.0
    view = world.animal_views()[0]
    assert 0.0 < view.look <= half  # up and to the left of its heading
    assert world.look_of(animal) == view.look
    detail = world.animal_detail(animal.id)
    assert detail.look == view.look and detail.focus == plant.id
    plant_gone = world.look_of(animal)
    world._plants.pop(plant.id)
    assert world.look_of(animal) == 0.0 and plant_gone != 0.0  # what it looked at is gone


def test_an_animal_that_senses_nothing_looks_straight_ahead():
    world = hourly_world(seed=4)
    animal = world.add_animal(animal_dna(), Vec.of(500, 500), heading=1.0)
    world.step()
    assert animal.focus is None and world.animal_views()[0].look == 0.0


def test_frames_carry_the_look_column_as_format_three():
    assert FRAME_FORMAT == 3 and ANIMAL_COLUMNS[-1] == "look"
    world = hourly_world(seed=4)
    animal = world.add_animal(animal_dna(), Vec.of(500, 500), heading=0.0)
    world.add_plant(plant_dna(), Vec.of(503, 502))
    world.step()
    frame = Session(world).frame()
    assert frame.format == 3
    assert frame.animals.column("look")[0] == pytest.approx(world.look_of(animal), abs=1e-6)
