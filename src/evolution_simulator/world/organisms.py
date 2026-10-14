"""Organisms in the world: a body (traits) with a place."""

from __future__ import annotations

from evolution_simulator.brain_adapter import BrainDecision
from evolution_simulator.traits import AnimalTraits, PlantTraits
from evolution_simulator.world.vector import Vec


class Animal:
    """A mobile organism. ``heading`` is in radians (0 faces +x, counterclockwise); the world
    keeps it between -pi and pi. ``last_decision`` is what its brain chose this tick (``None``
    while it sleeps). ``asleep`` is set by the world's day-night cycle; ``disturbed`` (woken by an alarm call) keeps
    it awake until the next day. ``partner`` is the id of the father while this animal is carrying his
    litter."""

    __slots__ = (
        "asleep",
        "awake_time",
        "disturbed",
        "heading",
        "id",
        "last_decision",
        "parents",
        "partner",
        "position",
        "traits",
    )

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
        self.awake_time: float = 0.0
        """Reference ticks (hours) since it last slept (``SENSE.14``'s tiredness)."""
        self.disturbed: bool = False
        self.partner: int | None = None

    @property
    def is_alive(self) -> bool:
        return self.traits.is_alive

    @property
    def radius(self) -> float:
        return self.traits.body_radius

    def __repr__(self) -> str:
        return f"Animal(id={self.id}, position={self.position.coords}, alive={self.is_alive})"


class Plant:
    """A rooted organism; it never moves. ``shade`` and ``soil`` (each 0 to 1) are how much light
    and soil water neighbouring plants leave it; the world refreshes them every few ticks."""

    __slots__ = ("id", "parents", "position", "shade", "soil", "traits")

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
        self.shade: float = 1.0
        self.soil: float = 1.0

    @property
    def is_alive(self) -> bool:
        return self.traits.is_alive

    @property
    def radius(self) -> float:
        return self.traits.canopy_radius

    def __repr__(self) -> str:
        return f"Plant(id={self.id}, position={self.position.coords}, alive={self.is_alive})"
