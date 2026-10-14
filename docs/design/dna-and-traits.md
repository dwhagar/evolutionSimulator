# DNA and traits objects

Design of the first two objects, `evolution_simulator.dna` and `evolution_simulator.traits`.
Written 2026-10-14 by the Foundations 1 thread.

## What exists

| Module | Contents |
| --- | --- |
| `dna.py` | `BaseDNA`, `AnimalDNA` (65 digits), `PlantDNA` (24 digits), the `Gene` and `Locus` descriptors |
| `traits.py` | `BaseTraits`, `AnimalTraits`, `PlantTraits` |

The model is the owner's prototype (archived in [`docs/archive/prototype`](../archive/prototype/README.md)),
not the defaults suggested by the research notes (PRs #12 and #13). The prototype answers several of the
open questions in issues #2 to #11 by example; those answers are used here and listed under
[Decisions taken from the prototype](#decisions-taken-from-the-prototype) so they can be confirmed.

## DNA

- A genome is an **immutable** tuple of base-4 digits (0 to 3). Haploid, fixed length.
- A **gene** is a run of consecutive digits read as a big-endian base-4 number and scaled to a float
  from 0.0 to 1.0. A **locus** is one digit read as a raw category (used for `sex_strategy`).
- The layout is declared once, in the class body, with `Gene()` / `Locus()` descriptors. Declaration
  order fixes the digit positions and the sum of widths is the genome length, so adding a gene means
  adding one line. Positions match the prototype digit for digit.
- Reading a gene is plain attribute access: `dna.size`, `dna.sex_strategy`.
- Genomes compare and hash by value, have `distance(other)` (fraction of digits that differ, for
  speciation and mate checks), and round-trip through `to_dict()` / `BaseDNA.from_dict()` (JSON friendly)
  or `str()` / `from_string()`.

### Operations

All take an injected `random.Random` and return a new genome; a parent is never changed.

| Method | Behaviour |
| --- | --- |
| `mutated(rng, rate)` | Each digit changes with probability `rate` (default 0.01 per digit) to one of the other three digits. |
| `crossover(partner, rng)` | Uniform per-digit crossover (the prototype's operator, the default). |
| `crossover_one_point(partner, rng)` | Front of this genome, back of the partner, one random cut. |
| `crossover_by_gene(partner, rng)` | Each whole gene from either parent. |
| `clone_with_mutation(rng, rate)` | Asexual path. |
| `reproduce(partner, rng, rate, crossover=None)` | Single entry point: no partner clones, a partner crosses over, then mutates. `crossover=` swaps in any of the strategies above. |

The prototype's `+` operator is gone because it cannot take an RNG or a rate. Mixing two species
(`AnimalDNA` with `PlantDNA`) raises `TypeError`.

The mutation rate is **per digit**, as the DNA research note recommends, so the expected number of
changes per child scales with genome length: about 0.65 for an animal and 0.24 for a plant at the
default.

## Traits

`AnimalTraits(dna)` and `PlantTraits(dna)` read the genes once to fix the phenotype (mass, speed,
sense ranges, upkeep, seed count and so on), then carry runtime state (energy, health, vitality, age,
drive flags) that the simulation advances with `update_metabolism_and_aging()` /
`update_growth_and_metabolism()`, `feed()`, `graze()`, `apply_damage()` and the stimulus setters.

The formulas and constants are the prototype's, unchanged. A comparison harness ran the prototype and the
port side by side over 300 random animals (300 ticks each, with feeding, damage, stimuli, mating and
signalling) and 300 random plants (400 ticks each, with grazing and seeding) and found identical state at
every step. The harness is not in the repo.

## Changes from the prototype

Behaviour is unchanged except where noted:

1. **Randomness is injected.** The prototype used the global `random`, so runs could not be seeded. DNA
   operations take a `random.Random`, and `AnimalTraits.inspect_food(toxicity, rng)` takes one too.
2. **DNA is immutable.** `mutate()` in place became `mutated()` returning a new genome.
3. **Layout is data.** Gene positions come from descriptors instead of `GENE_*` tuples plus one property
   per gene. `BaseDNA.random(rng)` replaces the constructor's implicit random fill, and the sequence is
   now required to construct.
4. **Extras:** `distance`, value equality and hash, `to_dict` / `from_dict`, `crossover_one_point`,
   `crossover_by_gene`, and a single `reproduce` entry point.
5. **Python 3.12 typing** (`X | None`, built-in generics) and ruff clean.

## Decisions taken from the prototype

These are the points where the prototype and the research defaults differ. Each is built the prototype's
way and is easy to change.

| Issue | Research default | Built | How to change |
| --- | --- | --- | --- |
| #2 genome detail | Gene-level | Base-4 digit sequence with genes as slices (closest to the "sequence" level) | Genes are descriptors, so another encoding changes `decode_*` only |
| #3 ploidy | Diploid, haploid option | Haploid | A diploid genome would hold two `BaseDNA` and add gamete and fertilise steps; traits read through the descriptors and would not change |
| #4 reproduction | Both modes, no sexes | Both modes, plus a `sex_strategy` digit that shifts temperament and mating cost | The digit is read in one place in `AnimalTraits.__init__` and `consume_mating_cost` |
| #5 length | Fixed | Fixed | Gene IDs are not reserved yet; layout position is the identity |
| #6 trait set | Fixed | Fixed (16 animal genes, 6 plant genes) | Add a `Gene()` line and use it in traits |
| #8 diet | Plants only | Herbivore and carnivore efficiency genes, so predation is in | |
| #9 behaviour | No behaviour genes | `aggression` and `fear` are genes feeding a fixed fight-or-flight rule | |

## Known quirks, kept as in the prototype

Flagged by the research threads; not changed without the owner's call.

- **Digit position matters.** The first digit of a four-digit gene carries three quarters of its range, so
  one mutation there can move a value by 0.25 to 0.75, while a last-digit change moves it by about 0.004.
  A Gray code would smooth this.
- **Uniform per-digit crossover blends inside a gene.** Parents at 0.0 and 1.0 can give a child at
  0.75. `crossover_by_gene` avoids it; switching the default is one argument to `reproduce`.
- **Sex is an inherited digit with no balancing.** A small population can lose one sex. Assigning it at
  birth is a change to `reproduce`.
- **`fertility` is decoded but nothing reads it.**
- **`somatic_maint` is cheap and cuts wear up to 4.5 times**, so selection will push it to the maximum
  unless something penalises long life.
- **Plant vitality starts at 1.0** although a seedling's health starts at half of its maximum; the
  first tick's growth uses 1.0 and it is refreshed at the end of that tick.
- **Constants are inline.** Moving the tuning numbers into a config object is listed in
  [TODO.md](../../TODO.md).
