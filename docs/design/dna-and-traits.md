# DNA and traits objects

Design of the first two objects, `evolution_simulator.dna` and `evolution_simulator.traits`.
Written 2026-10-14 by the Foundations 1 thread.

## What exists

| Module | Contents |
| --- | --- |
| `dna.py` | `DNA` (immutable genome), `GenomeLayout`, `GeneSpec` and `BlockSpec` (the gene table); knows gene IDs only |
| `diploid.py` | `DiploidDNA` (two `DNA` strands read through a `DominanceModel`), `DominanceModel`, `CODOMINANT` |
| `layouts.py` | `ANIMAL_LAYOUT` (1264 digits: 100 body, 1164 brain, version 9) and `PLANT_LAYOUT` (33 digits) as plain data, and `dna_from_dict` |
| `brain.py`, `brain_adapter.py` | The `Brain` network and the world-side inputs and outputs; see [brain.md](brain.md) |
| `trait_defs.py` | `TraitDef` and `TraitSet`: what each trait reads from DNA, its range, scale and mutation step; `ANIMAL_TRAITS`, `PLANT_TRAITS` |
| `traits.py` | `BaseTraits`, `AnimalTraits`, `PlantTraits`: runtime organism state and the formulas built on the traits; `AnimalTraits` also builds the animal's `Brain` |

