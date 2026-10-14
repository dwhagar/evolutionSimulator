# DNA and traits objects

Design of the first two objects, `evolution_simulator.dna` and `evolution_simulator.traits`.
Written 2026-10-14 by the Foundations 1 thread.

## What exists

| Module | Contents |
| --- | --- |
| `dna.py` | `BaseDNA`, `AnimalDNA` (61 digits), `PlantDNA` (24 digits), the `Gene` and `Locus` descriptors |
| `traits.py` | `BaseTraits`, `AnimalTraits`, `PlantTraits` |

The model is the owner's prototype (archived in [`docs/archive/prototype`](../archive/prototype/README.md)),
not the defaults suggested by the research notes ([DNA and reproduction](../research/dna-and-reproduction.md),
including its review of the prototype, and the traits note in PR #12). The prototype answers several of the
open questions in issues #2 to #11 by example; those answers are used here and listed under
[Decisions taken from the prototype](#decisions-taken-from-the-prototype) so they can be confirmed. Where the
research threads recommended changes to the prototype's DNA operators, their defaults are built (see
[Defaults taken from the research threads](#defaults-taken-from-the-research-threads)).

## DNA

- A genome is an **immutable** tuple of base-4 digits (0 to 3). Haploid, fixed length.
- A **gene** is a run of consecutive digits read as a big-endian base-4 number and scaled to a float
  from 0.0 to 1.0. A **locus** is one digit read as a raw category (used for `sex_strategy`).
- The layout is declared once, in the class body, with `Gene()` / `Locus()` descriptors. Declaration
  order fixes the digit positions and the sum of widths is the genome length, so adding a gene means
  adding one line. Positions match the prototype digit for digit, except that the unused `fertility` gene is
  gone, so the animal genome is 61 digits and the sex digit sits at index 60.
- Each class has a `LAYOUT_VERSION`, saved in `to_dict()` and checked by `from_dict()`, because changing
  the layout invalidates saved genomes. `AnimalDNA` is at version 2 (version 1 would have been the
  prototype's 65-digit layout).
- Reading a gene is plain attribute access: `dna.size`, `dna.sex_strategy`.
- Genomes compare and hash by value, have `distance(other)` (fraction of digits that differ, for
  speciation and mate checks), and round-trip through `to_dict()` / `BaseDNA.from_dict()` (JSON friendly)
  or `str()` / `from_string()`.

### Operations

All take an injected `random.Random` and return a new genome; a parent is never changed.

| Method | Behaviour |
| --- | --- |
| `mutated(rng, mutations_per_genome=None, position_weights=None)` | Point mutation set as the **expected number of changed digits per genome**: each digit changes with probability `mutations_per_genome / length`, to one of the other three digits. Optional per-digit `position_weights` skew where changes land while keeping the expected total. |
| `crossover_linked(partner, rng, mean_cuts=1.0)` | **Default.** Cuts fall between genes, never inside one, as a Poisson process with about one cut per genome and a random starting parent. Neighbouring genes travel together. |
| `crossover(partner, rng)` | Uniform per-digit crossover (the prototype's operator). |
| `crossover_by_gene(partner, rng)` | Each whole gene from either parent independently (no linkage). |
| `crossover_one_point(partner, rng)` | Front of this genome, back of the partner, one random cut (may cut inside a gene). |
| `clone_with_mutation(rng, ...)` | Asexual path. |
| `reproduce(partner, rng, mutations_per_genome=None, position_weights=None, crossover=None)` | Single entry point: no partner clones, a partner crosses over, then the child (never a parent) mutates. `crossover=` swaps in any strategy above. |

The prototype's `+` operator is gone because it cannot take an RNG or a rate. Mixing two species
(`AnimalDNA` with `PlantDNA`) raises `TypeError`.

`DEFAULT_MUTATIONS` is derived from the prototype's 0.01 per digit, so the default is about 0.61 changes per
animal child and 0.24 per plant child. Callers who want a species-independent setting pass
`mutations_per_genome` explicitly.

## Traits

`AnimalTraits(dna)` and `PlantTraits(dna)` read the genes once to fix the phenotype (mass, speed,
sense ranges, upkeep, seed count and so on), then carry runtime state (energy, health, vitality, age,
drive flags) that the simulation advances with `update_metabolism_and_aging()` /
`update_growth_and_metabolism()`, `feed()`, `graze()`, `apply_damage()` and the stimulus setters.

The formulas and constants are the prototype's, unchanged. A comparison harness first ran the prototype and
the port side by side over 300 random animals (300 ticks each, with feeding, damage, stimuli, mating and
signalling) and 300 random plants (400 ticks each, with grazing and seeding) and found identical state at
every step. After the later changes below, the static phenotype of 300 random animals still matched the
prototype's (with the removed gene padded in). The harness is not in the repo; pinned phenotype numbers for
fixed genomes are in `tests/test_traits.py` so formula changes show up in review.

## Changes from the prototype

Behaviour is unchanged except where noted:

1. **Randomness is injected.** The prototype used the global `random`, so runs could not be seeded. DNA
   operations take a `random.Random`, and `AnimalTraits.inspect_food(toxicity, rng)` takes one too.
2. **DNA is immutable.** `mutate()` in place became `mutated()` returning a new genome.
3. **Layout is data.** Gene positions come from descriptors instead of `GENE_*` tuples plus one property
   per gene. `BaseDNA.random(rng)` replaces the constructor's implicit random fill, and the sequence is
   now required to construct.
4. **Extras:** `distance`, value equality and hash, `to_dict` / `from_dict` with a layout version, extra
   crossover strategies, and a single `reproduce` entry point.
5. **Python 3.12 typing** (`X | None`, built-in generics) and ruff clean.
6. **Small fixes:** both traits classes now compute their drive flags and vitality at the end of `__init__`
   (the prototype left them unset or at 1.0 until the first tick), and `consume_mating_cost` cannot push
   energy below zero.

## Decisions taken from the prototype

These are the points where the prototype and the research defaults differ. Each is built the prototype's
way and is easy to change.

| Issue | Research default | Built | How to change |
| --- | --- | --- | --- |
| #2 genome detail | Gene-level | Base-4 digit sequence with genes as slices (closest to the "sequence" level) | Genes are descriptors, so another encoding changes `decode_*` only |
| #3 ploidy | Diploid, haploid option | Haploid | A diploid genome would hold two `BaseDNA` and add gamete and fertilise steps; traits read through the descriptors and would not change |
| #4 reproduction | Both modes, no sexes | Both modes, plus a `sex_strategy` digit that shifts temperament and mating cost | The digit is read in one place in `AnimalTraits.__init__` and `consume_mating_cost` |
| #5 length | Fixed | Fixed | Gene IDs are not reserved yet; layout position is the identity |
| #6 trait set | Fixed | Fixed (15 animal genes plus the sex digit, 6 plant genes) | Add a `Gene()` line and use it in traits |
| #8 diet | Plants only | Herbivore and carnivore efficiency genes, so predation is in | |
| #9 behaviour | No behaviour genes | `aggression` and `fear` are genes feeding a fixed fight-or-flight rule | |

## Defaults taken from the research threads

Briefs from the Research 1 and Research 2 threads asked for these, so they are built even though the owner
has not yet answered the related issues. All are easy to reverse.

- **Crossover between genes, about one cut per genome** (#14): `crossover_linked`, the `reproduce` default.
- **Mutation as expected changes per genome, with an optional per-position weight** (#15): the weights
  default to uniform, so the prototype's big-endian effect sizes are unchanged until someone sets them.
- **`fertility` gene removed** (#17), because nothing reads it and neutral genes only add drift.
- **Layout version** on every DNA class.
- **Sex stays an ordinary inherited digit** that traits decode; deciding who may mate is the simulation's job.

## Known quirks, kept as in the prototype

Not changed without the owner's call.

- **Digit position matters** ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)). The first digit
  of a four-digit gene carries three quarters of its range, so one mutation there can move a value by 0.25
  to 0.75, while a last-digit change moves it by about 0.004. `position_weights` can damp the large digits;
  a Gray code would smooth it at the encoding level.
- **Sex is an inherited digit with no balancing.** A small population can lose one sex. Assigning it at
  birth is a change to `reproduce`.
- **`somatic_maint` is cheap and cuts wear up to 4.5 times** (#16), so selection will push it to the maximum
  unless something penalises long life.
- **Constants are inline.** Tuning numbers are not yet in a config object, and traits are not yet described
  as data (name, genes, range, scale, mutation step). Both are for the TODO thread to schedule.
