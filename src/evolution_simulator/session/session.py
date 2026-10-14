"""The simulation session (UX.6): one simulation, run at the speed asked for, driven by commands.

``Session`` wraps a ``Simulation`` (a ``World``, or ``FakeSimulation``) and has no window code and
no threads of its own. Whoever hosts it (the simulation process of UX.7, the headless run of UX.22,
a test) calls ``handle`` with the commands that arrive and ``update`` in a loop. ``update`` works
out how many ticks real time owes, runs them, and says what to send: a ``Frame`` when it is time for
one and something changed, and the selected animal's ``AnimalDetail``. Frames and details are
immutable values, so the host can queue, drop or pickle them.

Pacing follows the design note (``docs/design/ux.md``): the session never waits for the viewer, the
ticks owed beyond what the computer can run in ``work_budget`` seconds are dropped rather than
queued (the speed achieved falls below the speed asked, and the status says so), and a frame goes
out at most ``1 / frame_interval`` times a second, sooner only when nothing has changed since the
last. The plants, which change slowly, go out with a frame only every ``plant_interval`` seconds,
and at once when the session settles (paused, steps done) so a paused world is shown exactly.

Nothing but the clock passed in is read for timing, so a test that passes a fake clock is exact.
Running ticks does not depend on timing at all: the same commands give the same world.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace

from evolution_simulator.config import TimeRules
from evolution_simulator.deaths import DeathCause
from evolution_simulator.session.commands import (
    MAX_SPEED,
    Command,
    CommandError,
    Deselect,
    NewRun,
    Pause,
    Play,
    Select,
    SetSpeed,
    Step,
)
from evolution_simulator.session.protocol import Simulation
from evolution_simulator.session.snapshot import (
    FRAME_FORMAT,
    Frame,
    Status,
    pack_animals,
    pack_corpses,
    pack_plants,
)
from evolution_simulator.world.events import Died, WorldEvent
from evolution_simulator.world.timescale import SPEED_PRESETS, Pacer, TimeScale
from evolution_simulator.world.views import AnimalDetail
from evolution_simulator.world.world import StepReport, World


def _preset_for(speed: float) -> str | None:
    for name, value in SPEED_PRESETS.items():
        if math.isclose(speed, value, rel_tol=1e-9):
            return name
    return None


@dataclass(frozen=True, slots=True)
class StatusChanged:
    """Something in the ``Status`` changed (play, pause, speed, selection). Subscribers get it
    next to the world's own events."""

    status: Status


@dataclass(frozen=True, slots=True)
class RunStarted:
    """A ``NewRun`` replaced the world (UX.17). Everything a viewer holds about the old run (the
    selected animal, the plants last sent, the tick counter) is out of date; the next frame, which
    carries the plants, shows the new world."""

    label: str
    animals: int
    plants: int


SessionEvent = WorldEvent | StatusChanged | RunStarted


def build_world(command: NewRun) -> World:
    """The real world a ``NewRun`` asks for."""
    try:
        world = World(command.config)
        world.populate(animals=command.animals, plants=command.plants, seeded=command.seeded)
    except ValueError as error:
        raise CommandError(f"The world could not be built: {error}") from error
    return world


@dataclass(frozen=True)
class SessionRules:
    frame_interval: float = 1.0 / 30.0
    """Least real time between frames."""
    detail_interval: float = 0.1
    """Least real time between details of the selected animal."""
    plant_interval: float = 0.5
    """Least real time between frames that carry the plants."""
    work_budget: float = 0.03
    """Most real time one ``update`` spends running ticks, so commands are heard in time."""
    max_ticks_per_update: int = 100_000
    max_elapsed: float = 0.5
    """Real time longer than this since the last ``update`` (the host stalled) is cut to it."""
    speed_window: float = 1.0
    """Real time the achieved speed is measured over."""

    def __post_init__(self) -> None:
        for name in ("frame_interval", "detail_interval", "plant_interval", "work_budget"):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be zero or more.")
        if self.max_ticks_per_update < 1 or self.max_elapsed <= 0.0 or self.speed_window <= 0.0:
            raise ValueError("max_ticks_per_update, max_elapsed and speed_window must be positive.")


