"""The world: space, time, the step loop and the senses that connect organisms to it.

Modules: ``vector`` (positions), ``bounds`` (WORLD.4), ``timescale`` (WORLD.3), ``spatial`` (finding
neighbours), ``daycycle`` and ``sleep`` (WORLD.5), ``organisms``, ``combat`` (attacks, BRAIN.10), ``corpses`` (what the dead leave, WORLD.12), ``mating`` (who mates with
whom, REPRO.4), ``events`` and ``views`` (what listeners and viewers may read, UX.6), ``senses``
(swappable), ``persistence`` (save and load, UX.9) and ``world`` (WORLD.2).
"""

from evolution_simulator.config import DayCycle, PlantRules
from evolution_simulator.world.bounds import Bounds
from evolution_simulator.world.combat import AttackRules
from evolution_simulator.world.corpses import Corpse, CorpseRules
from evolution_simulator.world.events import Ate, Born, Died, EventListener, Mated, WorldEvent
from evolution_simulator.world.organisms import Animal, Plant
from evolution_simulator.world.persistence import SaveFormatError, load_world, save_world
from evolution_simulator.world.senses import Senses, WorldSenses
from evolution_simulator.world.sleep import SleepListener, SleepRules
from evolution_simulator.world.timescale import (
    SPEED_PRESETS,
    Pacer,
    TimeScale,
    format_duration,
)
from evolution_simulator.world.vector import Vec
from evolution_simulator.world.views import (
    ANIMAL_FIELDS,
    CORPSE_FIELDS,
    PLANT_FIELDS,
    AnimalDetail,
    AnimalView,
    CorpseView,
    PlantView,
)
from evolution_simulator.world.world import StepReport, World, WorldConfig

__all__ = [
    "ANIMAL_FIELDS",
    "CORPSE_FIELDS",
    "PLANT_FIELDS",
    "SPEED_PRESETS",
    "Animal",
    "AnimalDetail",
    "AnimalView",
    "Ate",
    "AttackRules",
    "Born",
    "Bounds",
    "Corpse",
    "CorpseRules",
    "CorpseView",
    "DayCycle",
    "Died",
    "EventListener",
    "Mated",
    "Pacer",
    "Plant",
    "PlantRules",
    "PlantView",
    "SaveFormatError",
    "Senses",
    "SleepListener",
    "SleepRules",
    "StepReport",
    "TimeScale",
    "Vec",
    "World",
    "WorldConfig",
    "WorldEvent",
    "WorldSenses",
    "format_duration",
    "load_world",
    "save_world",
]
