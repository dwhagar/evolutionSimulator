"""The viewer's end of the conversation (UX.7): one face, three ways to reach a simulation.

The windows hold a ``SimClient`` and never know which kind: call ``send`` with a command and
``poll`` (from a timer, once per paint) for what has come back as an ``Inbox``.

- ``ProcessClient``: the real thing. The simulation runs in its own process (``multiprocessing``
  with the ``spawn`` start method, the only one Windows has), so the window answers however slow or
  fast the simulation is. A program that is frozen into an ``.exe`` must call
  ``multiprocessing.freeze_support()`` first thing in ``__main__``.
- ``InProcessClient``: the same host driven from ``poll`` in the caller's process, for tests, tools
  and the headless run. Nothing runs between polls.
- ``fake_client()``: an ``InProcessClient`` on a ``FakeSimulation``, to build and test screens.

``poll`` is the acknowledgement: what it hands over counts as taken in, so a window that polls less
often is sent fewer frames. Frames that piled up are folded into the newest (the plants of the
last frame that carried them are kept), so a window always draws the latest world.
"""

from __future__ import annotations

import multiprocessing
import traceback
from collections.abc import Callable
from dataclasses import dataclass, replace
from multiprocessing.connection import Connection
from typing import Protocol

from evolution_simulator.session.host import Host, HostRules, run_host
from evolution_simulator.session.messages import (
    Ack,
    CommandRejected,
    Crashed,
    EventBatch,
    HostInfo,
    Outgoing,
    Ready,
    Request,
    Shutdown,
    Stopped,
)
from evolution_simulator.session.protocol import Simulation
from evolution_simulator.session.session import Session, SessionEvent
from evolution_simulator.session.snapshot import Block, Frame
from evolution_simulator.session.specs import FakeSpec
from evolution_simulator.world.views import AnimalDetail


@dataclass(frozen=True, slots=True)
class Inbox:
    """Everything that came back since the last ``poll``."""

    frame: Frame | None = None
    """The newest frame. Its ``plants`` are filled in from an older one if it carried none."""
    detail: AnimalDetail | None = None
    """The newest detail of the selected animal (a dead animal's last one is never lost)."""
    events: tuple[SessionEvent, ...] = ()
    events_dropped: int = 0
    """World events left out so far, in all."""
    rejected: tuple[CommandRejected, ...] = ()
    info: HostInfo | None = None
    ready: bool = False
    """The simulation came up in this batch."""
    stopped: bool = False
    crash: str | None = None
    """The traceback, or a note that the process ended, if the simulation failed."""

    @property
    def empty(self) -> bool:
        return self == Inbox()


class SimClient(Protocol):
    def send(self, request: Request) -> None:
        """Send a command (or ``SetFrameRate``, ``RequestPlants``, ``Shutdown``). Never blocks on
        the simulation; a command it refuses comes back in ``Inbox.rejected``."""
        ...

    def poll(self) -> Inbox:
        """Take what has arrived. Never blocks."""
        ...

    def close(self) -> None:
        """Stop the simulation and release everything. Safe to call twice."""
        ...

    @property
    def crashed(self) -> str | None:
        """Why the simulation failed, once it has."""
        ...


class _Collector:
    """Folds the messages of one poll into an ``Inbox`` and counts what to acknowledge."""

    def __init__(self) -> None:
        self.received = 0
        self.plants: Block | None = None
        self.events_dropped = 0

    def collect(self, messages: list[Outgoing]) -> Inbox:
        frame: Frame | None = None
        detail: AnimalDetail | None = None
        events: list[SessionEvent] = []
        rejected: list[CommandRejected] = []
        info: HostInfo | None = None
        ready = stopped = False
        crash: str | None = None
        for message in messages:
            if isinstance(message, (Frame, Ready, AnimalDetail, EventBatch)):
                self.received += 1
            if isinstance(message, Ready):
                ready = True
                message = message.frame
            if isinstance(message, Frame):
                if message.plants is not None:
                    self.plants = message.plants
                frame = message
            elif isinstance(message, AnimalDetail):
                detail = message
            elif isinstance(message, EventBatch):
                events.extend(message.events)
                self.events_dropped = message.dropped
            elif isinstance(message, CommandRejected):
                rejected.append(message)
            elif isinstance(message, HostInfo):
                info = message
            elif isinstance(message, Stopped):
                stopped = True
            elif isinstance(message, Crashed):
                crash = message.report
        if frame is not None and frame.plants is None and self.plants is not None:
            frame = replace(frame, plants=self.plants)
        return Inbox(
            frame, detail, tuple(events), self.events_dropped, tuple(rejected), info, ready,
            stopped, crash,
        )  # fmt: skip


