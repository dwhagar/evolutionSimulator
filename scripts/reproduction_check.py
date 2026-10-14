"""Long-run check for the reproduction genes (``REPRO.8``).

The design note's toy model had no crowding, so ``fertility`` and a short ``repro_cooldown`` ran to
the top of their ranges. This script runs the real ``AnimalTraits`` (upkeep, wear, healing, matings,
pregnancies, paid births) in a small ecology with a fixed food supply shared by everyone alive, so
more young means less food for each, and reports where the reproduction genes settle.

It is a chemostat, not the world: no space, no plants and no brains. Each hour tick the food is split
evenly among the living (up to an intake cap), the willing animals of the two sexes meet at random
with a fixed chance, and the real ``AnimalTraits.mate`` and ``AnimalTraits.give_birth`` do the rest.
Two pressures the world will supply are stood in for, or ``recovery`` and ``parenting`` would have
nothing to pay for: now and then an animal is injured (so healing matters), and a newborn cannot eat
for its first 18 hours (so the energy its parents gave it matters).

Run ``python scripts/reproduction_check.py [ticks] [seed] [injury_chance] [newborn_fast_ticks]``. A gene "piles up at an end" when the
population's mean value in the last fifth of the run is within ``EDGE`` of 0 or 1.

``TRAIT.9`` gave the genes that used to be free a cost (speed, agility, aggression, fear, the sex
digit, the learning rate). Add ``traits`` as a fifth argument to switch on stand-ins for what they buy
in the world, so the cost has something to balance: every animal moves at half speed while it forages,
the food is shared in proportion to ``1 + 0.5 * speed + 0.2 * agility + 0.3 * aggression``, fear cuts
the chance of injury by up to half, and the genes are watched too. The stand-in benefits are guesses,
chosen only so each gene has a reason to be high.
"""

from __future__ import annotations

import random
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evolution_simulator.config import DEFAULT_RULES, TraitRules
from evolution_simulator.layouts import founder_animal_dna
from evolution_simulator.traits import AnimalTraits

GENES: tuple[str, ...] = ("fertility", "parenting", "repro_drive", "repro_cooldown", "recovery")
TRAIT_GENES: tuple[str, ...] = ("speed", "agility", "aggression", "fear", "learning_rate")
"""The genes ``TRAIT.9`` made pay; watched when the trait pressures are on."""
"""The reproduction genes to watch (``somatic_maint`` is the repair gene they trade against)."""
WATCHED: tuple[str, ...] = (*GENES, "somatic_maint")
EDGE: float = 0.08
"""A mean this close to 0 or 1 counts as piled up at an end."""


@dataclass
class Ecology:
    """Settings of the chemostat."""

    founders: int = 80
    food_per_tick: float = 45.0
    """Biomass available each tick, shared evenly among the living."""
    intake_cap: float = 3.0
    """The most one animal can eat in a tick."""
    meeting_chance: float = 0.05
    """Chance per tick that a willing animal meets a willing animal of the other sex."""
    injury_chance: float = 0.002
    """Chance per tick that an animal is hurt, losing between ``injury_low`` and ``injury_high``
    points of health (a body holds 100 to 300)."""
    injury_low: float = 5.0
    injury_high: float = 40.0
    newborn_fast_ticks: int = 18
    """A newborn cannot eat for this many ticks (it lives off the energy its parents gave it)."""
    max_population: int = 400
    trait_pressures: bool = False
    """Stand-ins for what speed, agility, aggression and fear buy (see the module note)."""
    rules: TraitRules = DEFAULT_RULES
    """The trait rules of every animal; a run with the ``TRAIT.9`` costs zeroed shows what they do."""
    forage_ratio: float = 0.5
    """Share of top speed an animal moves at each tick while foraging (with ``trait_pressures``)."""
    seed: int = 1
    history: list[dict[str, float]] = field(default_factory=list)


