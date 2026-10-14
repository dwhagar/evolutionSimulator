"""The world view's parts that need no window (UX.12): camera, colours and the glide."""

import math

import pytest

pytest.importorskip("numpy")

from worldview_support import WORLD, animal, luminance, make_frame, status  # noqa: F401

from evolution_simulator.session import ANIMAL_COLUMNS, ANIMAL_FLAGS
from evolution_simulator.session.snapshot import pack_animals
from evolution_simulator.viewer.worldview import glide, palette
from evolution_simulator.viewer.worldview.camera import Camera, nice_step
from evolution_simulator.viewer.worldview.layers import Layer

SIZE = (400.0, 300.0)


# --- camera ------------------------------------------------------------------------


def test_world_y_points_up_the_screen_and_the_two_conversions_agree():
    camera = Camera(scale=2.0, cx=50.0, cy=50.0)
    assert camera.to_screen(50.0, 50.0, SIZE) == (200.0, 150.0)
    _, high = camera.to_screen(50.0, 60.0, SIZE)
    assert high < 150.0
    x, y = camera.to_world(*camera.to_screen(12.0, 77.0, SIZE), SIZE)
    assert (round(x, 9), round(y, 9)) == (12.0, 77.0)


def test_fit_shows_the_whole_world_centred():
    camera = Camera()
    camera.fit(WORLD, SIZE)
    left, top = camera.to_screen(0.0, 100.0, SIZE)
    right, bottom = camera.to_screen(100.0, 0.0, SIZE)
    assert 0 < left and right < SIZE[0] and 0 < top and bottom < SIZE[1]
    assert (left + right) / 2 == pytest.approx(SIZE[0] / 2)
    assert (top + bottom) / 2 == pytest.approx(SIZE[1] / 2)


def test_zooming_keeps_the_point_under_the_pointer_still_and_stops_at_the_limits():
    camera = Camera()
    camera.fit(WORLD, SIZE)
    anchor = (320.0, 90.0)
    before = camera.to_world(*anchor, SIZE)
    camera.zoom_at(2.0, *anchor, SIZE, WORLD)
    after = camera.to_world(*anchor, SIZE)
    assert after == pytest.approx(before)
    for _ in range(40):
        camera.zoom_at(2.0, 10.0, 10.0, SIZE, WORLD)
    assert camera.scale == pytest.approx(60.0)
    for _ in range(40):
        camera.zoom_at(0.5, 10.0, 10.0, SIZE, WORLD)
    assert camera.scale == pytest.approx(Camera.fit_scale(WORLD, SIZE) * 0.5)


def test_dragging_moves_the_picture_with_the_pointer_and_cannot_lose_the_world():
    camera = Camera(scale=2.0, cx=50.0, cy=50.0)
    camera.pan_pixels(20.0, 10.0, WORLD)  # drag right and down: the world slides right and down
    assert (camera.cx, camera.cy) == (40.0, 55.0)
    camera.pan_pixels(-10_000.0, 10_000.0, WORLD)
    assert (camera.cx, camera.cy) == (100.0, 100.0)


def test_nice_steps_are_one_two_or_five_times_a_power_of_ten():
    assert [nice_step(v) for v in (0.9, 1.0, 1.1, 3.0, 7.0, 120.0)] == [1, 1, 2, 5, 10, 200]
    assert nice_step(0.0) == 1.0 and nice_step(float("nan")) == 1.0


# --- layers and colours ------------------------------------------------------------


def test_a_layer_reads_a_block_as_arrays():
    layer = Layer(pack_animals([animal(7, x=3.0, sex=1), animal(9, x=4.0, asleep=True)]))
    assert layer.count == 2 and list(layer.ids) == [7, 9]
    assert list(layer.col("x")) == [3.0, 4.0]
    assert list(layer.flag(ANIMAL_FLAGS["female"])) == [True, False]
    assert list(layer.flag(ANIMAL_FLAGS["asleep"])) == [False, True]
    assert Layer(pack_animals([])).values.shape == (0, len(ANIMAL_COLUMNS))


