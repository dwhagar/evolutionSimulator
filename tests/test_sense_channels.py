"""The sense-channel table (SENSE.8) and what is generated from it."""

import dataclasses
import math
import pickle

import pytest

from evolution_simulator import brain_adapter
from evolution_simulator.brain import DEFAULT_BLUEPRINT, DEFAULT_SHAPE
from evolution_simulator.brain_adapter import INPUT_NAMES, Percepts, Temperament, build_inputs
from evolution_simulator.sense_channels import (
    INPUT_CHANNELS,
    SENSE_KINDS,
    TARGETS,
    InputChannel,
    body_channels,
    channels_for_target,
    inputs_builder,
    percepts_class,
    senses_reporting,
    validate_channels,
    world_channels,
)

BODY = {
    "energy_ratio": 0.5,
    "health_ratio": 0.5,
    "vitality": 0.5,
    "ready_to_mate": True,
    "pain": 0.0,
    "tiredness": 0.0,
}


# --- the table ---------------------------------------------------------------


def test_the_table_is_the_inputs_in_their_documented_order():
    assert INPUT_NAMES == tuple(c.name for c in INPUT_CHANNELS)
    assert len(INPUT_CHANNELS) == DEFAULT_SHAPE.inputs == DEFAULT_BLUEPRINT.inputs == 28
    assert INPUT_NAMES[:4] == ("energy_ratio", "health_ratio", "vitality", "ready_to_mate")
    assert INPUT_NAMES[4:12] == (
        "plant_direction",
        "plant_closeness",
        "prey_direction",
        "prey_closeness",
        "threat_direction",
        "threat_closeness",
        "mate_direction",
        "mate_closeness",
    )
    assert INPUT_NAMES[12:17] == (
        "touching",
        "alarm_strength",
        "mating_call_strength",
        "call_direction",
        "crowding",
    )
    assert INPUT_NAMES[17:20] == ("pain", "daylight", "relative_size")  # SENSE.9
    assert INPUT_NAMES[20:] == (  # SENSE.14
        "young_direction",
        "young_closeness",
        "mate_similarity",
        "tiredness",
        "edge_direction",
        "edge_closeness",
        "clock_sin",
        "clock_cos",
    )


def test_ranges_match_the_design_note():
    by_name = {c.name: c for c in INPUT_CHANNELS}
    for name in INPUT_NAMES:
        c = by_name[name]
        if c.role == "bearing" or name in ("relative_size", "clock_sin", "clock_cos"):
            assert (c.low, c.high) == (-1.0, 1.0)
        else:
            assert (c.low, c.high) == (0.0, 1.0)


def test_body_rows_have_no_senses_and_world_rows_make_the_percepts():
    body = body_channels()
    assert [c.name for c in body] == [*INPUT_NAMES[:4], "pain", "tiredness"]
    assert all(c.senses == () for c in body)
    assert [c.name for c in world_channels()] == [
        name for name in INPUT_NAMES[4:] if name not in ("pain", "tiredness")
    ]


def test_the_time_of_day_is_ambient_and_the_only_input_the_sensing_ignores():
    assert [c.name for c in INPUT_CHANNELS if c.ambient] == ["daylight", "clock_sin", "clock_cos"]
    assert Percepts(daylight=0.7, clock_sin=0.5, clock_cos=-0.5).senses_nothing  # time is no sense
    assert not Percepts(relative_size=-0.5).senses_nothing
    assert senses_reporting("relative_size") == ("vision", "hearing")
    assert senses_reporting("daylight") == ()


def test_every_target_has_a_bearing_and_a_closeness():
    for target in TARGETS:
        roles = sorted(c.role for c in channels_for_target(target))
        assert roles == ["bearing", "closeness"]
    assert {c.target for c in INPUT_CHANNELS if c.target} == set(TARGETS)


def test_which_senses_report_what_follows_the_design_note():
    assert senses_reporting("plant_closeness") == ("vision", "smell")
    assert senses_reporting("threat_direction") == ("vision", "hearing", "smell")
    assert senses_reporting("touching") == ("touch",)
    assert senses_reporting("alarm_strength") == ("hearing",)
    assert senses_reporting("energy_ratio") == ()
    # plants make no sound and only vision and smell can find them
    assert "hearing" not in senses_reporting("plant_direction")
    assert all(set(c.senses) <= set(SENSE_KINDS) for c in INPUT_CHANNELS)
    with pytest.raises(KeyError):
        senses_reporting("nope")


def test_temperament_scaled_channels_name_real_temperament_fields():
    scaled = {c.name: c.scaled_by for c in INPUT_CHANNELS if c.scaled_by}
    assert scaled == {
        "prey_closeness": "aggression",
        "threat_closeness": "fear",
        "mate_closeness": "repro_drive",
        "young_closeness": "parenting",
    }
    fields = {f.name for f in dataclasses.fields(Temperament)}
    assert set(scaled.values()) <= fields