def run(ticks: int = 20_000, ecology: Ecology | None = None, report_every: int = 0) -> Ecology:
    """Run the chemostat and record the population and the mean of each watched gene every
    ``max(1, ticks // 25)`` ticks in ``ecology.history``."""
    eco = ecology if ecology is not None else Ecology()
    rng = random.Random(eco.seed)
    animals = [AnimalTraits(founder_animal_dna(rng), rules=eco.rules) for _ in range(eco.founders)]
    every = max(1, ticks // 25)
    for tick in range(ticks + 1):
        if tick % every == 0:
            eco.history.append(snapshot(tick, animals, eco))
            if report_every:
                print(format_row(eco.history[-1]), flush=True)
        if not animals:
            break
        _tick(animals, eco, rng)
        animals = [a for a in animals if a.is_alive]
    return eco


def _tick(animals: list[AnimalTraits], eco: Ecology, rng: random.Random) -> None:
    weights = [_food_weight(a, eco) for a in animals]
    per_weight = eco.food_per_tick / sum(weights)
    for animal, weight in zip(animals, weights, strict=True):
        share = min(eco.intake_cap, per_weight * weight)
        if animal.age_ticks >= eco.newborn_fast_ticks:
            animal.current_energy = min(animal.max_energy, animal.current_energy + share)
        injury = eco.injury_chance
        if eco.trait_pressures:
            injury *= 1.0 - 0.5 * animal.phenotype["fear"]
        if rng.random() < injury:
            animal.apply_damage(rng.uniform(eco.injury_low, eco.injury_high))
        animal.update_metabolism_and_aging(eco.forage_ratio if eco.trait_pressures else 0.0)
    willing = [a for a in animals if a.is_alive and a.wants_mate]
    males = [a for a in willing if a.sex == 0]
    females = [a for a in willing if a.sex == 1]
    rng.shuffle(males)
    for female in females:
        if not males or rng.random() >= eco.meeting_chance:
            continue
        male = males.pop()
        if male.is_alive and female.is_alive:
            AnimalTraits.mate(male, female, rng)
    born: list[AnimalTraits] = []
    for mother in animals:
        pregnancy = mother.pregnancy
        if not mother.is_alive or pregnancy is None or not pregnancy.due:
            continue
        room = eco.max_population - len(animals) - len(born)
        litter = [
            AnimalTraits(genome, rules=eco.rules) for genome in pregnancy.children[: max(0, room)]
        ]
        if litter and AnimalTraits.give_birth(mother, litter):
            born.extend(litter)
    animals.extend(born)


def _food_weight(animal: AnimalTraits, eco: Ecology) -> float:
    """Share of the food an animal gets relative to the others: 1, or more with the stand-ins."""
    if not eco.trait_pressures:
        return 1.0
    t = animal.phenotype
    return 1.0 + 0.5 * t["speed"] + 0.2 * t["agility"] + 0.3 * t["aggression"]


def snapshot(
    tick: int, animals: list[AnimalTraits], eco: Ecology | None = None
) -> dict[str, float]:
    row: dict[str, float] = {"tick": float(tick), "population": float(len(animals))}
    watched = WATCHED + (TRAIT_GENES if eco is not None and eco.trait_pressures else ())
    for gene in watched:
        values = [a.dna.value(gene) for a in animals]
        row[gene] = statistics.fmean(values) if values else float("nan")
    return row


def format_row(row: dict[str, float]) -> str:
    genes = " ".join(f"{g}={row[g]:.2f}" for g in (*WATCHED, *TRAIT_GENES) if g in row)
    return f"tick {int(row['tick']):>6} pop {int(row['population']):>4}  {genes}"


def piled_up(history: list[dict[str, float]]) -> list[str]:
    """The genes whose mean over the last fifth of the run sits at an end of the range."""
    tail = history[-max(1, len(history) // 5) :]
    stuck = []
    for gene in (*GENES, *(g for g in TRAIT_GENES if g in tail[-1])):
        values = [row[gene] for row in tail if row["population"] > 0]
        if not values:
            continue
        mean = statistics.fmean(values)
        if mean < EDGE or mean > 1.0 - EDGE:
            stuck.append(gene)
    return stuck


def main(argv: list[str]) -> int:
    ticks = int(argv[1]) if len(argv) > 1 else 20_000
    seed = int(argv[2]) if len(argv) > 2 else 1
    eco = Ecology(seed=seed)
    if len(argv) > 3:
        eco.injury_chance = float(argv[3])
    if len(argv) > 4:
        eco.newborn_fast_ticks = int(argv[4])
    if len(argv) > 5 and argv[5] == "traits":
        eco.trait_pressures = True
    eco = run(ticks, eco, report_every=1)
    stuck = piled_up(eco.history)
    final = eco.history[-1]
    if final["population"] == 0:
        print("The population died out.")
        return 2
    print("At an end of the range:", ", ".join(stuck) if stuck else "none")
    return 1 if stuck else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
