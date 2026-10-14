"""Vectors, bounds, time scale and the neighbour index."""

import math

import pytest

from evolution_simulator.world import SPEED_PRESETS, Bounds, Pacer, TimeScale, Vec, format_duration
from evolution_simulator.world.spatial import SpatialIndex
from evolution_simulator.world.timescale import DAY, YEAR

# --- vectors ------------------------------------------------------------------


def test_vector_arithmetic_works_in_any_dimension():
    assert Vec.of(1, 2) + Vec.of(3, 4) == Vec.of(4, 6)
    assert Vec.of(1, 2, 3) - Vec.of(1, 1, 1) == Vec.of(0, 1, 2)
    assert Vec.of(1, 2) * 2 == 2 * Vec.of(1, 2) == Vec.of(2, 4)
    assert Vec.of(3, 4).length() == 5.0
    assert Vec.of(1, 1, 1).distance_to(Vec.of(1, 1, 4)) == 3.0
    assert Vec.of(1, 2).dot(Vec.of(3, 4)) == 11.0
    assert Vec.zero(3).coords == (0.0, 0.0, 0.0)


def test_vector_rejects_mixed_sizes_empty_and_non_finite():
    with pytest.raises(ValueError):
        Vec.of(1, 2) + Vec.of(1, 2, 3)
    with pytest.raises(ValueError):
        Vec(())
    with pytest.raises(ValueError):
        Vec.of(1, math.nan)


def test_normalised_and_angles():
    assert Vec.of(0, 5).normalised() == Vec.of(0, 1)
    assert Vec.zero(2).normalised() == Vec.zero(2)
    assert Vec.from_angle(math.pi / 2, 2).coords == pytest.approx((0.0, 2.0))
    assert Vec.of(0, -1).angle() == pytest.approx(-math.pi / 2)
    with pytest.raises(ValueError):
        Vec.of(1, 2, 3).angle()


# --- bounds -------------------------------------------------------------------


def test_bounds_default_to_1000_by_1000():
    bounds = Bounds()
    assert bounds.size == (1000.0, 1000.0)
    assert bounds.centre == Vec.of(500, 500)


def test_bounds_clamp_acts_as_walls():
    bounds = Bounds((100, 50))
    assert bounds.clamp(Vec.of(150, -5)) == Vec.of(100, 0)
    assert bounds.clamp(Vec.of(10, 20)) == Vec.of(10, 20)
    assert bounds.contains(Vec.of(100, 50))
    assert not bounds.contains(Vec.of(100.1, 50))


def test_bounds_can_be_user_sized_and_other_dimensions():
    assert Bounds((10, 10, 10)).dimensions == 3
    with pytest.raises(ValueError):
        Bounds((0, 10))
    with pytest.raises(ValueError):
        Bounds(())
    with pytest.raises(ValueError):
        Bounds((10, 10)).clamp(Vec.of(1, 2, 3))


# --- time scale ---------------------------------------------------------------


def test_a_tick_is_one_second_by_default():
    scale = TimeScale()
    assert scale.seconds_per_tick == 1.0
    assert scale.ticks_per_real_second == 1.0
    assert scale.simulated_seconds(90) == 90.0


def test_all_the_owners_presets_exist_with_the_right_ratio():
    assert SPEED_PRESETS["minute"] == 60
    assert SPEED_PRESETS["hour"] == 3600
    assert SPEED_PRESETS["day"] == DAY
    assert SPEED_PRESETS["week"] == 7 * DAY
    assert SPEED_PRESETS["month"] == pytest.approx(YEAR / 12)
    assert SPEED_PRESETS["year"] == YEAR
    assert SPEED_PRESETS["decade"] == 10 * YEAR
    assert SPEED_PRESETS["century"] == 100 * YEAR
    assert SPEED_PRESETS["millennium"] == 1000 * YEAR


def test_a_preset_sets_ticks_per_real_second():
    assert TimeScale.from_preset("hour").ticks_per_real_second == 3600
    assert TimeScale.from_preset("hour", seconds_per_tick=60).ticks_per_real_second == 60
    with pytest.raises(ValueError):
        TimeScale.from_preset("fortnight")


