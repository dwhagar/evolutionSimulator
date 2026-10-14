"""The world and its step loop (WORLD.2).

A ``World`` holds animals and plants at positions in a bounded space, a seeded random generator and
a tick counter. ``step`` advances one tick, always in the same order:

1. Every living animal senses the world as it stands at the start of the tick and its brain
   decides, with the wander fallback on (all decisions are made before anyone acts).
2. In id order each animal ages and burns energy, turns, moves (walls stop it) and, if its brain
   says "eat" and a plant is in reach, grazes.
3. Animals that want to mate, are ready, and are close enough pair off in id order; each pair
   makes one child.
4. Plants grow in id order; a plant that is ready drops seeds around it.
5. The dead are removed and the clock advances.

Everything random comes from one ``random.Random`` seeded by ``WorldConfig.seed``, organisms are
visited in id order, and nothing reads a clock, so the same config, the same organisms and the same
sequence of calls always give the same world (``state_digest`` shows it).

Placeholders to replace later: the child's energy and the seeds' biomass do not come out of the
parents (REPRO.5), the mating energy guard belongs with the trait config (TRAIT.5, TRAIT.3), and
attacking prey and acting on the other brain outputs are BRAIN.10.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.traits import AnimalTraits, PlantTraits
from evolution_simulator.world.bounds import Bounds
from evolution_simulator.world.organisms import Animal, Plant
from evolution_simulator.world.senses import BasicSenses, Senses, wrap_angle
from evolution_simulator.world.spatial import SpatialIndex
from evolution_simulator.world.timescale import TimeScale, format_duration
from evolution_simulator.world.vector import Vec

INDEX_CELL_SIZE: float = 64.0
"""Grid cell for neighbour searches, about the longest sight range (60 units)."""


@dataclass(frozen=True)
class WorldConfig:
    """Everything that defines a run besides the organisms put into it."""

    bounds: Bounds = field(default_factory=Bounds)
    time_scale: TimeScale = field(default_factory=TimeScale)
    seed: int = 0
    graze_amount: float = 5.0
    """Biomass an animal can take from a plant in one tick."""
    mating_reach: float = 3.0
    """Two animals mate only if their centres are this close or closer."""
    min_mating_energy_ratio: float = 0.5
    """An animal below this fraction of its energy store will not mate (the cost is up to 45%)."""
    birth_scatter: float = 1.0
    """A child appears within this distance of its parents' midpoint."""
    max_animals: int = 1000
    max_plants: int = 5000
    """Safety caps so a run cannot grow without limit; births stop at the cap."""

    def __post_init__(self) -> None:
        for name in ("graze_amount", "mating_reach", "birth_scatter"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be zero or more, got {value}.")
        if not 0.0 <= self.min_mating_energy_ratio <= 1.0:
            raise ValueError("min_mating_energy_ratio must be between 0 and 1.")
        if self.max_animals < 0 or self.max_plants < 0:
            raise ValueError("Population caps must not be negative.")


@dataclass(frozen=True)
class StepReport:
    """What happened in one tick, or the sum over several (``tick`` is then the last one)."""

    tick: int
    animal_births: int = 0
    animal_deaths: int = 0
    plant_births: int = 0
    plant_deaths: int = 0

    def __add__(self, other: StepReport) -> StepReport:
        return StepReport(
            tick=max(self.tick, other.tick),
            animal_births=self.animal_births + other.animal_births,
            animal_deaths=self.animal_deaths + other.animal_deaths,
            plant_births=self.plant_births + other.plant_births,
            plant_deaths=self.plant_deaths + other.plant_deaths,
        )


class World:
    def __init__(self, config: WorldConfig | None = None, senses: Senses | None = None) -> None:
        self.config = config if config is not None else WorldConfig()
        self.senses: Senses = senses if senses is not None else BasicSenses()
        self.rng = random.Random(self.config.seed)
        self.tick: int = 0
        self._next_id: int = 1
        self._animals: dict[int, Animal] = {}
        self._plants: dict[int, Plant] = {}
        self._animal_index = SpatialIndex(INDEX_CELL_SIZE)
        self._plant_index = SpatialIndex(INDEX_CELL_SIZE)
        self.max_canopy: float = 0.0
        """Largest canopy radius of any plant added so far; bounds the plant search radius."""
        self.max_body: float = 0.0
        """Largest body radius of any animal added so far."""

    # -------------------------------------------------------------------------
    # Reading the world
    # -------------------------------------------------------------------------

    @property
    def bounds(self) -> Bounds:
        return self.config.bounds

    @property
    def time_scale(self) -> TimeScale:
        return self.config.time_scale

    @property
    def simulated_seconds(self) -> float:
        return self.time_scale.simulated_seconds(self.tick)

    @property
    def elapsed(self) -> str:
        """Simulated time so far, for example ``3d 04:00:00``."""
        return format_duration(self.simulated_seconds)

    @property
    def animals(self) -> list[Animal]:
        """Living animals in id order."""
        return [self._animals[i] for i in sorted(self._animals)]

    @property
    def plants(self) -> list[Plant]:
        """Living plants in id order."""
        return [self._plants[i] for i in sorted(self._plants)]

    def animals_near(self, position: Vec, radius: float) -> list[Animal]:
        """Animals whose position is within ``radius`` of ``position`` (as of the last index
        refresh: the start of the tick for the senses), in id order."""
        return [self._animals[i] for i in self._animal_index.query(position, radius)]

    def plants_near(self, position: Vec, radius: float) -> list[Plant]:
        return [self._plants[i] for i in self._plant_index.query(position, radius)]

    # -------------------------------------------------------------------------
    # Putting organisms in
    # -------------------------------------------------------------------------

    def _new_id(self) -> int:
        organism_id = self._next_id
        self._next_id += 1
        return organism_id

    def _place(self, position: Vec | None) -> Vec:
        if position is None:
            return Vec(tuple(self.rng.uniform(0.0, s) for s in self.bounds.size))
        if not self.bounds.contains(position):
            raise ValueError(f"Position {position.coords} is outside the world {self.bounds.size}.")
        return position

    def add_animal(
        self,
        dna: DNA,
        position: Vec | None = None,
        heading: float | None = None,
        parents: tuple[int, ...] = (),
    ) -> Animal:
        """Put an animal in the world; a missing position or heading is drawn from the world's
        random generator. Raises if the animal cap is reached or the position is outside."""
        if len(self._animals) >= self.config.max_animals:
            raise ValueError(f"The world already holds {self.config.max_animals} animals.")
        place = self._place(position)
        facing = self.rng.uniform(-math.pi, math.pi) if heading is None else wrap_angle(heading)
        animal = Animal(self._new_id(), AnimalTraits(dna), place, facing, parents)
        self._animals[animal.id] = animal
        self._animal_index.insert(animal.id, animal.position)
        self.max_body = max(self.max_body, animal.radius)
        return animal

    def add_plant(
        self, dna: DNA, position: Vec | None = None, parents: tuple[int, ...] = ()
    ) -> Plant:
        if len(self._plants) >= self.config.max_plants:
            raise ValueError(f"The world already holds {self.config.max_plants} plants.")
        place = self._place(position)
        plant = Plant(self._new_id(), PlantTraits(dna), place, parents)
        self._plants[plant.id] = plant
        self._plant_index.insert(plant.id, plant.position)
        self.max_canopy = max(self.max_canopy, plant.radius)
        return plant

    def populate(self, animals: int = 0, plants: int = 0) -> None:
        """Add random organisms at random places (plants first, then animals)."""
        for _ in range(plants):
            self.add_plant(DNA.random(PLANT_LAYOUT, self.rng))
        for _ in range(animals):
            self.add_animal(DNA.random(ANIMAL_LAYOUT, self.rng))

    # -------------------------------------------------------------------------
    # The step loop
    # -------------------------------------------------------------------------

    def run(self, ticks: int) -> StepReport:
        """Step ``ticks`` times and return the summed report."""
        if ticks < 0:
            raise ValueError(f"Cannot run a negative number of ticks, got {ticks}.")
        total = StepReport(tick=self.tick)
        for _ in range(ticks):
            total = total + self.step()
        return total

    def step(self) -> StepReport:
        """Advance one tick."""
        animals = self.animals
        plants = self.plants
        self._refresh_animal_index()

        # 1. Sense and decide, all from the same start-of-tick world.
        for animal in animals:
            percepts = self.senses.perceive(self, animal)
            animal.last_decision = animal.traits.think(percepts, self.rng)

        # 2. Live, move and eat.
        for animal in animals:
            decision = animal.last_decision
            assert decision is not None
            animal.traits.update_metabolism_and_aging(decision.speed)
            if not animal.is_alive:
                continue
            animal.heading = wrap_angle(
                animal.heading - decision.turn * animal.traits.base_turn_rate
            )
            step_length = decision.speed * animal.traits.current_max_speed
            animal.position = self.bounds.clamp(
                animal.position + Vec.from_angle(animal.heading, step_length)
            )
            if decision.eats_or_attacks:
                self._graze(animal)

        # 3. Mate.
        self._refresh_animal_index()
        animal_births = self._mate(animals)

        # 4. Plants grow and seed.
        plant_births = 0
        for plant in plants:
            plant.traits.update_growth_and_metabolism()
            if plant.is_alive and plant.traits.flag_ready_to_seed:
                plant_births += self._seed(plant)

        # 5. Remove the dead and advance the clock.
        animal_deaths = self._remove_dead(self._animals, self._animal_index)
        plant_deaths = self._remove_dead(self._plants, self._plant_index)
        self.tick += 1
        return StepReport(
            tick=self.tick,
            animal_births=animal_births,
            animal_deaths=animal_deaths,
            plant_births=plant_births,
            plant_deaths=plant_deaths,
        )

    def _refresh_animal_index(self) -> None:
        self._animal_index.clear()
        for animal in self.animals:
            self._animal_index.insert(animal.id, animal.position)

    def _graze(self, animal: Animal) -> None:
        reach = animal.radius + self.max_canopy
        best: Plant | None = None
        best_distance = math.inf
        for plant in self.plants_near(animal.position, reach):
            distance = animal.position.distance_to(plant.position)
            if distance <= animal.radius + plant.radius and (distance < best_distance):
                best, best_distance = plant, distance
        if best is None:
            return
        if animal.traits.inspect_food(best.traits.toxicity, self.rng):
            return  # it tasted the poison and refused
        eaten, toxicity = best.traits.graze(self.config.graze_amount)
        animal.traits.feed(eaten, is_meat=False, toxicity=toxicity)

    def _mate(self, animals: list[Animal]) -> int:
        cfg = self.config
        willing = [
            a
            for a in animals
            if a.is_alive
            and a.last_decision is not None
            and a.last_decision.seeks_mating
            and a.traits.mating_cooldown == 0
            and a.traits.current_energy >= cfg.min_mating_energy_ratio * a.traits.max_energy
        ]
        willing_ids = {a.id for a in willing}
        paired: set[int] = set()
        newborn: list[tuple[DNA, Vec, tuple[int, ...]]] = []
        for a in willing:
            if a.id in paired:
                continue
            best: Animal | None = None
            best_distance = math.inf
            for b in self.animals_near(a.position, cfg.mating_reach):
                if b is a or b.id in paired or b.id not in willing_ids:
                    continue
                distance = a.position.distance_to(b.position)
                if distance < best_distance:
                    best, best_distance = b, distance
            if best is None:
                continue
            if len(self._animals) + len(newborn) >= cfg.max_animals:
                break
            paired.update((a.id, best.id))
            child_dna = a.traits.dna.reproduce(
                best.traits.dna, self.rng, crossover=DNA.crossover_by_unit
            )
            at = Vec.midpoint(a.position, best.position)
            newborn.append((child_dna, self._scatter(at, cfg.birth_scatter), (a.id, best.id)))
            a.traits.consume_mating_cost()
            best.traits.consume_mating_cost()
        for child_dna, position, parents in newborn:
            self.add_animal(child_dna, position, parents=parents)
        return len(newborn)

    def _seed(self, plant: Plant) -> int:
        plant.traits.consume_reproduction_cost()
        born = 0
        for _ in range(plant.traits.seed_count):
            if len(self._plants) >= self.config.max_plants:
                break
            dna = plant.traits.dna.reproduce(None, self.rng)
            spot = self._scatter(plant.position, plant.traits.dispersal_radius)
            self.add_plant(dna, spot, parents=(plant.id,))
            born += 1
        return born

    def _scatter(self, centre: Vec, radius: float) -> Vec:
        """A random point within ``radius`` of ``centre`` (2D), kept inside the world."""
        angle = self.rng.uniform(-math.pi, math.pi)
        distance = radius * math.sqrt(self.rng.random())
        offset = Vec.from_angle(angle, distance)
        if centre.dimensions != 2:
            raise NotImplementedError("Scattering is 2D for now.")
        return self.bounds.clamp(centre + offset)

    @staticmethod
    def _remove_dead(organisms: dict, index: SpatialIndex) -> int:
        dead = [i for i, o in organisms.items() if not o.is_alive]
        for organism_id in dead:
            del organisms[organism_id]
            if organism_id in index:
                index.remove(organism_id)
        return len(dead)

    # -------------------------------------------------------------------------
    # Checking repeatability
    # -------------------------------------------------------------------------

    def state_digest(self) -> str:
        """A hash of the whole state: tick, random generator, and every organism's place, energy
        and genome. Two runs that are really the same give the same digest."""
        parts: list[str] = [str(self.tick), repr(self.rng.getstate())]
        for animal in self.animals:
            parts.append(
                f"A{animal.id}|{animal.position.coords!r}|{animal.heading!r}|"
                f"{animal.traits.current_energy!r}|{animal.traits.current_health!r}|"
                f"{animal.traits.dna}"
            )
        for plant in self.plants:
            parts.append(
                f"P{plant.id}|{plant.position.coords!r}|{plant.traits.current_biomass!r}|"
                f"{plant.traits.dna}"
            )
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()
