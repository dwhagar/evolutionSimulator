"""The sensing step (SENSE.10): what a creature perceives, as a pure function."""

import dataclasses
import math
import random
import statistics

import pytest

from evolution_simulator.brain_adapter import INPUT_NAMES, Percepts, build_inputs
from evolution_simulator.sensing import (
    Neighbour,
    SenseOrgans,
    SensingConditions,
    SensingRules,
    sense,
)
from evolution_simulator.world.vector import Vec

ORIGIN = Vec.of(0.0, 0.0)
BODY = {
    "energy_ratio": 0.5,
    "health_ratio": 0.5,
    "vitality": 0.5,
    "ready_to_mate": False,
    "pain": 0.0,
    "tiredness": 0.0,
}


def at(distance: float, degrees: float = 0.0) -> Vec:
    """A point ``distance`` away, ``degrees`` counterclockwise (to the left) of facing east."""
    return Vec.from_angle(math.radians(degrees), distance)


def look(neighbours, organs=None, heading=0.0, radius=0.0, **kwargs):
    organs = organs or SenseOrgans(vision_range=40.0, hearing_range=40.0, smell_range=40.0)
    return sense(ORIGIN, heading, radius, organs, neighbours, **kwargs)


def thing(role, distance, degrees=0.0, ident=1, **kwargs):
    return Neighbour(ident, role, at(distance, degrees), **kwargs)


# --- the worked example in the design note ----------------------------------------


def test_worked_example_by_day_and_by_night():
    organs = SenseOrgans(vision_range=40.0, vision_fov_degrees=120.0, smell_range=50.0)
    plant = thing("plant", 20.0, 30.0)
    day = sense(ORIGIN, 0.0, 0.0, organs, [plant], SensingConditions(daylight=1.0))
    assert day.plant_closeness == pytest.approx(0.6)  # R_class is the smell range, 50
    assert day.plant_direction == pytest.approx(-0.5)  # vision: -30 / 60, the left is negative
    night = sense(ORIGIN, 0.0, 0.0, organs, [plant], SensingConditions(daylight=0.3))
    # vision is dimmed to 0.475 * 40 = 19 and no longer reaches; smell still does
    assert night.plant_closeness == pytest.approx(0.6)
    assert night.plant_direction == pytest.approx(-30.0 / 180.0)


# --- nothing, one thing, many things ---------------------------------------------


def test_an_empty_world_gives_the_default_percepts():
    assert look([]) == Percepts(daylight=1.0)  # daylight is the time of day, not a sense
    assert look([]).senses_nothing


def test_closeness_and_direction_signs():
    right = look([thing("prey", 10.0, -45.0)])
    assert right.prey_direction > 0 and right.prey_closeness == pytest.approx(0.75)
    left = look([thing("prey", 10.0, 45.0)])
    assert left.prey_direction < 0
    ahead = look([thing("mate", 10.0, 0.0)])
    assert ahead.mate_direction == 0.0


def test_direction_is_relative_to_the_heading():
    percepts = look([thing("threat", 10.0, 90.0)], heading=math.radians(90.0))
    assert percepts.threat_direction == pytest.approx(0.0)
    behind = look([thing("threat", 10.0, 180.0)])
    assert abs(behind.threat_direction) == pytest.approx(1.0)  # all-round senses: 180 degrees = 1


def test_distance_is_between_surfaces():
    # centre 12 away, bodies of radius 2 and 2: the surfaces are 8 apart; range 40 -> 1 - 8/40
    percepts = look([Neighbour(1, "plant", at(12.0), radius=2.0)], radius=2.0)
    assert percepts.plant_closeness == pytest.approx(0.8)
    touching = look([Neighbour(1, "plant", at(3.0), radius=2.0)], radius=2.0)  # overlapping
    assert touching.plant_closeness == pytest.approx(1.0)


def test_the_nearest_of_each_class_is_reported_and_ties_go_to_the_lower_id():
    percepts = look(
        [
            thing("prey", 30.0, ident=1),
            thing("prey", 10.0, 20.0, ident=2),
            thing("prey", 10.0, -20.0, ident=3),
            thing("threat", 5.0, ident=4),
        ]
    )
    assert percepts.prey_closeness == pytest.approx(0.75)
    assert percepts.prey_direction < 0  # ident 2, on the left
    assert percepts.threat_closeness == pytest.approx(0.875)
    assert percepts.mate_closeness == 0.0


# --- what each organ can and cannot report ---------------------------------------


