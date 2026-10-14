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

from evolution_simulator.history import HistorySamples, Recorder
from evolution_simulator.session import Command, Frame, Session, SessionEvent, Status
from evolution_simulator.world.views import AnimalDetail


@dataclass(frozen=True, slots=True)
class Batch:
    """Everything that arrived since the last poll."""

    frame: Frame | None = None
    detail: AnimalDetail | None = None
    events: tuple[SessionEvent, ...] = ()
    history: HistorySamples | None = None
    """The statistics so far, whenever a new sample has been taken since the last poll (once per
    simulated day), so the charts redraw on a new point and not on every frame."""

    @property
    def empty(self) -> bool:
        return (
            self.frame is None and self.detail is None and not self.events and self.history is None
        )


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
    """A ``Session`` in this process: ``poll`` runs the ticks that real time owes.

    It keeps a statistics ``Recorder`` on the session's simulation (``record=False`` for none, or
    pass a ``Recorder`` already listening to it, as a resumed run does) and publishes its
    ``HistorySamples`` in the batch that follows each new sample.
    """

    def __init__(self, session: Session, *, record: bool | Recorder = True) -> None:
        self.session = session
        self._events: list[SessionEvent] = []
        self._unsubscribe = session.subscribe(self._events.append)
        self.recorder: Recorder | None = (
            record
            if isinstance(record, Recorder)
            else Recorder(session.simulation)
            if record
            else None
        )
        self._published: int | None = None

    def send(self, command: Command) -> None:
        self.session.handle(command)

    def poll(self) -> Batch:
        update = self.session.update()
        events, self._events = tuple(self._events), []
        return Batch(update.frame, update.detail, events, self._new_history())

    def _new_history(self) -> HistorySamples | None:
        if self.recorder is None:
            return None
        self.recorder.observe()  # a simulation with no step listener is sampled here
        history = self.recorder.history()
        latest = history.latest
        day = None if latest is None else latest.day
        if day == self._published:
            return None
        self._published = day
        return history

    @property
    def status(self) -> Status:
        return self.session.status

    def close(self) -> None:
        self._unsubscribe()
        if self.recorder is not None:
            self.recorder.close()
