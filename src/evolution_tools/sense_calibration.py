"""Measures what the senses cost and how noisy they are (``SENSE.13``).

Run ``python -m evolution_tools.sense_calibration [animals] [seed]``. It prints the sense bill as a share of
the whole upkeep bill (``basal_metabolism``) for first-generation animals and for random genomes,
the same for a specialist that maxes one sense (the others at 0 or in the middle), and the
direction noise each sense gives at gene levels 0, 0.5 and 1.
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from evolution_simulator.config import DEFAULT_RULES
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, founder_animal_dna
from evolution_simulator.sense_genes import circle_area, cone_area
from evolution_simulator.traits import AnimalTraits

ORGANS = DEFAULT_RULES.organs
SENSES = {
    "eye": ("sight_range", "sight_fov", "sight_acuity"),
    "hearing": ("hearing",),
    "smell": ("smell",),
    "touch": ("touch",),
    "taste": ("taste",),
}


def parts(t: AnimalTraits) -> dict[str, float]:
    """The sense bill of one animal, by organ, in energy per reference tick."""
    return {
        "eye": ORGANS.vision_cost_per_area
        * (1.0 + t.acuity)
        * cone_area(t.effective_sight_range, t.fov_degrees),
        "hearing": ORGANS.hearing_cost_per_area * circle_area(t.hearing_range),
        "smell": ORGANS.smell_cost_per_area * circle_area(t.smell_range),
        "touch": ORGANS.touch_cost * t.phenotype["touch"] ** 2,
        "taste": ORGANS.taste_cost * t.phenotype["taste"] ** 2,
    }


def share(dna: DNA) -> dict[str, float]:
    t = AnimalTraits(dna)
    out = {name: cost / t.basal_metabolism for name, cost in parts(t).items()}
    out["all"] = sum(out.values())
    return out


def summarize(label: str, genomes: list[DNA]) -> None:
    rows = [share(d) for d in genomes]
    line = "  ".join(
        f"{k} {statistics.mean(r[k] for r in rows):5.1%}"
        for k in ("eye", "hearing", "smell", "touch", "taste", "all")
    )
    sorted_all = sorted(r["all"] for r in rows)
    spread = (
        f"(all: 10th {sorted_all[len(rows) // 10]:.1%}, 90th {sorted_all[-len(rows) // 10]:.1%})"
    )
    print(f"{label:34s} {line}  {spread}")


def specialist(base: DNA, sense: str, level: float, others: float) -> DNA:
    dna = base
    for genes in SENSES.values():
        for gene in genes:
            dna = dna.with_value(gene, others)
    for gene in SENSES[sense]:
        dna = dna.with_value(gene, level)
    if sense == "eye":  # the eye's frontier: acuity = 1 - field
        dna = dna.with_value("sight_acuity", 1.0 - level)
    return dna


def main(count: int = 400, seed: int = 1) -> None:
    rng = random.Random(seed)
    print("Sense bill as a share of the whole upkeep bill, mean over", count, "animals\n")
    summarize("first generation", [founder_animal_dna(rng) for _ in range(count)])
    summarize("random genomes", [DNA.random(ANIMAL_LAYOUT, rng) for _ in range(count)])
    base = [founder_animal_dna(rng) for _ in range(count)]
    for sense in SENSES:
        summarize(f"{sense} at 1, others at 0", [specialist(d, sense, 1.0, 0.0) for d in base])
        summarize(f"{sense} at 1, others at 0.5", [specialist(d, sense, 1.0, 0.5) for d in base])
    print("\nWhat one sense at 0.5 costs, others at 0.5 (a mid animal)")
    summarize("everything at 0.5", [specialist(d, "taste", 0.5, 0.5) for d in base])
    print("\nDirection noise (a share of the half field) by gene level, mid animal")
    for level in (0.0, 0.5, 1.0):
        t = AnimalTraits(specialist(base[0], "eye", level, 0.5))
        print(
            f"  eye {level}: direction {t.vision_noise:.3f} closeness {t.vision_closeness_noise:.3f}"
            f"   hearing {level}: {AnimalTraits(specialist(base[0], 'hearing', level, 0.5)).hearing_noise:.3f}"
            f"   smell {level}: {AnimalTraits(specialist(base[0], 'smell', level, 0.5)).smell_noise:.3f}"
        )


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    main(*args)
