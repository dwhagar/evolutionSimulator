"""Scripted foragers with chosen sense settings, to see what a sense is worth (``SENSE.13``).

Run ``python -m evolution_tools.sense_probe senses|eye|smell|noise|light|cost [plants] [ticks]``. Every
animal follows the same fixed rule (walk to the plant it senses and eat it, else wander), has a
plant eater's gut and sees harmless plants that never run out, so the only thing that differs
between rows is the senses. It prints the energy eaten per animal, the share still alive and their
mean energy, averaged over three seeds. Brains, poison and breeding are left out on purpose.
"""

from __future__ import annotations

import dataclasses
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from evolution_simulator.brain_adapter import BrainDecision
from evolution_simulator.config import DEFAULT_RULES, TraitRules
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import PLANT_LAYOUT, founder_animal_dna
from evolution_simulator.sensing import SensingRules
from evolution_simulator.traits import AnimalTraits, PlantTraits
from evolution_simulator.world import Vec, World, WorldConfig
from evolution_simulator.world.senses import WorldSenses

OFF = {
    "sight_range": 0.0,
    "hearing": 0.0,
    "smell": 0.0,
    "sight_fov": 0.5,
    "sight_acuity": 0.5,
    "touch": 0.5,
    "taste": 0.5,
}
MID = {**OFF, "sight_range": 0.5, "hearing": 0.5, "smell": 0.5}


def eye(field: float, reach: float = 0.5) -> dict[str, float]:
    return {**OFF, "sight_range": reach, "sight_fov": field, "sight_acuity": 1.0 - field}


def forage(self, percepts, rng=None):
    """Walk to the plant it senses and eat it; otherwise wander."""
    if percepts.plant_closeness > 0.0:
        near = percepts.plant_closeness > 0.9 or percepts.touching
        self.wanderer.reset()
        return BrainDecision(
            turn=max(-1.0, min(1.0, percepts.plant_direction * 3.0)),
            speed=0.15 if near else 0.7,
            eat_or_attack=1.0,
            seek_mating=0.0,
            alarm_call=0.0,
            mating_call=0.0,
        )
    still = BrainDecision(
        turn=0.0,
        speed=0.0,
        eat_or_attack=1.0 if percepts.touching else 0.0,
        seek_mating=0.0,
        alarm_call=0.0,
        mating_call=0.0,
    )
    return self.wanderer.apply(still, percepts, rng) if rng is not None else still


def scaled(
    rules: TraitRules, cost: float, noise: float, sensing: SensingRules | None
) -> TraitRules:
    o = rules.organs
    organs = dataclasses.replace(
        o,
        hearing_noise=tuple(x * noise for x in o.hearing_noise),
        smell_noise=tuple(x * noise for x in o.smell_noise),
        acuity_direction_noise=tuple(x * noise for x in o.acuity_direction_noise),
        acuity_closeness_noise=tuple(x * noise for x in o.acuity_closeness_noise),
        vision_cost_per_area=o.vision_cost_per_area * cost,
        hearing_cost_per_area=o.hearing_cost_per_area * cost,
        smell_cost_per_area=o.smell_cost_per_area * cost,
        touch_cost=o.touch_cost * cost,
        taste_cost=o.taste_cost * cost,
    )
    return dataclasses.replace(rules, organs=organs, sensing=sensing or rules.sensing)


