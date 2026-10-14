"""The world: space, time, the step loop and the senses that connect organisms to it.

Modules: ``vector`` (positions), ``bounds`` (WORLD.4), ``timescale`` (WORLD.3), ``spatial`` (finding
neighbours), ``organisms``, ``senses`` (swappable) and ``world`` (WORLD.2).
"""

from evolution_simulator.world.bounds import Bounds
from evolution_simulator.world.organisms import Animal, Plant
from evolution_simulator.world.senses import BasicSenses, Senses
from evolution_simulator.world.timescale import (
    SPEED_PRESETS,
    Pacer,
    TimeScale,
    format_duration,
)
from evolution_simulator.world.vector import Vec
from evolution_simulator.world.world import StepReport, World, WorldConfig

__all__ = [
    "SPEED_PRESETS",
    "Animal",
    "BasicSenses",
    "Bounds",
    "Pacer",
    "Plant",
    "Senses",
    "StepReport",
    "TimeScale",
    "Vec",
    "World",
    "WorldConfig",
    "format_duration",
]
