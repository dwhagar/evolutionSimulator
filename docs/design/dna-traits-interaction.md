# How DNA and traits interact

Task `DOCS.5`, written 2026-10-14 by the Foundations 1 thread. It describes the code as merged in
[#31](https://github.com/dwhagar/evolutionSimulator/pull/31) (`TRAIT.4`) and follows the contract in
section 9.4 of the [traits research note](../research/basic-traits.md). For the wider design, including
reproduction and the decisions still waiting on the owner, see [dna-and-traits.md](dna-and-traits.md).

## The idea in one paragraph

DNA is a string of digits with a table that says where the genes are. A trait table says which genes each
trait reads and how to turn them into a number. The organism object (`AnimalTraits`, `PlantTraits`) applies
that table once, at birth, then runs formulas on the result and keeps changing state (energy, health, age).
Each layer knows only the one below it by name: traits know gene IDs, DNA knows nothing about traits.

```
 layouts.py        trait_defs.py            traits.py                  the simulation
 ----------        -------------            ---------                  --------------
 GenomeLayout  <-- TraitSet (TraitDef)  <-- AnimalTraits / PlantTraits <-- ticks, feeding, mating
 (gene IDs and     (which genes, what       (formulas on the phenotype,
  positions)        range and scale)         runtime state)
        ^                                              |
        |                                              |
       DNA  (digits, mutation, crossover) <------------+  reproduce() makes the next DNA
```

Information flows one way for an organism's life: **DNA, then trait table, then phenotype, then formulas
and state.** Inheritance goes the other way round the loop: only DNA is copied to the next generation,
never phenotype or state.

## The brain: a third piece

The animal's brain is not a trait. It is a block of 198 weights in the genome (`BlockSpec`, read with
`dna.values("brain")`) that `AnimalTraits` turns into a `Brain` object at birth, the same moment it expresses the
body. The trait table does not read it (`unread_genes()` skips gene blocks), and `Brain` knows nothing about
DNA: it receives plain numbers. The animal's energy cost of thinking is added to `basal_metabolism`.
See [brain.md](brain.md#as-built) for the layout, the cost and what is not built.

```
 DNA --body genes--> TraitSet --> phenotype --> formulas, state
  |
  +---brain block--> Brain  <-- inputs from the world (brain_adapter) and the animal's own state
```

## The three layers

### 1. Layout: where the genes are (`dna.py`, `layouts.py`)

A `GenomeLayout` is an ordered list of `GeneSpec(id, length)`. Order fixes positions, so reordering or
resizing changes every later position; bump the layout's `version` when you do. `ANIMAL_LAYOUT` (466 digits:
70 body digits, that is 15 four-digit genes, three three-digit genes and one single-digit gene, then a 396-digit brain block) and
`PLANT_LAYOUT` (24 digits) are plain data.

