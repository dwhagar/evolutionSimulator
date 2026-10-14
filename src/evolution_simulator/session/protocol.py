"""What the session needs from a simulation (UX.6).

``World`` already provides all of it, and so does ``FakeSimulation``; the session and everything
built on it (the process host, the tests of the screens) talks to this protocol, never to ``World``
directly, which is what lets a window be built and tested against a made-up world.
"""

from __future__ import annotations

from typing import Protocol

from evolution_simulator.world.bounds import Bounds
from evolution_simulator.world.events import EventListener
from evolution_simulator.world.timescale import TimeScale
from evolution_simulator.world.views import AnimalDetail, AnimalView, CorpseView, PlantView
from evolution_simulator.world.world import StepReport


class Simulation(Protocol):
    @property
    def tick(self) -> int: ...

    @property
    def bounds(self) -> Bounds: ...

    @property
    def time_scale(self) -> TimeScale:
        """``seconds_per_tick`` is the tick length; the session owns the speed."""
        ...

    @property
    def simulated_seconds(self) -> float: ...

    @property
    def elapsed(self) -> str: ...

    @property
    def day(self) -> int: ...

    @property
    def daylight(self) -> float: ...

    @property
    def is_night(self) -> bool: ...

    @property
    def plant_count(self) -> int: ...

    def step(self) -> StepReport: ...

    def animal_views(self) -> list[AnimalView]: ...

    def plant_views(self) -> list[PlantView]: ...

    def corpse_views(self) -> list[CorpseView]: ...

    def animal_detail(self, animal_id: int) -> AnimalDetail | None: ...

    def trace_brain(self, animal_id: int | None) -> bool: ...

    def add_event_listener(self, listener: EventListener) -> None: ...

    def remove_event_listener(self, listener: EventListener) -> None: ...
