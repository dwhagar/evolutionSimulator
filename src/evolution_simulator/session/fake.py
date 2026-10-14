"""A made-up simulation for building and testing the screens (UX.6).

``FakeSimulation`` has the same face as ``World`` as far as the session and the viewers see it
(the ``Simulation`` protocol) but does no biology: plants stand still and breathe, animals wander
in smooth loops, and the animal count follows a scripted curve (a slow sine wave), with births and
deaths announced as events with causes on the way. It costs almost nothing per tick, is exactly
repeatable from its seed, and needs no genomes, so a window can be built and tested without
waiting for a simulation, and the tests of ``Session`` run the same cases against it and the real
world.

The creature the inspector shows is made up too: a plausible body, a decision, and a brain trace of
the right sizes (``INPUT_NAMES``, ``OUTPUT_NAMES``).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from evolution_simulator.brain_adapter import INPUT_NAMES, OUTPUT_NAMES, BrainDecision, BrainTrace
from evolution_simulator.deaths import DeathCause
from evolution_simulator.world.bounds import Bounds
from evolution_simulator.world.daycycle import DayCycle
from evolution_simulator.world.events import Born, Died, EventListener, WorldEvent
from evolution_simulator.world.timescale import TimeScale, format_duration
from evolution_simulator.world.views import (
    AnimalDetail,
    AnimalView,
    CorpseView,
    PlantView,
)
from evolution_simulator.world.world import StepReport

FAKE_HIDDEN = 8
"""Hidden neurons in the made-up brain trace."""

_CAUSES = (DeathCause.STARVATION, DeathCause.OLD_AGE, DeathCause.PREDATION, DeathCause.POISON)


@dataclass
class _Animal:
    id: int
    x: float
    y: float
    heading: float
    radius: float
    turn: float
    speed: float
    phase: float
    sex: int
    diet: float
    age_ticks: int = 0


class FakeSimulation:
    """``animals`` and ``plants`` are the starting counts; the animal count then swings by a third
    of ``animals`` either way over ``period`` ticks. ``seed`` fixes everything."""

    def __init__(
        self,
        animals: int = 120,
        plants: int = 600,
        *,
        seed: int = 0,
        size: tuple[float, float] = (1000.0, 1000.0),
        seconds_per_tick: float = 3600.0,
        period: int = 600,
    ) -> None:
        self._rng = random.Random(seed)
        self._bounds = Bounds(size)
        self._time_scale = TimeScale(seconds_per_tick=seconds_per_tick)
        self._cycle = DayCycle()
        self._base = animals
        self._period = period
        self._tick = 0
        self._next_id = 1
        self._animals: dict[int, _Animal] = {}
        self._plants: list[PlantView] = []
        self._corpses: dict[int, CorpseView] = {}
        self._listeners: list[EventListener] = []
        self._traced: int | None = None
        self._trace_rng = random.Random(seed + 1)
        for _ in range(plants):
            self._plants.append(
                PlantView(
                    self._take_id(),
                    self._rng.uniform(0.0, size[0]),
                    self._rng.uniform(0.0, size[1]),
                    self._rng.uniform(1.0, 4.0),
                    self._rng.uniform(0.2, 1.0),
                    self._rng.random() < 0.1,
                )
            )
        for _ in range(animals):
            self._add_animal(announce=False)

    # -------------------------------------------------------------------------
    # The Simulation protocol
    # -------------------------------------------------------------------------

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def bounds(self) -> Bounds:
        return self._bounds

    @property
    def time_scale(self) -> TimeScale:
        return self._time_scale

    @property
    def simulated_seconds(self) -> float:
        return self._time_scale.simulated_seconds(self._tick)

    @property
    def elapsed(self) -> str:
        return format_duration(self.simulated_seconds)

    @property
    def day(self) -> int:
        return self._cycle.day_number(self.simulated_seconds)

    @property
    def daylight(self) -> float:
        return self._cycle.daylight(self.simulated_seconds)

    @property
    def is_night(self) -> bool:
        return self._cycle.is_night(self.simulated_seconds)

    @property
    def plant_count(self) -> int:
        return len(self._plants)

    def add_event_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def remove_event_listener(self, listener: EventListener) -> None:
        self._listeners.remove(listener)

    def animal_views(self) -> list[AnimalView]:
        return [self._view(a) for a in self._animals.values()]

    def plant_views(self) -> list[PlantView]:
        return list(self._plants)

    def corpse_views(self) -> list[CorpseView]:
        return list(self._corpses.values())

    def trace_brain(self, animal_id: int | None) -> bool:
        if animal_id is not None and animal_id not in self._animals:
            self._traced = None
            return False
        self._traced = animal_id
        return True

    def animal_detail(self, animal_id: int) -> AnimalDetail | None:
        animal = self._animals.get(animal_id)
        if animal is None:
            return None
        view = self._view(animal)
        rng = self._trace_rng
        brain = None
        if self._traced == animal_id:
            inputs = tuple(rng.uniform(0.0, 1.0) for _ in INPUT_NAMES)
            hidden = tuple(rng.uniform(-1.0, 1.0) for _ in range(FAKE_HIDDEN))
            proposal = tuple(rng.uniform(0.0, 1.0) for _ in OUTPUT_NAMES)
            brain = BrainTrace(inputs, hidden, proposal, proposal)
        turn = math.sin(animal.phase + self._tick * animal.turn)
        return AnimalDetail(
            tick=self._tick,
            id=animal.id,
            alive=True,
            x=animal.x,
            y=animal.y,
            heading=animal.heading,
            radius=animal.radius,
            sex=animal.sex,
            asleep=view.asleep,
            pregnant=view.pregnant,
            litter=2 if view.pregnant else 0,
            ready_to_mate=view.ready_to_mate,
            age_ticks=animal.age_ticks,
            age_ratio=view.age_ratio,
            energy=view.energy_ratio * 100.0,
            max_energy=100.0,
            health=view.health_ratio * 50.0,
            max_health=50.0,
            vitality=1.0 - view.age_ratio,
            mass=animal.radius**2,
            diet=animal.diet,
            matings=0,
            parents=(),
            partner=None,
            decision=BrainDecision(turn, animal.speed, 0.0, 0.0, 0.0, 0.0),
            brain=brain,
            traits={"speed": animal.speed, "size": animal.radius},
            genome="0123" * 8,
        )

    def step(self) -> StepReport:
        self._tick += 1
        births = deaths = 0
        for animal in list(self._animals.values()):
            animal.age_ticks += 1
            animal.heading = math.atan2(
                math.sin(animal.heading + animal.turn), math.cos(animal.heading + animal.turn)
            )
            step = animal.speed * 5.0
            animal.x = min(
                self._bounds.size[0], max(0.0, animal.x + math.cos(animal.heading) * step)
            )
            animal.y = min(
                self._bounds.size[1], max(0.0, animal.y + math.sin(animal.heading) * step)
            )
        wanted = round(self._base * (1.0 + math.sin(math.tau * self._tick / self._period) / 3.0))
        while len(self._animals) < wanted:
            self._add_animal(announce=True)
            births += 1
        while len(self._animals) > wanted:
            victim_id = next(iter(self._animals))
            self._kill(victim_id)
            deaths += 1
        return StepReport(self._tick, animal_births=births, animal_deaths=deaths)

    # -------------------------------------------------------------------------
    # Making things up
    # -------------------------------------------------------------------------

    def _take_id(self) -> int:
        organism_id = self._next_id
        self._next_id += 1
        return organism_id

    def _emit(self, event: WorldEvent) -> None:
        for listener in self._listeners:
            listener(event)

    def _add_animal(self, *, announce: bool) -> None:
        rng = self._rng
        size = self._bounds.size
        animal = _Animal(
            id=self._take_id(),
            x=rng.uniform(0.0, size[0]),
            y=rng.uniform(0.0, size[1]),
            heading=rng.uniform(-math.pi, math.pi),
            radius=rng.uniform(0.5, 1.5),
            turn=rng.uniform(-0.1, 0.1),
            speed=rng.uniform(0.1, 1.0),
            phase=rng.uniform(0.0, math.tau),
            sex=rng.randrange(2),
            diet=rng.random(),
        )
        self._animals[animal.id] = animal
        if announce and self._listeners:
            self._emit(Born(self._tick, "animal", animal.id, animal.x, animal.y))

    def _kill(self, animal_id: int) -> None:
        animal = self._animals.pop(animal_id)
        cause = _CAUSES[animal_id % len(_CAUSES)]
        if self._listeners:
            self._emit(
                Died(
                    self._tick,
                    "animal",
                    animal.id,
                    animal.x,
                    animal.y,
                    cause,
                    None,
                    animal.age_ticks,
                )
            )
        corpse = CorpseView(self._take_id(), animal.x, animal.y, animal.radius, 50.0)
        self._corpses[corpse.id] = corpse
        if len(self._corpses) > 20:
            del self._corpses[next(iter(self._corpses))]

    def _view(self, animal: _Animal) -> AnimalView:
        wave = 0.5 + 0.5 * math.sin(animal.phase + self._tick * 0.05)
        age = min(1.0, animal.age_ticks / 2000.0)
        return AnimalView(
            animal.id,
            animal.x,
            animal.y,
            animal.heading,
            animal.radius,
            wave,
            1.0 - 0.3 * wave,
            age,
            animal.diet,
            self.is_night and animal.id % 3 == 0,
            animal.sex == 1 and wave > 0.8,
            wave > 0.5,
            animal.id % 7 == 0,
            animal.sex,
        )