The model is the owner's prototype (archived in [`docs/archive/prototype`](../archive/prototype/README.md)),
not the defaults suggested by the research notes ([DNA and reproduction](../research/dna-and-reproduction.md), including its review of the prototype, and the traits note in PR #12). The prototype answers several of the
open questions in issues #2 to #11 by example; those answers are used here and listed under
[Decisions taken from the prototype](#decisions-taken-from-the-prototype) so they can be confirmed.

## DNA

- A genome is an **immutable** tuple of base-4 digits (0 to 3), fixed length. `DNA` is one strand (haploid); a diploid genome is two of them, see [Diploid genomes](#diploid-genomes).
- A **gene** is a run of consecutive digits read as a big-endian base-4 number and scaled to a float
  from 0.0 to 1.0 (`dna.value(gene_id)`). A single-digit gene can instead be read as a raw category
  (`dna.digit(gene_id)`, used for `sex_strategy`).
- The shape of a genome is a **`GenomeLayout`**: an ordered table of `GeneSpec(id, length)` rows. Order fixes
  the digit positions and the sum of lengths is the genome length, so adding a gene means adding one row.
  Genes that feed one system are tagged as a cluster and sit together (`DNA.15`), so positions are no longer
  the prototype's. Each layout has a name and a `version` to bump whenever the table changes shape.
- A **gene block** (`BlockSpec`) is a gene that holds an array of numbers instead of one value: `count`
  values of `digits_per_value` digits each, decoded onto a range `low` to `high` (`dna.values(gene_id)`).
  The animal's brain is one block of 198 two-digit values over -2 to 2. A block's values come in `groups`
  that crossover keeps together (one per hidden neuron). A block is still a gene with a position, so it is
  read, replaced (`dna.replaced(gene_id, digits)`, or `dna.with_value(gene_id, 0.75)` to set a gene to the digits nearest a
  value from 0 to 1), saved and compared like any other.
- Genes belong to a named **segment** (`GeneSpec(..., segment="brain")`, default `"body"`); the genes of a
  segment must be consecutive. Segments are what mutation is set per, and they are the only place the genome
  has structure beyond the gene table. `ANIMAL_LAYOUT` has `body` (digits 0 to 100) and `brain` (100 to 1264).
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
| `mutated(rng, rate=None, mutations_per_segment=None, position_bias=None, locality=None, gene_biases=None)` | A changed digit moves to another digit. **How many** change: with `rate`, every digit changes with that probability whatever its segment; with `mutations_per_segment={"brain": 1.0}`, each named segment gets that expected number of changed digits per child; with neither, the layout's `default_mutations` apply (0.01 per digit for the animal body, 0.005 per digit for the plant, 1.0 per child for the animal brain). The two cannot be combined. **Which** digits (`DNA.8`, [#15](https://github.com/dwhagar/evolutionSimulator/issues/15) option B): inside each value, every more significant digit is `position_bias` times as likely to change as the one below it (default 0.5, plants 0.75; 1.0 is the old even spread), so most mutations are small nudges and a few are big jumps. The total number of changes does not depend on it. `gene_biases={"size": 0.3}` sets it per gene, for example from `TraitSet.position_biases()`. **What** it becomes ([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)): with chance `locality` (default 0.0, fully random) it moves to a neighbouring digit (+-1), otherwise to one of the other three digits with equal chance. |
| `crossover_linked(partner, rng, mean_cuts=1.0, gene_fidelity=0.9)` | **The default** (`DNA.7`). A few cut points, starting from a random parent and switching parent at each cut, so neighbouring genes travel together. `mean_cuts` is the expected number of cuts (a value below 1 is the chance of one cut). `gene_fidelity` is how closely a cut follows the gene table: 1.0 always cuts between whole genes (a brain neuron stays whole), 0.0 always cuts at a random digit inside the unit, and the default 0.9 is mostly between genes with the occasional odd cut inside one. |
| `crossover(partner, rng)` | Uniform per-digit crossover (the prototype's operator); no longer the default. |
| `crossover_one_point(partner, rng)` | Front of this genome, back of the partner, one random cut. |
| `crossover_by_gene(partner, rng)` | Each whole gene from either parent (a block counts as one gene). |
| `crossover_by_unit(partner, rng)` | Each whole **unit** from either parent: a gene, or one group inside a block. For the brain that is a whole hidden neuron with its incoming and outgoing weights, so a child never gets a blend inside a neuron. The same as `crossover_by_gene` on a layout with no blocks. |
| `clone_with_mutation(rng, ...)` | Asexual path; the same mutation settings as `mutated`. |
| `reproduce(partner, rng, rate=None, crossover=None, mutations_per_segment=None, position_bias=None, locality=None, gene_biases=None)` | Single entry point: no partner clones, a partner crosses over, then mutates. `crossover=` swaps in any of the strategies above; the default is `crossover_linked`, and `functools.partial(DNA.crossover_linked, mean_cuts=2, gene_fidelity=1.0)` changes its settings. |

The prototype's `+` operator is gone because it cannot take an RNG or a rate. Mixing two species
(different layouts) raises `TypeError`.

The mutation rate is **per digit** by default, as the DNA research note recommends, so the expected number of
changes per child scales with genome length: about 0.76 for the animal body and 0.15 for a plant (the plant layout uses half the animal rate, `REPRO.3`). That would
give the 396-digit brain about 4 changes per child on its own, so the animal layout sets the brain's default as
**expected changes per segment** instead (1.0 per child). The defaults live on the layout
(`GenomeLayout(..., segment_mutations={...})`), and every call can override them, so the owner's answers to
[#14](https://github.com/dwhagar/evolutionSimulator/issues/14) and [#15](https://github.com/dwhagar/evolutionSimulator/issues/15)
change numbers, not code.

## Diploid genomes

Owner's answer to [#3](https://github.com/dwhagar/evolutionSimulator/issues/3) (`DNA.13`): every gene comes in
two copies. `DiploidDNA(first, second, dominance=CODOMINANT)` in `diploid.py` holds two ordinary `DNA` strands
with the same layout. Haploid is kept as an option by simply using `DNA`; both satisfy the `Genome`
protocol in `dna.py` (`layout`, `ploidy`, `value`, `digit`, `values`, `distance`, `reproduce`), so
`TraitSet.express`, `AnimalTraits` and `PlantTraits` take either and nothing in the trait tables changes.

- **Reading.** For each gene the two strands' decoded values `a` and `b` are blended by the
  `DominanceModel`: `(a + b) / 2 + c * |a - b| / 2`. The coefficient `c` runs from -1 to 1. `0` is
  codominant, the plain average, and is the default; `1` makes the higher strand fully dominant, `-1` the
  lower, and values between are partial dominance. `DominanceModel(default, {gene_id: c})` sets it per
  gene. A single-digit category gene (`sex_strategy`) blends its digits and rounds half up. The brain
  block blends weight by weight, so the brain is built from the decoded expressed values. A
  homozygous genome (`DiploidDNA.from_haploid`) expresses exactly as the haploid one, whatever the model.
- **Making a child.** `reproduce(partner, rng, ...)` follows meiosis: each parent makes a gamete
  (`gamete(rng)`: its own two strands recombined with `crossover_linked`, or any strategy passed as
  `crossover=`), each gamete is mutated, and the child takes one from each parent. With no partner the
  two strands are copied and mutated separately (asexual; `DiploidDNA(g, g)` with `g = parent.gamete(rng)`
  is selfing). The child inherits the first parent's dominance model.
- **Mutation counts.** Expected changes per segment (the layout defaults and `mutations_per_segment`)
  stay *per child*, so each of the two strands gets half; a per-digit `mutation_rate` applies to every
  digit of both strands as it stands. All other mutation settings (`position_bias`, `locality`,
  `gene_biases`) pass straight through.
- **Other behaviour.** `distance` is the mean fraction of differing digits over the closer pairing of
  strands (the order does not matter, which suits mate choice, `REPRO.4`). Equality and hash ignore strand
  order. `to_dict` / `DiploidDNA.from_dict` save both strands (each checks its layout version) and the
  dominance model.
- **Not decided.** Which species are diploid. Nothing creates diploid organisms yet; the world loop picks
  `DNA` or `DiploidDNA` when it creates the first generation.

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

The formulas and constants are the prototype's, unchanged apart from reproduction and repair
(see [Reproduction and longevity](#reproduction-and-longevity)). A comparison harness ran the prototype and the
port side by side over 300 random animals (300 ticks each, with feeding, damage, stimuli, mating and
signalling) and 300 random plants (400 ticks each, with grazing and seeding) and found identical state at
every step. The harness is not in the repo.

## Reproduction and longevity

`REPRO.5`, `TRAIT.6` and, on top of them, `REPRO.8` (with `TRAIT.7`, `DNA.9` and the per-hour charging of
`WORLD.7`), from the design in [reproduction-genes.md](reproduction-genes.md) and the owner's answers to
[#16](https://github.com/dwhagar/evolutionSimulator/issues/16),
[#17](https://github.com/dwhagar/evolutionSimulator/issues/17) and
[#36](https://github.com/dwhagar/evolutionSimulator/issues/36). The animal layout was version 5 then (76 body digits,
five 3-digit reproduction genes, `parenting`, `repro_cooldown`, `repro_drive`, `fertility` and `recovery`, and the
396-digit brain, 472 in all). `SENSE.16` added `sight_acuity` (96 body digits, 1,004 in all) and `DNA.15` regrouped the genes
into clusters, with the five reproduction genes next to each other: layout version 7 (see
[gene-clusters.md](gene-clusters.md)).

| Gene | Trait | Range | What it does |
| --- | --- | --- | --- |
| `parenting` | `care_fraction` | 0.10 to 0.80 | A newborn starts with the mean of its parents' share of its own energy store. Each parent pays at its own value. |
| `repro_cooldown` | `cooldown_days` | 2 to 90 days, log | Gap between matings, in simulated days, stretched by repair. |
| `repro_drive` | `repro_drive` | 0 to 1 | Lowers the energy needed to start looking for a mate, makes the animal bolder while a mate is in view, bends how close a possible mate looks to the brain (`Temperament.repro_drive`), and shortens life. |
| `fertility` | `fertility` | 0 to 1 | Chance a mating takes, litter size (1 to 8) and gestation (2 to 20 days) when the animal bears; upkeep for either sex. |
| `recovery` | `recovery` | 0 to 1 | How fast lost health heals and how fast energy is regained at rest; upkeep. |
| `sex_strategy` | `sex`, `drive_modifier` | digit 0 to 3 | `digit % 2` is the sex (0 impregnates, 1 bears); digit 2 raises the effective drive by 25%, digit 3 lowers it by 25%. The prototype's behaviour offsets for digits 0 and 3 are kept as they were. |

- **The reference tick.** Every per-tick rate in `traits.py` is "per reference tick", an hour of simulated time
  (`REFERENCE_TICK_SECONDS = 3600`), and every duration is kept in reference ticks (`TICKS_PER_DAY = 24`). The
  world multiplies the rates by `dt = seconds_per_tick / 3600` (`World.dt`), and
  `update_metabolism_and_aging(movement_speed_ratio, dt)` charges wear, upkeep, healing, the cooldown and the
  pregnancy by it. Since `WORLD.7` the world scales movement, turning, the energy spent moving, grazing,
  poison and plant growth and upkeep by `dt` too, and the default tick is one hour (`dt` = 1), which is what the
  numbers were set for.
- **Lifespan.** `wear_per_tick` is `WEAR_BASE * (1 + 0.6 * repro_drive) / (1 + 3.5 * somatic_maint)` with
  `WEAR_BASE = 0.0362`, so `lifespan_ticks` (in reference ticks, hours) is the damage the body can take divided by
  that. An animal with size 0.5 and repair and drive 0.5 lives 8,765 hours, about a simulated year; a drive of 1
  gives 62.5% of the life of a drive of 0.
- **Maturity.** A newborn is a juvenile for 6% of its expected lifespan (`MATURITY_SHARE`): its
  `mating_cooldown` starts there and counts down by `dt`. Bigger, longer-lived animals mature later.
- **Mating.** `AnimalTraits.mate(impregnator, bearer, rng)` takes a sex-0 and a sex-1 animal that can mate
  (alive, off cooldown, not pregnant, more energy than the effort) or returns `REFUSED` and charges nobody.
  Otherwise each spends 3% of its store, starts its cooldown (`cooldown_days * 24 * (1 + somatic_maint)`
  hours), and the mating takes with chance `0.30 + 0.60 * mean fertility`. A mating that takes fixes the litter's
  genomes now (`bearer.dna.reproduce(father.dna)`, one per young, the bearer's `fertility` sets how many)
  and makes the bearer pregnant: a `Pregnancy` on `AnimalTraits.pregnancy` holding the genomes, the time left
  and the father. Her cooldown starts at the birth.
- **Pregnancy.** The bearer cannot mate, does not look for a mate and shows no mate to her brain; she is
  slowed by `0.3 * litter / 8` and burns `0.5 * litter / 8` more of her basal metabolism. The time left counts down
  by `dt`; when it is up and `World._deliver` finds room under the animal cap, `AnimalTraits.give_birth(bearer,
  newborns)` runs.
- **Birth.** Each parent pays `0.5 * care_fraction_own * (sum of the newborns' energy stores) * (1 + 2 *
  somatic_maint)`; each newborn starts with half of each paying parent's `care_fraction` times its own store (the
  parents' mean when both pay), without the surcharge. Every payer needs strictly more energy than the cost, else
  nobody is charged and the bearer keeps carrying the litter (the guard of `TRAIT.5`). A father who has died pays
  nothing and gives nothing. The litter appears next to the bearer, as far as the animal cap allows, and she pays
  only for those born.
- **Longevity trade-off (`TRAIT.6`).** Repair costs upkeep `0.20 * somatic_maint ** 2`, a birth costs
  `1 + 2 * somatic_maint` times as much, and the cooldown is stretched by `1 + somatic_maint`.
- **Upkeep.** Staying ready costs `0.03 * (5 / cooldown_days) ** 0.5`, the drive `0.05 * drive ** 2`, fertility
  `0.04 * fertility ** 2` and recovery `0.10 * recovery ** 2`, all per reference tick and in `basal_metabolism`.
  Drive costs use the gene, not the sex-modified drive.
- **Wanting a mate.** The energy share needed is `clamp(0.85 - 0.5 * effective_drive - 0.2 * (1 - vitality), 0.10,
  0.95)`. In a cooldown or a pregnancy a possible mate does not show up in the brain's inputs, `ready_to_mate` is
  0 and the animal does not call for one.
- **Recovery (`TRAIT.7`).** Lost health heals with a half-life of `20 * (1/20) ** recovery` days (20 days at 0, 1
  day at 1) while the energy store is at least half full, at 0.5 energy per point; it replaces the old "4 health per
  feeding". Wear (ageing) does not heal. `SleepRules.energy_regain` is multiplied by `0.5 + 1.5 * recovery` (the
  world reads `AnimalTraits.rest_regain_factor`). An average sleeper roughly breaks even, a fast healer gains.
- **First generation.** `World.populate` builds animals with `layouts.founder_animal_dna`: random genomes with
  `fertility` 0.3 (about three young), `parenting` 0.1 and the rest of the reproduction genes at 0.5 (`FOUNDER_LEVELS`).
  `add_animal` takes whatever genome it is given.
- **Built later (`SENSE.14`).** The protective effect of `parenting` on aggression and fear and the "own young" channel
  exist now (animal layout version 8; version 9 added `camouflage`, below). The pregnancy list is kept on
  the bearers (visited in id order) rather than as a separate list in the world; the behaviour is the same.
- **Constants.** They are fields of the rules tree in `config.py` (`TRAIT.3`; `life.wear_base`, `life.drive_wear`,
  `reproduction.*`, `recovery.*` and so on, listed in [trait-config.md](trait-config.md)), named after the design note's
  table. The gene ranges are in `trait_defs.py`.
- **Long-run check.** `src/evolution_tools/reproduction_check.py` runs the real traits in a small food-limited ecology and
  reports where the genes settle; see [reproduction-genes.md](reproduction-genes.md#long-run-check).

## What every gene costs (TRAIT.9)

`DNA.15`'s cost table showed eight genes that paid nothing, so selection would push the useful ones to the top.
Each now pays, or has a recorded reason not to (`TraitSet.free`, a gene-to-reason table; `unpaid_genes()` is empty and a
test keeps it so). All the numbers are in the rules tree ([trait-config.md](trait-config.md)) and are placeholders to tune.

| Gene | Cost | How it works | Top of the range |
| --- | --- | --- | --- |
| `speed` | `body.speed_reference`, `body.kinetic_burn` | Moving burns `kinetic_burn * mass * (speed / speed_reference) ** 2` per reference tick, with `speed` the distance moved per tick (it was `ratio ** 2`, whatever the gene). A fast animal pays more per hour, and twice as much per unit of distance for twice the speed. `speed_reference` 3.5 is an average animal (speed 0.5, size 0.5), so its burn is as before. | A fast small body (speed 8 per tick) burns 5 times the reference when it runs flat out |
| `agility` | `body.agility_cost` 0.06 | Reflex upkeep, `0.06 * agility ** 2` in the basal metabolism. | 0.06 (14% of a basal 0.43) |
| `aggression`, `fear` | `body.temperament_cost` 0.04 | Upkeep `0.04 * (aggression ** 2 + fear ** 2)`. A placeholder: neither has a price of its own until fights and flights cost something (`BRAIN.10`). They already trade against each other and, for fear, against mating (an afraid animal does not look for a mate). | 0.04 each (9%) |
| `sex_strategy` | the drive costs | The drive's upkeep and wear now use the effective drive (the gene times 1.25 for digit 2, 0.75 for digit 3), so digit 2 finds mates earlier and pays for it in life and upkeep, and digit 3 is the reverse. Digits 0 and 1 are the two sexes and cost the same. | digit 2 at drive 1: 1.25 effective, 56% more upkeep and 24% more wear |
| `learning_rate` | `brain.learning_cost` 0.004 | Plasticity upkeep, `0.004 * learning_rate` per reference tick (0 to 2), paid by every animal whatever the world's learning switch. | 0.008 (2%) |
| `camouflage` | `body.camouflage_cost` 0.03, `body.camouflage_slowing` 0.25 (`SENSE.21`) | Hiding costs upkeep, `0.03 * camouflage ** 2` in the basal metabolism, and speed: top speed times `1 - 0.25 * camouflage`. Others see the animal from up to half as far ([sense-genes.md](sense-genes.md#how-visible-a-thing-is-sense21)). Founders start at 0. | 0.03 (7%) and a quarter off top speed |
| `brain_gain` | none, recorded | A scale on the weights, which evolve too: any gain can be matched by the weights, so selection has no direction to push it. | |
| `curiosity` | none, recorded | Pays for itself: it nudges every output at random, so the animal moves, eats and mates less reliably, and a noisy speed burns more than a steady one because the burn is convex. | |

**Effect.** An average animal's basal metabolism rises by about 4% (0.4227 to 0.4409 for the all-ones reference) and its
movement burn is unchanged at average speed; a fast animal moving fast burns several times as much, a slow one a
fraction.

**Long-run check.** `src/evolution_tools/reproduction_check.py ... traits` runs the chemostat with stand-ins for what the genes buy
(half-speed foraging every tick; food shared in proportion to `1 + 0.5 speed + 0.2 agility + 0.3 aggression`; fear
halving injuries at the top). Three seeds, 12,000 ticks, population about 80: with the costs off, `speed` ends at 0.63,
0.84 and 0.84; with them on, 0.24 to 0.28, so the speed cost holds the gene low where it was running up. `agility`,
`aggression`, `fear` and `learning_rate` move between about 0.1 and 0.9 from seed to seed (drift in a population this
size), `aggression` mostly high because the stand-in benefit is generous (30% of the food share at the top against 9%
upkeep), and none stays pinned at 0 or 1 across seeds. The stand-in benefits are guesses, so this shows that the costs
bite, not where the genes will settle: recheck once fights and flights exist (`BRAIN.10`) and in the real world
(`REPRO.9`).

## Plants (REPRO.3 and TRAIT.8)

Plants are asexual and mutate slower than animals. `PLANT_LAYOUT` is version 3 and 33 digits: the six old
genes plus `seed_provision`, `seeding_interval` and `longevity` (3 digits each).

- **Asexual.** A seed's genome is `dna.reproduce(None, rng)`: a clone with the layout's default mutations,
  which for plants are 0.005 per digit (0.15 changed digits per seed, half the animal body's per-digit rate).
- **Lifespan is a gene (`TRAIT.8`).** `longevity` is 7 to 365 simulated days on a log scale (`lifespan_days`;
  a month, 30.4 days, is gene value 0.371, where a first generation starts, give or take 0.1). A plant dies when
  the time it has lived reaches that. Ageing is charged per reference tick (an hour) times the world's `dt`, like
  the animals', so only an hourly tick ages a plant as designed (`WORLD.7`). Long life trades against the rest:
  growth is multiplied by `1 - 0.3 * longevity` and the seed budget share by `1 - 0.4 * longevity`
  (`PLANT_LONGEVITY_GROWTH`, `PLANT_LONGEVITY_SEEDS`), so a perennial grows slower and seeds less than an
  annual. Plants therefore start shorter-lived than animals (a month against a year) and can evolve longer.
- **Pays for seeds.** `seed_provision` (5% to 50% of the seed's own full biomass, log scale) is what each
  seed starts with. The 35% seed budget (`SEED_BUDGET_SHARE`) is spent on as many seeds as it pays for, up to
  `seed_clutch`, so `seed_capacity = min(seed_clutch, budget / (provision * max_biomass))`. If the seeds
  came out bigger than the budget (a mutated `max_biomass`), `launch_seeds` scales every seed down together.
- **Waits between bursts.** `seeding_interval` (the `seeding_days` trait) is 2 to 60 simulated days on a log
  scale. A seedling is a juvenile for 6% of its lifespan, and after each burst the cooldown starts again for
  the interval. A plant seeds when it has reached 85% of its full size, its vitality is above 0.4, the cooldown is over
  and the budget pays for at least one seed.
- **Not built.** Plants have no behaviour, so there is no plant drive gene. Growth and upkeep are still per
  tick, not per hour, so the balance is untested until `WORLD.7` makes the hourly tick the default.

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
5. **Start-of-life state (`TRAIT.5`).** An animal's drive flags are set in `__init__` (the prototype left
   them unset until the first tick) and a plant's vitality starts at its seedling health (0.5, the
   prototype had 1.0 until the first tick).
6. **Reproduction and repair (`REPRO.5`, `TRAIT.6`).** The fixed mating cost (25% or 45% of the energy store,
   no check that it could be paid), the fixed cooldowns (40 or 100 ticks), the unused `fertility` gene and
   the linear repair cost are replaced as described under
   [Reproduction and longevity](#reproduction-and-longevity).
7. **Python 3.12 typing** (`X | None`, built-in generics) and ruff clean.

## Decisions taken from the prototype

These are the points where the prototype and the research defaults differ. Each is built the prototype's
way and is easy to change.

| Issue | Research default | Built | How to change |
| --- | --- | --- | --- |
| #2 genome detail | Gene-level | Base-4 digit sequence with genes as slices (closest to the "sequence" level) | Traits read genes only through `value` / `digit`, so another encoding changes `decode_*` only |
| #3 ploidy | Diploid, haploid option | Both: `DNA` is haploid, `DiploidDNA` is diploid (`DNA.13`, owner chose diploid) | See [Diploid genomes](#diploid-genomes); traits read through the `Genome` protocol and did not change |
| #4 reproduction | Both modes, no sexes | Both modes, plus a `sex_strategy` digit that shifts temperament (it no longer changes the mating cost, which now comes from the genes) | The digit is read in one place in `AnimalTraits.__init__` |
| #5 length | Fixed | Fixed | Gene IDs are not reserved yet; layout position is the identity |
| #6 trait set | Fixed | Fixed (16 animal genes plus the brain block, 8 plant genes) | Add a `GeneSpec` row to the layout and a `TraitDef` row that reads it |
| #8 diet | Plants only | Herbivore and carnivore efficiency genes, so predation is in | |
| #9 behaviour | No behaviour genes | `aggression` and `fear` are genes feeding a fixed fight-or-flight rule | |

## Known quirks, kept as in the prototype

Flagged by the research threads; not changed without the owner's call.

- **Digit position matters** ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)). The first digit of a four-digit gene carries three quarters of its range, so
  one mutation there can move a value by 0.25 to 0.75, while a last-digit change moves it by about 0.004.
  Resolved by `DNA.8` as option B: `mutated` favours the low digits (`position_bias`, default 0.5) and
  keeps a small chance of a big jump (about 1 change in 15 hits the top digit at 0.5, 1 in 7 for plants
  at 0.75). A Gray code was not needed.
- **Uniform per-digit crossover blends inside a gene** ([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)). Parents at 0.0 and 1.0 can give a child at
  0.75. Resolved by `DNA.7`: `reproduce` now defaults to `crossover_linked`, which cuts mostly between
  genes (and between whole brain neurons) with a small, configurable chance of a cut inside one. The
  uniform operator is still there as `DNA.crossover`.
- **Sex is an inherited digit with no balancing.** A small population can lose one sex. Assigning it at
  birth is a change to `reproduce`.
- **Mutation rate is per digit for the body and plants**, so the same 0.01 would give 0.65 changes per animal body
  but 0.30 per plant. Both are now readable as expected changes per child: `layout.default_mutations`
  holds them per segment and any call can set them with `mutations_per_segment` (`DNA.8`). The plant default is now 0.005 per digit
  (0.15 per child) as `REPRO.3` asked.
- **`somatic_maint` still cuts wear up to 4.5 times**, but it now competes with reproduction (`TRAIT.6`), so
  selection should not push it to the maximum. That rests on the design note's toy model, not on the
  simulator, which has no stable ecology yet.
- **Constants** are no longer inline: they are in the rules tree of `config.py` (`TRAIT.3`,
  [trait-config.md](trait-config.md)).
