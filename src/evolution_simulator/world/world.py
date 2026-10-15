"""The world and its step loop (WORLD.2).

A ``World`` holds animals and plants at positions in a bounded space, a seeded random generator and
a tick counter. ``step`` advances one tick, always in the same order:

1. Every living animal senses the world as it stands at the start of the tick and its brain
   decides, with the wander fallback on (all decisions are made before anyone acts).
2. In id order each animal ages and burns energy, turns, moves (walls stop it) and, if its brain
   says "eat" and a plant is in reach, grazes.
3. Animals that want to mate, are ready, and are close enough pair off in id order, each taking the
   willing animal of the other sex in reach with the closest genome (REPRO.4, ``mating.py``). A
   mating that takes makes the bearer pregnant; a bearer whose time is up gives birth to her litter
   next to her, if both parents can pay (REPRO.8).
4. Plants grow in id order; a plant that is ready drops seeds around it.
5. The dead are removed and the clock advances.

Everything random comes from one ``random.Random`` seeded by ``WorldConfig.seed``, organisms are
visited in id order, and nothing reads a clock, so the same config, the same organisms and the same
sequence of calls always give the same world (``state_digest`` shows it).

A child's starting energy and a seed's starting biomass come out of its parents (REPRO.5, REPRO.8),
and a litter is born only if both parents can afford it (TRAIT.5). Animals age, burn energy, heal
and carry young per reference tick (an hour of simulated time), scaled by the world's tick length:
a tick of ``seconds_per_tick`` is ``seconds_per_tick / 3600`` of that clock (``World.dt``). So are
movement, turning, grazing, the plants' growth and upkeep and the energy a sleeper regains (WORLD.7):
every rate in the code is "per reference tick", and the one-hour tick the numbers were set for is the
default. Attacking prey and acting on the other brain outputs are BRAIN.10.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from evolution_simulator.config import (
    DEFAULT_RULES,
    AttackRules,
    CorpseRules,
    DayCycle,
    LearningRules,
    PlantRules,
    SensingRules,
    SleepRules,
    TraitRules,
)
from evolution_simulator.deaths import DeathCause
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import founder_animal_dna, founder_plant_dna
from evolution_simulator.learning import NightlyLearning
from evolution_simulator.seed_brain import seeded_dna
from evolution_simulator.sense_genes import HEARING_RANGE, SIGHT_REACH, SMELL_RANGE
from evolution_simulator.traits import AnimalTraits, MatingResult, PlantTraits
from evolution_simulator.world.ancestry import AncestryBook
from evolution_simulator.world.bounds import Bounds
from evolution_simulator.world.corpses import Corpse
from evolution_simulator.world.events import Ate, Born, Died, EventListener, Mated, WorldEvent
from evolution_simulator.world.mating import choose_mate
from evolution_simulator.world.organisms import Animal, Plant
from evolution_simulator.world.scent import ANIMAL, CARRION, ScentField
from evolution_simulator.world.senses import (
    MEAT_EATER,
    Senses,
    WorldSenses,
    classify,
    wrap_angle,
)
from evolution_simulator.world.sleep import SleepListener
from evolution_simulator.world.spatial import SpatialIndex
from evolution_simulator.world.timescale import TimeScale, format_duration
from evolution_simulator.world.vector import Vec
from evolution_simulator.world.views import (
    AnimalDetail,
    AnimalView,
    CorpseView,
    FamilyView,
    PlantView,
    animal_detail,
    animal_view,
    corpse_view,
    plant_view,
    trait_columns,
)

INDEX_CELL_SIZE: float = max(SIGHT_REACH[1], HEARING_RANGE[1], SMELL_RANGE[1])
"""Grid cell for neighbour searches: the longest sense range any animal can have (100 units)."""
FOUNDER_PLANT_TRIES: int = 50
"""Draws ``populate`` makes to find a founder plant that can pay its way before it takes the last."""


@dataclass(frozen=True)
class WorldConfig:
    """Everything that defines a run besides the organisms put into it."""

    bounds: Bounds = field(default_factory=Bounds)
    seed: int = 0
    traits: TraitRules = DEFAULT_RULES
    """The tuning constants of a run (``TRAIT.3``, ``TRAIT.10``, ``TRAIT.11``): body, behaviour,
    brain costs, reproduction, recovery, plants, sense costs, time, day and sleep, learning, bites,
    corpses and the world's grazing, mating reach, birth scatter and calls."""
    max_animals: int = 1000
    max_plants: int = 5000
    """Safety caps so a run cannot grow without limit; births stop at the cap."""

    @property
    def graze_amount(self) -> float:
        """Biomass an animal can take from a plant in one reference tick (``traits.world``)."""
        return self.traits.world.graze_amount

    @property
    def mating_reach(self) -> float:
        """Two animals mate only if their centres are this close (``traits.world``)."""
        return self.traits.world.mating_reach

    @property
    def birth_scatter(self) -> float:
        """A litter appears within this distance of its mother (``traits.world``)."""
        return self.traits.world.birth_scatter

    @property
    def calls_enabled(self) -> bool:
        """Whether animals can call (``traits.world``); off studies a silent world."""
        return self.traits.world.calls_enabled

    @property
    def attack(self) -> AttackRules:
        """Bites (``BRAIN.10``). Part of the trait rules (``TRAIT.11``)."""
        return self.traits.attack

    @property
    def corpses(self) -> CorpseRules:
        """What the dead leave (``WORLD.12``). Part of the trait rules (``TRAIT.11``)."""
        return self.traits.corpses

    @property
    def sensing(self) -> SensingRules:
        """The constants of the sensing step: light and sleep factors, weak smell, noise."""
        return self.traits.sensing

    @property
    def time_scale(self) -> TimeScale:
        """The tick length and speed of the run: ``traits.time`` as a ``TimeScale``."""
        time = self.traits.time
        return TimeScale(seconds_per_tick=time.seconds_per_tick, speed=time.speed)

    @property
    def day_cycle(self) -> DayCycle | None:
        """Light and night over simulated time; ``None`` means permanent full daylight and no
        sleep. Part of the trait rules."""
        return self.traits.day_cycle

    @property
    def plants(self) -> PlantRules:
        """How crowded soil and shade limit plant growth. Part of the trait rules."""
        return self.traits.plant_limits

    @property
    def sleep(self) -> SleepRules:
        """Who sleeps at night and what sleep does (``WORLD.5``). Part of the trait rules."""
        return self.traits.sleep

    @property
    def learning(self) -> LearningRules | None:
        """Learning during life (``BRAIN.24``): animals log their day and learn when they fall
        asleep; ``None`` turns it off. Part of the trait rules (``TRAIT.10``)."""
        return self.traits.learning

    def with_rules(self, **sections: object) -> WorldConfig:
        """This config with some sections of its trait rules replaced, e.g.
        ``config.with_rules(learning=None)``. Sections that already equal the given value are
        left alone, so a change that changes nothing returns the same config."""
        changes = {k: v for k, v in sections.items() if getattr(self.traits, k) != v}
        if not changes:
            return self
        return replace(self, traits=replace(self.traits, **changes))

    def with_time_scale(self, time_scale: TimeScale) -> WorldConfig:
        """This config with the tick length and speed of ``time_scale``."""
        time = replace(
            self.traits.time, seconds_per_tick=time_scale.seconds_per_tick, speed=time_scale.speed
        )
        return self.with_rules(time=time)

    def __post_init__(self) -> None:
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
        self.senses: Senses = senses if senses is not None else WorldSenses()
        self.rng = random.Random(self.config.seed)
        self.tick: int = 0
        self._next_id: int = 1
        self._animals: dict[int, Animal] = {}
        self._plants: dict[int, Plant] = {}
        self._animal_index = SpatialIndex(INDEX_CELL_SIZE)
        self._plant_index = SpatialIndex(INDEX_CELL_SIZE)
        self._corpses: dict[int, Corpse] = {}
        self._corpse_index = SpatialIndex(INDEX_CELL_SIZE)
        scent_rules = self.config.traits.world.scent
        self.scent: ScentField | None = (
            ScentField(scent_rules, self.dt) if scent_rules.enabled else None
        )
        """Smell trails (``SENSE.20``); ``None`` when the run does not have them."""
        self.ancestry = AncestryBook()
        """Who is whose child, dead animals included, up to a bound (UX.39)."""
        self.max_canopy: float = 0.0
        """Largest canopy radius of any plant added so far; bounds the plant search radius."""
        self.max_body: float = 0.0
        """Largest body radius of any animal added so far."""
        self._sleep_listeners: list[SleepListener] = []
        self._event_listeners: list[EventListener] = []
        self._step_listeners: list[Callable[[StepReport], None]] = []
        self._stepping: bool = False
        self._traced: int | None = None
        self._light: tuple[int, object, float, float | None] | None = None
        """The light of the current tick, kept because every animal's senses ask for it."""
        self.calls: dict[int, tuple[float, float]] = {}
        """Animals calling this tick, by id: (alarm call radius, mating call radius), 0 for none."""
        if self.config.learning is not None:
            self.add_sleep_listener(NightlyLearning())

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
    def dt(self) -> float:
        """How many reference ticks (hours) one tick is: the factor on per-reference-tick rates."""
        return self.time_scale.seconds_per_tick / self.config.traits.time.reference_tick_seconds

    @property
    def simulated_seconds(self) -> float:
        return self.tick * self.config.traits.time.seconds_per_tick

    @property
    def elapsed(self) -> str:
        """Simulated time so far, for example ``3d 04:00:00``."""
        return format_duration(self.simulated_seconds)

    def _light_now(self) -> tuple[float, float | None]:
        """``(daylight, day_phase)`` now. Worked out once a tick: it depends only on the tick and
        the (immutable) rules, and each awake animal's senses ask for it."""
        traits = self.config.traits
        cached = self._light
        if cached is not None and cached[0] == self.tick and cached[1] is traits:
            return cached[2], cached[3]
        cycle = traits.day_cycle
        if cycle is None:
            daylight, phase = 1.0, None
        else:
            seconds = self.simulated_seconds
            daylight, phase = cycle.daylight(seconds), cycle.phase(seconds)
        self._light = (self.tick, traits, daylight, phase)
        return daylight, phase

    @property
    def daylight(self) -> float:
        """Light now, from 0 (midnight) to 1 (noon); always 1 without a day cycle."""
        return self._light_now()[0]

    @property
    def is_night(self) -> bool:
        cycle = self.config.day_cycle
        return False if cycle is None else cycle.is_night(self.simulated_seconds)

    @property
    def day(self) -> int:
        """Midnights passed since the start (0 on the first day)."""
        cycle = self.config.day_cycle
        return 0 if cycle is None else cycle.day_number(self.simulated_seconds)

    @property
    def day_phase(self) -> float | None:
        """The position in the day from 0 (midnight) up to 1, or ``None`` without a day cycle."""
        return self._light_now()[1]

    def edge_vector(self, position: Vec) -> tuple[float, float]:
        """A unit vector from ``position`` toward the nearest wall (the lowest axis, then the low
        side, wins a tie)."""
        best = (math.inf, 0, 0.0)
        for axis, (c, size) in enumerate(zip(position.coords, self.bounds.size)):
            for gap, sign in ((c, -1.0), (size - c, 1.0)):
                if gap < best[0]:
                    best = (gap, axis, sign)
        _, axis, sign = best
        return (sign, 0.0) if axis == 0 else (0.0, sign)

    def edge_state(self, position: Vec) -> tuple[float, tuple[float, float]]:
        """``(edge_distance, edge_vector)`` for ``position`` in one pass over the walls."""
        gap, axis, sign = math.inf, 0, 0.0
        for index, (c, size) in enumerate(zip(position.coords, self.bounds.size)):
            if c < gap:
                gap, axis, sign = c, index, -1.0
            if size - c < gap:
                gap, axis, sign = size - c, index, 1.0
        return gap, ((sign, 0.0) if axis == 0 else (0.0, sign))

    def edge_distance(self, position: Vec) -> float:
        """Distance from ``position`` to the nearest wall."""
        return min(min(c, size - c) for c, size in zip(position.coords, self.bounds.size))

    def add_sleep_listener(self, listener: SleepListener) -> None:
        """Be told, in id order, when an animal falls asleep or wakes (the hook for BRAIN.24)."""
        self._sleep_listeners.append(listener)

    def add_event_listener(self, listener: EventListener) -> None:
        """Be told about every birth, death and mating as it happens (``world/events.py``). Events
        are built only while at least one listener is added."""
        self._event_listeners.append(listener)

    def remove_event_listener(self, listener: EventListener) -> None:
        self._event_listeners.remove(listener)

    def add_step_listener(self, listener: Callable[[StepReport], None]) -> None:
        """Be called with each tick's ``StepReport`` once the step has finished (the statistics
        recorder uses it). Nothing is called, and nothing built, while there is no listener."""
        self._step_listeners.append(listener)

    def remove_step_listener(self, listener: Callable[[StepReport], None]) -> None:
        self._step_listeners.remove(listener)

    def _emit(self, event: WorldEvent) -> None:
        for listener in self._event_listeners:
            listener(event)

    @property
    def _event_tick(self) -> int:
        """The tick events carry: the one the running step will finish as."""
        return self.tick + 1 if self._stepping else self.tick

    # -------------------------------------------------------------------------
    # Read-only views, for the session and the viewers (UX.6)
    # -------------------------------------------------------------------------

    @property
    def plant_count(self) -> int:
        return len(self._plants)

    def animal_views(self) -> list[AnimalView]:
        """A value for every living animal, in id order."""
        dt = self.dt
        return [animal_view(a, dt) for a in self.animals]

    def plant_views(self) -> list[PlantView]:
        return [plant_view(p) for p in self.plants]

    def trait_columns(self, kind: str) -> dict[str, list[float]]:
        """Every living ``"animal"`` or ``"plant"``'s traits and genes, one list per name (see
        ``views.trait_columns``), for the statistics recorder."""
        if kind == "animal":
            return trait_columns(self.animals)
        if kind == "plant":
            return trait_columns(self.plants)
        raise ValueError(f"Unknown kind {kind!r}: expected 'animal' or 'plant'.")

    def corpse_views(self) -> list[CorpseView]:
        return [corpse_view(c) for c in self.corpses]

    def animal_detail(self, animal_id: int) -> AnimalDetail | None:
        """The inspector's picture of one living animal, or ``None`` if there is none by that id."""
        animal = self._animals.get(animal_id)
        return None if animal is None else animal_detail(self, animal)

    def children_of(self, animal_id: int) -> tuple[int, ...]:
        """The ids of the living animals that name ``animal_id`` as a parent, oldest first."""
        return tuple(a.id for a in self.animals if animal_id in a.parents)

    def family_of(self, animal_id: int) -> FamilyView | None:
        """The animal's place in the family tree: ancestors and descendants, dead ones too as far
        as ``ancestry`` remembers them (``None`` for an animal it does not know)."""
        return self.ancestry.family_of(animal_id)

    def trace_brain(self, animal_id: int | None) -> bool:
        """Keep the brain's last inputs, hidden values and outputs for this animal (and stop for
        the one traced before); ``None`` stops tracing. They appear in ``animal_detail`` once its
        brain next runs. Tracing only copies numbers the brain already computed: it changes
        nothing about the run. Returns whether there is such an animal to trace."""
        previous = self._animals.get(self._traced) if self._traced is not None else None
        if previous is not None:
            previous.traits.trace_brain = False
            previous.traits.brain_trace = None
        self._traced = None
        if animal_id is None:
            return True
        animal = self._animals.get(animal_id)
        if animal is None:
            return False
        animal.traits.trace_brain = True
        self._traced = animal_id
        return True

    @property
    def animals(self) -> list[Animal]:
        """Living animals in id order."""
        return [self._animals[i] for i in sorted(self._animals)]

    @property
    def plants(self) -> list[Plant]:
        """Living plants in id order."""
        return [self._plants[i] for i in sorted(self._plants)]

    @property
    def corpses(self) -> list[Corpse]:
        """Corpses in id order."""
        return [self._corpses[i] for i in sorted(self._corpses)]

    def corpses_in_reach(self, position: Vec, reach: float) -> list[tuple[Corpse, float, float]]:
        """Corpses within ``reach`` of ``position``, unordered, each with its centre distance and
        radius."""
        corpses = self._corpses
        return [(corpses[i], d, r) for i, d, r in self._corpse_index.within_reach(position, reach)]

    def animals_near(self, position: Vec, radius: float) -> list[Animal]:
        """Animals whose position is within ``radius`` of ``position`` (as of the last index
        refresh: the start of the tick for the senses), in id order."""
        return [self._animals[i] for i in self._animal_index.query(position, radius)]

    def animals_within(self, position: Vec, radius: float) -> list[tuple[Animal, float]]:
        """Like ``animals_near`` with each animal's distance from ``position``."""
        found = self._animal_index.query_with_distance(position, radius)
        return [(self._animals[i], distance) for i, distance in found]

    def plants_within(self, position: Vec, radius: float) -> list[tuple[Plant, float]]:
        """Like ``plants_near`` with each plant's distance from ``position``."""
        found = self._plant_index.query_with_distance(position, radius)
        return [(self._plants[i], distance) for i, distance in found]

    def plants_in_reach(self, position: Vec, reach: float) -> list[tuple[Plant, float, float]]:
        """Plants whose canopy edge is within ``reach`` of ``position``, unordered, each with its
        centre distance and canopy radius."""
        plants = self._plants
        return [(plants[i], d, r) for i, d, r in self._plant_index.within_reach(position, reach)]

    def animals_in_reach(self, position: Vec, reach: float) -> list[tuple[Animal, float, float]]:
        """Animals whose bodies are within ``reach`` of ``position`` (as of the last index
        refresh), unordered, each with its centre distance and body radius."""
        animals = self._animals
        return [(animals[i], d, r) for i, d, r in self._animal_index.within_reach(position, reach)]

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
        return self._insert_animal(
            AnimalTraits(dna, rules=self.config.traits, dt=self.dt), place, facing, parents
        )

    def _insert_animal(
        self, traits: AnimalTraits, place: Vec, facing: float, parents: tuple[int, ...]
    ) -> Animal:
        animal = Animal(self._new_id(), traits, place, facing, parents)
        self._animals[animal.id] = animal
        self._animal_index.insert(animal.id, animal.position, animal.radius)
        self.max_body = max(self.max_body, animal.radius)
        self.ancestry.born(animal.id, parents, traits.sex, self._event_tick, traits.family_key)
        if self._event_listeners:
            self._emit(
                Born(
                    self._event_tick, "animal", animal.id, place.coords[0], place.coords[1], parents
                )
            )
        return animal

    def add_plant(
        self, dna: DNA, position: Vec | None = None, parents: tuple[int, ...] = ()
    ) -> Plant:
        if len(self._plants) >= self.config.max_plants:
            raise ValueError(f"The world already holds {self.config.max_plants} plants.")
        return self._insert_plant(
            PlantTraits(dna, self.config.traits), self._place(position), parents
        )

    def _insert_plant(self, traits: PlantTraits, place: Vec, parents: tuple[int, ...]) -> Plant:
        plant = Plant(self._new_id(), traits, place, parents)
        self._plants[plant.id] = plant
        self._plant_index.insert(plant.id, plant.position, plant.radius)
        self.max_canopy = max(self.max_canopy, plant.radius)
        if self._event_listeners:
            self._emit(
                Born(self._event_tick, "plant", plant.id, place.coords[0], place.coords[1], parents)
            )
        return plant

    def populate(self, animals: int = 0, plants: int = 0, seeded: bool = True) -> None:
        """Add random organisms at random places (plants first, then animals).

        The animals are a first generation: random bodies with the reproduction and sense genes at
        their starting levels, and the seeded brain (``BRAIN.9``, slightly varied) unless ``seeded``
        is False, which leaves the brains random: those mostly die before they breed. The plants
        are a first generation too: part-grown, of ages spread over part of their life, and less
        poisonous than their genes say (``TraitRules.plant``, ``WORLD.15``).
        """
        grown = self.config.traits.plant
        for _ in range(plants):
            founder = self.add_plant(self._founder_plant())
            founder.traits.establish(
                grown.founder_size, self.rng.random() * grown.founder_age_spread
            )
        for _ in range(animals):
            founder = founder_animal_dna(self.rng)
            self.add_animal(seeded_dna(self.rng, base=founder) if seeded else founder)

    def _founder_plant(self) -> DNA:
        """A random plant that can pay its way (``founder_upkeep_share``): most of the ones that
        cannot would die as seedlings (``WORLD.11``). Gives up after a few draws and takes the last."""
        rules = self.config.traits
        for _ in range(FOUNDER_PLANT_TRIES):
            dna = founder_plant_dna(self.rng)
            if PlantTraits(dna, rules).upkeep_share <= rules.plant.founder_upkeep_share:
                break
        return dna.with_value("toxicity", dna.value("toxicity") * rules.plant.founder_toxicity)

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
        self._stepping = True
        try:
            report = self._step()
        finally:
            self._stepping = False
        for listener in list(self._step_listeners):
            listener(report)
        return report

    def _step(self) -> StepReport:
        animals = self.animals
        plants = self.plants
        self._refresh_animal_index()
        self._collect_calls(animals)
        self._update_sleep(animals)
        sunlight = self.daylight
        self._refresh_competition(plants)
        for plant in plants:
            plant.traits.set_environmental_conditions(sunlight * plant.shade, plant.soil)

        # 1. Sense and decide, all from the same start-of-tick world. Sleepers do not.
        for animal in animals:
            if not animal.asleep:
                if self._newly_touched(animal):
                    animal.traits.interrupt()
                decision = animal.traits.cached_decision(self.rng)
                if decision is None:
                    decision = animal.traits.think(self.senses.perceive(self, animal), self.rng)
                animal.last_decision = decision

        # 2. Live, move and eat (or sleep).
        dt = self.dt
        for animal in animals:
            if animal.asleep:
                self._rest(animal)
                continue
            decision = animal.last_decision
            assert decision is not None
            animal.traits.update_metabolism_and_aging(decision.speed, dt)
            if not animal.is_alive:
                continue
            animal.heading = wrap_angle(
                animal.heading - decision.turn * animal.traits.base_turn_rate * dt
            )
            step_length = decision.speed * animal.traits.current_max_speed * dt
            animal.position = self.bounds.clamp(
                animal.position + Vec.from_angle(animal.heading, step_length)
            )
            if (
                decision.eats_or_attacks
                and not self._graze(animal, dt)
                and not self._scavenge(animal, dt)
            ):
                self._attack(animal, dt)

        if self.scent is not None:
            self._lay_scent(dt)

        # 3. Mate, then deliver the litters that are due.
        self._refresh_animal_index()
        self._mate(animals)
        animal_births = self._deliver(animals)

        # 4. Plants grow and seed.
        plant_births = 0
        for plant in plants:
            traits = plant.traits
            traits.update_growth_and_metabolism(dt)
            if traits.is_alive and traits.flag_ready_to_seed:
                plant_births += self._seed(plant)

        # 5. Remove the dead and advance the clock.
        self._rot_corpses(dt)
        self._leave_corpses()
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

    def _newly_touched(self, animal: Animal) -> bool:
        """Whether something is in contact with an animal that was not when its brain last ran
        (``BRAIN.22``). It lets touch cut the decision interval short without sensing every tick, and
        costs a neighbour query only for animals that are between decisions."""
        traits = animal.traits
        if traits.decided_touch or traits.looks_every_tick:
            return False
        # Imported here because ``sensing`` itself imports from this package.
        from evolution_simulator.sensing import organs_from_traits

        reach = organs_from_traits(traits).touch_reach
        if reach <= 0.0:
            return False
        body = animal.radius
        position = animal.position
        for plant, centre, canopy in self.plants_in_reach(position, reach + body):
            if centre - body - canopy <= reach:
                return True
        for other, centre, radius in self.animals_in_reach(position, reach + body):
            if other is not animal and centre - body - radius <= reach:
                return True
        return False

    def _refresh_competition(self, plants: list[Plant]) -> None:
        """Update the shade and soil of this tick's share of the plants (see ``PlantRules``)."""
        rules = self.config.plants
        ground = math.pi * rules.neighbourhood**2
        for plant in plants:
            if plant.id % rules.refresh_interval != self.tick % rules.refresh_interval:
                continue
            biomass = 0.0
            shade_load = 0.0
            reach = max(rules.neighbourhood, self.max_canopy)
            for other, distance in self.plants_within(plant.position, reach):
                if other is plant:
                    continue
                if distance <= rules.neighbourhood:
                    biomass += other.traits.current_biomass
                if (
                    distance < other.radius
                    and other.traits.current_biomass > plant.traits.current_biomass
                ):
                    shade_load += 1.0 - distance / other.radius
            plant.soil = max(0.0, 1.0 - biomass / (ground * rules.capacity))
            plant.shade = 1.0 / (1.0 + rules.shade_strength * shade_load)

    def _collect_calls(self, animals: list[Animal]) -> None:
        """Work out who calls this tick, from the decisions of the last one, and charge them.

        An awake animal whose brain said "alarm call" or "mating call" and that has a call radius
        (the encoder gene) and the energy pays ``call_energy_cost`` per call and is heard this
        tick by the animals whose hearing reaches it. Acting on the rest of the brain's outputs is
        ``BRAIN.10``. Does nothing unless ``WorldConfig.calls_enabled``.
        """
        self.calls = {}
        if not self.config.calls_enabled:
            return
        for animal in animals:
            decision = animal.last_decision
            traits = animal.traits
            if animal.asleep or decision is None or not animal.is_alive:
                continue
            if traits.call_radius <= 0.0:
                continue
            alarm = traits.call_radius if decision.calls_alarm else 0.0
            mating = traits.call_radius if decision.calls_for_mate else 0.0
            cost = traits.call_energy_cost * ((alarm > 0.0) + (mating > 0.0))
            if cost > 0.0 and traits.current_energy > cost:
                traits.current_energy -= cost
                self.calls[animal.id] = (alarm, mating)

    def _wake_by_alarm(self) -> None:
        """Sleepers who hear an alarm call loudly enough are disturbed and stay awake until the
        next day (SENSE.7: a sleeper's hearing works at the sleep factor)."""
        threshold = self.config.sleep.alarm_wakes_above
        hearing_factor = self.config.sensing.sleep_factor("hearing")
        for caller_id, (alarm, _) in self.calls.items():
            if alarm <= 0.0:
                continue
            caller = self._animals[caller_id]
            for other, centre in self.animals_within(
                caller.position, alarm + caller.radius + self.max_body
            ):
                if not other.asleep or other.disturbed:
                    continue
                surface = centre - caller.radius - other.radius
                hears = other.traits.current_hearing_range * hearing_factor
                if surface <= hears and surface < alarm and 1.0 - surface / alarm >= threshold:
                    other.disturbed = True

    def _update_sleep(self, animals: list[Animal]) -> None:
        """Put animals to sleep at night and wake them in the morning, when starving, or when an
        alarm call disturbs them."""
        night = self.is_night
        self._update_tiredness(animals)
        starving_below = self.config.sleep.starving_below
        if night:
            self._wake_by_alarm()
        for animal in animals:
            if not animal.is_alive:
                continue
            traits = animal.traits
            if not night:
                animal.disturbed = False
            hungry = traits.current_energy < starving_below * traits.max_energy
            should_sleep = night and not hungry and not animal.disturbed
            if should_sleep and not animal.asleep:
                animal.asleep = True
                animal.last_decision = None
                traits.reset_behaviour()
                for listener in self._sleep_listeners:
                    listener.fell_asleep(self, animal)
            elif animal.asleep and not should_sleep:
                animal.asleep = False
                for listener in self._sleep_listeners:
                    listener.woke(self, animal)

    def _update_tiredness(self, animals: list[Animal]) -> None:
        """Count the time each animal has been awake and hand it to the brain as a share of a day
        (``SENSE.14``). Without a day cycle nobody sleeps, so nobody is tired."""
        cycle = self.config.day_cycle
        day = (
            0.0
            if cycle is None
            else cycle.length_seconds / self.config.traits.time.reference_tick_seconds
        )
        dt = self.dt
        for animal in animals:
            if animal.asleep:
                animal.awake_time = 0.0
            else:
                animal.awake_time += dt
            animal.traits.tiredness = min(1.0, animal.awake_time / day) if day > 0.0 else 0.0

    def _rest(self, animal: Animal) -> None:
        """One tick of sleep: age as usual, burn less energy and regain some."""
        rules = self.config.sleep
        traits = animal.traits
        dt = self.dt
        traits.update_metabolism_and_aging(0.0, dt)
        if traits.is_alive:
            saved = traits.energy_burn * (1.0 - rules.metabolism_factor)
            regained = rules.energy_regain * traits.max_energy * traits.rest_regain_factor
            gained = (saved + regained) * dt
            traits.current_energy = min(traits.max_energy, traits.current_energy + gained)

    def _refresh_animal_index(self) -> None:
        self._animal_index.clear()
        for animal in self.animals:
            self._animal_index.insert(animal.id, animal.position, animal.radius)

    def _graze(self, animal: Animal, dt: float) -> bool:
        """Eat from the plant the animal touches, if any. Returns whether it touched one (even if
        it refused the poison), so the brain's "eat or attack" is spent on the plant."""
        reach = animal.radius + self.max_canopy
        best: Plant | None = None
        best_distance = math.inf
        for plant in self.plants_near(animal.position, reach):
            distance = animal.position.distance_to(plant.position)
            if distance <= animal.radius + plant.radius and (distance < best_distance):
                best, best_distance = plant, distance
        if best is None:
            return False
        if animal.traits.inspect_food(best.traits.toxicity, self.rng):
            return True  # it tasted the poison and refused
        eaten, toxicity = best.traits.graze(self.config.graze_amount * dt)
        animal.traits.feed(eaten, is_meat=False, toxicity=toxicity, dt=dt)
        if self._event_listeners:
            self._emit(Ate(self._event_tick, animal.id, "plant", best.id, eaten))
        return True

    def _attack(self, animal: Animal, dt: float) -> None:
        """Bite the nearest animal in contact that this one counts as prey. A sleeper is woken by
        the bite; the one that kills eats the meat. A bite does its damage per reference tick, so a
        tick of ``dt`` reference ticks does ``dt`` times as much."""
        rules = self.config.attack
        reach = animal.radius + self.max_body
        target: Animal | None = None
        best_distance = math.inf
        for other, _ in self.animals_within(animal.position, reach):
            if other is animal or not other.is_alive:
                continue
            distance = animal.position.distance_to(other.position)
            if (
                distance <= animal.radius + other.radius
                and distance < best_distance
                and classify(animal, other) == "prey"
            ):
                target, best_distance = other, distance
        if target is None:
            return
        traits = animal.traits
        target.traits.apply_damage(
            rules.bite(traits.effective_carn_eff, traits.mass, target.traits.mass) * dt,
            DeathCause.PREDATION,
        )
        target.disturbed = True
        target.killed_by = animal.id

    def _scavenge(self, animal: Animal, dt: float) -> bool:
        """Eat from the nearest corpse the animal touches, if it can digest meat. Returns whether
        it touched one, so the brain's "eat or attack" is spent on the meal and not on a bite."""
        if animal.traits.effective_carn_eff <= MEAT_EATER:
            return False
        found = [
            (distance, corpse.id, corpse)
            for corpse, distance, radius in self.corpses_in_reach(animal.position, animal.radius)
        ]
        if not found:
            return False
        corpse = min(found, key=lambda item: item[:2])[2]
        taken = min(corpse.meat, self.config.corpses.bite * dt)
        corpse.meat -= taken
        animal.traits.feed(taken, is_meat=True, dt=dt)
        if self._event_listeners:
            self._emit(Ate(self._event_tick, animal.id, "corpse", corpse.id, taken))
        return True

    def _leave_corpses(self) -> None:
        """Every animal that died this tick leaves a corpse where it fell."""
        rules = self.config.corpses
        for animal in self.animals:
            if animal.is_alive:
                continue
            meat = rules.meat(animal.traits.max_energy)
            if meat < rules.gone_below:
                continue
            corpse = Corpse(
                self._new_id(), animal.position, animal.radius, animal.traits.mass, meat
            )
            self._corpses[corpse.id] = corpse
            self._corpse_index.insert(corpse.id, corpse.position, corpse.radius)

    def _lay_scent(self, dt: float) -> None:
        """Animals and corpses add to the scent of the cell they are in (``SENSE.20``), and now and
        then trails too weak to matter are dropped."""
        field = self.scent
        assert field is not None
        rules = field.rules
        tick = self.tick
        every = rules.deposit_interval
        amount = rules.deposit * dt * every
        if amount > 0.0:
            for animal in self.animals:
                if (tick + animal.id) % every == 0 and animal.is_alive:
                    traits = animal.traits
                    field.deposit(
                        ANIMAL,
                        animal.position,
                        amount,
                        tick,
                        traits.mass,
                        traits.effective_carn_eff > MEAT_EATER,
                        animal.id,
                    )
        amount = rules.carrion_deposit * dt
        if amount > 0.0:
            for corpse in self.corpses:
                field.deposit(CARRION, corpse.position, amount, tick, corpse.mass, False, corpse.id)
        if tick % rules.purge_interval == 0:
            field.purge(tick)

    def _rot_corpses(self, dt: float) -> None:
        """Corpses lose meat to rot and are removed when almost nothing is left."""
        rules = self.config.corpses
        keep = 0.5 ** (dt / rules.rot_halflife)
        for corpse in self.corpses:
            corpse.meat *= keep
            if corpse.meat < rules.gone_below:
                del self._corpses[corpse.id]
                self._corpse_index.remove(corpse.id)

    def _mate(self, animals: list[Animal]) -> int:
        """Pair the willing animals off and try each pair. Returns the matings that took."""
        cfg = self.config
        willing = [
            a
            for a in animals
            if a.is_alive
            and not a.asleep
            and a.last_decision is not None
            and a.last_decision.seeks_mating
            and a.traits.can_mate
        ]
        willing_ids = {a.id for a in willing}
        paired: set[int] = set()
        conceived = 0
        for a in willing:
            if a.id in paired:
                continue
            reachable = [
                b
                for b in self.animals_near(a.position, cfg.mating_reach)
                if b.id not in paired and b.id in willing_ids
            ]
            best = choose_mate(a, reachable)
            if best is None:
                continue
            paired.update((a.id, best.id))
            father, mother = (a, best) if a.traits.sex == 0 else (best, a)
            result = AnimalTraits.mate(father.traits, mother.traits, self.rng)
            if result is MatingResult.CONCEIVED:
                mother.partner = father.id
                conceived += 1
            if result is not MatingResult.REFUSED and self._event_listeners:
                self._emit(
                    Mated(self._event_tick, father.id, mother.id, result is MatingResult.CONCEIVED)
                )
        return conceived

    def _deliver(self, animals: list[Animal]) -> int:
        """Birth the litters that are due, in id order of the mothers. A litter is born next to its
        mother as far as the animal cap allows, and only if both parents can pay; if not, she goes
        on carrying it and tries again next tick. Returns the number of young born."""
        born = 0
        for mother in animals:
            pregnancy = mother.traits.pregnancy
            if not mother.is_alive or pregnancy is None or not pregnancy.due:
                continue
            room = self.config.max_animals - len(self._animals)
            count = min(pregnancy.litter, room)
            if count <= 0:
                continue
            litter = [
                AnimalTraits(genome, rules=self.config.traits, dt=self.dt)
                for genome in pregnancy.children[:count]
            ]
            if not AnimalTraits.give_birth(mother.traits, litter):
                continue
            parents = (mother.id,) if mother.partner is None else (mother.partner, mother.id)
            mother.partner = None
            for child in litter:
                position = self._scatter(mother.position, self.config.birth_scatter)
                facing = self.rng.uniform(-math.pi, math.pi)
                self._insert_animal(child, position, facing, parents)
            born += count
        return born

    def _seed(self, plant: Plant) -> int:
        """Drop seeds. The plant pays for as many as its budget allows (up to its clutch gene), each
        seed starts with the plant's ``seed_provision`` of its own full size, and a plant that cannot
        place any seed spends nothing."""
        count = min(plant.traits.seed_capacity(), self.config.max_plants - len(self._plants))
        if count <= 0:
            return 0
        seeds = [
            PlantTraits(plant.traits.dna.reproduce(None, self.rng), self.config.traits)
            for _ in range(count)
        ]
        plant.traits.launch_seeds(seeds)
        for traits in seeds:
            spot = self._scatter(plant.position, plant.traits.dispersal_radius)
            self._insert_plant(traits, spot, (plant.id,))
        return count

    def _scatter(self, centre: Vec, radius: float) -> Vec:
        """A random point within ``radius`` of ``centre`` (2D), kept inside the world."""
        angle = self.rng.uniform(-math.pi, math.pi)
        distance = radius * math.sqrt(self.rng.random())
        offset = Vec.from_angle(angle, distance)
        if centre.dimensions != 2:
            raise NotImplementedError("Scattering is 2D for now.")
        return self.bounds.clamp(centre + offset)

    def _remove_dead(self, organisms: dict, index: SpatialIndex) -> int:
        dead = sorted(i for i, o in organisms.items() if not o.is_alive)
        for organism_id in dead:
            organism = organisms.pop(organism_id)
            if organism_id in index:
                index.remove(organism_id)
            if isinstance(organism, Animal):
                cause = organism.traits.death_cause or DeathCause.DAMAGE
                self.ancestry.died(organism_id, self._event_tick, cause)
            if self._event_listeners:
                self._emit_death(organism)
        return len(dead)

    def _emit_death(self, organism: Animal | Plant) -> None:
        traits = organism.traits
        cause = traits.death_cause or DeathCause.DAMAGE
        killer = (
            organism.killed_by
            if isinstance(organism, Animal) and cause is DeathCause.PREDATION
            else None
        )
        x, y = organism.position.coords[:2]
        self._emit(
            Died(
                self._event_tick, organism.kind, organism.id, x, y, cause, killer, traits.age_ticks
            )
        )

    # -------------------------------------------------------------------------
    # Checking repeatability
    # -------------------------------------------------------------------------

    def state_digest(self) -> str:
        """A hash of the state that decides what happens next: tick, random generator, and every
        organism's place, energy, health, age, sleep, pregnancy, learned changes and genome. Two
        runs that are really the same give the same digest. It is a check, not a full copy: whatever
        else a world holds is saved by ``persistence.py`` (``UX.9``), which has to learn about any
        new state."""
        parts: list[str] = [str(self.tick), repr(self.rng.getstate())]
        for animal in self.animals:
            traits = animal.traits
            pregnancy = traits.pregnancy
            learner = traits.learner
            parts.append(
                f"A{animal.id}|{animal.position.coords!r}|{animal.heading!r}|"
                f"{traits.current_energy!r}|{traits.current_health!r}|{traits.dna}|"
                f"{animal.asleep}|{animal.disturbed}|{animal.awake_time!r}|{animal.partner}|{traits.age_ticks}|"
                f"{traits.matings}|{traits.mating_cooldown!r}|"
                f"{None if pregnancy is None else (pregnancy.litter, pregnancy.remaining)!r}|"
                f"{None if learner is None else (learner.offsets, learner.open_decisions)!r}"
            )
        for plant in self.plants:
            traits = plant.traits
            parts.append(
                f"P{plant.id}|{plant.position.coords!r}|{traits.current_biomass!r}|{traits.dna}|"
                f"{traits.lived_ticks!r}|{traits.seed_cooldown!r}"
            )
        for corpse in self.corpses:
            parts.append(f"C{corpse.id}|{corpse.position.coords!r}|{corpse.meat!r}")
        if self.scent is not None:
            parts.append(f"S{self.scent.records()!r}")
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()
