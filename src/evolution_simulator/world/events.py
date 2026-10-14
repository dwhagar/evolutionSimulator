"""World events (UX.6): births, deaths and matings, told to listeners as they happen.

A listener is any callable taking one event, added with ``World.add_event_listener``. Events are
built only while someone listens, so a headless run with no listener pays nothing. They are
delivered during the step, in the order the world handles the organisms (id order), and carry
plain numbers only (no references into the world), so a listener may keep, send or pickle them.

``tick`` is the number the world's clock shows once the tick that caused the event has finished
(the ``tick`` of that step's ``StepReport``); organisms added by hand between steps carry the
current tick.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from evolution_simulator.deaths import DeathCause


@dataclass(frozen=True, slots=True)
class Born:
    """An organism entered the world: put in by hand, born to a mother, or seeded by a plant."""

    tick: int
    kind: str
    """``"animal"`` or ``"plant"``."""
    id: int
    x: float
    y: float
    parents: tuple[int, ...] = ()
    """Father then mother for an animal born of a mating, the mother alone when the father is
    unknown, the seeding plant for a seed, and empty for a founder."""


@dataclass(frozen=True, slots=True)
class Died:
    """An organism died and was removed. An animal's body stays on as a corpse (a separate
    ``Corpse`` in the world, not an event)."""

    tick: int
    kind: str
    id: int
    x: float
    y: float
    cause: DeathCause
    killer: int | None = None
    """The animal whose bite killed it, when ``cause`` is ``DeathCause.PREDATION``."""
    age_ticks: int = 0
    """How many ticks it lived."""


@dataclass(frozen=True, slots=True)
class Mated:
    """Two animals tried to mate and paid for it. ``conceived`` says whether it took (the mother
    is then pregnant); a mating that was refused outright, before anything was spent, is no event."""

    tick: int
    father: int
    mother: int
    conceived: bool


WorldEvent = Born | Died | Mated

EventListener = Callable[[WorldEvent], None]
