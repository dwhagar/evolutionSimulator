"""Helpers for the world tests: genomes with chosen genes and brains with fixed behaviour."""

from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, BRAIN_GENE, PLANT_LAYOUT
from evolution_simulator.world import TimeScale, Vec, World, WorldConfig

BRAIN_SIZE = BRAIN_GENE.count
ANIMAL_BASE = DNA(ANIMAL_LAYOUT, "1" * ANIMAL_LAYOUT.length)
PLANT_BASE = DNA(PLANT_LAYOUT, "1" * PLANT_LAYOUT.length)


def animal_dna(brain: dict[str, float] | None = None, **genes: str) -> DNA:
    """An animal genome of all 1s with the named genes set to the given digit strings.

    ``brain`` sets the six output biases (turn, speed, eat, mate, alarm, call) of an otherwise flat
    brain: use +-2 for "always" and "never". Without it the brain is left as the base genome's.
    """
    dna = ANIMAL_BASE
    for gene_id, digits in genes.items():
        dna = dna.replaced(gene_id, digits)
    if brain is not None:
        biases = [
            brain.get(name, -2.0) for name in ("turn", "speed", "eat", "mate", "alarm", "call")
        ]
        values = [0.0] * (BRAIN_SIZE - 6) + biases
        dna = dna.replaced("brain", BRAIN_GENE.encode(values))
    return dna


def plant_dna(**genes: str) -> DNA:
    dna = PLANT_BASE
    for gene_id, digits in genes.items():
        dna = dna.replaced(gene_id, digits)
    return dna


def grown(*animals):
    """Let animals breed now: a newborn is a juvenile for 6% of its lifespan first (`REPRO.8`)."""
    for animal in animals:
        animal.traits.mating_cooldown = 0.0
        animal.traits._update_needs_and_drives()
    return animals


HOURLY = TimeScale(seconds_per_tick=3600.0)
"""One tick is one reference tick (an hour), so per-tick rates apply as they are written."""


def hourly_world(seed: int = 0, **config) -> World:
    """A world whose tick is an hour and that has no night, so reproduction tests see rates as
    written and nobody sleeps."""
    config.setdefault("time_scale", HOURLY)
    config.setdefault("day_cycle", None)
    return World(WorldConfig(seed=seed, **config))


LOVING = {"speed": -2.0, "mate": 2.0}
"""A brain that stays nearly still and always wants a mate."""


def lover_dna(sex: int, **genes: str) -> DNA:
    """A mate-seeking animal of the given sex digit (0 or 1, or 2 or 3 to change the drive)."""
    return animal_dna(brain=LOVING, sex_strategy=str(sex), **genes)


def breeding_pair(world: World, x: float = 500.0, gap: float = 1.0, **genes: str):
    """A grown sex-0 and a grown sex-1 lover side by side; returns (father, mother)."""
    father = world.add_animal(lover_dna(0, **genes), Vec.of(x, 500), heading=0.0)
    mother = world.add_animal(lover_dna(1, **genes), Vec.of(x + gap, 500), heading=0.0)
    grown(father, mother)
    return father, mother
