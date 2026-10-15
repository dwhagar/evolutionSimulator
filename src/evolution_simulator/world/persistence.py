"""Saving and loading a world (``UX.9``).

A save is a versioned JSON document (gzip-compressed when the file name ends in ``.gz``) that holds
everything the next tick reads: the config, the clock, the random generator, every animal, plant and
corpse with its genome and runtime state, each animal's learner (the day log and the learned
offsets) and pending litter, and a ``state_digest`` taken at save time. Loading rebuilds the world,
checks the digest, and the restored world then steps exactly as the saved one would have.

What is saved and what is rebuilt
---------------------------------
An organism's body (its traits, brain, costs) is a function of its genome, the trait rules and the
world's tick length, so it is rebuilt by the same constructors that made it. Only what changes
during a life is written: energy, health, damage, age, cooldowns, drive flags, the cached decision,
the wander turn, the learner and the pregnancy. The spatial indexes are rebuilt from positions.
The ancestry book (``UX.39``: who is whose child, the dead too, up to a bound) is written as it is; a
save from before it (format 5) starts one from the living animals.

**If you add state to the world, an organism or one of the objects below, add it here.**
``tests/test_persistence.py`` runs a rich world, saves it and compares *every attribute* of the
restored world with the original (and then runs both on), so a field that is forgotten fails there
with the path of the attribute. The scalar runtime fields of organisms are plain name tables
(``_BASE_FIELDS``, ``_ANIMAL_FIELDS``, ``_PLANT_FIELDS``), so a new number is one line.

Versions
--------
``FORMAT_VERSION`` counts changes to this document's layout. Add a function to ``_MIGRATIONS`` that
turns version ``n`` into ``n + 1`` whenever a save from the old layout can still be read (a field
renamed or moved); an old save then loads by running the chain. A field that the code now has but
the save lacks is filled from the dataclass default for the config, and has to be handled by hand
for organisms. Genomes carry their layout version (``DNA.to_dict``): a layout change makes older
genomes unreadable, which loading reports up front rather than part way through.

Not saved: the ``Senses`` object (a ``WorldSenses`` is recorded by its settings; any other has to be
passed to ``load_world`` again) and sleep listeners beyond the default learning one (pass them to
``load_world``).
"""

from __future__ import annotations

import gzip
import json
import os
import types
import typing
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any

from evolution_simulator import __version__
from evolution_simulator.brain_adapter import BrainDecision, WanderPolicy
from evolution_simulator.config import SensingRules
from evolution_simulator.deaths import DeathCause
from evolution_simulator.diploid import DiploidDNA
from evolution_simulator.dna import Genome
from evolution_simulator.layouts import LAYOUTS, dna_from_dict
from evolution_simulator.learning import Learner, Snapshot, State
from evolution_simulator.traits import AnimalTraits, PlantTraits, Pregnancy
from evolution_simulator.world.ancestry import AncestryBook
from evolution_simulator.world.corpses import Corpse
from evolution_simulator.world.organisms import Animal, Plant
from evolution_simulator.world.senses import Senses, WorldSenses
from evolution_simulator.world.sleep import SleepListener
from evolution_simulator.world.vector import Vec
from evolution_simulator.world.world import World, WorldConfig

FORMAT = "evolution-simulator-world"
"""The document type, so a file of something else is refused with a clear message."""
FORMAT_VERSION = 6
"""The layout of the document. Bump it when the layout changes and add a migration if old saves can
still be read."""


def _learning_into_the_trait_rules(data: dict[str, Any]) -> dict[str, Any]:
    """Version 1 to 2 (``TRAIT.10``): ``config.learning`` became ``config.traits.learning``."""
    config = data["world"]["config"]
    if "learning" in config:
        config.setdefault("traits", {})["learning"] = config.pop("learning")
    return data


def _sleep_into_the_trait_rules(data: dict[str, Any]) -> dict[str, Any]:
    """Version 2 to 3 (``TRAIT.10``): ``config.sleep`` became ``config.traits.sleep``."""
    config = data["world"]["config"]
    if "sleep" in config:
        config.setdefault("traits", {})["sleep"] = config.pop("sleep")
    return data


