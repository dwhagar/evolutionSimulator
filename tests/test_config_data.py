"""Reading the config dataclasses generically, and the setup presets built on it (UX.17)."""

import json
from dataclasses import dataclass, field, replace

import pytest

from evolution_simulator.config import DayCycle, LearningRules, LifeRules, TraitRules
from evolution_simulator.session import CommandError
from evolution_simulator.viewer.configdata import (
    class_doc,
    coerce,
    field_info,
    from_data,
    is_config_class,
    optional_of,
    to_data,
)
from evolution_simulator.viewer.presets import BUILTIN_PRESETS, RunSetup
from evolution_simulator.world import World, WorldConfig
from evolution_simulator.world.bounds import Bounds


@dataclass(frozen=True)
class Inner:
    """A small section."""

    depth: float = 2.5
    """How deep it goes,
    in units."""
    label: str = "x"


@dataclass(frozen=True)
class Outer:
    count: int = 3
    flag: bool = False
    pair: tuple[float, float] = (1.0, 2.0)
    inner: Inner = field(default_factory=Inner)
    maybe: Inner | None = field(default_factory=Inner)
    limit: float | None = None


# --- fields and docs -------------------------------------------------------------------


def test_field_info_lists_the_fields_with_hints_defaults_and_the_text_under_each():
    info = {i.name: i for i in field_info(Inner)}
    assert list(info) == ["depth", "label"]
    assert info["depth"].hint is float and info["depth"].default == 2.5
    assert info["depth"].doc == "How deep it goes, in units."
    assert info["label"].doc == ""
    assert class_doc(Inner) == "A small section."
    assert class_doc(Outer) == ""  # dataclass's own "Outer(count=...)" text is not a description


def test_the_real_config_explains_its_fields():
    life = {i.name: i for i in field_info(LifeRules)}
    assert life["wear_base"].doc.startswith("Damage per reference tick")
    assert is_config_class(life["wear_base"].hint) is False
    world = {i.name: i for i in field_info(WorldConfig)}
    assert is_config_class(world["traits"].hint) and is_config_class(world["bounds"].hint)
    assert optional_of(field_info(TraitRules)[10].hint) is DayCycle
    assert optional_of(float) is None


# --- coerce ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "hint", "expected"),
    [
        (3, int, 3),
        (3, float, 3.0),
        (True, bool, True),
        ("a", str, "a"),
        ([1, 2], tuple[float, float], (1.0, 2.0)),
        ((1, 2, 3), tuple[float, ...], (1.0, 2.0, 3.0)),
        (5, tuple[float, ...], (5.0,)),
        ([[0, 1], [2, 3.5]], tuple[tuple[int, float], ...], ((0, 1.0), (2, 3.5))),
        (None, float | None, None),
        (4, float | None, 4.0),
    ],
)
def test_coerce_gives_the_value_the_type_asks_for(value, hint, expected):
    result = coerce(value, hint)
    assert result == expected and type(result) is type(expected)


@pytest.mark.parametrize(
    ("value", "hint"),
    [
        (1.5, int),
        (True, int),
        (1, bool),
        ("1", float),
        (float("nan"), float),
        ((1, 2, 3), tuple[float, float]),
        (None, float),
        (1.0, set),
    ],
)
def test_coerce_refuses_what_does_not_fit(value, hint):
    with pytest.raises(ValueError, match=r"expected|cannot be edited"):
        coerce(value, hint)


# --- to_data and from_data --------------------------------------------------------------


def test_a_whole_world_config_round_trips_through_json():
    config = WorldConfig(
        seed=7,
        bounds=Bounds((300.0, 400.0)),
        traits=replace(
            WorldConfig().traits,
            life=replace(LifeRules(), wear_base=0.05),
            day_cycle=None,
            learning=LearningRules(),
        ),
    )
    data = json.loads(json.dumps(to_data(config)))
    assert from_data(WorldConfig, data) == config
    assert isinstance(data["bounds"]["size"], list)


def test_missing_fields_keep_their_default_and_unknown_ones_are_ignored():
    config = from_data(WorldConfig, {"seed": 4, "no_such_field": 1, "traits": {"life": {}}})
    assert config == WorldConfig(seed=4)


def test_a_value_that_does_not_fit_names_its_field():
    with pytest.raises(ValueError, match="seed: expected a whole number"):
        from_data(WorldConfig, {"seed": "x"})
    with pytest.raises(ValueError, match="caps must not be negative"):  # the class's own check
        from_data(WorldConfig, {"max_animals": -1})
    with pytest.raises(ValueError, match="expected a section"):
        from_data(WorldConfig, {"traits": 3})


def test_an_optional_section_can_be_null():
    assert from_data(TraitRules, {"day_cycle": None}).day_cycle is None
    assert from_data(TraitRules, {"day_cycle": {"night_below": 0.1}}).day_cycle.night_below == 0.1


# --- the setup and its presets ------------------------------------------------------------


def test_a_setup_round_trips_and_makes_its_command():
    setup = RunSetup(10, 40, False, WorldConfig(seed=3))
    assert RunSetup.from_json(setup.to_json()) == setup
    command = setup.command()
    assert (command.animals, command.plants, command.seeded, command.config.seed) == (
        10,
        40,
        False,
        3,
    )
    assert setup.with_seed(9).config.seed == 9


def test_a_setup_that_does_not_fit_its_caps_has_no_command():
    setup = RunSetup(5000, 10, True, WorldConfig())
    with pytest.raises(CommandError, match="at most 1,000 animals"):
        setup.command()


@pytest.mark.parametrize("text", ["", "[]", "{", '{"animals": "many"}', '{"animals": true}'])
def test_text_that_is_not_a_setup_is_refused(text):
    with pytest.raises(ValueError, match="saved setup|whole number"):
        RunSetup.from_json(text)


def test_a_setup_missing_most_of_its_fields_uses_the_defaults():
    assert RunSetup.from_json("{}") == RunSetup()
    assert RunSetup.from_json('{"plants": 9}').plants == 9


@pytest.mark.parametrize("preset", BUILTIN_PRESETS, ids=lambda p: p.name)
def test_every_built_in_preset_starts_a_world_that_runs(preset):
    assert RunSetup.from_json(preset.setup.to_json()) == preset.setup
    command = preset.setup.command()
    world = World(command.config)
    world.populate(animals=min(command.animals, 20), plants=min(command.plants, 60))
    world.run(3)
    assert world.tick == 3
    assert preset.description


def test_the_presets_differ_in_what_they_say_they_do():
    by_name = {p.name: p.setup for p in BUILTIN_PRESETS}
    assert by_name["Default"] == RunSetup()
    assert by_name["Small and quick"].config.bounds.size == (500.0, 500.0)
    assert by_name["Large world"].config.bounds.size == (2000.0, 2000.0)
    assert by_name["No night"].config.day_cycle is None
    assert by_name["No learning"].config.learning is None
