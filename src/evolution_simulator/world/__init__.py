"""The world: space, time, the step loop and the senses that connect organisms to it.

Modules: ``vector`` (positions), ``bounds`` (WORLD.4), ``timescale`` (WORLD.3), ``spatial`` (finding
neighbours), ``daycycle`` and ``sleep`` (WORLD.5), ``organisms``, ``combat`` (attacks, BRAIN.10), ``corpses`` (what the dead leave, WORLD.12), ``mating`` (who mates with
whom, REPRO.4), ``senses`` (swappable) and ``world`` (WORLD.2).
"""

from evolution_simulator.world.bounds import Bounds
from evolution_simulator.world.combat import AttackRules
from evolution_simulator.world.corpses import Corpse, CorpseRules
from evolution_simulator.world.daycycle import DayCycle
from evolution_simulator.world.organisms import Animal, Plant
from evolution_simulator.world.senses import Senses, WorldSenses
from evolution_simulator.world.sleep import SleepListener, SleepRules
from evolution_simulator.world.timescale import (
    SPEED_PRESETS,
    Pacer,
    TimeScale,
    format_duration,
)
from evolution_simulator.world.vector import Vec
from evolution_simulator.world.world import PlantRules, StepReport, World, WorldConfig

__all__ = [
    "SPEED_PRESETS",
    "Animal",
    "AttackRules",
    "Bounds",
    "Corpse",
    "CorpseRules",
    "DayCycle",
    "Pacer",
    "Plant",
    "PlantRules",
    "Senses",
    "SleepListener",
    "SleepRules",
    "StepReport",
    "TimeScale",
    "Vec",
    "World",
    "WorldConfig",
    "WorldSenses",
    "format_duration",
]
