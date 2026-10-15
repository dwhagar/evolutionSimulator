"""Saved runs inside the viewer (UX.18): the one object the run screens talk to.

``RunManager`` ties the run store (``evolution_simulator.runs``, UX.10) to the running window. It
saves the world that is on screen (``save_now`` starts a run on the first call and checkpoints it
after that, and autosaves from then on), brings a saved run back (``resume`` swaps a new session in
behind the controller), and answers what the run list and the history view need (``list_runs``,
``history``, ``space_warning``, ``export_csv``, ``delete``). Screens never touch the store.

Saving and resuming need the world itself. On a ``LocalBackend`` the session is in this process
(``local_world``) and the manager checkpoints it and autosaves it. On a ``ProcessBackend`` (UX.33) the
world is in the simulation process, which keeps the run itself (UX.31): the manager asks it to start a
run or to save (``hosted``), reads the run from the store, and starts a new simulation process on
``ResumeSpec`` to resume. Listing, history, deleting and exporting need no world and work with any
backend.

One manager belongs to a controller: ``RunManager.install(controller, store)`` before the window is
built (the app does this for ``--runs-folder``), and ``RunManager.for_controller(controller)`` from a
screen, which makes one on the default folder when none was installed.
"""

from __future__ import annotations

import csv
import logging
import os
import weakref
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from evolution_simulator.history import HistorySamples, Recorder
from evolution_simulator.runs import (
    Autosaver,
    CheckpointInfo,
    Compacted,
    Run,
    RunError,
    RunStore,
    RunSummary,
)
from evolution_simulator.session import ResumeSpec, Session
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.process_backend import ProcessBackend
from evolution_simulator.world import World, WorldConfig

log = logging.getLogger(__name__)

REFRESH_MS = 3000
"""How often the label is brought up to date ("saved 2 min ago") and an autosave is noticed."""

_managers: weakref.WeakKeyDictionary[ViewerController, RunManager] = weakref.WeakKeyDictionary()


def format_ago(seconds: float) -> str:
    """ "just now", "5 min ago", "3 h ago", "2 days ago" for the label."""
    if seconds < 60.0:
        return "just now"
    if seconds < 3600.0:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400.0:
        return f"{int(seconds // 3600)} h ago"
    days = int(seconds // 86400)
    return f"{days} day{'s' if days != 1 else ''} ago"


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1024.0:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def folder_size(path: Path) -> int:
    """Bytes in a folder and everything under it (files that vanish while counting are skipped)."""
    total = 0
    for folder, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(folder) / name).stat().st_size
            except OSError:
                continue
    return total


def parse_utc(text: str) -> float | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


