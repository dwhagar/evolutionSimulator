"""The link between a backend and the panels (UX.11).

``ViewerController`` polls its backend on a timer and turns what comes back into Qt signals, so a
panel just connects to the ones it cares about and never talks to the backend or the session. It
also remembers the latest of each thing (``frame``, ``detail``, ``status``, ``plants``, ``history``), so a panel
built after the first frame can start from the current state instead of waiting for the next one.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from evolution_simulator.history import HistorySamples
from evolution_simulator.session import (
    CommandError,
    Frame,
    RunStarted,
    Status,
    StatusChanged,
)
from evolution_simulator.session.snapshot import Block
from evolution_simulator.viewer.backend import Backend, Request
from evolution_simulator.world.views import AnimalDetail

POLL_MS = 16
"""Milliseconds between polls of the backend (about 60 a second; the session itself decides how
often a frame is due)."""


class ViewerController(QObject):
    frame_received = Signal(object)
    """A ``Frame``. When its ``plants`` block is ``None`` the plants did not change; use
    ``controller.plants`` for the last ones sent."""
    detail_received = Signal(object)
    """The selected animal's ``AnimalDetail`` (``alive`` false once when it has just died)."""
    status_changed = Signal(object)
    """A ``Status``, when anything in it differs from the last one heard (the measured speed too)."""
    event_received = Signal(object)
    """A world event (``Born``, ``Died``, ``Mated``), or ``RunStarted`` when a new run replaced the
    world (the controller has by then forgotten the old frame, plants, detail and history)."""
    history_received = Signal(object)
    """The ``HistorySamples`` so far, each time a new sample has been taken (once per simulated day)."""
    command_failed = Signal(str)
    """Text for a command the backend refused; nothing was changed."""
    backend_failed = Signal(str)
    """The backend raised while being polled; polling has stopped."""
    backend_crashed = Signal(str)
    """The simulation, running in another process, failed; the text is its traceback. Polling has
    stopped; ``restart()`` puts a fresh simulation in its place."""
    backend_ready = Signal()
    """A simulation in another process has finished starting (``starting`` is false from here)."""
    backend_replaced = Signal(object)
    """A different run now sits behind the controller (``replace_backend``, e.g. a resumed run).
    The cached ``frame``, ``detail`` and ``plants`` were cleared first; a panel drops anything it
    holds about the old run (the selected animal, a trail, a zoom to the old world) and starts again
    from the frame that follows."""

    def __init__(self, backend: Backend, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.frame: Frame | None = None
        self.detail: AnimalDetail | None = None
        self.status: Status = backend.status
        self.plants: Block | None = None
        self.history: HistorySamples | None = None
        self._started = False
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.poll)

    @property
    def polling(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        self._started = True
        self._timer.start()

    def stop(self) -> None:
        self._started = False
        self._timer.stop()

    def replace_backend(self, backend: Backend) -> None:
        """Show a different run: forget everything cached from the old backend, switch, tell the
        panels (``backend_replaced``) and poll once so the new world appears at once. The caller
        closes the old backend. Polling restarts if it was running or had stopped after a failure."""
        self.backend = backend
        self.frame = None
        self.detail = None
        self.plants = None
        self.history = None
        self.status = backend.status
        self.backend_replaced.emit(backend)
        self.status_changed.emit(self.status)
        if self._started:
            self._timer.start()
        self.poll()

    @property
    def starting(self) -> bool:
        """The backend is a simulation in another process that has not come up yet."""
        return bool(getattr(self.backend, "starting", False))

    def restart(self) -> bool:
        """Put a fresh simulation where a failed one was, when the backend can make one
        (``restarted()``: from the run's newest checkpoint if it was saved, else from the start).
        ``False`` if it cannot."""
        old = self.backend
        make = getattr(old, "restarted", None)
        if make is None:
            return False
        # The old one goes first: it may be the writer of the run the new one resumes.
        old.close()  # type: ignore[attr-defined]
        self.replace_backend(make())
        return True

    def send(self, command: Request) -> bool:
        """Hand a command to the backend; ``False`` (and ``command_failed``) if it was refused."""
        try:
            self.backend.send(command)
        except CommandError as error:
            self.command_failed.emit(str(error))
            return False
        self._set_status(self.backend.status)  # so a menu or button is right before the next poll
        return True

    def poll(self) -> None:
        """Fetch what the backend has and emit it. Called by the timer; tests call it directly."""
        try:
            batch = self.backend.poll()
        except Exception as error:  # noqa: BLE001 - any failure must stop the timer, not loop
            self._timer.stop()
            self.backend_failed.emit(f"{type(error).__name__}: {error}")
            return
        if batch.ready:
            self.backend_ready.emit()
        for text in batch.rejected:
            self.command_failed.emit(text)
        for event in batch.events:
            if isinstance(event, StatusChanged):
                self._set_status(event.status)
            else:
                if isinstance(event, RunStarted):  # nothing held about the old run is true now
                    self.frame = self.detail = self.plants = self.history = None
                self.event_received.emit(event)
        if batch.frame is not None:
            frame = batch.frame
            self.frame = frame
            if frame.plants is not None:
                self.plants = frame.plants
            self._set_status(frame.status)
            self.frame_received.emit(frame)
        if batch.detail is not None:
            self.detail = batch.detail
            self.detail_received.emit(batch.detail)
        if batch.history is not None:
            self.history = batch.history
            self.history_received.emit(batch.history)
        if batch.crash is not None:
            self._timer.stop()
            self.backend_crashed.emit(batch.crash)

    def _set_status(self, status: Status) -> None:
        if status != self.status:
            self.status = status
            self.status_changed.emit(status)
