"""The sensing step: what one creature perceives of the things around it (``SENSE.10``).

``sense`` is a pure function. Give it where a creature is and which way it faces, what its sense
organs can do and a list of already-classified neighbours, and it returns the ``Percepts`` the brain
adapter needs. It knows nothing about the world, DNA or traits, so it can be tested without any of
them and with a fixed seed. The world's job (``SENSE.12``) is to find the neighbours and classify
them (plant, prey, threat, mate or other); the sense genes (``SENSE.11``) turn into a
``SenseOrgans``. The rules are in ``docs/design/senses.md`` ("From senses to brain inputs").

What the function does, in order:

1. Each organ's range is scaled by the conditions: vision by daylight, and every organ by its
   sleep factor while the creature is asleep. An organ with no range left is switched off.
2. Each neighbour is placed in the creature's own frame as a vector (forward and to the left), and
   its distance is measured between the two bodies' surfaces. Positions are vectors, so 3D is more
   components; the bearing is 2D for now.
3. Each organ detects what it is allowed to report (the ``senses`` of the matching rows in
   ``sense_channels.py``): vision within its field of view, hearing in every direction (quiet things
   are harder to hear), smell in every direction (weak for prey and threats).
4. Each class reports its nearest detected member. Closeness is ``1 - d / R_class`` where
   ``R_class`` is the largest range among the organs that report that class, so a creature's
   inputs are scaled to its own senses. The bearing comes from the most precise organ that detected
   it (vision, then hearing, then smell), divided by the half field of view for vision and by 180
   degrees otherwise, left negative.
5. The nearest prey or threat also gives the relative-size input, ``log2(mass ratio) / 2``, with the
   direction error of the organ that found it (vision's falls with acuity). Calls, touch and
   crowding are read off the same neighbours, and the daylight input is the conditions' daylight.
6. If a random generator is given, each report gets seeded noise that falls as the organ improves.

Everything not sensed is 0 (daylight aside). Nothing here changes its arguments.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from evolution_simulator.brain_adapter import Percepts
from evolution_simulator.sense_channels import (
    SENSE_KINDS,
    TARGETS,
    channels_for_target,
    senses_reporting,
)
from evolution_simulator.world.vector import Vec

if TYPE_CHECKING:
    from evolution_simulator.traits import AnimalTraits

ROLES: tuple[str, ...] = (*TARGETS, "other")
"""What a neighbour is to the creature: a ``TARGETS`` class, or an animal that is none of them."""

PRECISION_ORDER: tuple[str, ...] = tuple(k for k in SENSE_KINDS if k != "touch")
"""Organs that give a direction, most precise first."""

_CROWDING_SENSES: tuple[str, ...] = senses_reporting("crowding")


def _plan_for(target: str) -> tuple[str, str, tuple[str, ...]]:
    rows = {c.role: c.name for c in channels_for_target(target)}
    closeness_row = rows["closeness"]
    reporters = tuple(k for k in PRECISION_ORDER if k in senses_reporting(closeness_row))
    return rows["bearing"], closeness_row, reporters


_TARGET_PLAN: dict[str, tuple[str, str, tuple[str, ...]]] = {t: _plan_for(t) for t in TARGETS}
"""Per class: the names of its direction and closeness inputs and the senses that may report it,
most precise first. Fixed by the channel table, so worked out once."""


@dataclass(frozen=True)
class SensingRules:
    """The constants of the sensing step: starting values from the design note, for calibration
    against a running world (``SENSE.13``) and to move into the constants config (``TRAIT.3``)."""

    light_floor: float = 0.25
    """Vision range at full darkness as a fraction of its daylight range:
    ``light_floor + (1 - light_floor) * daylight``."""
    sleep_vision: float = 0.0
    sleep_hearing: float = 0.5
    sleep_smell: float = 0.5
    sleep_touch: float = 1.0
    """The fraction of each organ's range that still works while asleep."""
    weak_smell: float = 0.5
    """Fraction of the smell range at which prey and threats can be smelled (a presence, not a
    precise report). A placeholder: the design note gives no number."""
    crowding_reference: int = 8
    """This many animals in reach gives a crowding input of 1."""
    closeness_noise: float = 0.03
    """Standard deviation of the error on every closeness report (input units)."""

    def __post_init__(self) -> None:
        for name in (
            "light_floor",
            "sleep_vision",
            "sleep_hearing",
            "sleep_smell",
            "sleep_touch",
            "weak_smell",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1, got {getattr(self, name)}.")
        if self.crowding_reference < 1:
            raise ValueError("crowding_reference must be at least 1.")
        if not (math.isfinite(self.closeness_noise) and self.closeness_noise >= 0.0):
            raise ValueError("closeness_noise cannot be negative.")

    def light_factor(self, daylight: float) -> float:
        return self.light_floor + (1.0 - self.light_floor) * daylight

    def sleep_factor(self, sense: str) -> float:
        return {
            "vision": self.sleep_vision,
            "hearing": self.sleep_hearing,
            "smell": self.sleep_smell,
            "touch": self.sleep_touch,
        }[sense]


@dataclass(frozen=True)
class SenseOrgans:
    """What a creature's sense organs can do, before daylight and sleep (``SENSE.11`` makes these
    from the sense genes). Ranges are in world units and 0 means the organ is not there. Noise is the
    standard deviation of the error on a direction report, in input units (0.1 is about 18 degrees on
    an all-round organ)."""

    vision_range: float = 0.0
    vision_fov_degrees: float = 360.0
    hearing_range: float = 0.0
    smell_range: float = 0.0
    touch_reach: float = 0.0
    """How far past its own surface the creature feels; contact itself always counts."""
    vision_noise: float = 0.0
    hearing_noise: float = 0.0
    smell_noise: float = 0.0
    closeness_noise: float | None = None
    """Error on every closeness report (input units). ``None``: the rules' ``closeness_noise``."""

    def __post_init__(self) -> None:
        for name in (
            "vision_range",
            "hearing_range",
            "smell_range",
            "touch_reach",
            "vision_noise",
            "hearing_noise",
            "smell_noise",
            "closeness_noise",
        ):
            value = getattr(self, name)
            if value is None and name == "closeness_noise":
                continue
            if not (math.isfinite(value) and value >= 0.0):
                raise ValueError(f"{name} must be a finite number, 0 or more, got {value}.")
        if not (0.0 < self.vision_fov_degrees <= 360.0):
            raise ValueError("vision_fov_degrees must be above 0 and at most 360.")

    def range_of(self, sense: str) -> float:
        return {
            "vision": self.vision_range,
            "hearing": self.hearing_range,
            "smell": self.smell_range,
            "touch": self.touch_reach,
        }[sense]

    def noise_of(self, sense: str) -> float:
        return {
            "vision": self.vision_noise,
            "hearing": self.hearing_noise,
            "smell": self.smell_noise,
            "touch": 0.0,
        }[sense]


def organs_from_traits(traits: AnimalTraits) -> SenseOrgans:
    """The sense organs of an animal as it is now: ranges after vitality, the field of view, the
    noise its sense genes give, and the touch reach beyond its body (``SENSE.11``)."""
    return SenseOrgans(
        vision_range=traits.current_sight_range,
        vision_fov_degrees=traits.fov_degrees,
        hearing_range=traits.current_hearing_range,
        smell_range=traits.smell_range,
        touch_reach=max(0.0, traits.tactile_range - traits.body_radius),
        vision_noise=traits.vision_noise,
        hearing_noise=traits.hearing_noise,
        smell_noise=traits.smell_noise,
        closeness_noise=traits.vision_closeness_noise,
    )


@dataclass(frozen=True)
class SensingConditions:
    """The state of the world and the creature that changes how well it senses."""

    daylight: float = 1.0
    """0 (full night) to 1 (full day)."""
    asleep: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.daylight <= 1.0:
            raise ValueError(f"daylight must be between 0 and 1, got {self.daylight}.")


@dataclass(frozen=True)
class Neighbour:
    """Something near the creature, as the world's classifier describes it to this creature."""

    ident: int
    """Breaks ties between equally near things, so a run repeats."""
    role: str
    """``plant``, ``prey``, ``threat``, ``mate`` or ``other`` (an animal that is none of those)."""
    position: Vec
    radius: float = 0.0
    loudness: float = 1.0
    """0 to 1: how well it can be heard. A still animal is quiet, a moving one loud; a plant makes
    no sound and is never reported by hearing whatever this says."""
    scent: float = 1.0
    """0 to 1: how well it can be smelled (a plant's grows with its biomass)."""
    alarm_call_radius: float = 0.0
    """How far its alarm call carries, 0 when it is not calling."""
    mating_call_radius: float = 0.0
    """How far its mating call carries, 0 when it is not calling."""
    mass: float = 0.0
    """Its body mass, for the relative-size input; 0 when not known."""

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"A neighbour's role must be one of {ROLES}, got {self.role!r}.")
        if self.radius < 0.0:
            raise ValueError("A neighbour's radius cannot be negative.")
        for name in ("loudness", "scent"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1, got {getattr(self, name)}.")
        if self.alarm_call_radius < 0.0 or self.mating_call_radius < 0.0:
            raise ValueError("A call radius cannot be negative.")
        if self.mass < 0.0:
            raise ValueError("A neighbour's mass cannot be negative.")

    @property
    def is_animal(self) -> bool:
        return self.role != "plant"


def effective_reach(
    organs: SenseOrgans,
    conditions: SensingConditions | None = None,
    rules: SensingRules | None = None,
) -> dict[str, float]:
    """What each organ can still do right now: its range scaled by the light (vision) and the
    sleep factor (every organ while asleep). An organ with no range left is switched off (0)."""
    conditions = conditions if conditions is not None else SensingConditions()
    rules = rules if rules is not None else SensingRules()
    light = rules.light_factor(conditions.daylight)
    reach: dict[str, float] = {}
    for kind in SENSE_KINDS:
        scale = rules.sleep_factor(kind) if conditions.asleep else 1.0
        if kind == "vision":
            scale *= light
        reach[kind] = organs.range_of(kind) * scale
    return reach


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sense(
    position: Vec,
    heading: float,
    radius: float,
    organs: SenseOrgans,
    neighbours: Iterable[Neighbour],
    conditions: SensingConditions | None = None,
    rules: SensingRules | None = None,
    rng: random.Random | None = None,
    edge_distance: float | None = None,
    mass: float = 0.0,
) -> Percepts:
    """What a creature at ``position`` facing ``heading`` (radians, 0 is +x, counterclockwise) with
    a body of ``radius`` perceives of ``neighbours``.

    ``rng`` supplies the noise; without it every report is exact, which is the zero-noise setting
    for tests. Draws happen in a fixed order, so equal seeds give equal reports.
    ``edge_distance`` is the distance from the creature's surface to the nearest edge of the world,
    if it knows it; touch reports the edge as it does anything else in contact.
    """
    if position.dimensions != 2:
        raise ValueError("The sensing step supports 2D positions only for now.")
    conditions = conditions if conditions is not None else SensingConditions()
    rules = rules if rules is not None else SensingRules()

    reach = effective_reach(organs, conditions, rules)
    half_fov = math.radians(organs.vision_fov_degrees) / 2.0
    reach_vision, reach_hearing = reach["vision"], reach["hearing"]
    reach_smell, reach_touch = reach["smell"], reach["touch"]
    weak_smell = reach_smell * rules.weak_smell

    # Each neighbour in the creature's own frame, worked out on plain numbers because this runs
    # for every neighbour of every animal every tick. The distance is between the two surfaces.
    # Which organs detect a neighbour is settled once, here, from its own class: vision within its
    # field of view (always when touching), hearing and smell all round, scaled by how loud and
    # how smelly it is, and smell weak for prey and threats.
    fx, fy = math.cos(heading), math.sin(heading)
    px, py = position.coords
    best: dict[str, tuple[float, int, Neighbour, dict[str, bool], float, float]] = {}
    callers: list[tuple[float, Neighbour, float, float]] = []
    nearest = math.inf
    crowd = 0
    for n in neighbours:
        role = n.role
        nx, ny = n.position.coords
        dx, dy = nx - px, ny - py
        distance = max(0.0, math.hypot(dx, dy) - radius - n.radius)
        nearest = min(nearest, distance)
        sees = False
        if reach_vision > 0.0 and distance <= reach_vision:
            sees = distance == 0.0 or (
                abs(math.atan2(dy * fx - dx * fy, dx * fx + dy * fy)) <= half_fov
            )
        hears = reach_hearing > 0.0 and distance <= reach_hearing * n.loudness
        smell_limit = weak_smell if role in ("prey", "threat") else reach_smell
        smells = smell_limit > 0.0 and distance <= smell_limit * n.scent
        if n.alarm_call_radius > 0.0 or n.mating_call_radius > 0.0:
            callers.append((distance, n, dx, dy))
        if role == "plant":
            crowded = False
        else:
            crowded = (sees and "vision" in _CROWDING_SENSES) or (
                hears and "hearing" in _CROWDING_SENSES
            )
            crowded = crowded or (smells and "smell" in _CROWDING_SENSES)
            crowded = crowded or (
                reach_touch > 0.0 and distance <= reach_touch and ("touch" in _CROWDING_SENSES)
            )
            if crowded:
                crowd += 1
        if role not in _TARGET_PLAN:
            continue
        flags = {"vision": sees, "hearing": hears, "smell": smells}
        if not any(flags[k] for k in _TARGET_PLAN[role][2]):
            continue
        key = (distance, n.ident)
        held = best.get(role)
        if held is None or key < held[:2]:
            best[role] = (distance, n.ident, n, flags, dx, dy)

    def bearing_of(dx: float, dy: float) -> float:
        """Radians, positive to the creature's left, between -pi and pi."""
        if dx == 0.0 and dy == 0.0:
            return 0.0
        return math.atan2(dy * fx - dx * fy, dx * fx + dy * fy)

    def noise(sense_kind: str, sd: float | None = None) -> float:
        deviation = organs.noise_of(sense_kind) if sd is None else sd
        if rng is None or deviation <= 0.0:
            return 0.0
        return rng.gauss(0.0, deviation)

    def direction(sense_kind: str, bearing: float) -> float:
        norm = half_fov if sense_kind == "vision" else math.pi
        return _clamp(-bearing / norm + noise(sense_kind), -1.0, 1.0)

    closeness_noise = (
        rules.closeness_noise if organs.closeness_noise is None else organs.closeness_noise
    )
    reported: dict[str, float] = {}
    sizeable: list[tuple[float, int, Neighbour, str]] = []  # prey and threats found, for size
    for target in TARGETS:
        direction_row, closeness_row, reporters = _TARGET_PLAN[target]
        class_range = max(
            (weak_smell if k == "smell" and target in ("prey", "threat") else reach[k])
            for k in reporters
        )
        found = best.get(target)
        if found is None or class_range <= 0.0:
            continue
        distance, ident, neighbour, flags, dx, dy = found
        by = next(k for k in reporters if flags[k])
        if target in ("prey", "threat"):
            sizeable.append((distance, ident, neighbour, by))
        reported[direction_row] = direction(by, bearing_of(dx, dy))
        reported[closeness_row] = _clamp(
            1.0 - distance / class_range + noise("vision", closeness_noise),
            0.0,
            1.0,
        )

    # Relative size of the nearest prey or threat: vision is exact, other senses are noisy.
    if sizeable and mass > 0.0:
        _, _, closest, by = min(sizeable, key=lambda item: item[:2])
        if closest.mass > 0.0:
            ratio = math.log2(closest.mass / mass) / 2.0
            noisy = ratio + noise(by)
            reported["relative_size"] = _clamp(noisy, -1.0, 1.0)

    # Calls come only through hearing.
    alarm = mating = 0.0
    loudest: tuple[float, int, float, float] | None = None
    if reach_hearing > 0.0:
        for distance, n, dx, dy in callers:
            if distance > reach_hearing:
                continue
            for call_radius, is_alarm in (
                (n.alarm_call_radius, True),
                (n.mating_call_radius, False),
            ):
                if call_radius <= 0.0 or distance >= call_radius:
                    continue
                strength = 1.0 - distance / call_radius
                if is_alarm:
                    alarm = max(alarm, strength)
                else:
                    mating = max(mating, strength)
                if loudest is None or (-strength, n.ident) < loudest[:2]:
                    loudest = (-strength, n.ident, dx, dy)
    call_direction = (
        direction("hearing", bearing_of(loudest[2], loudest[3])) if loudest is not None else 0.0
    )

    # Touch: anything in contact, or the world's edge.
    touching = nearest <= reach_touch or (
        edge_distance is not None and edge_distance <= reach_touch
    )

    return Percepts(
        **reported,
        touching=touching,
        alarm_strength=alarm,
        mating_call_strength=mating,
        call_direction=call_direction,
        crowding=min(1.0, crowd / rules.crowding_reference),
        daylight=conditions.daylight,
    )