class RunManager(QObject):
    changed = Signal()
    """The list of runs, or which run is current, or what the current run has saved, changed."""
    label_changed = Signal(str)
    """The text for the status bar and title: the run's name, seed and when it was last saved."""
    message = Signal(str)
    """Something to tell the user once (saved, resumed, a warning)."""

    def __init__(
        self,
        controller: ViewerController,
        store: RunStore | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.store = store if store is not None else RunStore()
        self.current_run: Run | None = None
        self.recorder: Recorder | None = None
        self._own_recorder = False
        """True when this manager made the recorder (the backend had none) and so closes it."""
        self.autosaver: Autosaver | None = None
        self._label = ""
        self._seen_written = 0
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        _managers[controller] = self

    # ---- finding the manager ----------------------------------------------------------------

    @classmethod
    def install(cls, controller: ViewerController, store: RunStore | None = None) -> RunManager:
        """Make the manager for this controller, on ``store`` (the default folder when ``None``),
        replacing any made before."""
        return cls(controller, store, parent=controller)

    @classmethod
    def for_controller(cls, controller: ViewerController) -> RunManager:
        manager = _managers.get(controller)
        return manager if manager is not None else cls.install(controller)

    # ---- the world on screen -----------------------------------------------------------------

    def local_world(self) -> World | None:
        """The real world the backend runs in this process, or ``None`` (a made-up world, or one
        in another process: nothing here can save those)."""
        session = getattr(self.controller.backend, "session", None)
        world = getattr(session, "simulation", None)
        return world if isinstance(world, World) else None

    def hosted(self) -> ProcessBackend | None:
        """The backend, when it runs a real world in its own process (which keeps the run)."""
        backend = self.controller.backend
        if isinstance(backend, ProcessBackend) and backend.saveable:
            return backend
        return None

    @property
    def can_save(self) -> bool:
        hosted = self.hosted()
        if hosted is not None:
            return hosted.crashed is None
        return self.local_world() is not None

    @property
    def unsaved_progress(self) -> bool:
        """The world on screen has ticks that no saved run holds."""
        if self.hosted() is not None:
            frame = self.controller.frame
            tick = 0 if frame is None else frame.tick
        else:
            world = self.local_world()
            if world is None:
                return False
            tick = world.tick
        if self.current_run is None:
            return tick > 0
        return tick > self.current_run.summary.tick

    @property
    def unsaved_on_close(self) -> bool:
        """Closing the window would lose ticks: the world was never saved, or (a world in this
        process) has gone on since its last checkpoint. A world in its own process writes a last
        checkpoint of its run when the window closes, so only one never saved counts there."""
        if not self.can_save or not self.unsaved_progress:
            return False
        return self.hosted() is None or self.current_run is None

    # ---- saving ------------------------------------------------------------------------------

    def save_now(self, name: str | None = None) -> CheckpointInfo:
        """Checkpoint the world on screen. The first save starts a run (named ``name``, else after
        its seed) with a recorder and autosave; later saves add a checkpoint to the same run."""
        hosted = self.hosted()
        if hosted is not None:
            return self._save_hosted(hosted, name)
        world = self.local_world()
        if world is None:
            raise RunError(
                "This simulation is not a real world in this program, so it cannot be saved."
            )
        if self.current_run is None:
            recorder = getattr(self.controller.backend, "recorder", None)
            made = recorder is None
            if recorder is None:
                recorder = Recorder(world)
            try:
                run = self.store.create(world, name=name, recorder=recorder)
            except Exception:
                if made:
                    recorder.close()
                raise
            self.recorder = recorder
            self._own_recorder = made
            self._adopt(run, world)
            info = run.checkpoints()[-1]
        else:
            info = self.current_run.checkpoint(world, self.recorder)
            self._seen_written = self.autosaver.written if self.autosaver else 0
        self._after_change()
        warning = self.store.space_warning()
        self.message.emit(f"Saved {self.current_run.name}" + (f". {warning}" if warning else ""))  # type: ignore[union-attr]
        return info

    def adopt(self, run: Run) -> None:
        """Make ``run`` the current run without touching the world: the simulation behind the
        controller was started on it (a launch that opened the newest saved run)."""
        self._release()
        self.current_run = run
        self._seen_written = 0
        self._timer.start()
        self._after_change()

    def _save_hosted(self, hosted: ProcessBackend, name: str | None) -> CheckpointInfo:
        """Ask the simulation process to start a run or checkpoint it, and wait for its answer. The
        process autosaves from then on."""
        notice = hosted.save_now(self.store.root, name)
        run = self.store.open(notice.run_id)
        self._release()
        self.current_run = run
        self._seen_written = notice.saved
        self._timer.start()
        info = run.checkpoints()[-1]
        self._after_change()
        warning = self.store.space_warning()
        self.message.emit(f"Saved {run.name}" + (f". {warning}" if warning else ""))
        return info

    def _adopt(self, run: Run, world: World) -> None:
        """Make ``run`` the current run and autosave it as the world goes on."""
        self._release()
        self.current_run = run
        if self.recorder is None:
            self.recorder = Recorder(world)
        self.autosaver = run.autosave(world, self.recorder)
        self._seen_written = 0
        self._timer.start()

    def _release(self) -> None:
        if self.autosaver is not None:
            self.autosaver.close()
        self.autosaver = None
        self._timer.stop()

    def _stop_current(self, final_checkpoint: bool) -> None:
        """Stop autosaving the current run, with a last checkpoint when asked; it is no longer
        current and its recorder stops listening."""
        if self.autosaver is not None and final_checkpoint:
            try:
                self.autosaver.finish()
            except Exception:  # leaving a run must not fail because the disk did
                log.exception("The last checkpoint of %s could not be written", self.current_run)
        self._release()
        if self.recorder is not None and self._own_recorder:
            self.recorder.close()
        self.recorder = None
        self._own_recorder = False
        self.current_run = None

    def detach(self) -> None:
        """Let the current run go (with a last checkpoint) while the world on screen carries on
        unsaved; the next Save now starts a new run. For a new world replacing this one."""
        self._stop_current(final_checkpoint=True)
        self._after_change()

    # ---- resuming ----------------------------------------------------------------------------

    def resume(self, run_id: str, checkpoint: str | None = None) -> Run:
        """Bring a saved run back (its newest checkpoint, or the named one) and show it, paused.
        A different run on screen is saved first (a last checkpoint); resuming the run that is
        already on screen goes back to its saved state, dropping what came after (the caller asks
        first, and also about a world that was never saved: ``unsaved_progress``). Raises ``RunError`` and changes nothing if the run
        cannot be restored."""
        run = self.store.open(run_id)
        resumed = run.resume(checkpoint)  # raises before anything on screen is touched
        previous = self.controller.backend
        same_run = self.current_run is not None and self.current_run.id == run_id
        if isinstance(previous, ProcessBackend):
            return self._resume_hosted(previous, run, resumed.checkpoint.name, checkpoint, same_run)
        self._stop_current(final_checkpoint=self.current_run is not None and not same_run)
        backend = LocalBackend(
            Session(resumed.world),
            record=resumed.recorder if resumed.recorder is not None else True,
        )
        self.recorder = backend.recorder
        self.controller.replace_backend(backend)
        close = getattr(previous, "close", None)
        if close is not None:
            close()
        self._adopt(run, resumed.world)
        self._after_change()
        self.message.emit(f"Resumed {run.name} from {resumed.checkpoint.name}")
        return run

    def _resume_hosted(
        self,
        previous: ProcessBackend,
        run: Run,
        checkpoint_name: str,
        checkpoint: str | None,
        same_run: bool,
    ) -> Run:
        """Resume in a new simulation process. The old one is stopped first (with a last checkpoint
        of its run, unless it is the run being gone back into) so two never write one folder."""
        self._release()
        self.current_run = None
        previous.close(save=not same_run)
        backend = ProcessBackend(ResumeSpec(str(self.store.root), run.id, checkpoint))
        self.recorder = None
        self.controller.replace_backend(backend)
        self.current_run = run
        self._seen_written = 0
        self._timer.start()
        self._after_change()
        self.message.emit(f"Resumed {run.name} from {checkpoint_name}")
        return run

    # ---- the run list ------------------------------------------------------------------------

    def list_runs(self) -> list[RunSummary]:
        return self.store.list_runs()

    def size_of(self, run: RunSummary) -> int:
        return folder_size(run.path)

    def space_warning(self) -> str | None:
        return self.store.space_warning()

    def history(self, run_id: str) -> HistorySamples | None:
        return self.store.open(run_id).history()

    def checkpoints(self, run_id: str) -> list[CheckpointInfo]:
        return self.store.open(run_id).checkpoints()

    def run_config(self, run_id: str) -> WorldConfig:
        """The settings a run was made with."""
        return self.store.open(run_id).config

    def starting_counts(self, run_id: str) -> tuple[int, int] | None:
        """``(animals, plants)`` the run began with, or ``None`` when that is no longer known.

        The run's manifest has them when it was made by this version; an older run's are read from its
        first checkpoint when that is from tick 0 (older ones are pruned), else from its first history
        sample.
        """
        run = self.store.open(run_id)
        setup = run.setup
        if isinstance(setup.get("animals"), int) and isinstance(setup.get("plants"), int):
            return setup["animals"], setup["plants"]
        first = next(iter(run.checkpoints()), None)
        if first is not None and first.tick == 0:
            return first.animals, first.plants
        history = run.history()
        if history is None:
            return None
        animals, plants = history.series("animals")[1], history.series("plants")[1]
        if not animals or not plants:
            return None
        return round(animals[0]), round(plants[0])

    def compact(self, run_id: str) -> Compacted:
        """Rewrite a saved run's file without its free space (``STORE.3``). The run on screen is
        refused, as is any run a simulation is writing; the store says which."""
        if self.current_run is not None and self.current_run.id == run_id:
            raise RunError(
                "It is the run on screen. Open another run (or start a new one) and compact it then."
            )
        result = self.store.compact(run_id)
        self.changed.emit()
        return result

    def delete(self, run_id: str) -> None:
        """Remove a run for good. If it is the current run, the world on screen goes on but is no
        longer saved anywhere (Save now starts a new run)."""
        if self.current_run is not None and self.current_run.id == run_id:
            self._stop_current(final_checkpoint=False)
            self._set_label()
        self.store.delete(run_id)
        self.changed.emit()

    def export_csv(self, run_id: str, path: str | os.PathLike[str]) -> int:
        """Write a run's recorded history as a table (one row per sample, one column per value);
        returns the rows written. Flows are per day, as the charts show them."""
        samples = self.history(run_id)
        if samples is None:
            raise RunError("This run has no recorded history.")
        names = samples.names()
        rows = samples.samples()
        with open(path, "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["day", "tick", *names])
            for sample in rows:
                writer.writerow(
                    [sample.day, sample.tick]
                    + ["" if (v := sample.rate(n)) is None else repr(v) for n in names]
                )
        return len(rows)

    # ---- the label ---------------------------------------------------------------------------

    def refresh(self) -> None:
        """Notice an autosave and bring the label ("saved 2 min ago") up to date."""
        if self.autosaver is not None and self.autosaver.written != self._seen_written:
            self._seen_written = self.autosaver.written
            self.changed.emit()
        hosted = self.hosted()
        notice = None if hosted is None else hosted.run_notice
        if notice is not None and notice.saved != self._seen_written:
            self._seen_written = notice.saved
            self.changed.emit()
        self._set_label()

    def _after_change(self) -> None:
        self._set_label()
        self.changed.emit()

    def _set_label(self) -> None:
        run = self.current_run
        if run is None:
            text = ""
        else:
            summary = run.summary
            text = f"{run.name}, seed {summary.seed}"
            saved = parse_utc(summary.updated)
            if saved is not None:
                text += f" - saved {format_ago(max(0.0, self.store.clock() - saved))}"
        if text != self._label:
            self._label = text
            self.label_changed.emit(text)

    @property
    def label(self) -> str:
        return self._label
