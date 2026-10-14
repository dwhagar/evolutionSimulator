"""Recipes for a simulation (UX.7): picklable, so a spawned process can build its own.

A spawned process cannot be handed a ``World`` (it would have to be pickled whole and the child
would then own a copy); it is handed a recipe and builds the world itself. A recipe is any picklable
callable that returns a ``Simulation``; these two cover the program and the tests. ``UX.9``'s
``load_world`` and ``UX.17``'s new-run dialog add more.
"""

from __future__ import annotations

from dataclasses import dataclass

from evolution_simulator.session.fake import FakeSimulation
from evolution_simulator.session.protocol import Simulation
from evolution_simulator.world.world import World, WorldConfig


@dataclass(frozen=True)
class WorldSpec:
    """A new ``World`` from a config, populated with a first generation."""

    config: WorldConfig | None = None
    animals: int = 0
    plants: int = 0
    seeded: bool = True

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

    def __call__(self) -> Simulation:
        return FakeSimulation(
            self.animals,
            self.plants,
            seed=self.seed,
            size=self.size,
            seconds_per_tick=self.seconds_per_tick,
            period=self.period,
        )