class InProcessClient:
    """The host driven from ``poll`` in this process. ``simulation`` is the simulation itself or a
    recipe for it."""

    def __init__(
        self,
        simulation: Simulation | Callable[[], Simulation],
        rules: HostRules | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        rules = rules if rules is not None else HostRules()
        sim = simulation if hasattr(simulation, "step") else simulation()  # type: ignore[operator]
        kwargs = {} if clock is None else {"clock": clock}
        session = Session(sim, rules=rules.session, **kwargs)  # type: ignore[arg-type]
        self.host = Host(session, rules, **kwargs)  # type: ignore[arg-type]
        self._collector = _Collector()
        self._pending: list[Outgoing] = [self.host.first_message()]
        self._crash: str | None = None
        self._closed = False

    @property
    def crashed(self) -> str | None:
        return self._crash

    def send(self, request: Request) -> None:
        if not self._closed and self._crash is None:
            self.host.receive(request)

    def poll(self) -> Inbox:
        if self._closed:
            return Inbox()
        messages, self._pending = self._pending, []
        if self._crash is None and not self.host.stopped:
            try:
                messages.extend(self.host.step())
            except Exception:  # noqa: BLE001 - the report is the point
                self._crash = traceback.format_exc()
                messages.append(Crashed(self._crash))
        inbox = self._collector.collect(messages)
        self.host.receive(Ack(self._collector.received))
        return inbox

    def close(self) -> None:
        self._closed = True


def fake_client(rules: HostRules | None = None, **fake: object) -> InProcessClient:
    """An ``InProcessClient`` on a made-up world: ``fake_client(animals=50, seed=3)``."""
    return InProcessClient(FakeSpec(**fake), rules)  # type: ignore[arg-type]


class ProcessClient:
    """The simulation in its own process, reached over a pipe. ``recipe`` is a picklable callable
    that builds the simulation in the new process (``WorldSpec``, ``FakeSpec``)."""

    def __init__(
        self,
        recipe: Callable[[], Simulation],
        rules: HostRules | None = None,
        *,
        join_timeout: float = 5.0,
    ) -> None:
        context = multiprocessing.get_context("spawn")
        self._connection: Connection
        self._connection, child = context.Pipe()
        self._process = context.Process(
            target=run_host, args=(recipe, child, rules), name="simulation", daemon=True
        )
        self._process.start()
        child.close()  # the child has its own end; closing ours lets a dead child end the pipe
        self._join_timeout = join_timeout
        self._collector = _Collector()
        self._crash: str | None = None
        self._ended = False
        self._closed = False

    @property
    def crashed(self) -> str | None:
        return self._crash

    @property
    def process(self) -> multiprocessing.process.BaseProcess:
        return self._process

    def send(self, request: Request) -> None:
        if self._closed or self._ended:
            return
        try:
            self._connection.send(request)
        except (BrokenPipeError, OSError):
            self._note_end()

    def poll(self) -> Inbox:
        if self._closed:
            return Inbox()
        messages: list[Outgoing] = []
        gone = False
        try:
            while self._connection.poll(0):
                messages.append(self._connection.recv())
        except (EOFError, OSError):
            gone = True
        for message in messages:
            if isinstance(message, Crashed):
                self._crash = message.report
            if isinstance(message, (Crashed, Stopped)):
                self._ended = True
        if gone:
            self._note_end()
        inbox = self._collector.collect(messages)
        if self._collector.received and not self._ended:
            self.send(Ack(self._collector.received))
        if self._crash is not None and inbox.crash is None:
            inbox = replace(inbox, crash=self._crash)
        return inbox

    def _note_end(self) -> None:
        """The pipe broke: the process is gone. Say how, unless it stopped cleanly or already said
        what went wrong."""
        if self._ended:
            return
        self._ended = True
        if self._crash is None:
            self._process.join(0.5)
            code = self._process.exitcode
            self._crash = f"The simulation process ended without a word (exit code {code})."

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._connection.send(Shutdown())
        except (BrokenPipeError, OSError):
            pass
        self._process.join(self._join_timeout)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(self._join_timeout)
        self._connection.close()