def test_time_scale_rejects_bad_values():
    with pytest.raises(ValueError):
        TimeScale(seconds_per_tick=0)
    with pytest.raises(ValueError):
        TimeScale(speed=-1)


def test_pacer_carries_the_fraction_between_calls():
    pacer = Pacer(TimeScale(speed=2.5))  # 2.5 ticks per real second
    assert pacer.advance(1.0) == 2
    assert pacer.advance(1.0) == 3  # 0.5 carried + 2.5
    assert pacer.advance(0.0) == 0


def test_pacer_drops_ticks_over_the_cap():
    pacer = Pacer(TimeScale.from_preset("year"))
    assert pacer.advance(1.0, max_ticks=500) == 500
    assert pacer.advance(0.0) == 0  # nothing queued behind it
    with pytest.raises(ValueError):
        pacer.advance(-1.0)


def test_format_duration():
    assert format_duration(0) == "00:00:00"
    assert format_duration(3725) == "01:02:05"
    assert format_duration(DAY + 61) == "1d 00:01:01"
    assert format_duration(2 * YEAR + 3 * DAY) == "2y 3d 00:00:00"


# --- spatial index ------------------------------------------------------------


def test_index_finds_ids_within_a_radius_in_order():
    index = SpatialIndex(10.0)
    index.insert(3, Vec.of(5, 5))
    index.insert(1, Vec.of(14, 5))
    index.insert(2, Vec.of(100, 100))
    assert index.query(Vec.of(5, 5), 10) == [1, 3]
    assert index.query(Vec.of(5, 5), 8) == [3]
    assert index.query(Vec.of(-30, -30), 5) == []


def test_index_query_with_distance_reports_each_distance():
    index = SpatialIndex(10.0)
    index.insert(2, Vec.of(3, 4))
    index.insert(1, Vec.of(0, 1))
    index.insert(3, Vec.of(50, 50))
    assert index.query_with_distance(Vec.of(0, 0), 6) == [(1, 1.0), (2, 5.0)]


def test_index_within_reach_goes_by_surfaces_not_centres():
    index = SpatialIndex(10.0)
    index.insert(1, Vec.of(30, 0), extent=5.0)  # surface 25 from the origin
    index.insert(2, Vec.of(0, 12), extent=0.0)
    index.insert(3, Vec.of(-100, 0), extent=20.0)  # surface 80
    found = sorted(index.within_reach(Vec.of(0, 0), 25))
    assert found == [(1, 30.0, 5.0), (2, 12.0, 0.0)]
    assert sorted(index.within_reach(Vec.of(0, 0), 24.9)) == [(2, 12.0, 0.0)]
    assert sorted(i for i, _, _ in index.within_reach(Vec.of(0, 0), 80)) == [1, 2, 3]
    index.remove(1)
    assert [i for i, _, _ in index.within_reach(Vec.of(0, 0), 25)] == [2]


def test_index_within_reach_finds_a_wide_item_whose_centre_is_in_a_far_cell():
    index = SpatialIndex(10.0)
    index.insert(7, Vec.of(95, 5), extent=40.0)  # many cells away, but the edge is 55 off
    assert [i for i, _, _ in index.within_reach(Vec.of(0, 5), 55)] == [7]
    assert index.within_reach(Vec.of(0, 5), 54) == []


def test_index_remove_and_duplicates():
    index = SpatialIndex(10.0)
    index.insert(1, Vec.of(1, 1))
    with pytest.raises(ValueError):
        index.insert(1, Vec.of(2, 2))
    index.remove(1)
    assert 1 not in index
    assert len(index) == 0
    assert index.query(Vec.of(1, 1), 5) == []


def test_index_works_in_three_dimensions():
    index = SpatialIndex(10.0)
    index.insert(1, Vec.of(1, 1, 1))
    index.insert(2, Vec.of(1, 1, 30))
    assert index.query(Vec.of(0, 0, 0), 5) == [1]
