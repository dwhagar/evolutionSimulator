"""Senses: the part that turns the world around an animal into brain ``Percepts``.

The world only asks ``senses.perceive(world, animal)``, so any object with that method can be
passed to ``World(config, senses=...)``. The default, ``WorldSenses`` (``SENSE.12``), is the world's
side of the sensing step in ``sensing.py``: it finds the things near an animal, classifies each one
for that animal, says how loud and how smelly it is, and hands the list to the pure ``sense()``
function with the animal's organs, the light and the world's edge.

Classes (``classify``), from the viewer's point of view:

- a plant is ``plant``;
- an animal at most 0.8 of the viewer's mass is ``prey`` if the viewer can digest meat (effective
  carnivore efficiency above 0.1), and an animal at least 1.25 times its mass is a ``threat`` if
  that animal can digest meat;
- an animal of about its own size (between the two) is a possible ``mate``;
- any other animal is ``other``: it is sensed and counts toward crowding, but is none of the above.

How much a neighbour can be heard or smelled (the world supplies it, see ``sensing.Neighbour``):
a still animal is quiet and a moving one loud, a sleeping one quiet; a plant makes no sound and its
scent grows with its biomass up to ``PLANT_SCENT_BIOMASS``; animals have full scent. Calls come
from the animals that called this tick (``World.calls``).

Directions are egocentric as the brain expects: measured from the way the animal faces, -1 hard
left to +1 hard right (so a positive direction needs a positive ``turn`` to steer toward it).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Protocol

from evolution_simulator.brain_adapter import Percepts
from evolution_simulator.world.organisms import Animal, Plant
from evolution_simulator.world.vector import Vec

if TYPE_CHECKING:
    from evolution_simulator.sensing import Neighbour, SensingRules
    from evolution_simulator.world.world import World

PREY_MASS_RATIO: float = 0.8
"""An animal at most this fraction of the viewer's mass can be prey."""
THREAT_MASS_RATIO: float = 1.25
"""An animal at least this multiple of the viewer's mass can be a threat."""
MEAT_EATER: float = 0.1
"""Effective carnivore efficiency above which an animal counts as able to eat animals."""
PLANT_SCENT_BIOMASS: float = 100.0
"""A plant of this biomass or more has full scent."""
QUIET: float = 0.1
"""Loudness of an animal that is still or asleep; loudness rises to 1 at full speed."""


class Senses(Protocol):
    def perceive(self, world: World, animal: Animal) -> Percepts:
        """What ``animal`` senses of ``world`` right now. Must not change the world."""
        ...


def wrap_angle(angle: float) -> float:
    """``angle`` brought into -pi to pi (a half turn can come back as either)."""
    return (angle + math.pi) % math.tau - math.pi


def relative_direction(heading: float, origin: Vec, target: Vec) -> float:
    """-1 to 1: where ``target`` lies from ``origin`` when facing ``heading`` (+1 hard right)."""
    ox, oy = origin.coords
    tx, ty = target.coords
    return -wrap_angle(math.atan2(ty - oy, tx - ox) - heading) / math.pi


def classify(viewer: Animal, other: Animal) -> str:
    """What ``other`` is to ``viewer``: ``young`` (its own child, still dependent on it), ``prey``,
    ``threat``, ``mate`` or ``other``."""
    if viewer.id in other.parents and other.traits.lived_ticks < viewer.traits.dependence_ticks:
        return "young"
    ratio = other.traits.mass / viewer.traits.mass
    if ratio <= PREY_MASS_RATIO:
        return "prey" if viewer.traits.effective_carn_eff > MEAT_EATER else "other"
    if ratio >= THREAT_MASS_RATIO:
        return "threat" if other.traits.effective_carn_eff > MEAT_EATER else "other"
    return "mate"


def _similarity_to(viewer: Animal, other: Animal, unrelated: float):
    """A function giving how alike ``other``'s genome is to ``viewer``'s, 1 identical and 0 as
    different as strangers; the genomes are only compared if the sensing step asks."""

    def similarity() -> float:
        return max(0.0, 1.0 - viewer.traits.dna.distance(other.traits.dna) / unrelated)

    return similarity


def loudness(animal: Animal) -> float:
    """How well an animal can be heard: quiet when still or asleep, loud at full speed."""
    decision = animal.last_decision
    if animal.asleep or decision is None:
        return QUIET
    return QUIET + (1.0 - QUIET) * decision.speed


def speed_ratio(animal: Animal) -> float:
    """How fast an animal is moving as a share of its top speed: 0 when asleep or still."""
    decision = animal.last_decision
    return 0.0 if animal.asleep or decision is None else decision.speed


