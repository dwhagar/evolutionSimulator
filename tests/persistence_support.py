"""Helpers for the save and load tests: a world with a bit of everything in it, and a comparison
that looks at every attribute of a world, not only at what ``state_digest`` hashes."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from typing import Any

from world_support import animal_dna, breeding_pair, hourly_world

from evolution_simulator.config import DEFAULT_RULES
from evolution_simulator.dna import DNA, GenomeLayout
from evolution_simulator.traits import AnimalTraits, Pregnancy
from evolution_simulator.world import Bounds, DayCycle, Vec, World
from evolution_simulator.world.spatial import SpatialIndex

SAVE_TICK = 45
"""Ticks to run before saving: night has fallen, animals have learned and corpses lie about."""
MORE_TICKS = 90
"""Ticks to run after the save: the litters are born."""

SURE_CONCEPTION = replace(
    DEFAULT_RULES,
    reproduction=replace(DEFAULT_RULES.reproduction, conception_base=1.0, conception_slope=0.0),
)


def rich_world(seed: int = 5) -> World:
    """A world with every kind of state in it, as of tick 1.

    Founders with the seeded brain (they learn, sleep at night and graze), plants that shade each
    other, three breeding pairs (one father is killed at once, so his litter has no father to pay),
    two corpses, and callers that cost energy. Conception is certain and the litters are due while
    a test is running.
    """
    world = hourly_world(
        seed=seed,
        traits=SURE_CONCEPTION,
        bounds=Bounds((600.0, 600.0)),
        day_cycle=DayCycle(),
        mating_reach=10.0,
    )
    world.populate(animals=30, plants=300)
    pairs = [breeding_pair(world, x=300.0 + 10.0 * i) for i in range(3)]
    caller = animal_dna(brain={"speed": -2.0, "alarm": 2.0}, encoder_fidelity="0013")
    for i in range(3):  # cheap callers that stay put and keep raising the alarm
        placed = world.add_animal(caller, Vec.of(200.0 + 5.0 * i, 400.0), heading=0.0)
        placed.traits.current_energy = placed.traits.max_energy
    doomed = world.animals[:2]
    world.step()  # the pairs mate
    for (_, mother), remaining in zip(pairs, (60.0, 100.0, 400.0), strict=True):
        assert mother.traits.pregnancy is not None
        mother.traits.pregnancy.remaining = remaining
    for parent in (animal for pair in pairs for animal in pair):
        parent.traits.current_energy = parent.traits.max_energy  # they can pay for the litters
    pairs[2][0].traits.apply_damage(1e9)  # a father who dies before the birth
    for animal in doomed:
        animal.traits.apply_damage(1e9)  # two corpses
    return world


def what_the_scenario_covers(world: World) -> dict[str, int]:
    """Counts of the kinds of state a world holds, to show a test world is not trivially simple."""
    animals = world.animals
    learners = [a.traits.learner for a in animals if a.traits.learner is not None]
    pregnancies = [a.traits.pregnancy for a in animals if a.traits.pregnancy is not None]
    return {
        "animals": len(animals),
        "plants": len(world.plants),
        "corpses": len(world.corpses),
        "asleep": sum(a.asleep for a in animals),
        "awake": sum(not a.asleep for a in animals),
        "open_decisions": sum(learner.open_decisions for learner in learners),
        "logged_decisions": sum(len(learner.log) for learner in learners),
        "learned_brains": sum(a.traits.brain is not a.traits.innate_brain for a in animals),
        "pregnancies": len(pregnancies),
        "fathers_alive": sum(p.father is not None and p.father.is_alive for p in pregnancies),
        "fathers_gone": sum(p.father is not None and not p.father.is_alive for p in pregnancies),
        "calls": len(world.calls),
        "partners": sum(a.partner is not None for a in animals),
        "decisions": sum(a.last_decision is not None for a in animals),
        "matings": sum(a.traits.matings > 0 for a in animals),
        "shaded_plants": sum(p.shade < 1.0 for p in world.plants),
    }


# --- the full-state comparison ------------------------------------------------------------------

_IGNORED = {(SpatialIndex, "_max_extent"), (World, "_light"), (DNA, "_packed")}
"""Attributes that only widen a search or keep a value worked out from the tick and the rules (or,
for ``DNA._packed``, from the sequence, filled when a distance first asks), so they cannot change
what happens."""


def flatten(obj: Any, path: str = "world") -> dict[str, Any]:
    """Every attribute of ``obj``, down to numbers, as ``{path: value}``.

    Containers keep their kind in the path (a tuple is not a list), floats are exact, and nothing
    is skipped except what ``_IGNORED`` names, so a field that a save forgets shows up as a
    difference with its path.
    """
    out: dict[str, Any] = {}
    _flatten(obj, path, out, ())
    return out


def _flatten(obj: Any, path: str, out: dict[str, Any], seen: tuple[int, ...]) -> None:
    if obj is None or isinstance(obj, (bool, int, str)):
        out[path] = (type(obj).__name__, obj)
        return
    if isinstance(obj, float):
        out[path] = ("float", obj.hex() if math.isfinite(obj) else repr(obj))
        return
    if isinstance(obj, Enum):
        out[path] = ("enum", type(obj).__name__, obj.name)
        return
    if isinstance(obj, GenomeLayout):
        out[path] = ("layout", obj.name, obj.version)
        return
    if id(obj) in seen:
        out[path] = ("cycle", type(obj).__name__)
        return
    seen = (*seen, id(obj))
    if isinstance(obj, Pregnancy):
        # A father who died and left the world pays nothing, the same as no father (the save keeps
        # no dead fathers), so only a living father is compared.
        father = obj.father
        out[f"{path}.father"] = (
            "father",
            str(father.dna) if father is not None and father.is_alive else None,
        )
        _flatten(obj.children, f"{path}.children", out, seen)
        _flatten(obj.remaining, f"{path}.remaining", out, seen)
        return
    if isinstance(obj, Mapping):
        out[f"{path}<{type(obj).__name__}>"] = len(obj)
        for key, value in obj.items():
            _flatten(value, f"{path}[{key!r}]", out, seen)
        return
    if isinstance(obj, (list, tuple, deque, set, frozenset)):
        items = sorted(obj, key=repr) if isinstance(obj, (set, frozenset)) else obj
        out[f"{path}<{type(obj).__name__}>"] = len(items)
        for i, item in enumerate(items):
            _flatten(item, f"{path}[{i}]", out, seen)
        return
    if is_dataclass(obj) and not isinstance(obj, type):
        for f in fields(obj):
            _flatten(getattr(obj, f.name), f"{path}.{f.name}", out, seen)
        return
    for name, value in _attributes(obj).items():
        if (type(obj), name) not in _IGNORED:
            _flatten(value, f"{path}.{name}", out, seen)
    if isinstance(obj, AnimalTraits):
        out[f"{path}.<brain is innate>"] = obj.brain is obj.innate_brain


def _attributes(obj: Any) -> dict[str, Any]:
    found: dict[str, Any] = dict(getattr(obj, "__dict__", {}))
    for cls in type(obj).__mro__:
        slots = cls.__dict__.get("__slots__", ())
        for name in (slots,) if isinstance(slots, str) else slots:
            if hasattr(obj, name):
                found[name] = getattr(obj, name)
    return found


def differences(left: World, right: World, limit: int = 8) -> list[str]:
    """The first attributes (by path) in which two worlds differ, or an empty list."""
    a, b = flatten(left), flatten(right)
    paths = sorted(p for p in a.keys() | b.keys() if a.get(p, "<missing>") != b.get(p, "<missing>"))
    return [f"{p}: {a.get(p, '<missing>')} != {b.get(p, '<missing>')}" for p in paths[:limit]]


def assert_same_world(left: World, right: World) -> None:
    """Fail naming the attributes in which two worlds differ."""
    found = differences(left, right)
    assert not found, "worlds differ:\n" + "\n".join(found)
    assert left.state_digest() == right.state_digest()
