"""What an animal looks at (UX.43), and which way its eyes turn.

The eyes are a cosmetic of the picture: they change nothing about what happens. An animal that has
sensed something looks at one of the things the sensing step reported (the nearest of each class,
``Percepts.targets``), chosen by ``choose_focus`` from what it decided to do; the world keeps its id
(``Animal.focus``) and, when a frame is made, ``look_angle`` turns it into the angle the eyes point
at, clamped to the animal's field of vision.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from evolution_simulator.brain_adapter import BrainDecision
from evolution_simulator.world.senses import wrap_angle
from evolution_simulator.world.vector import Vec


def choose_focus(targets: Sequence[tuple[str, int]], decision: BrainDecision) -> int | None:
    """The id of the thing it looks at, or ``None`` when it senses nothing worth looking at.

    Danger first: a threat takes the eyes whatever it is doing. Otherwise what it is doing decides
    (looking for a mate: the mate; eating or attacking: its prey, else a plant), and after that
    its young, a mate, prey and a plant, in that order. Each class offers its nearest member."""
    found = dict(targets)
    order = ["threat"]
    if decision.seeks_mating:
        order.append("mate")
    if decision.eats_or_attacks:
        order += ["prey", "plant"]
    order += ["young", "mate", "prey", "plant"]
    for kind in order:
        if kind in found:
            return found[kind]
    return None


def look_angle(heading: float, origin: Vec, target: Vec, half_fov: float) -> float:
    """Where the eyes point, in radians from straight ahead (positive to the left, as headings
    turn), toward ``target`` but never past the edge of the field of vision (``half_fov``, half the
    field's width)."""
    ox, oy = origin.coords[:2]
    tx, ty = target.coords[:2]
    if tx == ox and ty == oy:
        return 0.0
    bearing = wrap_angle(math.atan2(ty - oy, tx - ox) - heading)
    return max(-half_fov, min(half_fov, bearing))