class WorldSenses:
    """The default senses: the world's neighbour search and classifier feeding ``sense()``."""

    def __init__(self, rules: SensingRules | None = None, noisy: bool = True) -> None:
        self._rules = rules
        self._noisy = noisy
        """With ``noisy=False`` every report is exact and the world's random stream is untouched:
        the zero-noise setting for tests and for studying the world without sensing error."""

    def perceive(self, world: World, animal: Animal) -> Percepts:
        # Imported here because ``sensing`` itself imports from this package.
        from evolution_simulator.sensing import (
            Neighbour,
            SensingConditions,
            effective_reach,
            organs_from_traits,
            sense,
        )

        rules = self._rules if self._rules is not None else world.config.sensing
        traits = animal.traits
        organs = organs_from_traits(traits)
        conditions = SensingConditions(
            daylight=world.daylight, asleep=animal.asleep, clock=world.day_phase
        )
        reach = effective_reach(organs, conditions, rules)
        seen_up_to = rules.visibility_size_range[1] * max(
            rules.still_visibility, rules.moving_visibility
        )
        farthest = max(max(reach.values()), reach["vision"] * seen_up_to)
        unrelated = world.config.traits.reproduction.similarity_unrelated
        position = animal.position

        neighbours: list[Neighbour] = []
        # Plants are seen and smelled (and touched), never heard. The sensing step reports only
        # the nearest plant that is detected, and touch only needs to know that something is in
        # contact, so two plants are enough: the nearest detected one and the nearest one in touch
        # reach. The rest cannot change the answer.
        vision, smelling, touch = reach["vision"], reach["smell"], reach["touch"]
        rules_visibility = rules.visibility
        biggest = rules.visibility_size_range[1]
        plant_reach = max(vision * biggest, smelling, touch)
        if plant_reach > 0.0:
            half_fov = math.radians(organs.vision_fov_degrees) / 2.0
            ax, ay = position.coords
            heading = animal.heading
            body = animal.radius
            detected: tuple[float, int, Plant] | None = None
            felt: tuple[float, int, Plant] | None = None
            for plant, centre, canopy in world.plants_in_reach(position, plant_reach + body):
                surface = centre - body - canopy
                key = (surface, plant.id)
                if surface <= touch and (felt is None or key < felt[:2]):
                    felt = (*key, plant)
                if detected is not None and key >= detected[:2]:
                    continue
                if surface <= smelling * min(
                    1.0, plant.traits.current_biomass / PLANT_SCENT_BIOMASS
                ):
                    detected = (*key, plant)
                elif surface <= vision * rules_visibility(canopy):
                    px, py = plant.position.coords
                    if surface <= 0.0 or (
                        abs(wrap_angle(math.atan2(py - ay, px - ax) - heading)) <= half_fov
                    ):
                        detected = (*key, plant)
            for found in {id(f): f for f in (detected, felt) if f is not None}.values():
                plant = found[2]
                neighbours.append(
                    Neighbour(
                        ident=plant.id,
                        role="plant",
                        position=plant.position,
                        radius=plant.traits.canopy_radius,
                        loudness=0.0,
                        scent=min(1.0, plant.traits.current_biomass / PLANT_SCENT_BIOMASS),
                        visibility=rules_visibility(plant.traits.canopy_radius),
                    )
                )
        if farthest > 0.0:
            for other, centre, _ in world.animals_in_reach(position, farthest + animal.radius):
                if other is animal:
                    continue
                alarm, mating = world.calls.get(other.id, (0.0, 0.0))
                role = classify(animal, other)
                neighbours.append(
                    Neighbour(
                        ident=other.id,
                        role=role,
                        position=other.position,
                        radius=other.radius,
                        loudness=loudness(other),
                        scent=1.0,
                        visibility=rules_visibility(
                            other.radius, speed_ratio(other), other.traits.camouflage
                        ),
                        alarm_call_radius=alarm,
                        mating_call_radius=mating,
                        mass=other.traits.mass,
                        similarity=_similarity_to(animal, other, unrelated)
                        if role == "mate"
                        else 0.0,
                    )
                )
        if farthest > 0.0 and traits.effective_carn_eff > MEAT_EATER:
            # Corpses are food for a meat eater: reported as prey that cannot hide or run.
            for corpse, _, _ in world.corpses_in_reach(position, farthest + animal.radius):
                neighbours.append(
                    Neighbour(
                        ident=corpse.id,
                        role="prey",
                        position=corpse.position,
                        radius=corpse.radius,
                        loudness=0.0,
                        scent=min(1.0, corpse.meat / world.config.corpses.scent_meat),
                        mass=corpse.mass,
                        carrion=True,
                    )
                )
        edge_gap, edge_direction = world.edge_state(position)
        return sense(
            position,
            animal.heading,
            animal.radius,
            organs,
            neighbours,
            conditions,
            rules,
            world.rng if self._noisy else None,
            edge_distance=edge_gap - animal.radius,
            mass=traits.mass,
            edge_direction=edge_direction,
            reach=reach,
        )
