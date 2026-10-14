"""What the viewer and the simulation process say to each other (UX.7).

Everything here is a plain value (frozen dataclasses of numbers, strings, bytes and the frames and
details of ``snapshot`` and ``world.views``) so it pickles over a ``multiprocessing`` pipe today and
could go over a socket tomorrow. Viewer to simulation: a ``Command`` of ``commands.py`` or one of
``Ack``, ``SetFrameRate``, ``RequestPlants`` and ``Shutdown`` below. Simulation to viewer: a
``Frame``, an ``AnimalDetail`` or one of the messages below.
"""

from __future__ import annotations

from dataclasses import dataclass

from evolution_simulator.session.commands import Command
from evolution_simulator.session.session import SessionEvent
from evolution_simulator.session.snapshot import Frame
from evolution_simulator.world.views import AnimalDetail

# --- viewer to simulation -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Ack:
    """The viewer has taken in this many frames, details and event batches in all. While more than
    ``HostRules.max_in_flight`` are unacknowledged the host stops sending frames (a slow window
    slows nothing but itself)."""

    received: int


@dataclass(frozen=True, slots=True)
class SetFrameRate:
    """At most this many frames a second; 0 stops them (a minimised window costs nothing) while
    the simulation runs on."""

    hz: float


@dataclass(frozen=True, slots=True)
class RequestPlants:
    """Put the plants in the next frame (a window that has just opened or lost them)."""


@dataclass(frozen=True, slots=True)
class Shutdown:
    """Stop cleanly."""


Request = Command | Ack | SetFrameRate | RequestPlants | Shutdown

# --- simulation to viewer -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Ready:
    """The simulation is built and listening. ``frame`` is its first frame, so a window has
    something to draw at once."""

    frame: Frame


@dataclass(frozen=True, slots=True)
class EventBatch:
    """World events (births, deaths, matings) and status changes since the last batch, in order.
    ``dropped`` counts, in all, the world events left out because more than
    ``HostRules.max_events_per_second`` happened in a second or the viewer was behind."""

    events: tuple[SessionEvent, ...]
    dropped: int = 0


@dataclass(frozen=True, slots=True)
class CommandRejected:
    """A command could not be carried out (nothing changed): a bad speed, an animal that is not
    there."""

    command: object
    reason: str


@dataclass(frozen=True, slots=True)
class HostInfo:
    """How the host is doing, about once a second."""

    frames_sent: int
    frames_dropped: int
    """Frames held back because the viewer was behind."""
    events_dropped: int
    details_dropped: int


@dataclass(frozen=True, slots=True)
class Crashed:
    """The simulation failed. ``report`` is the traceback as text; the host has stopped."""

    report: str


@dataclass(frozen=True, slots=True)
class Stopped:
    """The host shut down cleanly after a ``Shutdown``."""


Notice = Ready | EventBatch | CommandRejected | HostInfo | Crashed | Stopped
Outgoing = Frame | AnimalDetail | Notice
