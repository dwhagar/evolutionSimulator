"""The simulation in its own process, behind the window's ``Backend`` face (UX.33).

``ProcessBackend`` wraps a ``SimClient`` (a ``ProcessClient`` by default: the world runs in a spawned
process, so the window answers however fast or slow the simulation is). Everything arrives later
than with ``LocalBackend``, so a few things the local one never needed show up here:

- ``starting`` is true until the host's ``Ready`` message (a spawned process takes a moment, more on
  Windows). Commands sent meanwhile are queued in the pipe and carried out once it is up.
- A command the host refuses comes back in ``Batch.rejected``; a failed host in ``Batch.crash``, with
  ``crashed`` holding the traceback from then on and ``restarted()`` making a fresh backend (from the
  run's newest checkpoint when it was saved into a run, else from the same recipe).
- ``Batch.history`` is filled from the host's history messages, and ``run_notice`` is the newest word
  about the run the world is saved into. ``save_now`` starts a run or checkpoints it and waits for
  the answer, which is what the run screens (``RunManager``) need.

No Qt in here, so it can be tested without a window.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from evolution_simulator.history import HistorySamples
from evolution_simulator.runs import RunError
from evolution_simulator.session import (
    Command,
    CommandError,
    HostRules,
    ProcessClient,
    ResumeSpec,
    RunNotice,
    Shutdown,
    SimClient,
    Simulation,
    StartRun,
    Status,
    StatusChanged,
)
from evolution_simulator.session.client import Inbox
from evolution_simulator.session.snapshot import Frame
from evolution_simulator.session.specs import Prepared
from evolution_simulator.viewer.backend import Batch
from evolution_simulator.world.views import AnimalDetail

STARTING_STATUS = Status(
    running=False,
    steps_left=0,
    speed_asked=1.0,
    speed_preset="real-time",
    speed_achieved=None,
    behind=False,
    ticks_dropped=0,
    selected=None,
)
"""What the controls show until the first frame says better."""

SAVE_WAIT = 120.0
"""Seconds ``save_now`` waits for the host (a checkpoint of a big world takes a while)."""


class ProcessBackend:
    def __init__(
        self,
        recipe: Callable[[], Simulation | Prepared],
        rules: HostRules | None = None,
        *,
        client: SimClient | None = None,
    ) -> None:
        self.recipe = recipe
        self.rules = rules
        self.client: SimClient = client if client is not None else ProcessClient(recipe, rules)
        self.starting = True
        self.crashed: str | None = None
        self.run_notice: RunNotice | None = None
        self._status = STARTING_STATUS
        self._closed = False
        self._frame: Frame | None = None
        self._detail: AnimalDetail | None = None
        self._events: list = []
        self._history: HistorySamples | None = None
        self._rejected: list = []
        self._crash_reported = False
        self._tokens = 0
        self._ready_reported = False

    # ---- the Backend face -------------------------------------------------------------------

    @property
    def status(self) -> Status:
        return self._status

    @property
    def saveable(self) -> bool:
        """The world can be saved into a run (a real one, not the made-up world)."""
        return bool(getattr(self.recipe, "saveable", False))

    def send(self, command: Command) -> None:
        if self.crashed is not None:
            raise CommandError("The simulation has stopped.")
        self.client.send(command)

    def poll(self) -> Batch:
        """Whatever has arrived; never blocks."""
        self._take_in()
        batch = Batch(
            self._frame,
            self._detail,
            tuple(self._events),
            self._history,
            tuple(r.reason for r in self._rejected),
            self.crashed if self.crashed is not None and not self._crash_reported else None,
            not self.starting and not self._ready_reported,
        )
        self._crash_reported = self._crash_reported or self.crashed is not None
        self._ready_reported = self._ready_reported or not self.starting
        self._frame = self._detail = self._history = None
        self._events, self._rejected = [], []
        return batch

    def close(self, save: bool = True) -> None:
        """Stop the simulation process. The run it is saved into, if any, gets a last checkpoint
        unless ``save`` is false (going back to an earlier checkpoint of the same run)."""
        if self._closed:
            return
        self._closed = True
        if not save:
            self.client.send(Shutdown(save=False))
        self.client.close()

    # ---- taking in what the host says -------------------------------------------------------

    def _take_in(self) -> None:
        if self._closed:
            return
        self._add(self.client.poll())

    def _add(self, inbox: Inbox) -> None:
        if inbox.ready:
            self.starting = False
        if inbox.frame is not None:
            self._frame = inbox.frame
            self._status = inbox.frame.status
        if inbox.detail is not None:
            self._detail = inbox.detail
        if inbox.history is not None:
            self._history = inbox.history
        if inbox.run is not None:
            self.run_notice = inbox.run
        for event in inbox.events:
            if isinstance(event, StatusChanged):
                self._status = event.status
        self._events.extend(inbox.events)
        self._rejected.extend(inbox.rejected)
        if inbox.crash is not None and self.crashed is None:
            self.crashed = inbox.crash

    def _wait(self, done: Callable[[], bool], timeout: float, what: str) -> None:
        """Poll until ``done()``, keeping everything that arrives for the next ``poll``."""
        deadline = time.monotonic() + timeout
        while not done():
            if self.crashed is not None:
                raise RunError(f"The simulation stopped while {what}.")
            if time.monotonic() >= deadline:
                raise RunError(f"The simulation did not answer while {what}.")
            time.sleep(0.005)
            self._take_in()

    def wait_ready(self, timeout: float = 60.0) -> None:
        """Block until the simulation is up (for tests and scripts; a window just polls)."""
        self._wait(lambda: not self.starting, timeout, "starting")

    # ---- runs -------------------------------------------------------------------------------

    def save_now(self, root: str | Path | None, name: str | None = None) -> RunNotice:
        """Save the world into a run: start one in the run store at ``root`` the first time (named
        ``name``), checkpoint it after that. Waits for the host to say so; raises ``RunError`` if it
        refuses, fails or does not answer."""
        if not self.saveable:
            raise RunError("This simulation is not a real world, so it cannot be saved.")
        if self.crashed is not None:
            raise RunError("The simulation has stopped, so there is nothing to save.")
        self._tokens += 1
        request = StartRun(None if root is None else str(root), name, self._tokens)
        self.client.send(request)

        def refused() -> str | None:
            for rejection in self._rejected:
                if rejection.command == request:
                    return rejection.reason
            return None

        def done() -> bool:
            notice = self.run_notice
            return refused() is not None or (notice is not None and notice.answers >= request.token)

        self._wait(done, SAVE_WAIT, "saving")
        reason = refused()
        if reason is not None:
            self._rejected = [r for r in self._rejected if r.command != request]
            raise RunError(reason)
        assert self.run_notice is not None
        return self.run_notice

    def restarted(self) -> ProcessBackend:
        """A new backend to put in this one's place after a failure: from the newest checkpoint of
        the run the world was saved into, else from the recipe it started with."""
        notice = self.run_notice
        recipe: Callable[[], Simulation | Prepared] = self.recipe
        if notice is not None and notice.checkpoints > 0:
            recipe = ResumeSpec(str(Path(notice.path).parent), notice.run_id)
        return ProcessBackend(recipe, self.rules)
