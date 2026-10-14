"""Senses: the swappable part that turns the world around an animal into brain ``Percepts``.

The world only asks ``senses.perceive(world, animal)``, so the sense design from SENSE.1 can replace
``BasicSenses`` without touching the step loop. ``BasicSenses`` is a stand-in: sight only, with
simple rules for what counts as prey, threat and mate.

Directions are egocentric as the brain expects: measured from the way the animal faces, -1 hard
left to +1 hard right (so a positive direction needs a positive ``turn`` to steer toward it).
Closeness runs from 0 at the edge of the sense range to 1 at the animal's centre. The angle
helpers are 2D.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Protocol

from evolution_simulator.brain_adapter import Percepts
from evolution_simulator.world.organisms import Animal, Plant
from evolution_simulator.world.vector import Vec

if TYPE_CHECKING:
    from evolution_simulator.world.world import World

PREY_MASS_RATIO: float = 0.8
"""An animal lighter than this fraction of the viewer's mass counts as possible prey."""
THREAT_MASS_RATIO: float = 1.25
"""An animal heavier than this multiple of the viewer's mass counts as a threat."""
CROWDING_FULL: int = 10
"""This many animals in sight gives a crowding input of 1."""


class Senses(Protocol):
    def perceive(self, world: World, animal: Animal) -> Percepts:
        """What ``animal`` senses of ``world`` right now. Must not change the world."""
        ...


def wrap_angle(angle: float) -> float:
    """``angle`` brought into -pi to pi."""
    return math.atan2(math.sin(angle), math.cos(angle))


def relative_direction(heading: float, origin: Vec, target: Vec) -> float:
    """-1 to 1: where ``target`` lies from ``origin`` when facing ``heading`` (+1 hard right)."""
    bearing = (target - origin).angle()
    return -wrap_angle(bearing - heading) / math.pi


def _closeness(distance: float, sense_range: float) -> float:
    if sense_range <= 0.0:
        return 0.0
    return min(1.0, max(0.0, 1.0 - distance / sense_range))


class BasicSenses:
    """Sight within the animal's range and field of view, plus touch and crowding.

    Prey is a lighter animal, a threat a heavier one, and a possible mate is the nearest animal
    that is neither (so roughly its own size). Calls are not heard yet.
    """

    def perceive(self, world: World, animal: Animal) -> Percepts:
        traits = animal.traits
        sight = traits.current_sight_range
        half_view = math.radians(traits.fov_degrees) / 2.0
        touch_range = traits.tactile_range if traits.phenotype["touch"] > 0.1 else 0.0

        def in_view(position: Vec) -> bool:
            if animal.position == position:
                return True
            bearing = (position - animal.position).angle()
            return abs(wrap_angle(bearing - animal.heading)) <= half_view

        best_plant: tuple[float, int, Plant] | None = None
        touching = False
        for plant in world.plants_near(animal.position, max(sight, touch_range + world.max_canopy)):
            distance = animal.position.distance_to(plant.position)
            if touch_range and distance <= touch_range + plant.radius:
                touching = True
            if (
                distance <= sight
                and in_view(plant.position)
                and (best_plant is None or (distance, plant.id) < best_plant[:2])
            ):
                best_plant = (distance, plant.id, plant)

        nearest: dict[str, tuple[float, int, Animal]] = {}
        crowd = 0
        for other in world.animals_near(animal.position, max(sight, touch_range + world.max_body)):
            if other is animal:
                continue
            distance = animal.position.distance_to(other.position)
            if touch_range and distance <= touch_range + other.radius:
                touching = True
            if distance > sight or not in_view(other.position):
                continue
            crowd += 1
            if other.traits.mass < PREY_MASS_RATIO * traits.mass:
                role = "prey"
            elif other.traits.mass > THREAT_MASS_RATIO * traits.mass:
                role = "threat"
            else:
                role = "mate"
            if role not in nearest or (distance, other.id) < nearest[role][:2]:
                nearest[role] = (distance, other.id, other)

        def aim(found: tuple[float, int, Animal | Plant] | None) -> tuple[float, float]:
            if found is None:
                return 0.0, 0.0
            distance, _, thing = found
            return (
                relative_direction(animal.heading, animal.position, thing.position),
                _closeness(distance, sight),
            )

        plant_dir, plant_close = aim(best_plant)
        prey_dir, prey_close = aim(nearest.get("prey"))
        threat_dir, threat_close = aim(nearest.get("threat"))
        mate_dir, mate_close = aim(nearest.get("mate"))
        return Percepts(
            plant_direction=plant_dir,
            plant_closeness=plant_close,
            prey_direction=prey_dir,
            prey_closeness=prey_close,
            threat_direction=threat_dir,
            threat_closeness=threat_close,
            mate_direction=mate_dir,
            mate_closeness=mate_close,
            touching=touching,
            crowding=min(1.0, crowd / CROWDING_FULL),
        )