def test_vision_only_sees_inside_its_field_of_view():
    eye = SenseOrgans(vision_range=40.0, vision_fov_degrees=90.0)
    assert look([thing("prey", 10.0, 40.0)], eye).prey_closeness > 0
    assert look([thing("prey", 10.0, 50.0)], eye).prey_closeness == 0.0
    assert look([thing("prey", 10.0, 180.0)], eye).prey_closeness == 0.0
    edge = look([thing("prey", 10.0, 44.0)], eye)
    assert abs(edge.prey_direction) == pytest.approx(44.0 / 45.0)  # the edge of view reads 1


def test_hearing_and_smell_work_all_round_but_hearing_cannot_find_plants():
    ears = SenseOrgans(hearing_range=40.0)
    assert look([thing("prey", 10.0, 180.0)], ears).prey_closeness == pytest.approx(0.75)
    assert look([thing("plant", 10.0)], ears).plant_closeness == 0.0
    nose = SenseOrgans(smell_range=40.0)
    assert look([thing("plant", 10.0, 180.0)], nose).plant_closeness == pytest.approx(0.75)


def test_smell_is_weak_for_prey_and_threats():
    nose = SenseOrgans(smell_range=40.0)
    rules = SensingRules(weak_smell=0.5)
    near = look([thing("prey", 10.0)], nose, rules=rules)
    assert near.prey_closeness == pytest.approx(0.5)  # scaled to the weak range, 20
    assert look([thing("prey", 25.0)], nose, rules=rules).prey_closeness == 0.0
    assert look([thing("mate", 25.0)], nose, rules=rules).mate_closeness > 0.0


def test_loudness_and_scent_shrink_what_hearing_and_smell_find():
    ears = SenseOrgans(hearing_range=40.0)
    assert look([thing("prey", 15.0, loudness=0.25)], ears).prey_closeness == 0.0
    assert look([thing("prey", 15.0, loudness=1.0)], ears).prey_closeness > 0.0
    nose = SenseOrgans(smell_range=40.0)
    assert look([thing("plant", 15.0, scent=0.25)], nose).plant_closeness == 0.0
    assert look([thing("plant", 15.0, scent=0.5)], nose).plant_closeness > 0.0


def test_the_most_precise_organ_gives_the_direction_and_the_best_range_the_scale():
    organs = SenseOrgans(vision_range=20.0, vision_fov_degrees=180.0, smell_range=60.0)
    percepts = look([thing("plant", 15.0, 45.0)], organs)
    assert percepts.plant_direction == pytest.approx(-0.5)  # vision: 45 / 90
    assert percepts.plant_closeness == pytest.approx(0.75)  # smell: 1 - 15/60
    behind = look([thing("plant", 15.0, 170.0)], organs)  # vision cannot see it
    assert behind.plant_direction == pytest.approx(-170.0 / 180.0)


def test_an_organ_with_no_range_is_off():
    assert look([thing("plant", 1.0)], SenseOrgans()) == Percepts(daylight=1.0)
    assert (
        look([thing("plant", 1.0)], SenseOrgans(vision_range=0.0, smell_range=10.0)).plant_closeness
        > 0
    )


# --- daylight and sleep ----------------------------------------------------------


def test_darkness_dims_vision_but_not_smell_or_hearing():
    rules = SensingRules(light_floor=0.25)
    eye = SenseOrgans(vision_range=40.0)
    assert look(
        [thing("plant", 12.0)], eye, conditions=SensingConditions(0.0), rules=rules
    ).plant_closeness == pytest.approx(0.0)  # range 10: out of reach
    assert look(
        [thing("plant", 8.0)], eye, conditions=SensingConditions(0.0), rules=rules
    ).plant_closeness == pytest.approx(0.2)
    nose = SenseOrgans(smell_range=40.0)
    dark = look([thing("plant", 12.0)], nose, conditions=SensingConditions(0.0))
    assert dark.plant_closeness == pytest.approx(0.7)


def test_light_factor_follows_the_design_note():
    assert SensingRules().light_factor(0.3) == pytest.approx(0.475)
    assert SensingRules().light_factor(1.0) == 1.0


def test_sleep_switches_vision_off_and_halves_hearing_and_smell():
    asleep = SensingConditions(asleep=True)
    eye = SenseOrgans(vision_range=40.0)
    assert look([thing("plant", 5.0)], eye, conditions=asleep) == Percepts(daylight=1.0)
    nose = SenseOrgans(smell_range=40.0)
    assert look([thing("plant", 5.0)], nose, conditions=asleep).plant_closeness == pytest.approx(
        0.75
    )
    assert look([thing("plant", 25.0)], nose, conditions=asleep).plant_closeness == 0.0
    feel = SenseOrgans(touch_reach=1.0)
    assert look([thing("plant", 1.0)], feel, conditions=asleep).touching


# --- touch, calls, crowding -----------------------------------------------------