def _day_time_and_plants_into_the_trait_rules(data: dict[str, Any]) -> dict[str, Any]:
    """Version 3 to 4 (``TRAIT.10``): ``config.day_cycle``, ``config.plants`` and
    ``config.time_scale`` became ``config.traits.day_cycle``, ``.plant_limits`` and the
    ``seconds_per_tick`` and ``speed`` of ``config.traits.time``."""
    config = data["world"]["config"]
    traits = config.setdefault("traits", {})
    if "day_cycle" in config:
        traits["day_cycle"] = config.pop("day_cycle")
    if "plants" in config:
        traits["plant_limits"] = config.pop("plants")
    if "time_scale" in config:
        scale = config.pop("time_scale")
        traits.setdefault("time", {}).update(
            seconds_per_tick=scale["seconds_per_tick"], speed=scale["speed"]
        )
    return data


def _bites_corpses_and_world_settings_into_the_trait_rules(
    data: dict[str, Any],
) -> dict[str, Any]:
    """Version 4 to 5 (``TRAIT.11``): ``config.attack`` and ``config.corpses`` became
    ``config.traits.attack`` and ``.corpses``; ``config.graze_amount``, ``.mating_reach``,
    ``.birth_scatter`` and ``.calls_enabled`` became the same names in ``config.traits.world``."""
    config = data["world"]["config"]
    traits = config.setdefault("traits", {})
    for name in ("attack", "corpses"):
        if name in config:
            traits[name] = config.pop(name)
    for name in ("graze_amount", "mating_reach", "birth_scatter", "calls_enabled"):
        if name in config:
            traits.setdefault("world", {})[name] = config.pop(name)
    return data


def _ancestry_book(data: dict[str, Any]) -> dict[str, Any]:
    """Version 5 to 6 (``UX.39``): the world keeps an ancestry book. A save from before has none
    (``None``): loading starts one from the living animals, who know their parents."""
    data["world"].setdefault("ancestry", None)
    return data


_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _learning_into_the_trait_rules,
    2: _sleep_into_the_trait_rules,
    3: _day_time_and_plants_into_the_trait_rules,
    4: _bites_corpses_and_world_settings_into_the_trait_rules,
    5: _ancestry_book,
}
"""``{n: f}``: ``f`` takes a document of version ``n`` and returns it as version ``n + 1``."""


class SaveFormatError(ValueError):
    """A save cannot be read: wrong kind of file, too new, from other gene layouts, damaged, or it
    does not reproduce the digest taken when it was written."""


# =============================================================================
# Plain data: dataclasses, tuples and numbers (the config tree and small records)
# =============================================================================


