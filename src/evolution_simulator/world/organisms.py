"""Organisms in the world: a body (traits) with a place."""

from __future__ import annotations

from evolution_simulator.brain_adapter import BrainDecision
from evolution_simulator.traits import AnimalTraits, PlantTraits
from evolution_simulator.world.vector import Vec


class Animal:
    """A mobile organism. ``heading`` is in radians (0 faces +x, counterclockwise); the world
    keeps it between -pi and pi. ``last_decision`` is what its brain chose this tick (``None``
    while it sleeps). ``asleep`` is set by the world's day-night cycle."""

    __slots__ = ("asleep", "heading", "id", "last_decision", "parents", "position", "traits")

    kind = "animal"

    def __init__(
        self,
        organism_id: int,
        traits: AnimalTraits,
        position: Vec,
        heading: float,
        parents: tuple[int, ...] = (),
    ) -> None:
        self.id = organism_id
        self.traits = traits
        self.position = position
        self.heading = heading
        self.parents = parents
        self.last_decision: BrainDecision | None = None
        self.asleep: bool = False

    @property
    def is_alive(self) -> bool:
        return self.traits.is_alive

    @property
    def radius(self) -> float:
        return self.traits.body_radius

    def __repr__(self) -> str:
        return f"Animal(id={self.id}, position={self.position.coords}, alive={self.is_alive})"


class Plant:
    """A rooted organism; it never moves."""

    __slots__ = ("id", "parents", "position", "traits")

    kind = "plant"

    def __init__(
        self,
        organism_id: int,
        traits: PlantTraits,
        position: Vec,
        parents: tuple[int, ...] = (),
    ) -> None:
        self.id = organism_id
        self.traits = traits
        self.position = position
        self.parents = parents

    @property
    def is_alive(self) -> bool:
        return self.traits.is_alive

    @property
    def radius(self) -> float:
        return self.traits.canopy_radius

    def __repr__(self) -> str:
        return f"Plant(id={self.id}, position={self.position.coords}, alive={self.is_alive})"