def test_touch_is_contact_within_reach_and_includes_the_world_edge():
    feel = SenseOrgans(touch_reach=1.0)
    assert look([thing("plant", 0.5)], feel).touching
    assert look([thing("plant", 1.0)], feel).touching
    assert not look([thing("plant", 1.5)], feel).touching
    assert look([], feel, edge_distance=0.5).touching
    assert not look([], feel, edge_distance=2.0).touching
    # with no reach beyond the body, only overlap counts
    assert look([Neighbour(1, "other", at(1.5), radius=1.0)], SenseOrgans(), radius=0.5).touching
    assert not look(
        [Neighbour(1, "other", at(5.0), radius=1.0)], SenseOrgans(), radius=0.5
    ).touching


def test_calls_are_heard_with_a_strength_and_a_direction():
    ears = SenseOrgans(hearing_range=40.0)
    alarm = thing("threat", 10.0, 90.0, alarm_call_radius=40.0)
    mating = thing("mate", 20.0, -90.0, ident=2, mating_call_radius=40.0)
    percepts = look([alarm, mating], ears)
    assert percepts.alarm_strength == pytest.approx(0.75)
    assert percepts.mating_call_strength == pytest.approx(0.5)
    assert percepts.call_direction == pytest.approx(-0.5)  # the louder alarm, on the left
    quiet = look([mating], ears)
    assert quiet.call_direction == pytest.approx(0.5)  # on the right


def test_a_call_needs_hearing_range_and_call_range():
    far = thing("threat", 30.0, alarm_call_radius=100.0)
    assert look([far], SenseOrgans(hearing_range=20.0)).alarm_strength == 0.0
    assert look([far], SenseOrgans(hearing_range=40.0)).alarm_strength == pytest.approx(0.7)
    short = thing("threat", 30.0, alarm_call_radius=20.0)
    assert look([short], SenseOrgans(hearing_range=40.0)).alarm_strength == 0.0
    assert look([far], SenseOrgans(vision_range=40.0, smell_range=40.0)).alarm_strength == 0.0


def test_crowding_counts_animals_that_vision_or_hearing_find_and_is_capped():
    rules = SensingRules(crowding_reference=4)
    crowd = [thing("other", 5.0, ident=i, degrees=10.0 * i) for i in range(1, 3)]
    assert look(crowd, rules=rules).crowding == pytest.approx(0.5)
    crowd += [
        thing("prey", 6.0, ident=10),
        thing("threat", 6.0, ident=11),
        thing("mate", 6.0, ident=12),
    ]
    assert look(crowd, rules=rules).crowding == 1.0
    assert look([thing("plant", 5.0)], rules=rules).crowding == 0.0  # plants are not crowds
    assert (
        look(crowd, SenseOrgans(smell_range=40.0), rules=rules).crowding == 0.0
    )  # smell does not count
    assert look([thing("other", 90.0)], rules=rules).crowding == 0.0  # out of reach


# --- noise -----------------------------------------------------------------------


def test_without_a_generator_every_report_is_exact():
    organs = SenseOrgans(vision_range=40.0, vision_noise=0.5, hearing_range=40.0, hearing_noise=0.5)
    a = look([thing("prey", 10.0, 20.0)], organs)
    b = look([thing("prey", 10.0, 20.0)], organs)
    assert a == b
    assert a.prey_closeness == pytest.approx(0.75)


def test_noise_is_seeded_and_repeatable():
    organs = SenseOrgans(smell_range=40.0, smell_noise=0.3)
    plant = [thing("plant", 10.0, 30.0)]
    one = look(plant, organs, rng=random.Random(5))
    two = look(plant, organs, rng=random.Random(5))
    three = look(plant, organs, rng=random.Random(6))
    exact = look(plant, organs)
    assert one == two
    assert one != three
    assert one.plant_direction != exact.plant_direction


def test_noise_falls_as_the_organ_improves_and_stays_inside_the_range():
    plant = [thing("plant", 10.0, 30.0)]
    spreads = {}
    for noise in (0.05, 0.5):
        organs = SenseOrgans(smell_range=40.0, smell_noise=noise)
        rng = random.Random(1)
        values = [look(plant, organs, rng=rng).plant_direction for _ in range(400)]
        spreads[noise] = statistics.pstdev(values)
        assert all(-1.0 <= v <= 1.0 for v in values)
    assert spreads[0.05] < spreads[0.5]
    assert spreads[0.05] == pytest.approx(0.05, abs=0.01)


def test_closeness_gets_a_small_error_and_unsensed_things_stay_zero():
    organs = SenseOrgans(vision_range=40.0)
    rng = random.Random(3)
    values = [look([thing("prey", 10.0)], organs, rng=rng).prey_closeness for _ in range(200)]
    assert statistics.pstdev(values) == pytest.approx(0.03, abs=0.01)
    assert all(0.0 <= v <= 1.0 for v in values)
    empty = look([], organs, rng=random.Random(3))
    assert empty == Percepts(daylight=1.0)  # nothing sensed: no error invented


