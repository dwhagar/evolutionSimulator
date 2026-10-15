"""The rules for how an animal is drawn (UX.43): where the eyes, spots and colours go."""

import math

import numpy as np
import pytest
from worldview_support import animal, make_frame

from evolution_simulator.viewer.worldview import bodies, palette
from evolution_simulator.viewer.worldview.layers import Layer


def layer_of(*views):
    return Layer(make_frame(list(views)).animals)


def test_bodies_are_never_under_five_pixels_across():
    radius = np.array([0.01, 1.0, 10.0])
    assert bodies.body_radius_px(radius, 4.0) == pytest.approx([2.5, 4.0, 40.0])


def test_eyes_and_spots_are_dropped_below_a_size():
    assert not bodies.has_eyes(5.9) and bodies.has_eyes(6.0)
    assert not bodies.has_spots(4.9) and bodies.has_spots(5.0)


def test_the_spotted_sex_is_one_constant_and_defaults_to_females():
    layer = layer_of(animal(1, sex=0), animal(2, sex=1))
    assert bodies.SPOTTED_SEX == "female"
    assert bodies.spotted(layer).tolist() == [False, True]
    assert bodies.spotted(layer, "male").tolist() == [True, False]
    with pytest.raises(ValueError):
        bodies.spotted(layer, "other")


def test_the_eyes_are_at_the_front_either_side_and_the_pupils_lean_toward_the_gaze():
    left, right = bodies.eyes(100.0, 100.0, 40.0, heading=0.0, look=0.0)
    assert left.x == right.x == pytest.approx(100.0 + 18.0)  # forward is +x on screen
    assert left.y == pytest.approx(100.0 - 15.2) and right.y == pytest.approx(100.0 + 15.2)
    assert left.pupil_x > left.x and left.pupil_y == pytest.approx(left.y)  # straight ahead
    up, _ = bodies.eyes(100.0, 100.0, 40.0, heading=0.0, look=math.pi / 2)  # to its left
    assert up.pupil_y < up.y and up.pupil_x == pytest.approx(up.x)
    north, _ = bodies.eyes(100.0, 100.0, 40.0, heading=math.pi / 2, look=0.0)  # facing up
    assert north.y < 100.0 - 15.0


def test_the_spots_are_on_the_back_half():
    for x, y, r in bodies.spot_places(0.0, 0.0, 40.0, heading=0.0):
        assert x < 0.0 and r == pytest.approx(8.0)
    for x, y, r in bodies.spot_places(0.0, 0.0, 40.0, heading=math.pi):  # facing left
        assert x > 0.0


def test_a_frame_without_the_look_column_looks_straight_ahead():
    frame = make_frame([animal(1), animal(2)])
    assert bodies.looks(Layer(frame.animals)).tolist() == [0.0, 0.0]
    block = frame.animals
    columns = block.columns[:-1]
    values = np.frombuffer(block.values, dtype="<f4").reshape(-1, len(block.columns))[:, :-1]
    from dataclasses import replace

    old = Layer(replace(block, columns=columns, values=values.tobytes()))
    assert "look" not in old.columns and bodies.looks(old).tolist() == [0.0, 0.0]


def test_body_colour_runs_blue_to_red_with_diet_and_has_a_colour_blind_safe_pair():
    layer = layer_of(animal(1, diet=0.0), animal(2, diet=0.5), animal(3, diet=1.0))
    plain = palette.body_colours(layer)
    assert tuple(plain[0]) == palette.DIET_STOPS[0] and tuple(plain[2]) == palette.DIET_STOPS[-1]
    blue, red = plain[0].astype(int), plain[2].astype(int)
    assert blue[2] > blue[0] and red[0] > red[2]  # herbivores blue, carnivores red
    assert tuple(plain[1]) == palette.DIET_STOPS[1]  # omnivores between
    safe = palette.body_colours(layer, safe=True)
    assert tuple(safe[0]) == palette.SAFE_DIET_STOPS[0]
    assert tuple(safe[2]) == palette.SAFE_DIET_STOPS[-1]
    mode = palette.MODES_BY_ID["diet"]
    assert (mode.paint(layer) == plain).all() and (mode.paint(layer, safe=True) == safe).all()
    other = palette.MODES_BY_ID["energy"]
    assert (other.paint(layer, safe=True) == other.colours(layer)).all()


def test_plants_get_darker_the_tougher_they_are():
    plain = palette.plant_shades(4)
    tough = palette.plant_shades(4, toughness=1.0)
    assert tuple(plain[-1]) == palette.PLANT_FULL
    assert (tough < plain).all() and palette.plant_shades(4, toughness=0.5).sum() < plain.sum()