def run(seed, genes, ticks=1200, animals=100, plants=1500, cost=1.0, noise=1.0, sensing=None):
    rules = scaled(DEFAULT_RULES, cost, noise, sensing)
    eaten = [0.0]
    think, feed, grow = (
        AnimalTraits.think,
        AnimalTraits.feed,
        PlantTraits.update_growth_and_metabolism,
    )

    def counted(self, *args, **kwargs):
        result = feed(self, *args, **kwargs)
        eaten[0] += result or 0.0
        return result

    def never_runs_out(self, *args, **kwargs):
        self.current_biomass = max(self.current_biomass, 30.0)

    AnimalTraits.think, AnimalTraits.feed = forage, counted
    PlantTraits.update_growth_and_metabolism = never_runs_out
    try:
        world = World(WorldConfig(seed=seed, max_plants=4000, traits=rules), senses=WorldSenses())
        rng = random.Random(seed * 7 + 1)
        for _ in range(plants):
            plant = DNA.random(PLANT_LAYOUT, rng).replaced("toxicity", "0000")
            world.add_plant(plant, Vec.of(rng.uniform(0, 1000), rng.uniform(0, 1000)))
        for _ in range(animals):
            dna = founder_animal_dna(rng)
            dna = dna.replaced("herbivore_eff", "3333").replaced("carnivore_eff", "0000")
            for gene, level in genes.items():
                dna = dna.with_value(gene, level)
            where = Vec.of(rng.uniform(0, 1000), rng.uniform(0, 1000))
            world.add_animal(dna, where, heading=rng.uniform(-3.1, 3.1))
        for _ in range(ticks):
            world.step()
        alive = world.animals
        mean_energy = (
            statistics.mean(a.traits.current_energy / a.traits.max_energy for a in alive)
            if alive
            else 0.0
        )
        return eaten[0] / animals, len(alive) / animals, mean_energy
    finally:
        AnimalTraits.think, AnimalTraits.feed = think, feed
        PlantTraits.update_growth_and_metabolism = grow


def table(title, variants, plants, ticks):
    print(f"\n## {title}")
    print(f"{'setting':38s} {'eaten/an':>9s} {'alive':>7s} {'energy':>7s}")
    for name, genes, extra in variants:
        rows = [run(s, genes, ticks=ticks, plants=plants, **extra) for s in (1, 2, 3)]
        mean = [statistics.mean(r[i] for r in rows) for i in range(3)]
        print(f"{name:38s} {mean[0]:9.1f} {mean[1]:7.2f} {mean[2]:7.2f}", flush=True)


def main(which: str, plants: int = 1500, ticks: int = 1200) -> None:
    if which == "senses":
        table(
            "which senses",
            [
                ("blind (wander only)", OFF, {}),
                ("eye only, mid", eye(0.5), {}),
                ("smell only, 0.5", {**OFF, "smell": 0.5}, {}),
                ("hearing only, 0.5 (plants are silent)", {**OFF, "hearing": 0.5}, {}),
                ("eye, smell and hearing, mid", MID, {}),
            ],
            plants,
            ticks,
        )
    elif which == "eye":
        table(
            "the eye along its frontier (reach 0.5)",
            [(f"field {f:.2f} acuity {1 - f:.2f}", eye(f), {}) for f in (0.0, 0.2, 0.5, 0.8, 1.0)],
            plants,
            ticks,
        )
        table(
            "the eye's range gene (field 0.5)",
            [(f"reach {r:.2f}", eye(0.5, r), {}) for r in (0.25, 0.5, 0.75, 1.0)],
            plants,
            ticks,
        )
    elif which == "smell":
        table(
            "smell only, by gene",
            [(f"smell {s:.2f}", {**OFF, "smell": s}, {}) for s in (0.25, 0.5, 0.75, 1.0)],
            plants,
            ticks,
        )
    elif which == "noise":
        table(
            "noise scale (eye, smell and hearing, mid)",
            [(f"noise x{n:.1f}", MID, {"noise": n}) for n in (0.0, 1.0, 3.0, 6.0)],
            plants,
            ticks,
        )
    elif which == "light":
        table(
            "light floor (eye only)",
            [
                (f"light_floor {f:.2f}", eye(0.5), {"sensing": SensingRules(light_floor=f)})
                for f in (0.0, 0.25, 0.5, 1.0)
            ],
            plants,
            ticks,
        )
    elif which == "cost":
        table(
            "cost scale (eye, smell and hearing, mid)",
            [(f"cost x{c:.1f}", MID, {"cost": c}) for c in (0.0, 1.0, 2.0, 4.0)],
            plants,
            ticks,
        )
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1], *[int(a) for a in sys.argv[2:]])