def test_channel_validation():
    ok = {"name": "x", "low": 0.0, "high": 1.0, "source": "world"}
    assert InputChannel(**ok)
    for bad in (
        dict(ok, name="not an identifier"),
        dict(ok, low=1.0, high=1.0),
        dict(ok, source="nowhere"),
        dict(ok, role="vibe"),
        dict(ok, role="flag", low=-1.0),
        dict(ok, senses=("telepathy",)),
        dict(ok, source="body", senses=("vision",)),
        dict(ok, role="closeness"),  # needs a target
        dict(ok, role="level", target="plant"),  # only bearing and closeness have one
        dict(ok, role="closeness", target="dragon"),
    ):
        with pytest.raises(ValueError):
            InputChannel(**bad)


def test_table_validation():
    with pytest.raises(ValueError):
        validate_channels(INPUT_CHANNELS + (INPUT_CHANNELS[0],))  # duplicate name
    lonely = InputChannel("a_closeness", 0.0, 1.0, "world", "closeness", ("vision",), "plant")
    with pytest.raises(ValueError):
        validate_channels((lonely,))  # a closeness without its bearing
    assert validate_channels(INPUT_CHANNELS) == INPUT_CHANNELS


def test_clamping_rules_per_channel():
    energy = INPUT_CHANNELS[0]
    assert energy.clamp(2.0) == 1.0 and energy.clamp(-1.0) == 0.0
    with pytest.raises(ValueError):
        energy.clamp(math.nan)
    flag = INPUT_CHANNELS[3]
    assert (flag.clamp(True), flag.clamp(False), flag.clamp(0.2)) == (1.0, 0.0, 1.0)


# --- Percepts is generated from the world rows --------------------------------


def test_percepts_fields_are_the_world_rows_in_order():
    names = [f.name for f in dataclasses.fields(Percepts)]
    # ``targets`` (UX.43) is not a brain input: it names what each sense found, for the eyes.
    assert names == [c.name for c in world_channels()] + ["targets"]
    blank = Percepts()
    for c in world_channels():
        assert getattr(blank, c.name) == (False if c.is_flag else 0.0)


def test_percepts_is_frozen_keyword_friendly_and_rejects_unknown_fields():
    p = Percepts(plant_closeness=0.5, touching=True)
    assert p.plant_closeness == 0.5 and p.touching is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.plant_closeness = 0.1
    with pytest.raises(TypeError):
        Percepts(energy_ratio=0.5)  # a body channel is not the world's to report
    with pytest.raises(TypeError):
        Percepts(bogus=1)
    assert p == Percepts(plant_closeness=0.5, touching=True)


def test_percepts_senses_nothing_and_pickles():
    assert Percepts().senses_nothing
    assert not Percepts(crowding=0.2).senses_nothing
    assert Percepts.__module__ == "evolution_simulator.brain_adapter"
    p = Percepts(prey_direction=-0.3)
    assert pickle.loads(pickle.dumps(p)) == p
    assert brain_adapter.Percepts is Percepts


# --- build_inputs is generated too -----------------------------------------


def test_inputs_come_out_in_table_order_with_body_values_in_their_rows():
    inputs = build_inputs(Percepts(call_direction=-0.5), **BODY)
    named = dict(zip(INPUT_NAMES, inputs))
    assert named["energy_ratio"] == 0.5 and named["ready_to_mate"] == 1.0
    assert named["call_direction"] == -0.5
    assert len(inputs) == 28


def test_body_values_must_be_given_by_name_and_all_of_them():
    with pytest.raises(TypeError):
        build_inputs(Percepts(), energy_ratio=0.5)  # missing the rest
    with pytest.raises(TypeError):
        build_inputs(Percepts(), thirst=0.1, **BODY)  # not a channel yet


def test_a_new_input_is_one_row():
    """Adding thirst (body) and wind (world) to a copy of the table changes nothing else."""
    extra = (
        InputChannel("thirst", 0.0, 1.0, "body", description="Need to drink."),
        InputChannel("wind", 0.0, 1.0, "world", "level", ("touch",)),
    )
    table = INPUT_CHANNELS[:4] + (extra[0],) + INPUT_CHANNELS[4:] + (extra[1],)
    FuturePercepts = percepts_class(table, "FuturePercepts")
    assert "wind" in {f.name for f in dataclasses.fields(FuturePercepts)}
    assert "thirst" not in {f.name for f in dataclasses.fields(FuturePercepts)}  # body, not percept
    build = inputs_builder(table, lambda name, t: 1.0)
    inputs = build(FuturePercepts(wind=0.75, plant_closeness=0.2), thirst=0.4, **BODY)
    assert len(inputs) == 30
    assert inputs[4] == 0.4  # thirst sits after the four old body rows
    assert inputs[-1] == 0.75
    assert inputs[5] == 0.0  # plant_direction, shifted by one
    assert inputs[6] == 0.2  # plant_closeness, shifted by one
    assert len(INPUT_CHANNELS) == 28  # the real table is untouched