@dataclass(frozen=True, slots=True)
class Update:
    """What one ``update`` did and what it has to send."""

    ticks: int = 0
    """Ticks run."""
    dropped: int = 0
    """Ticks owed by the speed asked for that were skipped."""
    report: StepReport | None = None
    """The summed report of the ticks run."""
    frame: Frame | None = None
    detail: AnimalDetail | None = None
    """The selected animal now; with ``alive`` false once, when it has just died."""
    frame_skipped: bool = False
    """A frame was due but ``update(frames=False)`` held it back; it is built by the next update
    that allows frames."""


class Session:
    def __init__(
        self,
        simulation: Simulation,
        *,
        rules: SessionRules | None = None,
        clock: Callable[[], float] = time.monotonic,
        new_run: Callable[[NewRun], Simulation] = build_world,
    ) -> None:
        """``new_run`` builds the simulation a ``NewRun`` command asks for; a test passes its own."""
        self.simulation = simulation
        self.rules = rules if rules is not None else SessionRules()
        self._clock = clock
        self._new_run = new_run
        self._subscribers: list[Callable[[SessionEvent], None]] = []
        self._listening = False
        self._seq = 0
        self._samples: deque[tuple[float, float]] = deque()
        self._last_update = clock()
        self._status_sent: Status | None = None
        self._restart()

    def _restart(self) -> None:
        """Everything that belongs to one run: paused at the simulation's own tick length and
        speed, nothing selected, nothing sent yet. The frame counter and subscribers carry on."""
        simulation = self.simulation
        self._tick_seconds = simulation.time_scale.seconds_per_tick
        self._running = False
        self._steps_left = 0
        self._speed: float | None = simulation.time_scale.speed
        self._pacer = Pacer(TimeScale(self._tick_seconds, simulation.time_scale.speed))
        self._selected: int | None = None
        self._last_detail: AnimalDetail | None = None
        self._death_cause: DeathCause | None = None
        self._ticks_dropped = 0
        self._last_drop_at: float | None = None
        self._samples.clear()
        self._last_frame_at: float | None = None
        self._last_plants_at: float | None = None
        self._plants_tick: int | None = None
        self._last_detail_at: float | None = None
        self._detail_tick: int | None = None
        self._dirty = True

    # -------------------------------------------------------------------------
    # Status and events
    # -------------------------------------------------------------------------

    @property
    def status(self) -> Status:
        speed = self._speed
        preset = MAX_SPEED if speed is None else _preset_for(speed)
        now = self._clock()
        behind = (
            self._last_drop_at is not None and now - self._last_drop_at <= self.rules.speed_window
        )
        return Status(
            running=self._running,
            steps_left=self._steps_left,
            speed_asked=speed,
            speed_preset=preset,
            speed_achieved=self._achieved(),
            behind=behind,
            ticks_dropped=self._ticks_dropped,
            selected=self._selected,
        )

    def subscribe(self, callback: Callable[[SessionEvent], None]) -> Callable[[], None]:
        """Be called, as they happen, with every world event (births, deaths, matings) and every
        ``StatusChanged``. Returns the function that unsubscribes. The world builds events only
        while someone listens, so a session with no subscriber (and no selection) pays nothing."""
        self._subscribers.append(callback)
        self._sync_listener()

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
            self._sync_listener()

        return unsubscribe

    def _sync_listener(self) -> None:
        wanted = bool(self._subscribers) or self._selected is not None
        if wanted and not self._listening:
            self.simulation.add_event_listener(self._on_event)
        elif not wanted and self._listening:
            self.simulation.remove_event_listener(self._on_event)
        self._listening = wanted

    def _on_event(self, event: WorldEvent) -> None:
        if isinstance(event, Died) and event.kind == "animal" and event.id == self._selected:
            self._death_cause = event.cause
        self._publish(event)

    def _publish(self, event: SessionEvent) -> None:
        for callback in list(self._subscribers):
            callback(event)

    def _announce_status(self) -> None:
        status = self.status
        comparable = replace(status, speed_achieved=None, behind=False)
        previous = self._status_sent
        if previous is None or comparable != replace(previous, speed_achieved=None, behind=False):
            self._status_sent = status
            self._dirty = True
            self._publish(StatusChanged(status))

    # -------------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------------

    def handle(self, command: Command) -> None:
        """Carry out one command. Raises ``CommandError`` if it cannot be done, changing nothing."""
        if isinstance(command, Play):
            self._running = True
            self._steps_left = 0
            self._samples.clear()
        elif isinstance(command, Pause):
            self._running = False
            self._steps_left = 0
        elif isinstance(command, Step):
            self._running = False
            self._steps_left += command.ticks
        elif isinstance(command, SetSpeed):
            self._set_speed(command.speed)
        elif isinstance(command, Select):
            self._select(command.animal_id)
        elif isinstance(command, Deselect):
            self._deselect()
        elif isinstance(command, NewRun):
            self._start_run(command)
        else:
            raise CommandError(f"Unknown command {command!r}.")
        self._dirty = True
        self._announce_status()

    def _start_run(self, command: NewRun) -> None:
        simulation = self._new_run(command)  # built first, so a failure changes nothing
        old = self.simulation
        if self._listening:
            old.remove_event_listener(self._on_event)
            self._listening = False
        if self._selected is not None:
            old.trace_brain(None)
        self.simulation = simulation
        speed = self._speed
        self._restart()
        if command.config.traits.time.speed == TimeRules().speed:
            self._speed = speed  # the viewer's choice, not a setting of the world
            if speed is not None:
                self._pacer = Pacer(TimeScale(self._tick_seconds, speed))
        self._sync_listener()
        self._publish(RunStarted(command.label, command.animals, command.plants))

    def _set_speed(self, speed: float | str) -> None:
        if speed == MAX_SPEED:
            self._speed = None
            return
        if isinstance(speed, str):
            if speed not in SPEED_PRESETS:
                names = ", ".join([*SPEED_PRESETS, MAX_SPEED])
                raise CommandError(f"Unknown speed {speed!r}; choose a number or one of: {names}.")
            speed = SPEED_PRESETS[speed]
        self._speed = float(speed)
        self._pacer = Pacer(TimeScale(self._tick_seconds, self._speed))
        self._samples.clear()

    def _select(self, animal_id: int) -> None:
        if self.simulation.animal_detail(animal_id) is None:
            raise CommandError(f"There is no living animal {animal_id} to select.")
        self.simulation.trace_brain(animal_id)
        self._selected = animal_id
        self._last_detail = None
        self._death_cause = None
        self._last_detail_at = None
        self._detail_tick = None
        self._sync_listener()

    def _deselect(self) -> None:
        if self._selected is not None:
            self.simulation.trace_brain(None)
        self._selected = None
        self._last_detail = None
        self._death_cause = None
        self._sync_listener()

    # -------------------------------------------------------------------------
    # Running
    # -------------------------------------------------------------------------

    def update(self, frames: bool = True) -> Update:
        """Run the ticks that are due and say what to send. Call it often (every few milliseconds
        to every frame); it returns at once when nothing is due. With ``frames=False`` no frame is
        built (the host does this while the viewer is behind): the update says so in
        ``frame_skipped`` and the frame comes with the next one that allows it."""
        now = self._clock()
        elapsed = min(max(0.0, now - self._last_update), self.rules.max_elapsed)
        self._last_update = now
        ticks, dropped, report = self._run(now, elapsed)
        if ticks:
            self._dirty = True

        detail = self._detail_due(now, ticks)
        skipped = False
        frame = None
        if self._frame_is_due(now):
            if frames:
                frame = self.frame(now=now)
            else:
                skipped = True
        return Update(ticks, dropped, report, frame, detail, skipped)

    def _run(self, now: float, elapsed: float) -> tuple[int, int, StepReport | None]:
        rules = self.rules
        owed = 0
        if self._steps_left > 0:
            owed = self._steps_left
        elif self._running:
            if self._speed is None:
                owed = rules.max_ticks_per_update
            else:
                owed = self._pacer.advance(elapsed, rules.max_ticks_per_update)
        sim = self.simulation
        start = self._clock()
        start_seconds = sim.simulated_seconds
        if owed <= 0:
            if self._running:
                self._measure(start, 0.0, start)
            return 0, 0, None
        report: StepReport | None = None
        ran = 0
        while ran < owed:
            step = sim.step()
            report = step if report is None else report + step
            ran += 1
            if self._clock() - start >= rules.work_budget:
                break
        dropped = 0
        if self._steps_left > 0:
            self._steps_left = max(0, self._steps_left - ran)
            self._announce_status()
        elif self._speed is not None:
            dropped = owed - ran
            if dropped:
                self._ticks_dropped += dropped
                self._last_drop_at = now
        if self._running:
            self._measure(self._clock(), sim.simulated_seconds - start_seconds, start)
        return ran, dropped, report

    def _measure(self, now: float, simulated: float, started: float) -> None:
        """Remember how much simulated time passed and when, for the achieved speed."""
        samples = self._samples
        if not samples:
            samples.append((started, 0.0))
        elif simulated <= 0.0 and now - samples[-1][0] < 0.05:
            return
        total = samples[-1][1] + simulated
        samples.append((now, total))
        while len(samples) > 2 and now - samples[1][0] > self.rules.speed_window:
            samples.popleft()

    def _achieved(self) -> float | None:
        if not self._running or len(self._samples) < 2:
            return None
        (t0, s0), (t1, s1) = self._samples[0], self._samples[-1]
        return (s1 - s0) / (t1 - t0) if t1 > t0 else None

    # -------------------------------------------------------------------------
    # What to send
    # -------------------------------------------------------------------------

    def _detail_due(self, now: float, ticks: int) -> AnimalDetail | None:
        selected = self._selected
        if selected is None:
            return None
        last_at = self._last_detail_at
        due = (
            last_at is None
            or now - last_at >= self.rules.detail_interval
            or (self._settled() and self._detail_tick != self.simulation.tick)
        )
        if not (due or ticks):
            return None
        detail = self.simulation.animal_detail(selected)
        if detail is None:
            return self._selection_ended()
        self._last_detail = detail
        if not due:
            return None
        self._last_detail_at = now
        self._detail_tick = detail.tick
        return detail

    def _selection_ended(self) -> AnimalDetail | None:
        """The selected animal is gone: send what was last known, marked dead, and deselect."""
        last = self._last_detail
        cause = self._death_cause
        self._deselect()
        self._announce_status()
        if last is None:
            return None
        return replace(last, alive=False, death_cause=cause, tick=self.simulation.tick)

    def _settled(self) -> bool:
        return not self._running and self._steps_left == 0

    def _frame_is_due(self, now: float) -> bool:
        last = self._last_frame_at
        if self.rules.frame_interval == float("inf"):
            return False
        if last is None:
            return True
        if not self._dirty:
            return False
        return now - last >= self.rules.frame_interval

    def set_frame_rate(self, hz: float) -> None:
        """Send at most ``hz`` frames a second (0 sends none: a minimised window costs nothing)."""
        if not hz >= 0.0 or hz == float("inf"):
            raise CommandError(f"A frame rate must be zero or more, got {hz!r}.")
        interval = float("inf") if hz == 0.0 else 1.0 / hz
        self.rules = replace(self.rules, frame_interval=interval)

    def request_plants(self) -> None:
        """Put the plants in the next frame (a viewer that has just opened or lost them)."""
        self._last_plants_at = None
        self._dirty = True

    def frame(self, *, include_plants: bool | None = None, now: float | None = None) -> Frame:
        """Build a frame of the world as it stands. ``include_plants`` forces the plants in or out;
        left out (``None``) they are in when they have not gone out for ``plant_interval``, or when
        the session has settled and the plants shown are not those of this tick."""
        sim = self.simulation
        now = self._clock() if now is None else now
        if include_plants is None:
            include_plants = (
                self._last_plants_at is None
                or now - self._last_plants_at >= self.rules.plant_interval
                or (self._settled() and self._plants_tick != sim.tick)
            )
        plants_block = None
        animals = sim.animal_views()
        corpses = sim.corpse_views()
        if include_plants:
            plants_block = pack_plants(sim.plant_views())
            self._last_plants_at = now
            self._plants_tick = sim.tick
        self._seq += 1
        self._last_frame_at = now
        self._dirty = False
        status = self.status
        self._status_sent = status
        return Frame(
            format=FRAME_FORMAT,
            seq=self._seq,
            tick=sim.tick,
            simulated_seconds=sim.simulated_seconds,
            elapsed=sim.elapsed,
            day=sim.day,
            daylight=sim.daylight,
            is_night=sim.is_night,
            world_size=sim.bounds.size,
            status=status,
            animal_count=len(animals),
            plant_count=sim.plant_count,
            corpse_count=len(corpses),
            animals=pack_animals(animals),
            corpses=pack_corpses(corpses),
            plants=plants_block,
        )

    def detail(self) -> AnimalDetail | None:
        """The selected animal now, or ``None`` if none is selected or it has died."""
        return None if self._selected is None else self.simulation.animal_detail(self._selected)