def test_diet_runs_from_blue_to_vermillion_and_sex_has_two_colours():
    layer = Layer(pack_animals([animal(1, diet=0.0), animal(2, diet=1.0), animal(3, sex=1)]))
    diet = palette.MODES_BY_ID["diet"].colours(layer)
    assert tuple(diet[0]) == palette.DIET_STOPS[0] and tuple(diet[1]) == palette.DIET_STOPS[-1]
    sex = palette.MODES_BY_ID["sex"].colours(layer)
    assert tuple(sex[0]) == palette.MALE and tuple(sex[2]) == palette.FEMALE


@pytest.mark.parametrize("mode, column", [("energy", "energy_ratio"), ("age", "age_ratio")])
def test_the_ramps_change_in_lightness_so_they_survive_colour_blindness(mode, column):
    levels = [0.0, 0.25, 0.5, 0.75, 1.0]
    layer = Layer(pack_animals([animal(i, **{column: v}) for i, v in enumerate(levels)]))
    lights = [luminance(c) for c in palette.MODES_BY_ID[mode].colours(layer)]
    ordered = sorted(lights, reverse=(mode == "age"))
    assert lights == ordered and len(set(lights)) == len(lights)


def test_the_family_mode_waits_for_its_column():
    family = palette.MODES_BY_ID["family"]
    assert not family.available(ANIMAL_COLUMNS) and family.available((*ANIMAL_COLUMNS, "family"))
    assert [m.id for m in palette.MODES if m.available(ANIMAL_COLUMNS)] == [
        "diet",
        "sex",
        "energy",
        "age",
    ]


def test_the_ground_goes_from_night_to_day():
    assert palette.ground(0.0) == palette.GROUND_NIGHT
    assert palette.ground(1.0) == palette.GROUND_DAY
    assert (
        palette.ground(5.0) == palette.GROUND_DAY and palette.ground(-1.0) == palette.GROUND_NIGHT
    )


# --- gliding -----------------------------------------------------------------------


def test_glide_duration_is_the_real_time_a_step_takes_and_none_when_it_is_not_worth_it():
    assert glide.duration(3600.0, 3600.0, running=True) == 1.0
    assert glide.duration(3600.0, 3600.0, running=False) is None  # paused or stepping: exact
    assert glide.duration(3600.0, None, running=True) is None  # as fast as possible
    assert glide.duration(3600.0, 86_400.0, running=True) is None  # 24 ticks a second
    assert glide.duration(3600.0, 1.0, running=True) == 3600.0  # real time: an hour, still
    assert glide.duration(0.0, 3600.0, running=True) is None


def test_blend_slides_known_animals_and_leaves_new_ones_where_they_are():
    before = Layer(pack_animals([animal(1, x=10.0, y=0.0), animal(2, x=0.0, y=0.0)]))
    after = Layer(pack_animals([animal(2, x=8.0, y=4.0), animal(3, x=50.0), animal(1, x=20.0)]))
    pose = glide.blend(glide.pose_of(before), after, 0.5)
    assert list(pose.ids) == [2, 3, 1]
    assert (
        list(pose.x) == [4.0, 50.0, 15.0] and list(pose.y) == [2.0, 50.0, 50.0 * 0.0 + 25.0] or True
    )
    assert pose.x.tolist() == [4.0, 50.0, 15.0]
    assert pose.y.tolist() == [2.0, 50.0, 25.0]
    assert glide.blend(glide.pose_of(before), after, 1.0).x.tolist() == [8.0, 50.0, 20.0]
    assert glide.blend(None, after, 0.0).x.tolist() == [8.0, 50.0, 20.0]


def test_blend_turns_the_short_way_round():
    before = Layer(pack_animals([animal(1, heading=3.0)]))
    after = Layer(pack_animals([animal(1, heading=-3.0)]))
    heading = float(glide.blend(glide.pose_of(before), after, 0.5).heading[0])
    assert math.cos(heading) == pytest.approx(-1.0, abs=1e-3)  # through pi, not through 0
