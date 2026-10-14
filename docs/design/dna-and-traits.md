# DNA and traits objects

Design of the first two objects, `evolution_simulator.dna` and `evolution_simulator.traits`.
Written 2026-10-14 by the Foundations 1 thread.

## What exists

| Module | Contents |
| --- | --- |
| `dna.py` | `DNA` (immutable genome), `GenomeLayout`, `GeneSpec` and `BlockSpec` (the gene table); knows gene IDs only |
| `layouts.py` | `ANIMAL_LAYOUT` (461 digits: 65 body, 396 brain) and `PLANT_LAYOUT` (24 digits) as plain data, and `dna_from_dict` |
| `brain.py`, `brain_adapter.py` | The `Brain` network and the world-side inputs and outputs; see [brain.md](brain.md) |
| `trait_defs.py` | `TraitDef` and `TraitSet`: what each trait reads from DNA, its range, scale and mutation step; `ANIMAL_TRAITS`, `PLANT_TRAITS` |
| `traits.py` | `BaseTraits`, `AnimalTraits`, `PlantTraits`: runtime organism state and the formulas built on the traits; `AnimalTraits` also builds the animal's `Brain` |

The model is the owner's prototype (archived in [`docs/archive/prototype`](../archive/prototype/README.md)),
not the defaults suggested by the research notes ([DNA and reproduction](../research/dna-and-reproduction.md), including its review of the prototype, and the traits note in PR #12). The prototype answers several of the
open questions in issues #2 to #11 by example; those answers are used here and listed under
[Decisions taken from the prototype](#decisions-taken-from-the-prototype) so they can be confirmed.

## DNA

- A genome is an **immutable** tuple of base-4 digits (0 to 3). Haploid, fixed length.
- A **gene** is a run of consecutive digits read as a big-endian base-4 number and scaled to a float
  from 0.0 to 1.0 (`dna.value(gene_id)`). A single-digit gene can instead be read as a raw category
  (`dna.digit(gene_id)`, used for `sex_strategy`).
- The shape of a genome is a **`GenomeLayout`**: an ordered table of `GeneSpec(id, length)` rows. Order fixes
  the digit positions and the sum of lengths is the genome length, so adding a gene means adding one row.
  Positions match the prototype digit for digit. Each layout has a name and a `version` to bump whenever
  the table changes shape.
- A **gene block** (`BlockSpec`) is a gene that holds an array of numbers instead of one value: `count`
  values of `digits_per_value` digits each, decoded onto a range `low` to `high` (`dna.values(gene_id)`).
  The animal's brain is one block of 198 two-digit values over -2 to 2. A block's values come in `groups`
  that crossover keeps together (one per hidden neuron). A block is still a gene with a position, so it is
  read, replaced (`dna.replaced(gene_id, digits)`), saved and compared like any other.
- Genes belong to a named **segment** (`GeneSpec(..., segment="brain")`, default `"body"`); the genes of a
  segment must be consecutive. Segments are what mutation is set per, and they are the only place the genome
  has structure beyond the gene table. `ANIMAL_LAYOUT` has `body` (digits 0 to 65) and `brain` (65 to 461).
- **DNA does not know trait names.** It exposes genes by ID (`value`, `digit`, `raw`, `slice_of`) and the
  decode API (`get_slice`, `decode_int`, `decode_normalized`), nothing else. The prototype's `dna.size`
  style properties are gone; what a gene is *for* is declared in `trait_defs.py`.
- Genomes compare and hash by value (layout and digits), have `distance(other)` (fraction of digits that
  differ, for speciation and mate checks), and round-trip through `to_dict()` (layout name, version,
  digits) and `dna_from_dict()`, which refuses a saved genome whose layout version no longer matches.

### Operations

All take an injected `random.Random` and return a new genome; a parent is never changed.

| Method | Behaviour |
| --- | --- |
| `mutated(rng, rate=None, mutations_per_segment=None)` | A changed digit moves to one of the other three digits. With `rate`, every digit changes with that probability whatever its segment. With `mutations_per_segment={"brain": 1.0}`, each named segment gets that expected number of changed digits per child; segments left out keep the layout's `default_mutations`. With neither, the layout defaults apply: 0.01 per digit for the plant and the animal body, 1.0 per child for the animal brain. The two settings cannot be combined. |
| `crossover(partner, rng)` | Uniform per-digit crossover (the prototype's operator, the default). |
| `crossover_one_point(partner, rng)` | Front of this genome, back of the partner, one random cut. |
| `crossover_by_gene(partner, rng)` | Each whole gene from either parent (a block counts as one gene). |
| `crossover_by_unit(partner, rng)` | Each whole **unit** from either parent: a gene, or one group inside a block. For the brain that is a whole hidden neuron with its incoming and outgoing weights, so a child never gets a blend inside a neuron. The same as `crossover_by_gene` on a layout with no blocks. |
| `clone_with_mutation(rng, rate=None, mutations_per_segment=None)` | Asexual path. |
| `reproduce(partner, rng, rate=None, crossover=None, mutations_per_segment=None)` | Single entry point: no partner clones, a partner crosses over, then mutates. `crossover=` swaps in any of the strategies above. |

The prototype's `+` operator is gone because it cannot take an RNG or a rate. Mixing two species
(different layouts) raises `TypeError`.

The mutation rate is **per digit** by default, as the DNA research note recommends, so the expected number of
changes per child scales with genome length: about 0.65 for the animal body and 0.24 for a plant. That would
give the 396-digit brain about 4 changes per child on its own, so the animal layout sets the brain's default as
**expected changes per segment** instead (1.0 per child). The defaults live on the layout
(`GenomeLayout(..., segment_mutations={...})`), and every call can override them, so the owner's answers to
[#14](https://github.com/dwhagar/evolutionSimulator/issues/14) and [#15](https://github.com/dwhagar/evolutionSimulator/issues/15)
change numbers, not code.

## Traits

Trait definitions are data (`trait_defs.py`): each `TraitDef` names the genes it reads, its range, scale
(linear or log), kind (continuous, integer, category) and a mutation step. A `TraitSet` per species
expresses a genome into a dictionary of primary values. The formulas that combine them (speed damped by
size, upkeep, and so on) stay as code in `traits.py`. See
[dna-traits-interaction.md](dna-traits-interaction.md).

`AnimalTraits(dna)` and `PlantTraits(dna)` express the genome once to fix the phenotype (mass, speed,
sense ranges, upkeep, seed count and so on, kept in `traits.phenotype`), then carry runtime state (energy, health, vitality, age,
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
3. **Layout and traits are data.** Gene positions come from a `GenomeLayout` table instead of `GENE_*`
   tuples plus one property per gene, and the gene-to-trait ranges that were scattered through the
   formulas (`10 + 50 * sight_range`) are rows in a `TraitSet`. `DNA.random(layout, rng)` replaces the
   constructor's implicit random fill, and the sequence is now required to construct.
4. **Extras:** `distance`, value equality and hash, `to_dict` / `dna_from_dict`, `crossover_one_point`,
   `crossover_by_gene`, and a single `reproduce` entry point.
5. **Python 3.12 typing** (`X | None`, built-in generics) and ruff clean.

## Decisions taken from the prototype

These are the points where the prototype and the research defaults differ. Each is built the prototype's
way and is easy to change.

| Issue | Research default | Built | How to change |
| --- | --- | --- | --- |
| #2 genome detail | Gene-level | Base-4 digit sequence with genes as slices (closest to the "sequence" level) | Traits read genes only through `value` / `digit`, so another encoding changes `decode_*` only |
| #3 ploidy | Diploid, haploid option | Haploid | A diploid genome would hold two `DNA` and add gamete and fertilise steps; traits read through `TraitDef.express` and would not change |
| #4 reproduction | Both modes, no sexes | Both modes, plus a `sex_strategy` digit that shifts temperament and mating cost | The digit is read in one place in `AnimalTraits.__init__` and `consume_mating_cost` |
| #5 length | Fixed | Fixed | Gene IDs are not reserved yet; layout position is the identity |
| #6 trait set | Fixed | Fixed (16 animal genes plus the brain block, 6 plant genes) | Add a `GeneSpec` row to the layout and a `TraitDef` row that reads it |
| #8 diet | Plants only | Herbivore and carnivore efficiency genes, so predation is in | |
| #9 behaviour | No behaviour genes | `aggression` and `fear` are genes feeding a fixed fight-or-flight rule | |

## Known quirks, kept as in the prototype

Flagged by the research threads; not changed without the owner's call.

- **Digit position matters** ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)). The first digit of a four-digit gene carries three quarters of its range, so
  one mutation there can move a value by 0.25 to 0.75, while a last-digit change moves it by about 0.004.
  A Gray code would smooth this.
- **Uniform per-digit crossover blends inside a gene** ([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)). Parents at 0.0 and 1.0 can give a child at
  0.75. `crossover_by_gene` avoids it, and `crossover_by_unit` also keeps brain neurons whole; switching the
  default is one argument to `reproduce`. Until it is answered, animals that reproduce should pass
  `crossover=DNA.crossover_by_unit`, or the brain's weights blend inside each neuron.
- **Sex is an inherited digit with no balancing.** A small population can lose one sex. Assigning it at
  birth is a change to `reproduce`.
- **`fertility` is decoded but nothing reads it**, so it drifts neutrally.
- **Mutation rate is per digit for the body and plants**, so the same 0.01 gives 0.65 changes per animal body
  but 0.24 per plant. The research note suggests defining it as expected changes per genome instead
  (`DNA.8`); not done. The brain segment is already set as expected changes (1.0 per child).
- **Animal drive flags start unset** until the first tick, because `__init__` never calls
  `_update_needs_and_drives()`.
- **`somatic_maint` is cheap and cuts wear up to 4.5 times**, so selection will push it to the maximum
  unless something penalises long life.
- **Plant vitality starts at 1.0** although a seedling's health starts at half of its maximum; the
  first tick's growth uses 1.0 and it is refreshed at the end of that tick.
- **Constants are inline.** Moving the tuning numbers into a config object is listed in
  [TODO.md](../../TODO.md).
