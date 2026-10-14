"""What the window talks to (UX.11).

A ``Backend`` takes ``Command`` values and, each time it is polled, hands back whatever the
simulation has published since: a ``Frame``, the selected animal's ``AnimalDetail``, the events.
It has no Qt in it, so it can be tested and reused anywhere. ``LocalBackend`` runs a ``Session`` in
the calling process, which is how the window is built and tested; the simulation process of UX.7
puts the same two methods over a pipe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from evolution_simulator.session import Command, Frame, Session, SessionEvent, Status
from evolution_simulator.world.views import AnimalDetail


@dataclass(frozen=True, slots=True)
class Batch:
    """Everything that arrived since the last poll."""

    frame: Frame | None = None
    detail: AnimalDetail | None = None
    events: tuple[SessionEvent, ...] = ()

    @property
    def empty(self) -> bool:
        return self.frame is None and self.detail is None and not self.events


class Backend(Protocol):
    def send(self, command: Command) -> None:
        """Hand a command over. A command that cannot be carried out raises ``CommandError``."""
        ...

    def poll(self) -> Batch:
        """Whatever has arrived since the last poll; never blocks."""
        ...

    @property
    def status(self) -> Status:
        """How the run stands now."""
        ...


class LocalBackend:
    """A ``Session`` in this process: ``poll`` runs the ticks that real time owes."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._events: list[SessionEvent] = []
        self._unsubscribe = session.subscribe(self._events.append)

    def send(self, command: Command) -> None:
        self.session.handle(command)

    def poll(self) -> Batch:
        update = self.session.update()
        events, self._events = tuple(self._events), []
        return Batch(update.frame, update.detail, events)

    @property
    def status(self) -> Status:
        return self.session.status

    def close(self) -> None:
        self._unsubscribe()