def _encode(value: Any) -> Any:
    """A dataclass tree as nested dicts and lists of JSON values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value) if f.init}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise SaveFormatError(f"Cannot save a {type(value).__name__}: {value!r}.")


def _decode(annotation: Any, data: Any) -> Any:
    """Rebuild a value of the type ``annotation`` from the form ``_encode`` wrote."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        options = [a for a in typing.get_args(annotation) if a is not type(None)]
        if data is None:
            if len(options) == len(typing.get_args(annotation)):
                raise SaveFormatError(f"Expected a value of {annotation}, got nothing.")
            return None
        if len(options) != 1:
            raise SaveFormatError(f"Cannot tell which of {annotation} a saved value is.")
        return _decode(options[0], data)
    if origin is tuple:
        args = typing.get_args(annotation)
        if not isinstance(data, list):
            raise SaveFormatError(f"Expected a list for {annotation}, got {data!r}.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], item) for item in data)
        if len(args) != len(data):
            raise SaveFormatError(f"Expected {len(args)} items for {annotation}, got {len(data)}.")
        return tuple(_decode(a, item) for a, item in zip(args, data, strict=True))
    if isinstance(annotation, type) and is_dataclass(annotation):
        return _decode_dataclass(annotation, data)
    if annotation is bool:
        if not isinstance(data, bool):
            raise SaveFormatError(f"Expected true or false, got {data!r}.")
        return data
    if annotation is int:
        if isinstance(data, bool) or not isinstance(data, int):
            raise SaveFormatError(f"Expected a whole number, got {data!r}.")
        return data
    if annotation is float:
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            raise SaveFormatError(f"Expected a number, got {data!r}.")
        return float(data)
    if annotation is str:
        if not isinstance(data, str):
            raise SaveFormatError(f"Expected text, got {data!r}.")
        return data
    raise SaveFormatError(f"Cannot read a saved {annotation}.")


def _decode_dataclass(cls: type, data: Any) -> Any:
    if not isinstance(data, dict):
        raise SaveFormatError(f"Expected the settings of {cls.__name__}, got {data!r}.")
    hints = typing.get_type_hints(cls)
    known = {f.name for f in fields(cls) if f.init}
    unknown = sorted(set(data) - known)
    if unknown:
        raise SaveFormatError(
            f"{cls.__name__} has no setting {unknown}: the save is from other rules."
        )
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if not f.init:
            continue
        if f.name in data:
            kwargs[f.name] = _decode(hints[f.name], data[f.name])
        elif f.default is MISSING and f.default_factory is MISSING:
            raise SaveFormatError(f"{cls.__name__} lacks {f.name!r} in the save.")
    return cls(**kwargs)


# =============================================================================
# Genomes
# =============================================================================


def _genome_to_data(genome: Genome) -> dict[str, Any]:
    return genome.to_dict()  # type: ignore[attr-defined]


def _genome_from_data(data: Mapping[str, Any]) -> Genome:
    if "strands" in data:
        return DiploidDNA.from_dict(data, LAYOUTS)
    return dna_from_dict(data)


# =============================================================================
# Organisms
# =============================================================================

_BASE_FIELDS: tuple[str, ...] = (
    "current_energy",
    "current_health",
    "accumulated_damage",
    "damage_since_decision",
    "damage_taken",
    "vitality",
    "age_ticks",
    "is_alive",
)
"""What ``BaseTraits`` tracks over a life."""

_ANIMAL_FIELDS: tuple[str, ...] = _BASE_FIELDS + (
    "matings",
    "mating_cooldown",
    "env_target_size_ratio",
    "env_local_density",
    "current_aggression",
    "current_max_speed",
    "effective_herb_eff",
    "effective_carn_eff",
    "current_sight_range",
    "current_hearing_range",
    "_last_threat",
    "_decided_threat",
    "_decided_touch",
    "_ticks_since_decision",
    "tiredness",
)
"""Scalar runtime state of ``AnimalTraits``. Anything with structure is handled in
``_animal_traits_to_data``: the pregnancy, the cached decision, the wander turn, the learner."""

_PLANT_FIELDS: tuple[str, ...] = _BASE_FIELDS + (
    "growth_cooldown",
    "lived_ticks",
    "sunlight_factor",
    "soil_competition_factor",
    "flag_ready_to_seed",
    "seed_cooldown",
    "current_biomass",
)
"""Scalar runtime state of ``PlantTraits``."""


def _vec(data: Sequence[float]) -> Vec:
    return Vec(tuple(data))


def _death_cause_to_data(traits: AnimalTraits | PlantTraits) -> str | None:
    return None if traits.death_cause is None else traits.death_cause.value


def _death_cause_from_data(data: Mapping[str, Any]) -> DeathCause | None:
    """The cause of death saved with an organism that is dead but not yet removed (saves from
    before ``UX.6`` have none)."""
    value = data.get("death_cause")
    if value is None:
        return None
    try:
        return DeathCause(value)
    except ValueError:
        raise SaveFormatError(f"Unknown cause of death {value!r}.") from None


def _animal_traits_to_data(traits: AnimalTraits, animal_ids: Mapping[int, int]) -> dict[str, Any]:
    """``animal_ids`` maps ``id(traits)`` of each animal in the world to its id, so a pregnancy can
    name the father."""
    data: dict[str, Any] = {
        "dna": _genome_to_data(traits.dna),
        "decision_interval": traits.decision_interval,
        "state": {name: getattr(traits, name) for name in _ANIMAL_FIELDS},
        "decision": _encode(traits._decision),
        "wander_turn": traits.wanderer._turn,
        "wander_policy": _encode(traits.wanderer.policy),
        "death_cause": _death_cause_to_data(traits),
        "brain_learned": traits.brain is not traits.innate_brain,
        "pregnancy": None,
        "learner": None,
    }
    pregnancy = traits.pregnancy
    if pregnancy is not None:
        father = pregnancy.father
        # A father who has died and left the world pays nothing at the birth, which is what a
        # missing father does, so he is not kept.
        father_id = None
        if father is not None and father.is_alive:
            father_id = animal_ids.get(id(father))
            if father_id is None:
                raise SaveFormatError("A pregnancy names a father who is not in the world.")
        data["pregnancy"] = {
            "children": [_genome_to_data(child) for child in pregnancy.children],
            "remaining": pregnancy.remaining,
            "father": father_id,
        }
    learner = traits.learner
    if learner is not None:
        data["learner"] = {
            "tick": learner._tick,
            "offsets": _encode(learner.offsets),
            "pending": [
                [tick, _encode(state), list(hidden), list(proposal), list(action)]
                for tick, state, hidden, proposal, action in learner._pending
            ],
            "log": _encode(tuple(learner._log)),
        }
    return data


def _restore_learner(traits: AnimalTraits, data: Mapping[str, Any]) -> None:
    rules = traits.learning_rules
    if rules is None:
        raise SaveFormatError("An animal has a learner but the world's learning is off.")
    shape = traits.innate_brain.shape
    learner = Learner(shape.hidden, shape.outputs, rules, traits.dt)
    offsets_type = tuple[tuple[tuple[float, ...], ...], tuple[float, ...]]
    learner.offsets = _decode(offsets_type, data["offsets"])
    learner._tick = _decode(int, data["tick"])
    learner._pending = deque(
        (
            _decode(int, tick),
            _decode(State, state),
            _decode(tuple[float, ...], hidden),
            _decode(tuple[float, ...], proposal),
            _decode(tuple[float, ...], action),
        )
        for tick, state, hidden, proposal, action in data["pending"]
    )
    learner._log = deque(
        (_decode(Snapshot, snap) for snap in data["log"]), maxlen=learner._log.maxlen
    )
    traits.learner = learner


def _restore_animal_traits(
    world: World, data: Mapping[str, Any], fathers: list[tuple[AnimalTraits, int]]
) -> AnimalTraits:
    traits = AnimalTraits(
        _genome_from_data(data["dna"]),
        decision_interval=_decode(int, data["decision_interval"]),
        rules=world.config.traits,
        dt=world.dt,
    )
    traits.learning_rules = world.config.learning
    for name in _ANIMAL_FIELDS:
        setattr(traits, name, _field_like(getattr(traits, name), data["state"][name], name))
    traits.death_cause = _death_cause_from_data(data)
    traits._decision = _decode(BrainDecision | None, data["decision"])
    traits.wanderer.policy = _decode(WanderPolicy, data["wander_policy"])
    traits.wanderer._turn = _decode(float | None, data["wander_turn"])
    if data["learner"] is not None:
        _restore_learner(traits, data["learner"])
    if data["brain_learned"]:
        if traits.learner is None:
            raise SaveFormatError("An animal has a learned brain but no learner.")
        weights, biases = traits.learner.offsets
        traits.brain = traits.innate_brain.with_output_offsets(weights, biases)
    pregnancy = data["pregnancy"]
    if pregnancy is not None:
        traits.pregnancy = Pregnancy(
            children=tuple(_genome_from_data(child) for child in pregnancy["children"]),
            remaining=_decode(float, pregnancy["remaining"]),
        )
        if pregnancy["father"] is not None:
            fathers.append((traits, _decode(int, pregnancy["father"])))
    return traits


def _field_like(template: Any, value: Any, name: str) -> Any:
    """``value`` from the save, checked to be a plain number or flag. A field that starts as a float
    and was saved as a whole number (JSON writes ``1.0`` as ``1.0``, but a hand edit may not) comes
    back a float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if isinstance(value, bool) and isinstance(template, bool):
            return value
        raise SaveFormatError(f"The field {name!r} should be a number, got {value!r}.")
    if isinstance(template, float):
        return float(value)
    return value


def _animal_to_data(animal: Animal, animal_ids: Mapping[int, int]) -> dict[str, Any]:
    return {
        "id": animal.id,
        "position": list(animal.position.coords),
        "heading": animal.heading,
        "parents": list(animal.parents),
        "asleep": animal.asleep,
        "disturbed": animal.disturbed,
        "awake_time": animal.awake_time,
        "partner": animal.partner,
        "killed_by": animal.killed_by,
        "last_decision": _encode(animal.last_decision),
        "traits": _animal_traits_to_data(animal.traits, animal_ids),
    }


def _plant_to_data(plant: Plant) -> dict[str, Any]:
    traits = plant.traits
    return {
        "id": plant.id,
        "position": list(plant.position.coords),
        "parents": list(plant.parents),
        "shade": plant.shade,
        "soil": plant.soil,
        "traits": {
            "dna": _genome_to_data(traits.dna),
            "state": {name: getattr(traits, name) for name in _PLANT_FIELDS},
            "death_cause": _death_cause_to_data(traits),
        },
    }


def _corpse_to_data(corpse: Corpse) -> dict[str, Any]:
    return {
        "id": corpse.id,
        "position": list(corpse.position.coords),
        "radius": corpse.radius,
        "mass": corpse.mass,
        "meat": corpse.meat,
    }


# =============================================================================
# The world
# =============================================================================


def _senses_to_data(senses: Senses) -> dict[str, Any]:
    if type(senses) is WorldSenses:
        return {
            "kind": "world_senses",
            "noisy": senses._noisy,
            "rules": _encode(senses._rules),
        }
    return {"kind": "custom", "type": type(senses).__name__}


def _senses_from_data(data: Mapping[str, Any], given: Senses | None) -> Senses:
    if given is not None:
        return given
    if data.get("kind") != "world_senses":
        raise SaveFormatError(
            f"The world used its own senses ({data.get('type')!r}); pass them as senses=."
        )
    return WorldSenses(_decode(SensingRules | None, data["rules"]), _decode(bool, data["noisy"]))


def config_to_dict(config: WorldConfig) -> dict[str, Any]:
    """A ``WorldConfig`` as a JSON-ready dict (the form a save and a run's manifest hold)."""
    return _encode(config)


def config_from_dict(data: Mapping[str, Any]) -> WorldConfig:
    """The ``WorldConfig`` ``config_to_dict`` wrote; a setting the save lacks takes its default and
    one the rules no longer have is refused (``SaveFormatError``)."""
    try:
        return _decode(WorldConfig, dict(data))
    except SaveFormatError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise SaveFormatError(
            f"The saved settings are damaged or incomplete: {error!r}."
        ) from error


def world_to_dict(world: World) -> dict[str, Any]:
    """The whole world as a JSON-ready document (see the module docstring)."""
    animals = world.animals
    animal_ids = {id(animal.traits): animal.id for animal in animals}
    version, internal, gauss = world.rng.getstate()
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "program_version": __version__,
        "layouts": {layout.name: layout.version for layout in LAYOUTS},
        "state_digest": world.state_digest(),
        "world": {
            "config": _encode(world.config),
            "senses": _senses_to_data(world.senses),
            "tick": world.tick,
            "next_id": world._next_id,
            "max_canopy": world.max_canopy,
            "max_body": world.max_body,
            "rng": [version, list(internal), gauss],
            "calls": [[i, alarm, mating] for i, (alarm, mating) in sorted(world.calls.items())],
            "animals": [_animal_to_data(a, animal_ids) for a in animals],
            "plants": [_plant_to_data(p) for p in world.plants],
            "corpses": [_corpse_to_data(c) for c in world.corpses],
            "scent": None if world.scent is None else world.scent.records(),
            "ancestry": world.ancestry.to_data(),
        },
    }


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("format") != FORMAT:
        raise SaveFormatError("This is not a saved evolution simulator world.")
    version = data.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SaveFormatError(f"The save has no usable format version: {version!r}.")
    if version > FORMAT_VERSION:
        raise SaveFormatError(
            f"The save is format {version}, newer than this program reads ({FORMAT_VERSION}): "
            f"it was written by version {data.get('program_version')!r}."
        )
    while version < FORMAT_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise SaveFormatError(
                f"The save is format {version} and cannot be upgraded to {FORMAT_VERSION}."
            )
        data = step(data)
        version += 1
        data["format_version"] = version
    return data


def _check_layouts(saved: Any) -> None:
    current = {layout.name: layout.version for layout in LAYOUTS}
    if saved != current:
        raise SaveFormatError(
            f"The save's gene layouts {saved!r} are not the current ones {current!r}, so its "
            "genomes cannot be read."
        )


def world_from_dict(
    data: Mapping[str, Any],
    senses: Senses | None = None,
    sleep_listeners: Iterable[SleepListener] = (),
) -> World:
    """Rebuild a world from ``world_to_dict`` output (migrating an older format first) and check
    that its ``state_digest`` is the one saved. ``senses`` replaces the saved senses (needed for
    anything but ``WorldSenses``); ``sleep_listeners`` are added after the default learning one."""
    try:
        document = _migrate(dict(data))
        _check_layouts(document["layouts"])
        world = _build_world(document["world"], senses)
        for listener in sleep_listeners:
            world.add_sleep_listener(listener)
        expected = document["state_digest"]
    except SaveFormatError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
        raise SaveFormatError(f"The save is damaged or incomplete: {error!r}.") from error
    if world.state_digest() != expected:
        raise SaveFormatError("The restored world does not match the digest saved with it.")
    return world


def _build_world(data: Mapping[str, Any], given_senses: Senses | None) -> World:
    config = _decode(WorldConfig, data["config"])
    world = World(config, _senses_from_data(data["senses"], given_senses))
    world.tick = _decode(int, data["tick"])
    world._next_id = _decode(int, data["next_id"])
    world.max_canopy = _decode(float, data["max_canopy"])
    world.max_body = _decode(float, data["max_body"])
    version, internal, gauss = data["rng"]
    world.rng.setstate((version, tuple(internal), gauss))
    world.calls = {
        _decode(int, i): (_decode(float, alarm), _decode(float, mating))
        for i, alarm, mating in data["calls"]
    }

    # Plants and corpses go into their indexes in id order, the order they were first inserted in.
    for plant_data in data["plants"]:
        traits = PlantTraits(_genome_from_data(plant_data["traits"]["dna"]), config.traits)
        for name in _PLANT_FIELDS:
            saved = plant_data["traits"]["state"][name]
            setattr(traits, name, _field_like(getattr(traits, name), saved, name))
        traits.death_cause = _death_cause_from_data(plant_data["traits"])
        plant = Plant(
            _decode(int, plant_data["id"]),
            traits,
            _vec(plant_data["position"]),
            tuple(plant_data["parents"]),
        )
        plant.shade = _decode(float, plant_data["shade"])
        plant.soil = _decode(float, plant_data["soil"])
        world._plants[plant.id] = plant
        world._plant_index.insert(plant.id, plant.position, plant.radius)

    for corpse_data in data["corpses"]:
        corpse = Corpse(
            _decode(int, corpse_data["id"]),
            _vec(corpse_data["position"]),
            _decode(float, corpse_data["radius"]),
            _decode(float, corpse_data["mass"]),
            _decode(float, corpse_data["meat"]),
        )
        world._corpses[corpse.id] = corpse
        world._corpse_index.insert(corpse.id, corpse.position, corpse.radius)

    if world.scent is not None:  # saves from before SENSE.20 have no trails
        world.scent.restore(data.get("scent") or [])

    fathers: list[tuple[AnimalTraits, int]] = []
    for animal_data in data["animals"]:
        animal = Animal(
            _decode(int, animal_data["id"]),
            _restore_animal_traits(world, animal_data["traits"], fathers),
            _vec(animal_data["position"]),
            _decode(float, animal_data["heading"]),
            tuple(animal_data["parents"]),
        )
        animal.asleep = _decode(bool, animal_data["asleep"])
        animal.disturbed = _decode(bool, animal_data["disturbed"])
        animal.awake_time = _decode(float, animal_data["awake_time"])
        animal.partner = _decode(int | None, animal_data["partner"])
        animal.killed_by = _decode(int | None, animal_data.get("killed_by"))
        animal.last_decision = _decode(BrainDecision | None, animal_data["last_decision"])
        world._animals[animal.id] = animal
        world._animal_index.insert(animal.id, animal.position, animal.radius)
    for mother_traits, father_id in fathers:
        father = world._animals.get(father_id)
        if father is None:
            raise SaveFormatError(f"A pregnancy names animal {father_id}, who is not in the save.")
        assert mother_traits.pregnancy is not None
        mother_traits.pregnancy.father = father.traits
    world.ancestry = _ancestry_from_data(world, data.get("ancestry"))
    return world


def _ancestry_from_data(world: World, rows: Sequence[Any] | None) -> AncestryBook:
    """The saved ancestry book, or for a save from before it a new one holding the living animals
    (born as long ago as their age says)."""
    if rows is not None:
        return AncestryBook.from_data(rows)
    book = AncestryBook()
    for animal in world.animals:
        traits = animal.traits
        born = max(0, world.tick - traits.age_ticks)
        book.born(animal.id, animal.parents, traits.sex, born, traits.family_key)
    return book


# =============================================================================
# Files
# =============================================================================


def dump_world(world: World) -> bytes:
    """The world as the bytes ``save_world`` writes to a ``.gz`` file (gzip of its JSON), for a store
    that keeps saves somewhere other than a file. The same world always gives the same bytes."""
    text = json.dumps(world_to_dict(world), separators=(",", ":"), sort_keys=True)
    # mtime 0 keeps the bytes the same from run to run. Level 1: four times faster than 6 for a file
    # about a fifth bigger, and a checkpoint is dominated by this call.
    return gzip.compress(text.encode("utf-8"), compresslevel=1, mtime=0)


def save_world(world: World, path: str | os.PathLike[str]) -> Path:
    """Write the world to ``path`` (gzip-compressed if the name ends in ``.gz``). The file is
    written beside the target and moved into place, so a crash cannot leave half a save. The same
    world always gives the same bytes."""
    target = Path(path)
    if target.suffix == ".gz":
        payload = dump_world(world)
    else:
        payload = json.dumps(world_to_dict(world), separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    scratch = target.with_name(target.name + ".part")
    scratch.write_bytes(payload)
    os.replace(scratch, target)
    return target


def load_world(
    path: str | os.PathLike[str],
    senses: Senses | None = None,
    sleep_listeners: Iterable[SleepListener] = (),
) -> World:
    """Read a world saved by ``save_world`` (see ``world_from_dict``)."""
    source = Path(path)
    return load_world_bytes(
        source.read_bytes(),
        senses,
        sleep_listeners,
        name=source.name,
        gzipped=source.suffix == ".gz",
    )


def load_world_bytes(
    raw: bytes,
    senses: Senses | None = None,
    sleep_listeners: Iterable[SleepListener] = (),
    *,
    name: str = "the save",
    gzipped: bool = True,
) -> World:
    """Read a world from the bytes ``dump_world`` made (``gzipped=False`` for plain JSON)."""
    try:
        if gzipped:
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SaveFormatError(f"{name} is not a readable save: {error}.") from error
    if not isinstance(data, dict):
        raise SaveFormatError(f"{name} is not a saved world.")
    return world_from_dict(data, senses, sleep_listeners)


__all__ = [
    "FORMAT",
    "FORMAT_VERSION",
    "SaveFormatError",
    "config_from_dict",
    "config_to_dict",
    "dump_world",
    "load_world",
    "load_world_bytes",
    "save_world",
    "world_from_dict",
    "world_to_dict",
]
