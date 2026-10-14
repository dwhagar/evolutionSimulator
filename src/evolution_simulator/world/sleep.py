"""Sleep (WORLD.5): the rules, and the hook the learning step (BRAIN.24) listens on.

At night every animal that is not starving sleeps. A sleeper does not sense, think, move, eat or
mate. It burns less energy and regains some, which is the owner's reason for sleep (issue 26). Its
brain is untouched while it sleeps; the nightly weight update (BRAIN.24) attaches through
``World.add_sleep_listener`` and runs when an animal falls asleep or wakes.

The rules (``SleepRules``, now ``TraitRules.sleep`` in ``config.py``) are starting values to calibrate (SENSE.13, TRAIT.3), and two open owner questions
shape them: whether sleepers are vulnerable (issue 57, default partly: sleeping animals stay in the
world and are sensed like any other, and their own senses work at reduced strength through the
sensing rules) and whether a creature can skip sleep when starving (this default says yes).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from evolution_simulator.config import SleepRules

if TYPE_CHECKING:
    from evolution_simulator.world.organisms import Animal
    from evolution_simulator.world.world import World


class SleepListener(Protocol):
    """Hears when an animal falls asleep or wakes; called in id order during the step."""

    def fell_asleep(self, world: World, animal: Animal) -> None: ...

    def woke(self, world: World, animal: Animal) -> None: ...


__all__ = ["SleepListener", "SleepRules"]
