"""Read-only views of the world (UX.6): what a viewer, a recorder or the session may read.

Anything outside the core that wants to look at the world (the session, the statistics recorder,
the windows) reads it through these, never through an organism's traits, so the organisms can
change inside without touching the screens. A view is a plain value with no reference back into
the world: an immutable ``NamedTuple`` for the many (animals, plants, corpses, a few numbers each,
cheap to make for every creature every frame) and a frozen dataclass for the one creature that is
being inspected. Positions are the first two coordinates (the world is 2D for now).

``World.animal_views()``, ``plant_views()``, ``corpse_views()`` and ``animal_detail()`` build them.
The field lists (``ANIMAL_FIELDS`` and so on) name the columns in order, and
``evolution_simulator.session`` packs them into frames from those lists.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

from evolution_simulator.brain import DEFAULT_BLUEPRINT, BrainNetwork
from evolution_simulator.brain_adapter import BrainDecision, BrainTrace
from evolution_simulator.deaths import DeathCause

if TYPE_CHECKING:
    from evolution_simulator.world.corpses import Corpse
    from evolution_simulator.world.organisms import Animal, Plant
    from evolution_simulator.world.world import World


class AnimalView(NamedTuple):
    """One animal as the world view draws it."""

    id: int
    x: float
    y: float
    heading: float
    """Radians, 0 faces +x, counterclockwise, between -pi and pi."""
    radius: float
    energy_ratio: float
    """Energy over its store, 0 to 1."""
    health_ratio: float
    age_ratio: float
    """Age over its lifespan (0 newborn, 1 worn out), capped at 1."""
    diet: float
    """Share of what it can digest that is meat, 0 (plants only) to 1 (meat only)."""
    asleep: bool
    pregnant: bool
    ready_to_mate: bool
    wandering: bool
    """Its brain could not decide and the random wander took over."""
    sex: int
    """0 impregnates, 1 bears the young."""
    family_a: float = 0.0
    family_b: float = 0.0
    """Two numbers that stay close for relatives (``lineage.family_key``), about 1 apart for
    unrelated random genomes and much less in a real population: stretch the range found in the
    frame over the colour scale."""


class PlantView(NamedTuple):
    id: int
    x: float
    y: float
    radius: float
    """Canopy radius."""
    biomass_ratio: float
    """Biomass over its full size, 0 to 1."""
    ready_to_seed: bool


class CorpseView(NamedTuple):
    id: int
    x: float
    y: float
    radius: float
    meat: float
    """Meat left; it rots, and the corpse goes when it is nearly gone."""


ANIMAL_FIELDS: tuple[str, ...] = AnimalView._fields
PLANT_FIELDS: tuple[str, ...] = PlantView._fields
CORPSE_FIELDS: tuple[str, ...] = CorpseView._fields


class KinView(NamedTuple):
    """One animal in a family tree: alive or dead (``World.family_of``, UX.39)."""

    id: int
    parents: tuple[int, ...]
    """Father, then mother; empty for a founder."""
    sex: int
    """0 impregnates, 1 bears the young."""
    born: int
    """The tick it was born (or, for a founder, put in the world)."""
    died: int | None
    """The tick it died, ``None`` while it lives."""
    cause: DeathCause | None
    family_a: float
    family_b: float
    """Its family key (``lineage.family_key``), kept so a dead animal can still be coloured."""


@dataclass(frozen=True, slots=True)
class FamilyView:
    """The neighbourhood of one animal in the family tree, as far as the world remembers it.

    ``kin`` holds the animal first, then its ancestors up to ``up`` generations, then its
    descendants down to ``down`` generations (each animal once, even when two paths reach it).
    Dead animals are remembered up to a bound (``AncestryBook``), so an old ancestor may be gone:
    its id then appears in a child's ``parents`` with no entry in ``kin``. ``truncated`` says there
    were more descendants than the view carries."""

    center: int
    up: int
    down: int
    kin: tuple[KinView, ...]
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class AnimalDetail:
    """Everything the inspector shows about one animal, as of ``tick``."""

    tick: int
    id: int
    alive: bool
    x: float
    y: float
    heading: float
    radius: float
    sex: int
    asleep: bool
    pregnant: bool
    litter: int
    """Young it is carrying (0 when not pregnant)."""
    ready_to_mate: bool
    age_ticks: int
    age_ratio: float
    energy: float
    max_energy: float
    health: float
    max_health: float
    vitality: float
    """1 in its prime, falling to 0 as wear accumulates."""
    mass: float
    diet: float
    matings: int
    parents: tuple[int, ...]
    partner: int | None
    """The father, while this animal carries his litter."""
    decision: BrainDecision | None
    """What it decided on the latest tick (``None`` while it sleeps)."""
    brain: BrainTrace | None
    """The inputs, hidden values and outputs of the last brain run; only filled in once the
    animal is traced (``World.trace_brain``) and its brain has run since."""
    network: BrainNetwork
    """The brain's wiring: biases, weights and which genome slots are switched on. Always filled
    (it is read from the brain, not from a run), and it includes what the animal has learned."""
    children: tuple[int, ...]
    """The ids of its living children, oldest first."""
    traits: dict[str, float]
    """The trait table, by trait id."""
    genome: str
    """The genome as base-4 digits."""
    death_cause: DeathCause | None = None
    family: FamilyView | None = None
    """Its place in the family tree (ancestors and descendants, alive or dead); ``None`` from a
    simulation that keeps no ancestry."""
    vision_range: float | None = None
    """How far its eye reaches now, in world units, after acuity and vitality (``None`` when the
    simulation does not say, as the stand-in simulation does not). The four ranges are what the
    sense overlays of the viewer draw."""
    hearing_range: float | None = None
    """How far its ear reaches now, after vitality."""
    smell_range: float | None = None
    touch_range: float | None = None
    """How far its touch reaches from the middle of its body."""


def diet_share(animal: Animal) -> float:
    """Meat share of what the animal can digest, from its genes (not its present health)."""
    phenotype = animal.traits.phenotype
    herb = float(phenotype["herbivore_eff"])
    carn = float(phenotype["carnivore_eff"])
    total = herb + carn
    return carn / total if total > 0.0 else 0.0


def age_ratio(animal: Animal, dt: float) -> float:
    traits = animal.traits
    lifespan = traits.lifespan_ticks
    return min(1.0, traits.age_ticks * dt / lifespan) if lifespan > 0.0 else 1.0


def animal_view(animal: Animal, dt: float) -> AnimalView:
    traits = animal.traits
    position = animal.position.coords
    decision = animal.last_decision
    return AnimalView(
        animal.id,
        position[0],
        position[1],
        animal.heading,
        animal.radius,
        max(0.0, traits.current_energy / traits.max_energy),
        max(0.0, traits.current_health / traits.max_damage_capacity),
        age_ratio(animal, dt),
        diet_share(animal),
        animal.asleep,
        traits.pregnancy is not None,
        traits.can_mate,
        decision is not None and decision.wandering,
        traits.sex,
        *traits.family_key,
    )


def plant_view(plant: Plant) -> PlantView:
    traits = plant.traits
    position = plant.position.coords
    return PlantView(
        plant.id,
        position[0],
        position[1],
        plant.radius,
        max(0.0, traits.current_biomass / traits.max_biomass),
        traits.flag_ready_to_seed,
    )


def corpse_view(corpse: Corpse) -> CorpseView:
    position = corpse.position.coords
    return CorpseView(corpse.id, position[0], position[1], corpse.radius, corpse.meat)


def animal_detail(world: World, animal: Animal) -> AnimalDetail:
    traits = animal.traits
    position = animal.position.coords
    pregnancy = traits.pregnancy
    return AnimalDetail(
        tick=world.tick,
        id=animal.id,
        alive=animal.is_alive,
        x=position[0],
        y=position[1],
        heading=animal.heading,
        radius=animal.radius,
        sex=traits.sex,
        asleep=animal.asleep,
        pregnant=pregnancy is not None,
        litter=0 if pregnancy is None else pregnancy.litter,
        ready_to_mate=traits.can_mate,
        age_ticks=traits.age_ticks,
        age_ratio=age_ratio(animal, world.dt),
        energy=traits.current_energy,
        max_energy=traits.max_energy,
        health=traits.current_health,
        max_health=traits.max_damage_capacity,
        vitality=traits.vitality,
        mass=traits.mass,
        diet=diet_share(animal),
        matings=traits.matings,
        parents=animal.parents,
        partner=animal.partner,
        decision=animal.last_decision,
        brain=traits.brain_trace,
        network=traits.brain.network(traits.brain_slots, DEFAULT_BLUEPRINT.max_hidden),
        children=world.children_of(animal.id),
        family=world.family_of(animal.id),
        traits={name: float(value) for name, value in traits.phenotype.items()},
        genome=str(traits.dna),
        death_cause=traits.death_cause,
        vision_range=traits.current_sight_range,
        hearing_range=traits.current_hearing_range,
        smell_range=traits.smell_range,
        touch_range=traits.tactile_range,
    )


def trait_columns(organisms: Iterable[Animal | Plant]) -> dict[str, list[float]]:
    """The numbers behind the trait and gene statistics (``UX.8``): for every organism given, each
    primary trait (``trait.<id>``) and each single-value gene (``gene.<id>``, 0 to 1; the brain's
    block of weights is left out), as one list per name in the order the organisms were given."""
    columns: dict[str, list[float]] = {}
    for organism in organisms:
        traits = organism.traits
        for name, value in traits.phenotype.items():
            columns.setdefault(f"trait.{name}", []).append(float(value))
        genome = traits.dna
        layout = genome.layout
        for gene_id in layout.gene_ids:
            if layout.gene(gene_id).block is None:
                columns.setdefault(f"gene.{gene_id}", []).append(genome.value(gene_id))
    return columns
