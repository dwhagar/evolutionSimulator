"""Recipes for a simulation (UX.7): picklable, so a spawned process can build its own.

A spawned process cannot be handed a ``World`` (it would have to be pickled whole and the child
would then own a copy); it is handed a recipe and builds the world itself. A recipe is any picklable
callable that returns a ``Simulation``, or a ``Prepared`` (a simulation with the run it is saved
into, UX.31). ``WorldSpec`` and ``FakeSpec`` cover the tests and a plain window; ``NewRunSpec`` and
``ResumeSpec`` start a run in the run store or carry one on. ``UX.17``'s new-run dialog adds more.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import ClassVar

from evolution_simulator.history import Recorder
from evolution_simulator.runs import Run, RunStore
from evolution_simulator.session.fake import FakeSimulation
from evolution_simulator.session.protocol import Simulation
from evolution_simulator.world.world import World, WorldConfig


@dataclass(frozen=True)
class Prepared:
    """What a recipe may return instead of a bare simulation: the simulation, the ``Recorder`` already
    watching it (the host makes one when this is ``None``) and the ``Run`` it is saved into (a world
    only; the host then autosaves into the run and checkpoints it when it shuts down)."""

    simulation: Simulation
    recorder: Recorder | None = None
    run: Run | None = None
    resumed_from: str | None = None
    """The name of the checkpoint the simulation was restored from, for the viewer's notice."""


@dataclass(frozen=True)
class WorldSpec:
    """A new ``World`` from a config, populated with a first generation."""

    config: WorldConfig | None = None
    animals: int = 0
    plants: int = 0
    seeded: bool = True

    saveable: ClassVar[bool] = True
    """Whether the world it makes can be saved into a run (a real ``World``)."""

    def __call__(self) -> Simulation:
        world = World(self.config)
        world.populate(self.animals, self.plants, self.seeded)
        return world


@dataclass(frozen=True)
class FakeSpec:
    """A ``FakeSimulation`` (made-up world) for building and testing screens."""

    animals: int = 120
    plants: int = 600
    seed: int = 0
    size: tuple[float, float] = (1000.0, 1000.0)
    seconds_per_tick: float = 3600.0
    period: int = 600

    saveable: ClassVar[bool] = False

    def __call__(self) -> Simulation:
        return FakeSimulation(
            self.animals,
            self.plants,
            seed=self.seed,
            size=self.size,
            seconds_per_tick=self.seconds_per_tick,
            period=self.period,
        )


@dataclass(frozen=True)
class NewRunSpec:
    """A new ``World`` and a new run folder for it in the run store at ``root`` (the default runs
    folder when ``None``), with its first checkpoint written before the window hears anything."""

    root: str | os.PathLike[str] | None = None
    config: WorldConfig | None = None
    animals: int = 0
    plants: int = 0
    seeded: bool = True
    name: str | None = None

    saveable: ClassVar[bool] = True

    def __call__(self) -> Prepared:
        world = World(self.config)
        world.populate(self.animals, self.plants, self.seeded)
        recorder = Recorder(world)
        run = RunStore(self.root).create(world, name=self.name, recorder=recorder)
        return Prepared(world, recorder, run)


@dataclass(frozen=True)
class ResumeSpec:
    """The world of a saved run, restored from its newest checkpoint that reads (or the named one),
    with its recorded history, carrying on in the same run folder. ``run_id`` may be ``"latest"``."""

    root: str | os.PathLike[str] | None = None
    run_id: str = "latest"
    checkpoint: str | None = None

    saveable: ClassVar[bool] = True

    def __call__(self) -> Prepared:
        store = RunStore(self.root)
        if self.run_id == "latest":
            runs = store.list_runs()
            if not runs:
                raise ValueError(f"There are no runs in {store.root} to resume.")
            run = store.open(runs[0].id)
        else:
            run = store.open(self.run_id)
        resumed = run.resume(self.checkpoint)
        recorder = resumed.recorder if resumed.recorder is not None else Recorder(resumed.world)
        return Prepared(resumed.world, recorder, run, resumed.checkpoint.name)
