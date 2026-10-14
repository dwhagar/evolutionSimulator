"""The simulation host (UX.7): a ``Session`` plus the rules of talking to a viewer.

``Host`` is transport-free: ``receive`` takes what the viewer sent and ``step`` does one pass of the
loop (run the ticks that are due, decide what to send) and returns the messages to send. The same
class runs inside the simulation process (``run_host``, over a ``multiprocessing`` pipe) and
inside the viewer's own process (``InProcessClient``), so the two behave alike and the logic is
tested without any process.

The rules that keep the window alive (``docs/design/ux.md``, "Frame pacing"):

- **The simulation never waits for the window.** Frames, details and event batches are *in flight*
  until the viewer acknowledges them (``Ack``); while ``max_in_flight`` are unacknowledged, no frame
  is built (the session says one was due, the host counts it as dropped) and event batches are
  held. A slow window therefore slows nothing but itself. A dead animal's last detail is always sent.
- **Events are capped.** At most ``max_events_per_second`` world events are kept in a second (the
  rest are counted in ``EventBatch.dropped``), and are sent in batches ``event_interval`` apart.
- **Failures are reported, not swallowed.** An exception in the simulation becomes a ``Crashed``
  message with the traceback, then the host stops. A command the session refuses becomes a
  ``CommandRejected``.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from multiprocessing.connection import Connection

from evolution_simulator.session.commands import CommandError
from evolution_simulator.session.messages import (
    Ack,
    CommandRejected,
    Crashed,
    EventBatch,
    HostInfo,
    Outgoing,
    Ready,
    RequestPlants,
    SetFrameRate,
    Shutdown,
    Stopped,
)
from evolution_simulator.session.protocol import Simulation
from evolution_simulator.session.session import Session, SessionEvent, SessionRules, StatusChanged


@dataclass(frozen=True)
class HostRules:
    max_in_flight: int = 4
    """Messages sent but not yet acknowledged before the host stops sending frames."""
    max_events_per_second: int = 200
    event_interval: float = 0.1
    """Least real time between event batches."""
    max_buffered_events: int = 1000
    """Events held while the viewer is behind; more are dropped."""
    info_interval: float = 1.0
    idle_wait: float = 0.005
    """How long the process loop sleeps (waking at once for a command) when nothing was due."""
    session: SessionRules = field(default_factory=SessionRules)

    def __post_init__(self) -> None:
        if self.max_in_flight < 1 or self.max_events_per_second < 1 or self.max_buffered_events < 1:
            raise ValueError(
                "max_in_flight, max_events_per_second and max_buffered_events must be 1+."
            )
        if self.event_interval < 0.0 or self.info_interval <= 0.0 or self.idle_wait < 0.0:
            raise ValueError("Intervals must not be negative (info_interval must be positive).")


class Host:
    def __init__(
        self,
        session: Session,
        rules: HostRules | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session = session
        self.rules = rules if rules is not None else HostRules()
        self._clock = clock
        self._sent = 0
        self._acked = 0
        self._frames_sent = 0
        self._frames_dropped = 0
        self._events_dropped = 0
        self._details_dropped = 0
        self._last_drop_at = float("-inf")
        self._events: list[SessionEvent] = []
        self._window_start = clock()
        self._window_count = 0
        self._last_batch_at = clock()
        self._last_info_at = clock()
        self._rejected: list[CommandRejected] = []
        self._stopping = False
        self.stopped = False
        self.busy = False
        """The last ``step`` ran ticks or sent something, so the loop should not sleep."""
        session.subscribe(self._on_event)

    # -------------------------------------------------------------------------
    # From the viewer
    # -------------------------------------------------------------------------

    def receive(self, message: object) -> None:
        if isinstance(message, Ack):
            self._acked = max(self._acked, min(message.received, self._sent))
        elif isinstance(message, SetFrameRate):
            try:
                self.session.set_frame_rate(message.hz)
            except CommandError as error:
                self._rejected.append(CommandRejected(message, str(error)))
        elif isinstance(message, RequestPlants):
            self.session.request_plants()
        elif isinstance(message, Shutdown):
            self._stopping = True
        else:
            try:
                self.session.handle(message)  # type: ignore[arg-type]
            except CommandError as error:
                self._rejected.append(CommandRejected(message, str(error)))

    # -------------------------------------------------------------------------
    # To the viewer
    # -------------------------------------------------------------------------

    @property
    def in_flight(self) -> int:
        return self._sent - self._acked

    def _can_send(self) -> bool:
        return self.in_flight < self.rules.max_in_flight

    def _on_event(self, event: SessionEvent) -> None:
        if not isinstance(event, StatusChanged):
            now = self._clock()
            if now - self._window_start >= 1.0:
                self._window_start, self._window_count = now, 0
            self._window_count += 1
            if self._window_count > self.rules.max_events_per_second:
                self._events_dropped += 1
                return
        if len(self._events) >= self.rules.max_buffered_events:
            self._events_dropped += 1
            return
        self._events.append(event)

    def first_message(self) -> Ready:
        """The message that tells the viewer the simulation is up, with a first full frame."""
        self._sent += 1
        return Ready(self.session.frame(include_plants=True))

    def step(self) -> list[Outgoing]:
        """One pass of the loop. Returns what to send, in order."""
        out: list[Outgoing] = []
        if self._stopping:
            self.stopped = True
            self.busy = False
            return [Stopped()]
        allow = self._can_send()
        update = self.session.update(frames=allow)
        now = self._clock()
        if self._rejected:
            out.extend(self._rejected)
            self._rejected.clear()
        if update.frame is not None:
            self._frames_sent += 1
            self._sent += 1
            out.append(update.frame)
        elif update.frame_skipped and now - self._last_drop_at >= self.session.rules.frame_interval:
            self._last_drop_at = now  # one dropped frame per frame interval of being held back
            self._frames_dropped += 1
        detail = update.detail
        if detail is not None:
            if allow or not detail.alive:
                self._sent += 1
                out.append(detail)
            else:
                self._details_dropped += 1
        if self._events and allow and now - self._last_batch_at >= self.rules.event_interval:
            self._sent += 1
            self._last_batch_at = now
            out.append(EventBatch(tuple(self._events), self._events_dropped))
            self._events.clear()
        if now - self._last_info_at >= self.rules.info_interval:
            self._last_info_at = now
            out.append(
                HostInfo(
                    self._frames_sent,
                    self._frames_dropped,
                    self._events_dropped,
                    self._details_dropped,
                )
            )
        self.busy = update.ticks > 0 or bool(out)
        return out


def run_host(
    recipe: Callable[[], Simulation],
    connection: Connection,
    rules: HostRules | None = None,
) -> None:
    """The simulation process: build the simulation from ``recipe``, then loop until told to stop.

    The target of the spawned process (``ProcessClient``). Anything that goes wrong inside is sent
    to the viewer as a ``Crashed`` message and ends the process with exit code 1; a viewer that has
    gone away (the pipe closes) ends it quietly.
    """
    rules = rules if rules is not None else HostRules()
    try:
        try:
            host = Host(Session(recipe(), rules=rules.session), rules)
            connection.send(host.first_message())
            while not host.stopped:
                while connection.poll(0):
                    host.receive(connection.recv())
                for message in host.step():
                    connection.send(message)
                if not host.busy:
                    connection.poll(rules.idle_wait)
        except (EOFError, BrokenPipeError, ConnectionResetError):
            return  # the viewer is gone
        except Exception:  # noqa: BLE001 - the report is the point
            connection.send(Crashed(traceback.format_exc()))
            raise SystemExit(1) from None
    finally:
        connection.close()