def test_a_zero_noise_setting_uses_no_random_draws():
    organs = SenseOrgans(vision_range=40.0)
    rng = random.Random(9)
    before = rng.getstate()
    percepts = look([thing("prey", 10.0)], organs, rng=rng, rules=SensingRules(closeness_noise=0.0))
    assert rng.getstate() == before
    assert percepts.prey_closeness == pytest.approx(0.75)


# --- the rest ---------------------------------------------------------------------


def test_percepts_feed_the_brain_inputs():
    percepts = look([thing("prey", 10.0, 20.0)])
    inputs = build_inputs(percepts, **BODY)
    assert len(inputs) == len(INPUT_NAMES)
    assert dict(zip(INPUT_NAMES, inputs))["prey_closeness"] == pytest.approx(0.75)


def test_the_arguments_are_not_changed():
    neighbours = [thing("prey", 10.0)]
    organs = SenseOrgans(vision_range=40.0)
    look(neighbours, organs)
    assert neighbours == [thing("prey", 10.0)]
    assert dataclasses.is_dataclass(organs)
    with pytest.raises(dataclasses.FrozenInstanceError):
        organs.vision_range = 1.0


def test_only_two_dimensions_for_now():
    with pytest.raises(ValueError):
        sense(Vec.of(0.0, 0.0, 0.0), 0.0, 0.0, SenseOrgans(), [])


def test_validation():
    for bad in (
        lambda: SenseOrgans(vision_range=-1.0),
        lambda: SenseOrgans(smell_noise=math.nan),
        lambda: SenseOrgans(vision_fov_degrees=0.0),
        lambda: SenseOrgans(vision_fov_degrees=361.0),
        lambda: SensingConditions(daylight=1.5),
        lambda: SensingRules(weak_smell=2.0),
        lambda: SensingRules(crowding_reference=0),
        lambda: SensingRules(closeness_noise=-0.1),
        lambda: Neighbour(1, "dragon", ORIGIN),
        lambda: Neighbour(1, "plant", ORIGIN, radius=-1.0),
        lambda: Neighbour(1, "plant", ORIGIN, loudness=2.0),
        lambda: Neighbour(1, "other", ORIGIN, alarm_call_radius=-1.0),
    ):
        with pytest.raises(ValueError):
            bad()


# --- the newer inputs (SENSE.14) ----------------------------------------------------------


def test_the_clock_is_the_time_of_day_as_a_sine_and_a_cosine():
    noon = look([], conditions=SensingConditions(clock=0.5))
    assert noon.clock_sin == pytest.approx(0.0, abs=1e-12) and noon.clock_cos == pytest.approx(-1.0)
    dusk = look([], conditions=SensingConditions(clock=0.75))
    assert dusk.clock_sin == pytest.approx(-1.0) and dusk.clock_cos == pytest.approx(0.0, abs=1e-12)
    blank = look([])
    assert (blank.clock_sin, blank.clock_cos) == (0.0, 0.0)  # no day cycle, no clock
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError):
            SensingConditions(clock=bad)


def test_the_wall_is_reported_by_bearing_and_closeness_when_in_reach():
    # The wall lies to the left of a creature facing east (+y is left): bearing -0.5.
    percepts = look([], edge_distance=10.0, edge_direction=(0.0, 1.0))
    assert percepts.edge_closeness > 0.0
    assert percepts.edge_direction == pytest.approx(-0.5)
    far = look([], edge_distance=500.0, edge_direction=(0.0, 1.0))
    assert far.edge_closeness == 0.0 and far.edge_direction == 0.0
    unknown = look([], edge_distance=10.0)
    assert unknown.edge_direction == 0.0  # no direction given, no bearing


def test_a_mates_likeness_is_reported_from_the_chosen_mate_and_only_when_asked_for():
    asked = []

    def likeness() -> float:
        asked.append(1)
        return 0.8

    mate = thing("mate", 10.0, similarity=likeness)
    assert look([mate]).mate_similarity == pytest.approx(0.8)
    assert len(asked) == 1
    asked.clear()
    assert look([thing("prey", 10.0, ident=2, similarity=likeness)]).mate_similarity == 0.0
    assert not asked  # nothing to compare, so the genomes are never read
    assert look([thing("mate", 10.0, similarity=0.3)]).mate_similarity == pytest.approx(0.3)


def test_own_young_are_found_like_any_other_target():
    percepts = look([thing("young", 10.0, -45.0)])
    assert percepts.young_closeness == pytest.approx(0.75)
    assert percepts.young_direction > 0.0
    assert percepts.mate_closeness == 0.0
