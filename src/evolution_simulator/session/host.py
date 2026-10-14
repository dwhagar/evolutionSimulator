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
- **History and the run (UX.31).** The host keeps the statistics ``Recorder`` of its world and tells
  the viewer about it with ``HistoryBatch`` messages: the whole history first (and again on
  ``RequestHistory``, or when the viewer fell too far behind to be sent every sample), then the new
  single-day samples at most every ``history_interval``. They wait, never get lost, while the viewer
  is behind. With a ``Run`` (a ``Prepared`` recipe) the host also autosaves checkpoints into the run
  folder, saves on ``SaveNow`` and once more when it shuts down, and says so in ``RunNotice``.
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

from evolution_simulator.history import Recorder, Sample
from evolution_simulator.runs import Autosaver, Run
from evolution_simulator.session.commands import CommandError
from evolution_simulator.session.messages import (
    Ack,
    CommandRejected,
    Crashed,
    EventBatch,
    HistoryBatch,
    HostInfo,
    Outgoing,
    Ready,
    RequestHistory,
    RequestPlants,
    RunNotice,
    SaveNow,
    SetFrameRate,
    Shutdown,
    Stopped,
)
from evolution_simulator.session.protocol import Simulation
from evolution_simulator.session.session import Session, SessionEvent, SessionRules, StatusChanged
from evolution_simulator.session.specs import Prepared


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
    record: bool = True
    """Keep a statistics ``Recorder`` for the world (one is used as given if the recipe made one)
    and send its history to the viewer."""
    history_interval: float = 0.25
    """Least real time between history batches."""
    max_pending_samples: int = 400
    """New samples held for a viewer that is behind; past this the next batch is a full history."""
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
        if self.history_interval < 0.0 or self.max_pending_samples < 1:
            raise ValueError("history_interval must not be negative; max_pending_samples 1+.")


class Host:
    def __init__(
        self,
        session: Session,
        rules: HostRules | None = None,
        clock: Callable[[], float] = time.monotonic,
        recorder: Recorder | None = None,
        run: Run | None = None,
        resumed_from: str | None = None,
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
        # History and the run (UX.31).
        if recorder is None and self.rules.record:
            recorder = Recorder(session.simulation)  # type: ignore[arg-type]
        self.recorder = recorder
        self.run = run
        self._resumed_from = resumed_from
        self._pending_samples: list[Sample] = []
        self._need_full = recorder is not None
        self._last_history_at = float("-inf")
        if recorder is not None:
            recorder.add_sample_listener(self._on_sample)
        self._autosaver: Autosaver | None = None
        if run is not None:
            self._autosaver = run.autosave(session.simulation, recorder)  # type: ignore[arg-type]
        self._manual_saves = 0
        self._noticed_saves: int | None = None

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
        elif isinstance(message, RequestHistory):
            if self.recorder is None:
                self._rejected.append(CommandRejected(message, "No history is being recorded."))
            else:
                self._need_full = True
        elif isinstance(message, SaveNow):
            if self.run is None:
                self._rejected.append(
                    CommandRejected(message, "This simulation is not saved into a run.")
                )
            else:
                self.run.checkpoint(self.session.simulation, self.recorder)  # type: ignore[arg-type]
                self._manual_saves += 1
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

    def _on_sample(self, sample: Sample) -> None:
        self._pending_samples.append(sample)
        if len(self._pending_samples) > self.rules.max_pending_samples:
            self._pending_samples.clear()
            self._need_full = True  # too far behind to send them one by one

    def _saves(self) -> int:
        return self._manual_saves + (self._autosaver.written if self._autosaver else 0)

    def _history_batch(self) -> HistoryBatch:
        assert self.recorder is not None
        if self._need_full:
            self._need_full = False
            self._pending_samples.clear()
            return HistoryBatch(self.recorder.rules, (), self.recorder.history())
        samples = tuple(self._pending_samples)
        self._pending_samples.clear()
        return HistoryBatch(self.recorder.rules, samples)

    def _run_notice(self) -> RunNotice:
        assert self.run is not None
        checkpoints = self.run.checkpoints()
        return RunNotice(
            self.run.id,
            self.run.name,
            str(self.run.path),
            len(checkpoints),
            checkpoints[-1].name if checkpoints else "",
            self._saves(),
            self._resumed_from,
        )

    def shutdown(self) -> None:
        """Leave the run with a last checkpoint and stop listening. Safe to call twice."""
        autosaver, self._autosaver = self._autosaver, None
        if autosaver is not None:
            autosaver.finish()
        if self.recorder is not None:
            self.recorder.remove_sample_listener(self._on_sample)

    def first_message(self) -> Ready:
        """The message that tells the viewer the simulation is up, with a first full frame."""
        self._sent += 1
        return Ready(self.session.frame(include_plants=True))

    def step(self) -> list[Outgoing]:
        """One pass of the loop. Returns what to send, in order."""
        out: list[Outgoing] = []
        if self._stopping:
            self.shutdown()
            self.stopped = True
            self.busy = False
            return [Stopped()]
        allow = self._can_send()
        update = self.session.update(frames=allow)
        if self.recorder is not None:
            self.recorder.observe()  # a simulation with no step listener is sampled here
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
        if (
            self.recorder is not None
            and (self._need_full or self._pending_samples)
            and now - self._last_history_at >= self.rules.history_interval
            and self._can_send()
        ):
            self._sent += 1
            self._last_history_at = now
            out.append(self._history_batch())
        if self.run is not None and self._noticed_saves != self._saves() and self._can_send():
            self._sent += 1
            self._noticed_saves = self._saves()
            out.append(self._run_notice())
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


def make_host(
    made: Simulation | Prepared,
    rules: HostRules | None = None,
    clock: Callable[[], float] | None = None,
) -> Host:
    """A ``Host`` for what a recipe made: a bare simulation, or a ``Prepared`` one with its recorder
    and run."""
    rules = rules if rules is not None else HostRules()
    kwargs = {} if clock is None else {"clock": clock}
    prepared = made if isinstance(made, Prepared) else Prepared(made)
    session = Session(prepared.simulation, rules=rules.session, **kwargs)  # type: ignore[arg-type]
    return Host(
        session,
        rules,
        recorder=prepared.recorder,
        run=prepared.run,
        resumed_from=prepared.resumed_from,
        **kwargs,  # type: ignore[arg-type]
    )


def run_host(
    recipe: Callable[[], Simulation | Prepared],
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
            host = make_host(recipe(), rules)
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
