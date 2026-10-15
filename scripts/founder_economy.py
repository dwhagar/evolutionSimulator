"""Runs a seeded first generation and reports whether it feeds and breeds (``WORLD.15``).

Run ``python scripts/founder_economy.py [name=value ...]``. A name with a dot overrides a rule in the
``TraitRules`` tree (``body.kinetic_burn=0.02``, ``world.graze_amount=20``); the others are options:

    seeds=1,2,3 ticks=3000 animals=100 plants=800 size=1000 step=500
    lvl.fertility=0.3 lvl.parenting=0.1   founder reproduction genes (``FOUNDER_LEVELS``)
    burn=0.1                               scale on every animal's whole upkeep bill (what an animal
                                           burns per hour; sleeping saves against the same bill)
    tox=0.3                                scale on the founder plants' toxicity gene
    grown=0.7 agespread=0.5                founder plants start at this share of full size and as old
                                           as up to this share of their lifespan, not as seedlings
    account=1                              print energy in and out per animal tick, in blocks

For each seed it prints the animals alive, births and the plants every ``step`` ticks, and how
the founders and their young died.
"""

from __future__ import annotations

import collections
import dataclasses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from evolution_simulator import layouts
from evolution_simulator.config import DEFAULT_RULES, TraitRules
from evolution_simulator.traits import AnimalTraits
from evolution_simulator.world import Bounds, World, WorldConfig
from evolution_simulator.world import world as world_module

OPTIONS: dict[str, float | str] = {
    "seeds": "1,2,3",
    "ticks": 3000,
    "animals": 100,
    "plants": 800,
    "size": 1000.0,
    "step": 500,
    "burn": 1.0,
    "tox": 1.0,
    "grown": 0.0,
    "agespread": 0.0,
    "account": 0,
}


def parse(args: list[str]) -> tuple[dict[str, str], dict[str, float]]:
    rules: dict[str, str] = {}
    levels: dict[str, float] = {}
    for arg in args:
        key, value = arg.split("=", 1)
        if key.startswith("lvl."):
            levels[key[4:]] = float(value)
        elif "." in key:
            rules[key] = value
        else:
            OPTIONS[key] = type(OPTIONS[key])(value)
    return rules, levels


def build_rules(overrides: dict[str, str]) -> TraitRules:
    rules = DEFAULT_RULES
    for key, value in overrides.items():
        group, name = key.split(".")
        current = getattr(getattr(rules, group), name)
        part = dataclasses.replace(getattr(rules, group), **{name: type(current)(value)})
        rules = dataclasses.replace(rules, **{group: part})
    return rules


def install_founder_changes() -> None:
    """Patch how ``World.populate`` draws founders, for the options that ask for it."""
    if OPTIONS["burn"] != 1.0:
        init = AnimalTraits.__init__

        def cheaper(self, *args, **kwargs):
            init(self, *args, **kwargs)
            self.basal_metabolism *= OPTIONS["burn"]

        AnimalTraits.__init__ = cheaper
    if OPTIONS["tox"] != 1.0:
        draw_plant = world_module.founder_plant_dna

        def tame(rng):
            dna = draw_plant(rng)
            return dna.with_value("toxicity", dna.value("toxicity") * OPTIONS["tox"])

        world_module.founder_plant_dna = tame
    if OPTIONS["grown"] > 0.0:
        add_plant = World.add_plant

        def add_grown(self, dna, position=None, parents=()):
            plant = add_plant(self, dna, position, parents)
            if not parents:  # a founder, not a seedling
                traits = plant.traits
                traits.set_starting_biomass(traits.max_biomass * OPTIONS["grown"])
                traits.current_health = traits.max_damage_capacity
                traits.lived_ticks = (
                    self.rng.random() * OPTIONS["agespread"] * traits.lifespan_ticks
                )
                traits.seed_cooldown = max(0.0, traits.seed_cooldown - traits.lived_ticks)
            return plant

        World.add_plant = add_grown


def account(rules: TraitRules) -> None:
    """Energy in and out per animal tick, in blocks of a quarter of the run."""
    totals: collections.Counter = collections.Counter()
    feed = AnimalTraits.feed
    update = AnimalTraits.update_metabolism_and_aging
    heal = AnimalTraits._heal

    def fed(self, biomass, is_meat, toxicity=0.0, dt=1.0):
        before = self.current_energy
        result = feed(self, biomass, is_meat, toxicity, dt)
        totals["gain"] += self.current_energy - before
        totals["bites"] += 1
        return result

    def aged(self, ratio=0.0, dt=1.0):
        before = self.current_energy
        update(self, ratio, dt)
        totals["loss"] += before - self.current_energy
        totals["animal ticks"] += 1
        totals["basal"] += self.basal_metabolism * dt

    def healed(self, dt):
        before = self.current_energy
        heal(self, dt)
        totals["healing"] += before - self.current_energy

    AnimalTraits.feed = fed
    AnimalTraits.update_metabolism_and_aging = aged
    AnimalTraits._heal = healed
    world = new_world(1, rules)
    block = int(OPTIONS["ticks"]) // 4
    for _ in range(4):
        totals.clear()
        world.run(block)
        n = max(totals["animal ticks"], 1)
        print(
            f"tick {world.tick}: {len(world.animals)} alive; per animal tick "
            f"gain {totals['gain'] / n:.3f}, loss {totals['loss'] / n:.3f} "
            f"(basal {totals['basal'] / n:.3f}, healing {totals['healing'] / n:.3f}), "
            f"bites {totals['bites'] / n:.3f}"
        )


def new_world(seed: int, rules: TraitRules) -> World:
    size = float(OPTIONS["size"])
    config = WorldConfig(seed=seed, max_plants=5000, bounds=Bounds((size, size)), traits=rules)
    world = World(config)
    world.populate(animals=int(OPTIONS["animals"]), plants=int(OPTIONS["plants"]))
    return world


def run(seed: int, rules: TraitRules) -> str:
    world = new_world(seed, rules)
    founders = {a.id for a in world.animals}
    causes: collections.Counter = collections.Counter()
    births = 0
    series = []
    step = int(OPTIONS["step"])
    for t in range(int(OPTIONS["ticks"])):
        before = list(world.animals)
        births += world.step().animal_births
        alive = {a.id for a in world.animals}
        for animal in before:
            if animal.id not in alive:
                traits = animal.traits
                cause = (
                    "old age"
                    if traits.vitality <= 0
                    else "starved"
                    if traits.current_energy <= 0
                    else "health"
                )
                causes[cause if animal.id in founders else "young " + cause] += 1
        if (t + 1) % step == 0:
            series.append(f"{len(world.animals)}/{births}/{len(world.plants)}")
    return (
        f"seed {seed}: alive {len(world.animals)}, births {births}, deaths {dict(causes)}\n"
        f"  every {step} ticks (alive/births/plants): " + " ".join(series)
    )


def main(args: list[str]) -> None:
    overrides, levels = parse(args)
    if levels:
        layouts.FOUNDER_LEVELS = {**layouts.FOUNDER_LEVELS, **levels}
    rules = build_rules(overrides)
    install_founder_changes()
    started = time.time()
    if OPTIONS["account"]:
        account(rules)
        return
    for seed in str(OPTIONS["seeds"]).split(","):
        print(run(int(seed), rules), flush=True)
    print(f"({time.time() - started:.0f} s) rules {overrides} levels {levels} options {OPTIONS}")


if __name__ == "__main__":
    main(sys.argv[1:])