A `DNA` pairs a layout with an immutable digit string. It offers four reads and nothing else (a
`DiploidDNA` of two strands offers `value`, `digit` and `values`, with the two blended; see
[dna-and-traits.md](dna-and-traits.md#diploid-genomes)):

| Call | Returns |
| --- | --- |
| `dna.value("size")` | the gene as a float from 0.0 to 1.0 (digits as a big-endian base-4 number, divided by the maximum) |
| `dna.digit("sex_strategy")` | the raw digit 0 to 3 of a single-digit gene |
| `dna.raw("size")` | the gene as an integer |
| `dna.slice_of("size")` | the gene's digits |

Gene IDs such as `"size"` are only names for slots. DNA does not know what `"size"` is for, and has no
properties named after traits.

### 2. Trait table: what each trait reads (`trait_defs.py`)

A `TraitDef` is one row:

| Field | Meaning |
| --- | --- |
| `name` | the trait's name in the phenotype |
| `genes` | gene IDs it reads; with several, the mean of their values (polygeny) |
| `lo`, `hi`, `scale` | the range, and whether 0 to 1 maps onto it linearly or geometrically (`Scale.LOG`, `lo` must be above 0) |
| `kind` | `CONTINUOUS` (a float), `INTEGER` (`lo + int(g * (hi - lo))`), or `CATEGORY` (the raw digit of a single-digit gene) |
| `mutation_step` | typical mutation size as a fraction of the range; `TraitSet.position_biases()` turns it into the per-gene `gene_biases` that `DNA.mutated` reads |

A `TraitSet` is the table for one species. It checks at construction that every gene ID exists in the
layout and every name is unique, and `TraitSet.express(dna)` returns a dictionary of every trait's value. It
refuses a genome with a different layout.

Two patterns fall out of the table with no extra code:

- **Pleiotropy, one gene feeding several traits.** The `size` gene feeds the trait `size` (0 to 1, used by
  damage capacity, energy and speed) and the trait `mass` (1 to 4). `traits_reading("size")` lists them,
  which is what a mutation in that gene can change.
- **Polygeny, several genes feeding one trait.** List several gene IDs in `genes`. The animal and plant
  tables do not use it yet; the tests do.

Traits with simple linear ranges (`fov_degrees` 40 to 360, `max_biomass` 20 to 200) live in the table.
Quantities that combine traits live in code (see below).

### 3. Organism: formulas and state (`traits.py`)

`AnimalTraits(dna)` and `PlantTraits(dna)` check the layout, call `express`, and keep the result as
`phenotype` (a mapping fixed at birth). From it they compute derived values once (`base_max_speed` is
`(2 + 6 * speed) / (1 + 0.8 * size)`; `basal_metabolism` adds mass, repair and the cost of each sense), then
carry runtime state that the simulation changes every tick: energy, health, vitality, age, drive flags.

The split matters:

| Kind of value | Where it lives | Changes during life? |
| --- | --- | --- |
| Genotype | `DNA` | no (immutable) |
| Primary trait values | `phenotype`, from the `TraitSet` | no (fixed at birth) |
| Derived values (`mass`-based speed, upkeep) | attributes set in `__init__` | only through vitality scaling (`current_max_speed`, `effective_*_eff`) |
| State (energy, health, age, flags) | attributes updated by `update_*`, `feed`, `apply_damage` | yes |

## A worked example

An animal whose `size` gene is the digits `3 2 0 1`:

1. The layout says `size` occupies digits 8 to 11, so `dna.slice_of("size")` is `(3, 2, 0, 1)`.
2. Read as base 4 that is `3*64 + 2*16 + 0*4 + 1 = 225` of a maximum 255, so `dna.value("size")` is
   `0.8824`.
3. The trait table has two rows reading it: `size` (range 0 to 1) gives `0.8824`, and `mass` (range 1 to 4)
   gives `1 + 0.8824 * 3 = 3.647`.
4. `AnimalTraits` uses them: `max_energy = 100 * (1 + 2 * 0.8824) = 276.5`, `max_damage_capacity =
   188.2`, and the speed formula divides by `1 + 0.8 * 0.8824`.

## Reproduction touches only DNA

`dna.reproduce(partner, rng, ...)` (or no partner to clone) returns a new `DNA`. Mutation and crossover work
on digits and gene positions from the layout; they do not look at the trait table. A child is then given to
`AnimalTraits(child_dna)`, which expresses it fresh. Because DNA is immutable and the operators return new
objects, a parent's genome and phenotype are untouched by having children.

Every random choice (`random`, `mutated`, `crossover*`, `reproduce`, `inspect_food`) takes a
`random.Random`, so a seed reproduces a run.

## Adding things

| To add | Do this |
| --- | --- |
| A trait that reads existing genes | one `TraitDef` row in `trait_defs.py` |
| A gene | one `GeneSpec` row in `layouts.py`, and bump that layout's `version` (saved genomes stop loading, on purpose) |
| A new species | a `GenomeLayout`, a `TraitSet`, and an organism class that applies formulas to the phenotype; add the layout to `LAYOUTS` so saved genomes restore |
| A derived quantity | a formula in the organism class, reading `phenotype`, not DNA |

If a new trait needs a number the table cannot express (a product of two traits, a threshold), keep the
table row for each input and put the combination in code. That is how the existing speed, upkeep and sensing
formulas work.

## Rules the code keeps

- Traits never touch digits; DNA never touches trait names. Both are checked by tests
  (`test_dna_has_no_trait_names`, and `TraitSet` rejecting gene IDs that are not in the layout).
- Every expressed value is inside its range. Gene values are clamped to 0 to 1 before they are mapped, so a
  bad genome cannot produce an invalid organism.
- A genome only ever meets its own layout: crossover between layouts, a trait set given the wrong DNA, and
  loading a saved genome against a changed layout version all raise.
- The organism's formulas are the original prototype's; a side-by-side run of the prototype and this code
  matched at every tick.

## What is not built yet

These wait on the owner's answers or on other tasks and are tracked in [TODO.md](../../TODO.md).

- Mutation is built (`DNA.8`, [#15](https://github.com/dwhagar/evolutionSimulator/issues/15)): expected
  changes per segment, low digits favoured by `position_bias` (default 0.5), and a separate `locality`
  (default 0.0, random). `TraitSet.position_biases()` derives a per-gene bias from the traits'
  `mutation_step`; callers pass it as `gene_biases=` to `reproduce` / `mutated`. Nothing in the simulation
  passes it yet, so organisms use the layout defaults until the world loop wires it in.
- Crossover is built (`DNA.7`, [#14](https://github.com/dwhagar/evolutionSimulator/issues/14)):
  `reproduce` defaults to `crossover_linked`, a few cut points that mostly fall between genes, with
  `gene_fidelity` (default 0.9) setting how often one falls inside a gene. Its mutation counterpart is
  `locality`.
- Tuning constants inside the formulas are still inline numbers (`TRAIT.3`). The trait table already holds
  the ranges; the formula constants (`0.08`, `0.18`, `0.75`) are what remain.
- Diploid is built (`DNA.13`, [#3](https://github.com/dwhagar/evolutionSimulator/issues/3)):
  `DiploidDNA` holds two `DNA` strands and blends each gene by a `DominanceModel` (default codominant,
  the average) when `value`, `digit` or `values` is read, so the trait table does not change. Which species
  use it is decided when the world creates the first generation.
- The reproduction genes are built (`REPRO.5`, `TRAIT.6`): `fertility` is gone, and `caregiving`, `repro_interval` and
  `repro_drive` replace it, so every body gene is read by a trait and `TraitSet.unread_genes()` is empty (see
  [dna-and-traits.md](dna-and-traits.md#reproduction-and-longevity)). The plant seed genes are built too (`REPRO.3`, plant layout v2). Still to build: the protective effect of
  caregiving (needs the `SENSE.1` "young nearby" sense).
