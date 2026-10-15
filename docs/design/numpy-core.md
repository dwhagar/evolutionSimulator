# The numpy core

Design note for `WORLD.19`. The owner chose "rewrite the core with numpy" on the speed card
([#222](https://github.com/dwhagar/evolutionSimulator/issues/222), 2026-10-15) over keeping the core pure
Python, so that a full world (1,000 animals, 5,000 plants, hourly ticks) runs at one simulated day per real
second. This note says how, in what order, and what it costs. It writes no engine code: the two scripts
that come with it are a speed benchmark ([`src/evolution_tools/bench_world.py`](../../src/evolution_tools/bench_world.py))
and a feasibility check of the array techniques ([`src/evolution_tools/numpy_kernel_check.py`](../../src/evolution_tools/numpy_kernel_check.py)).
The build is `WORLD.20`, in the stages of [section 10](#10-build-stages), and does not start until the code it
would rewrite has stopped changing (`WORLD.15`, `SENSE.21`, `TRAIT.12` to `TRAIT.15`, and the `DNA.16`
report). Written by Research 5 from its measurements ([python-packages.md](../research/python-packages.md)).

## 1. The short version

- **The target is reachable but not by one trick.** A tick is 170 ms at 1,000 animals and 5,000 plants today;
  the goal is 41.7 ms (24 ticks a second). Sensing and thinking are about 64% of a tick, plants, eating,
  sleep and learning, indexing and bookkeeping the other 36%, so *everything* has to move to arrays: moving
  only the neighbour search would cap the gain near 1.3 times. A budget that adds up to about 32 ms is in
  [section 3](#3-the-target-and-the-budget); the array techniques behind its largest lines were run and
  cost 10 ms for sensing, brains, plants and bodies together at the largest size (kernel check, below).
- **State becomes columns, generated from the tables the project already has.** A gene is a row in the
  layout (`layouts.py`), a trait a row in the trait table (`trait_defs.py`): from those two tables the store
  gets a genome matrix, a column for every gene value and every trait, with no code per gene. Derived
  quantities (the 60 or so formulas in `AnimalTraits.__init__`) become named, array-style functions in a
  registry that declares what each one reads. A new gene (`TRAIT.13` to `TRAIT.17`, anything `DNA.16`
  recommends) is a table entry plus, if it changes behaviour, one short formula in one place. It is never a
  rewrite ([section 4](#4-state-as-columns)).
- **One formula, written once.** The formulas are written so that they work on a single number or a column
  of 1,000, so there is no scalar copy to keep in step. The old scalar classes stay in the repository until
  the cut only as the reference that new code is tested against, then go.
- **numpy becomes a core dependency** (`dependencies = ["numpy"]`). Windows wheels exist for Python 3.12 to
  3.14 (numpy 2.5.4: `win_amd64`, 12.9 MB, no compiler). SciPy is not needed: a sorted grid made of plain
  numpy matches `cKDTree` at this size. The "no numpy in the core" rule and its test
  (`tests/test_core_isolation.py`) are replaced by "no Qt, and nothing heavier than numpy".
- **Randomness becomes counter-based.** Every draw is a pure function of (seed, tick, organism id, purpose),
  so it does not depend on the order or number of other organisms, a viewer being attached, or how a run
  is cut into `run(n)` calls ([section 7](#7-randomness-determinism-and-the-break)). `state_digest` and the
  save format change at one clear version cut; old saves load by migration (state kept, the future differs).
- **Equivalence is checked twice.** Formula by formula against the old classes while both exist (no
  randomness, near-exact), and by statistics against *golden* records of the old engine over many seeds
  (the object engine is deleted at the cut, so the records must be taken first) ([section 9](#9-checking-old-against-new)).
- **Nine stages, one owner thread each**, in dependency order, with the old engine staying the default and
  fully working (viewer, saves, history, session, process host) until stage 8 flips it
  ([section 10](#10-build-stages)).

Where the six points of `WORLD.19` are: (1) what moves, sections [2](#2-what-moves-and-in-what-order) and
[5](#5-the-tick-as-array-phases); (2) columns from tables, [section 4](#4-state-as-columns); (3) the break,
[section 7](#7-randomness-determinism-and-the-break) and [8](#8-saves-the-read-api-and-the-consumers); (4) target and benchmark,
[section 3](#3-the-target-and-the-budget); (5) equivalence, [section 9](#9-checking-old-against-new); (6) stages,
[section 10](#10-build-stages).

## 2. What moves, and in what order

Cumulative shares of a tick by phase, from `cProfile` on 1,000 animals and 5,000 plants (48 ticks after 20
of warm-up, which include two nights; the profiler slows everything about 2.8 times, so read the shares,
not the seconds). Plain timing of the same run: 155 to 170 ms a tick.

| Phase in `World._step` | Share today | What it is in arrays | Stage |
| --- | --- | --- | --- |
| Sense (`WorldSenses.perceive`, `sensing.sense`, neighbour search) | 46% | A sorted grid, candidate pair tables, masks per organ, segmented nearest-by-class reductions, noise from counter draws ([section 6](#6-neighbour-search-and-sensing)) | 3 |
| Think, apart from the brain (`think`: inputs, interrupts, learner log, curiosity, wander, decode) | 14% | Columns for the 28 inputs and 6 outputs, vector arithmetic, a ring buffer for the learner | 4 |
| Brain forward pass (`Brain.decide_with_hidden`) | 4% | `einsum` over (animal, slot, input), gates as a mask: 0.4 ms for 1,000 brains measured | 4 |
| Contact check between decisions (`_newly_touched`) | 5% | Shares the pair tables of the sensing step | 3 |
| Sleep, tiredness, nightly learning | 4% | Boolean masks; learning is one batched update at dusk | 4, 5 |
| Plant environment, growth, soil and shade, seeding | 8% | Plain column arithmetic; soil and shade from a plant-plant pair table refreshed in the existing staggered slices | 5 |
| Eating, attacks, scavenging | 7% | Contact pair tables; contention settled by a sort, see [5.2](#52-rules-that-depended-on-the-order-of-animals) | 5 |
| Metabolism, ageing, healing, movement | 3% | About 20 column operations | 5 |
| Rebuilding the animal index twice a tick | 2% | One sort per tick | 3 |
| Mating, pregnancy, births, corpses, removal, calls, the rest | 7% | Masks; the few rows that give birth or pair are handled in small loops over events | 5 |

Everything is on the list. The cost is spread (no phase above half, the biggest is sensing), which is why
the package research found no single drop-in speed-up: SciPy's KD-tree makes neighbour search about 4 times
faster (9 against 41 ms in the research test) but search is only about a quarter of a tick.

**Order of the work** follows what each part needs from the others, not its size:

1. The store, the generated columns, the registry, the counter-based random numbers and a loader from an
   old `World` into arrays (needed early, to test everything else against the old engine).
2. Genomes and bodies in bulk: expression of traits, the derived quantities, reproduction operators.
3. Neighbour search and sensing (the biggest line).
4. The brain and the decisions.
5. Body and food, plants, life cycle.
6. The `World` look-alike, views, events, session and the other consumers.
7. Saves and migration.
8. Equivalence, goldens, flip the default, delete the old engine.

## 3. The target and the budget

**Target.** A full world (1,000 animals, 5,000 plants, the hourly default tick) at one simulated day per
real second: 24 ticks a second, **41.7 ms a tick**, against about 170 ms today (best of three, mean over two
simulated days, which include the night).

**The benchmark** is [`src/evolution_tools/bench_world.py`](../../src/evolution_tools/bench_world.py). It builds seeded worlds
of 60/300, 300/3,000 and 1,000/5,000 (animals/plants at the start; the plants die back at first, because the
founders are drawn to pay their way, so the table prints the counts at the end), warms up for 20 ticks and
times 48 single ticks, three times from a fresh world, and prints mean, median, 95th percentile and worst
tick, ticks a second and simulated days a second. `--target-ms 41.7` fails when the largest size is over;
`--json` and `--compare` check a change against an earlier run (`--tolerance`, default 15%); `--profile` shows
where a run goes; `--engine array` is added by `WORLD.20` (the `ENGINES` table in the script). Every PR that
touches the tick should rerun it and quote the three lines.

Measured on the sandbox the research ran on (4 cores used one at a time, CPython 3.13, numpy 2.5.4), with the
object engine as it is on `main`:

| World | Mean ms a tick | Median | 95th percentile | Ticks a second | Simulated days a second | Alive at the end (animals/plants) |
| --- | --- | --- | --- | --- | --- | --- |
| 60 animals, 300 plants | 4.4 | 4.6 | 8.4 | 230 | 9.6 | 60/268 |
| 300 animals, 3,000 plants | 40.7 | 52.6 | 70.4 | 25 | 1.02 | 298/2,060 |
| 1,000 animals, 5,000 plants | 169.9 | 210.8 | 301.4 | 5.9 | 0.25 | 973/1,998 |

Day ticks cost more than night ticks (sleepers do not sense), so the median sits above the mean. The target
is about the mean: a day per second on average.

**The budget** says what each part of the array tick may cost at 1,000/5,000, adding up to about 32 ms (a
little under 41.7, which leaves room for the lines that turn out dearer than estimated). Lines marked
*measured* are backed by the kernel check; the others are estimates from similar array work and are the
first thing each stage must confirm or correct.

| Part | Budget ms | Basis |
| --- | --- | --- |
| Sort the animals, plants and corpses into grids | 1.5 | Part of the 1.7 ms pair generation, *measured* |
| Sensing: plant pairs, animal pairs, corpses and trails, noise, the 28 input columns | 9 | Plant sensing 7.8 ms and animal sensing 1.3 ms for *all* animals at a reach of 50, *measured*; only the animals whose brain runs this tick sense (about 40% in the profile), which pays for corpses, trails and assembly |
| Decide: brains, curiosity, wander, decode, decision cache | 3 | Brain forward 0.4 to 0.5 ms *measured*; the rest estimated |
| Contact checks between decisions | 1 | Reuses the grid |
| Body: sleep, tiredness, metabolism, ageing, healing, movement, calls | 3 | A 15-operation body step is 0.07 ms *measured*; allowance for the rest |
| Eating, attacks, scavenging, with the contention sort | 3 | Estimated |
| Plants: environment, growth, soil and shade, seeding | 4 | A plant growth step is 0.08 ms *measured*; the soil and shade pair table and seeding are the cost |
| Mating, pregnancy and births | 2 | Estimated; the few events are loops |
| Nightly learning, averaged over the day | 1.5 | A batched update of about 1,000 animals once a day, estimated at 35 ms |
| Smell trails (`SENSE.20`, off by default) | 1 | A dense grid with a decay factor |
| Compaction, id table, events, recorder and species listeners | 3 | Estimated |

What would break it: the farthest sense is 100 units for smell (84 for sight, 85 for hearing). At a reach of
100 the plant pair table is 274,000 candidate pairs and the plant sensing kernel alone costs 21 ms
(*measured*), against 7.8 ms at a reach of 50. The founders start mid-range (sight about 30, smell about 50),
but evolution may push the reach up. Ways to bring it back are in [section 6](#6-neighbour-search-and-sensing)
and each is cheap to try; the stage 3 PR must report the sensing time at a reach of 50 and of 100.

**What to expect at other sizes.** The array tick has a floor of roughly 300 to 500 numpy calls at a few
microseconds each, about 1.5 ms, so small worlds gain little: 60/300 should go from 4.4 ms to about 2 ms
(about 2 times), 300/3,000 from 41 to about 10 ms (about 4 times), 1,000/5,000 from 170 to 30 to 40 ms (4 to
6 times). The gain grows with the world, which is the right way round for the runs that need it.

**Kernel check.** [`src/evolution_tools/numpy_kernel_check.py`](../../src/evolution_tools/numpy_kernel_check.py) times stand-ins for
the techniques (not the real rules): nearest plant in view and nearest prey, threat and mate through pair
tables on a sorted grid (checked against a plain double loop on a small world first), a batched network with
16 gated slots, a plant growth step and an animal body step.

| Animals/plants | Plant pairs | Sense plants | Animal pairs | Sense animals | Brains | Plants | Bodies | Total ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 60/300, reach 50 | 366 | 0.38 | 82 | 0.16 | 0.04 | 0.03 | 0.02 | 0.6 |
| 300/3,000, reach 50 | 18,677 | 1.70 | 1,886 | 0.32 | 0.12 | 0.06 | 0.03 | 2.2 |
| 1,000/5,000, reach 50 | 104,545 | 7.82 | 20,770 | 1.30 | 0.51 | 0.08 | 0.07 | 9.8 |
| 1,000/5,000, reach 100 | 274,485 | 20.93 | 55,270 | 2.36 | 0.39 | 0.08 | 0.06 | 23.8 |

## 4. State as columns

### 4.1 The store

- **Tables**: `animals`, `plants`, `corpses`, plus small side tables for the ragged things
  (`pregnancies`, `learner logs`, the scent grid). Each table is a set of numpy columns of one length.
- **Rows are always in id order.** Ids rise at birth, new rows are appended at the end, and removal is a
  stable compaction by a boolean mask (one pass over every column, about 0.3 ms for the animals, done only
  in ticks where something died). So "visit in id order", on which repeatability rests today, is "visit
  rows in order", and `id -> row` is a `searchsorted` on the id column. No free list, no slot reuse.
- **Columns are grouped by dtype into a few 2-D arrays** (`float64` for state and traits, `uint8` for
  genomes, `int64` for ids and counters, `bool` for flags) with named views, so growing, compacting and
  copying are one operation per group, not one per column. Capacity doubles when full.
- **Genomes are a `uint8` matrix** `(animals, 1260)` for the animals and `(plants, 33)` for the plants.
  Diploid organisms (`WORLD.10`) add a strand axis, `(n, 2, length)`; haploid is strand count 1. The packed
  integer form the species tracker uses (`species.py`) is made from a row when sampled.
- **Float64 for state, float32 only for frames.** The numbers must agree with the scalar code to rounding.
- **Ragged state is pooled, not compacted.** A pregnancy holds up to `litter_max` (8) child genomes: a
  `pregnancies` table keyed by mother id with a `(rows, 8, length)` genome block. A learner's day log
  (`log_size` 64 snapshots of 29 numbers) is a ring buffer in a pool indexed by animal id, allocated at the
  first use and freed at death, about 15 MB for 1,000 animals. Neither is copied every tick.

### 4.2 Generated from the tables

What the project has already, as data: `GenomeLayout` and `GeneSpec` (name, length, cluster, block) in
`layouts.py`; `TraitDef` (genes, `lo`, `hi`, `scale`, `kind`, `combine`, mutation step) and `TraitSet` in
`trait_defs.py`; the rule constants (`TraitRules` and its sections) in `config.py`; display names and units
in `catalogue.py`. The store is built from these:

| Generated, with no code per gene or trait | From |
| --- | --- |
| The genome matrix and the position of every gene in it | `GenomeLayout` |
| Bulk decoding of every gene to its value in 0 to 1 (with dominance when diploid) and of the brain block to its 582 weights | `GeneSpec`, `BlockSpec` |
| A column for every trait, by name, and the array form of `TraitSet.express`: mean or modified clusters, linear or log scale, integer and category kinds | `TraitDef` |
| Which genes feed which trait, which traits share a gene (pleiotropy), the cost audit (`TraitSet.explain`, `unpaid_genes`) | unchanged, they read the same tables |
| Display names, units and tooltips for views and charts | `catalogue.py`, keyed by the same trait names |
| The save format for every column (name, dtype, unit), so a new column is saved without touching `persistence.py` | the column table |
| `trait_columns` for the recorder as zero-copy slices | the column table |
| The matrix migration when a layout version changes (new gene padded with its starting value) | `LayoutMigration` rows next to the version bump |

**Derived quantities** are what `AnimalTraits.__init__` and `PlantTraits.__init__` compute from the traits
and the rules: about 60 of them for animals (`body_radius`, `max_energy`, `base_max_speed`, each upkeep
term, `basal_metabolism`, `gestation_ticks`, …). They are written once, as functions of columns and of the
run's rules, in a registry that lists what each reads:

```python
@derived("animal", "basal_metabolism", reads=("mass", "repair_upkeep", "drive_upkeep", ...))
def basal_metabolism(c, r):            # c: the columns, r: the run's TraitRules
    return r.body.basal_scale * c.mass ** r.body.basal_exponent + c.repair_upkeep + c.drive_upkeep + ...
```

- Written with operators and `numpy.minimum`, `maximum`, `where`, never `if` on a value, so the same function
  runs on one number or a column. There is one implementation, and a test calls it on length-1 columns.
- The registry sorts the formulas into dependency order at start-up (a missing or circular `reads` fails
  there, not in a run). A test fails if a formula touches a column it did not declare.
- *Static* derived quantities are computed once, for a batch of newborns, when they are born. *Dynamic* ones
  (`current_max_speed`, the vitality dependents, the effective efficiencies) are registered with the phase
  that refreshes them.
- The rules are bound once per run (`WorldConfig.traits` is immutable), so a formula reads
  `r.body.basal_scale` as a constant. A rules field is therefore never a column.

**State columns** (`current_energy`, `current_health`, `accumulated_damage`, `age_ticks`, `mating_cooldown`,
`asleep`, `awake_time`, `heading`, `position`, …) are one table with a name, a dtype and an initial rule
(for example `current_energy = max_energy * body.start_energy`). A column that can be recomputed from others
is marked transient and is not saved. A test fails if a column is written by a phase and is neither saved nor
transient.

**What is not generated**, said plainly: what a gene *does* in the tick. A gene appears as a column by
itself; its effect on behaviour or cost is a formula or a line in a phase. That is the same one-place edit it
is today in `traits.py`, with the difference that nothing else has to change.

### 4.3 What a new gene costs

Taking `TRAIT.13` (plant gene `toughness`, plant layout version 4) as the model:

1. `GeneSpec("toughness")` in `PLANT_LAYOUT` and the version bump with its migration row: the genome matrix
   and its decoding gain the gene. *(Today's work, unchanged.)*
2. `TraitDef("toughness", ("toughness",), ...)` in the plant trait table: a `toughness` column appears,
   expressed, saved, named in the catalogue, in `trait_columns`, in the cost audit.
3. `@derived("plant", "eat_effort", reads=("toughness", "toxicity", ...))`: three lines.
4. The bite in the grazing phase divides by `eat_effort`: one line.
5. A line in the plant upkeep sum for the toughness cost (`TRAIT.13`'s balancer), and the entry in the
   balancer table that `TRAIT.17`'s test reads.

A new state variable such as `TRAIT.16`'s `toxin_load` is one row of the state table plus its use. A new
phase is a function with declared reads and writes added to the phase list. `DNA.16` may recommend more
(per-gene dominance, linked genes, genes that set the mutation rate): per-gene settings are already columns
or table rows, a mutation rate that is a gene becomes a per-organism parameter array to the vectorised
mutation, and a new way of combining genes in a cluster is a new `Combine` value and its array form in the
one place that implements `unit`.

## 5. The tick as array phases

The five steps of today's `_step` map onto phases that run in the same order over the same start-of-tick
world. Each phase is a function `(world_state) -> None` with declared reads and writes.

1. **Start of tick**: rebuild the grids (animals, plants, corpses; plants are static but births and deaths
   change them, and a sort of 5,000 keys is 0.2 ms), light, calls, sleep and tiredness.
2. **Sense and decide**, for the awake animals whose brain runs this tick (the others repeat the cached
   decision, as `cached_decision` does): pair tables, percepts, inputs, brain, curiosity, wander, decode.
3. **Live, move, eat**: metabolism, ageing, healing, turn and move with the wall clamp, then grazing,
   scavenging and attacks.
4. **Mate and deliver**, then **plants grow and seed**.
5. **Remove the dead, leave corpses, rot, advance the clock.**

### 5.1 Loops that remain

A loop over rows is allowed only where the work per tick is a count of *events*, not of organisms: pairing
animals that want to mate (tens), births (well under one a tick on average), bearers giving birth, sleep
listeners other than learning, and rare branches. Nothing that touches every animal or plant each tick is a
Python loop; review should look for one the way it looks for a missing test.

### 5.2 Rules that depended on the order of animals

Today the animal loop runs in id order and later animals see the effects of earlier ones. Arrays resolve the
same situations together. Each of these is a deliberate choice, listed so the equivalence tests expect it:

| Situation | Today | Array rule |
| --- | --- | --- |
| Several animals eat the same plant | Sequential: the first takes its bite, the next finds less | Bites are sorted by (plant, animal id), a segmented cumulative sum is clipped to the plant's biomass, so the lowest ids are fed first. **Identical result** to today's order |
| Several animals bite the same prey | Each applies its damage in turn; the last attacker is `killed_by` | Damage is summed per target; `killed_by` is the highest-id attacker, as today. A victim killed this tick has already moved and bitten in this tick (today a lower-id animal's earlier bite can stop it). **Differs by up to one tick of life** |
| Scavenging a corpse | Sequential meat removal | Same segmented clip as plants |
| Who pairs with whom | Greedy by id: each willing animal takes the closest willing, unpaired animal in reach | Small loop over the willing animals (tens), same greedy rule. **Identical** |
| Births | A loop in id order; each checks the animal cap and whether both parents can pay | Same, as a loop over due bearers. **Identical** |
| Seeds | Plants in id order, each limited by the plant cap | Segmented count against the remaining cap in id order. **Identical** |
| Decisions | All made before anyone acts | Same |
| Soil and shade | A staggered slice of plants each tick, in id order | Same slice, computed from the pair table. **Identical** |

## 6. Neighbour search and sensing

This is 46% of a tick and the biggest budget line, so it has the most detail. The kernel check implements
the plant and animal parts.

1. **Grid.** A uniform grid of cells (50 units in the check) over the 1,000 by 1,000 world. Each kind
   (animals, plants, corpses) is argsorted by cell number (`cy * width + cx`), with a `searchsorted` for
   where each cell starts. The cells of one grid row are contiguous in that order, so an animal needs one
   slice per *row* of cells in its ring, not one per cell.
2. **Candidate pair table.** For the animals that sense this tick, `np.repeat` and `arange` expand those
   slices into arrays `(animal_index, thing_index)` grouped by animal. Pair counts at 1,000/5,000 and a
   reach of 50: 105,000 plant pairs (the exact circle holds 37,500, so the cell grid costs 2.8 times the
   work it needs) and 21,000 animal pairs.
3. **Per-pair arithmetic**, with no trigonometry: `dx`, `dy`, `dist = sqrt(dx*dx + dy*dy)`, the surface gap
   `dist - body_i - body_j`, the field-of-view test as `dx*fx + dy*fy >= cos(half_fov) * dist` (a dot
   product against the facing vector, valid for half angles up to 180 degrees), hearing as
   `surface <= hearing_reach * loudness`, smell as `surface <= smell_reach * scent` (weak for prey and
   threats), exactly the rules in `sensing.sense`. Classification (young, prey, threat, mate, other) is the
   mass ratio and efficiency tests of `senses.classify`, as masks over the pair table. Trigonometric
   functions are used only on the few *chosen* neighbours per animal, to give the bearing.
4. **Nearest of each class.** `nearest_by(group, key, ident)`: the minimum surface gap per animal by
   `np.minimum.at` (or `reduceat` on animal-grouped pairs, which is a little faster), then the lowest id
   among the equals. The tie-break by id is exactly today's `(distance, ident)` key. Plants need only the
   nearest detected one and the nearest touched one, as in `WorldSenses.perceive`.
5. **Percepts as columns.** Direction, closeness and noise per class, relative size of the nearest prey or
   threat, calls (alarm and mating, strength and direction), crowding (a count over the pair table with
   `bincount`), touch and the wall (from the position, no pairs), daylight and the clock. The noise terms
   come from counter-based draws ([section 7](#7-randomness-determinism-and-the-break)): the mate's
   genome similarity is computed only for the chosen mate, as now, by comparing two rows of the genome
   matrix. These become the 28 input columns directly; no `Percepts` object per animal.
6. **Between decisions**, the contact check (`_newly_touched`) reads the same pair table at touch range.

**Controls on the pair count**, in the order to try them if the stage 3 measurement is over budget:

- Only the animals whose brain runs this tick build pairs (about 40% in the profile; `decision_interval`
  and `idle_interval_factor` already skip the rest).
- A finer grid: cells of half the reach with a ring of two cut the candidate count from 2.8 times the exact
  one to about 2 times; quarter-reach cells to 1.6.
- For plants only the *nearest detected* is wanted. Expanding rings outward from the animal's own cell and
  stopping at the first ring that has a detected plant means dense stands (where the nearest plant is in the
  first ring) never see the far rings.
- `float32` for the per-pair arrays halves memory traffic; positions are kept in `float64`.
- A cap on the pair table per animal, if ever needed, would be a rule change and needs the owner.

SciPy's `cKDTree` is not needed. In the research test `sparse_distance_matrix` took 3.8 ms for the exact
37,600 pairs against 1.7 ms for the 105,000 candidates of the grid, but the grid then pays for the per-pair
arithmetic; whole kernel 7.8 ms against about 6 ms, within the noise of an estimate. Staying with numpy keeps
the dependency to one package.

## 7. Randomness, determinism and the break

### 7.1 Counter-based random numbers

Today everything draws from one `random.Random`, so the stream depends on the order of every draw, the
number of organisms, and anything that draws extra (a sensor with noise on, a viewer). That is why a small
change anywhere reshuffles a whole run.

The array engine draws from a **pure function of its key**: `uniform(seed, stream, tick, id, k)`, where
`stream` names the purpose (sensing noise, curiosity, wander, taste, conception, crossover, mutation, seed
scatter, …), `id` is the organism and `k` the draw within it. The key is mixed with the splitmix64
finalizer (the same scramble `species.py` already uses), in `uint64` arithmetic on whole arrays:

```python
z = ((seed ^ stream * C1) ^ tick * C2) ^ ids * C3 ^ k      # uint64 columns, wraps modulo 2**64
z = mix(mix(z))                                              # mix: add, xor-shift, multiply, twice
u = (z >> 11) * 2.0 ** -53                                   # uniform in [0, 1)
```

Tested on a million draws: mean 0.4998, variance 0.0834, no correlation between neighbouring ids, ticks or
streams (all under 0.002), chi-square per degree of freedom 0.96; 27 microseconds for 1,000 draws. A
Gaussian is two uniforms through Box-Muller. (Use arrays or Python integers for the constants:
`numpy.uint64` scalars warn on overflow.)

What this buys:

- A run is a function of (config, seed, commands). Saving needs **no generator state**, only the seed and the
  tick; `run(10)` then `run(10)` is the same as `run(20)`.
- An organism's draws do not move when another organism is added or removed, so a change to one rule does
  not reshuffle every outcome (the property that makes "compare two versions of the rules" mean something).
- No thread or process ordering can change a draw. A viewer, a recorder or a species tracker that reads the
  world cannot disturb a run (they never draw).
- It does not depend on numpy's `Generator`, whose stream the numpy project reserves the right to change
  between versions.

Draws that choose among a variable number of candidates (which neighbour wins a tie, which mate) use the ids
and keys, never a stream position.

### 7.2 What "same seed, same run" means after the cut

- **Promised:** the same config, seed and commands give the same run, bit for bit, on the same machine with
  the same numpy build, however the run is cut into calls, whatever is attached to it, and whatever the
  display rate. This is the promise today, and it was never wider: Python's `math` functions come from the
  platform's C library, so Windows and Linux already differed in the last bit.
- **Not promised:** bit-identical state across numpy versions or CPUs. numpy picks vectorised code paths for
  `exp`, `tanh`, `sin` by CPU feature, so results can differ in the last bit between machines. The array
  engine is deterministic on a machine, and **statistically** the same elsewhere.
- **Not promised between engines:** the object engine and the array engine differ by design (the random
  numbers, the rules in [5.2](#52-rules-that-depended-on-the-order-of-animals)). They are compared by
  statistics only.
- **No thread races:** the engine is single-threaded. numpy's `einsum` and elementwise operations are
  deterministic on one thread; matrix multiplication through BLAS may use threads and change the order of a
  sum, so the batched brain uses `einsum` and the host sets the BLAS thread count to one. Parallelism is
  between runs (processes), never inside one.

### 7.3 Digests

`state_digest()` keeps its name and meaning (a check that two runs are the same) but is computed over the
columns' raw bytes, not over `repr` text, which is also much faster. Two digests are kept:

- `exact`: every saved column. Compared on load only when the save records the same numpy version and
  machine type.
- `structure`: ids, genomes, ages, sleep flags, counts, pregnancy state, everything that is an integer or a
  boolean. Always compared.

### 7.4 The version cut

- A new save format number (`FORMAT_VERSION` 6) with `engine: "array"` in the header. The object engine's
  format 5 stays readable.
- **Old saves load by migration, state kept, future different.** Every organism's genome, position, heading,
  energy, health, damage, age, cooldowns, pregnancy (with the litter's genomes and father), sleep and
  learner (day log and offsets), every corpse, the scent records, the clock and the config are read into
  columns. The Mersenne Twister state is dropped: the new generator is keyed by the seed and the tick. The
  v5 `state_digest` cannot be checked after migration; instead counts, ids, genomes and positions are
  compared with what the save says. The run goes on, but not as the old engine would have taken it.
- A fixture save from the last object-engine commit (tagged, `tests/data/`) is loaded in the migration test.
- This is a milestone in the sense of `docs/versioning.md`: the TODO thread proposes the version bump to the
  owner at the flip (stage 8).

### 7.5 The dependency

`pyproject.toml` changes from `dependencies = []` to `dependencies = ["numpy>=2.0"]` (default for the build
thread to confirm; the `gui` extra's `numpy>=1.26` is raised to match, so there is one rule). numpy 2.5.4 has
`win_amd64` wheels for cp312, cp313 and cp314 (12.9 MB), so no compiler is needed on the owner's Windows
machine, and PyInstaller already bundles it for the viewer. `tests/test_core_isolation.py` changes from "no
numpy" to "no Qt or other GUI module, and no third-party module but numpy". The hand-written scripts that
say "needs numpy" (`fit_seed_brain.py`) simply lose the caveat.

## 8. Saves, the read API and the consumers

The array world has to look like the object world to everything outside the engine until the consumers are
moved. The contract, from a read of what `session`, `history`, `species` and `viewer` call:

| Consumer | Calls on the world | In the array world |
| --- | --- | --- |
| Session and process host (`session/`) | `step`, `run`, `tick`, `dt`, `bounds`, `config`, `animal_views`, `plant_views`, `corpse_views`, `animal_detail`, `children_of`, `trace_brain`, `add_event_listener`, `add_step_listener`, `state_digest`, `populate`, `plant_count` | Same names on the new class. Views are built from column slices: `pack_animals` takes the float32 columns directly, so a frame costs microseconds, not a loop over view objects |
| History recorder (`history/recorder.py`) | `trait_columns`, `animal_views`, events, step listener | `trait_columns` returns column slices, not lists built per animal |
| Species tracker (`species.py`) | `world.animals`, each `a.id` and `a.traits.dna` | A new accessor `genomes(kind, ids)` returning the digit rows (and packed integers on request); the tracker is moved to it in stage 6. `world.animals` stays as a compatibility sequence of lazy references until nothing uses it |
| Inspector (`animal_detail`) | one animal's traits, brain trace, parents | Built on demand for the selected animal from its row; the brain trace runs the single-brain `Brain` on that row's weights (which also serves as the test oracle for the batched pass) |
| Events (`Born`, `Died`, `Mated`, `Ate`) | listeners get one object per event | Built only while a listener exists, from the arrays of ids; a batch form is added if `Ate` volume (hundreds a tick) shows up in a profile |
| Persistence and run store | `save_world`, `load_world`, `world_to_dict` | Stage 7: columns written under their names, the document versioned (`FORMAT_VERSION` 6), the checkpoint stays a versioned blob (`STORE.2` expects that) |
| Tests | `World(...)`, `.traits`, custom `Senses` objects | The object engine's tests are ported or retired at the cut. `World(senses=...)` (used in four test files) is replaced by the `noisy` switch and the sensing rules; no plug-in sense objects |

Positions are `(n, 2)`. `Vec` supports any number of dimensions today but the sensing step and the seed
scatter are 2-D only ("2D for now"), so the array engine fixes two; a third dimension would be a later
change to the column shape, not a promise made here.

## 9. Checking old against new

Two checks at two levels, because the engines cannot be bit-identical (the random numbers differ, and
[5.2](#52-rules-that-depended-on-the-order-of-animals) lists the intended rule differences).

**Level 1: formula by formula, while both engines exist.** The old classes are the specification. The loader
from an old `World` into arrays (stage 1) makes a differential test for every phase: build a seeded old
world, copy it into arrays, switch off the randomness (`WorldSenses(noisy=False)`, curiosity 0, no wander,
a fixed taste), run one phase on both and compare the columns with `allclose` at 1e-12. The derived
quantities at birth should match to the last bits. Cases with contention are tested against the new rule
([5.2](#52-rules-that-depended-on-the-order-of-animals)), not the old loop. This catches porting mistakes in
the formulas, which are the most likely bugs.

**Level 2: statistics against golden records.** The object engine is removed at the cut, so its behaviour is
recorded first:

- Run the last object-engine commit (tagged) on **20 seeds** at 60/300, 300/3,000 and 1,000/5,000 for 60
  simulated days (1,440 ticks), after `WORLD.15` and `TRAIT.12` to `TRAIT.15` have made the economy sustain
  a population (a record of an extinction proves nothing). At 40 ms a tick the 300/3,000 runs take about a
  minute each.
- Record per simulated day: animals and plants alive, births, deaths by cause, mean energy ratio, mean age,
  the mean of about ten key genes and traits (size, speed, aggression, sight range, diet efficiencies,
  fertility), sleeping share. Store the ensemble mean and standard deviation per day, plus the seed list, in
  a small JSON under `tests/golden/`, with the commit hash.
- The array engine runs the same seeds. For each recorded series the test passes when its ensemble mean per
  day is within 3 standard errors of the golden mean on at least 95% of the days, and population and
  death-cause shares are inside the golden range. The exact thresholds belong to the stage 8 thread, who
  can see how much spread the golden runs have; the method is fixed here.
- A difference the owner accepts (a deliberate rule change) means new goldens from the array engine, with
  the owner's agreement logged in `docs/decisions.md`; a difference nobody intended is a bug.

Plus: the migration test (section 7.4), the property tests of the registry (reads match, no unsaved written
column), and the benchmark gate (`--target-ms 41.7`, and `--compare` against the previous stage's best).

## 10. Build stages

The IDs follow `WORLD.20` (renumbered by the TODO thread: the note's first numbers, `WORLD.21` to `WORLD.29`, clashed with the varied world). Owners are suggestions by the thread that
already owns the nearest code. **Until stage 8 the object engine stays the default and everything outside
the engine keeps working on it** (viewer frames, saves, history, session, process host, all tests); the
array engine is selected explicitly (`--engine array` in the benchmark, a `WorldConfig` engine field, a GUI
flag) so that no stage can break a run someone is watching.

```text
        gene freeze (WORLD.15, SENSE.21, TRAIT.12-15, DNA.16 report)
                          |
   1 store, columns, registry, RNG, old-world loader   (Foundations 1)
                          |
   2 genomes and bodies in bulk, reproduction operators (Foundations 1)
        |                 |                     |                    |
   3 index and sensing   4 brain and decisions  5a body and food    5b life cycle
     (Foundations 3)       (Foundations 2)        (Foundations 3)     (Foundations 1)
        |                 |                     |                    |
        +--------+--------+---------------------+--------------------+
                 |
   6 World look-alike, views, events, consumers      (Foundations 5, Viewer 1 for the inspector)
                 |
   7 saves, migration, digests, run store            (Foundations 4)
                 |
   8 equivalence, goldens, flip the default, delete the object engine, version cut   (Foundations 3, TODO)
```

Stage 6 starts when stage 2 has fixed the store layout (it needs the columns, not the phases) and finishes
when 3 to 5 have made a tick run; stage 7 needs the learner and pregnancy tables of stages 4 and 5b.

| Stage | Builds | Must leave working | Gate |
| --- | --- | --- | --- |
| **1. Store and tables** (`WORLD.30`) | The column store (tables, id order, compaction, capacity), the generator from layouts and trait tables, the derived registry with its tests, the counter-based random numbers with the tests of section 7.1, the state table, `numpy` in `dependencies` and the changed isolation test, the loader from an old `World` into arrays (and back, for the tests) | Everything: no behaviour yet | Round trip of 1,000 old animals through the store keeps every field; registry tests pass |
| **2. Genomes and bodies** (`WORLD.31`) | Bulk decoding and trait expression; every static derived quantity of animals and plants; reproduction in bulk: `crossover_linked`, by gene and by unit, point mutation with the per-segment rates and biases, cloning for plants, founders; the brain block decoded to the 582 weights | Everything | All derived columns equal `AnimalTraits` and `PlantTraits` attributes for 1,000s of random genomes to 1e-12; operator statistics (mean cuts, mutation counts, gene fidelity) match `DNA` over many draws |
| **3. Index and sensing** (`WORLD.32`) | Grids, pair tables, the sensing step for plants, animals, corpses, trails, calls, touch and walls; noise from counter draws; the scent grid | Everything | Percepts equal `sensing.sense` with noise off on 100s of random worlds; sensing time at 1,000/5,000 reported at a reach of 50 and of 100 against the budget |
| **4. Brain and decisions** (`WORLD.33`) | Input and output columns, batched forward pass with gates, dead zone and gain, decision interval and cache, interrupts (pain, new threat, new touch), curiosity, wander, decode; learner ring buffers and the batched nightly update | Everything | Outputs equal `Brain.decide_with_hidden` and `think` with noise off; nightly update equals `nightly_update` |
| **5a. Body and food** (`WORLD.34`) | Day cycle, sleep, tiredness, metabolism, ageing, healing, movement, calls, grazing, scavenging, attacks with the contention rules of 5.2, corpses and rot, deaths and compaction | Everything | One tick of each phase equals the old phase on a world with no contention; contested cases equal the stated rules |
| **5b. Life cycle** (`WORLD.35`) | Plant environment, growth, soil and shade, seeding and germination; mating and pregnancy, births, the pregnancies table | Everything | Same as 5a; litter and seed counts match the old engine's distributions |
| **6. Facade and consumers** (`WORLD.36`) | The class with `World`'s read API; views and frames from columns; events; session, history recorder and species tracker moved to array accessors; inspector detail from a row | Viewer, session, host and history run on either engine | The viewer and the history tests pass on the array engine; frame time measured |
| **7. Saves** (`WORLD.37`) | The next save format after 7 (formats 6 and 7 came with the object engine: 6 with the family book, 7 with WORLD.15), the two digests, migration from format 7 (state kept), checkpoints through the run store | Format 7 saves still load, on either engine | Migration fixture test; save and load of a 1,000-animal world |
| **8. Equivalence and the flip** (`WORLD.38`) | Golden records taken from the last object-engine commit before anything is deleted, the statistical test, the benchmark gate, flip the default engine, delete the object engine and its tests, update `docs/design/` (world, dna-and-traits, ux), changelog and version proposal | The array engine is the only one | Section 9 level 2 passes; `bench-world --target-ms 41.7` passes; the owner agrees to the cut |

Each stage's PR quotes its phase time at 1,000/5,000 against the budget line of section 3 (the benchmark
cannot run the whole tick before stage 6, so stages 3 to 5 report their kernel timings in the style of
`numpy_kernel_check.py`). A stage that is over its line says so and says which control of section 6
it will try; it does not wait for the end to find out.

**Coordination rules** for the build:

- **Gene freeze.** While stages 1 to 8 are open, a change to a layout, a trait table, a derived quantity or
  a rules field in the object engine is made in both engines in the same PR, or waits. `WORLD.20` therefore
  waits for the genes already queued, as `TODO.md` says, and `DNA.16`'s report is folded in first.
- The cut is one PR (stage 8), so history before it has the object engine to compare with.
- A conformance test that fails is a finding to report to the stage owner, not a reason to loosen the test.

## 11. Risks and open points

| Risk or open point | Why it matters | What to do |
| --- | --- | --- |
| Pair counts grow with sense reach | Plant sensing is 7.8 ms at a reach of 50 and 21 ms at 100, from 105,000 and 274,000 pairs | Section 6 controls; stage 3 reports both reaches; a reach cap would be an owner decision |
| Small worlds speed up little | A floor of a few hundred numpy calls a tick | Say so (section 3); the interface for small runs stays fine |
| Python loops creeping back in | One `for animal in ...` in an O(N) path is a 1.5 times slowdown | Review rule of 5.1; the benchmark gate catches it |
| Two engines during the build | Doubles the work of any gene change | Gene freeze, section 10 |
| Float differences between CPUs | Digests differ across machines | Two digests, section 7.3; saves record numpy version and machine type |
| Inspector, tests and tools that use `AnimalTraits` objects | 16 test files import them, 27 read `.traits.` | The old classes live until the cut; tests ported stage by stage; the inspector builds from a row |
| `Senses` plug-in objects disappear | Four test files pass custom senses | Replaced by the `noisy` switch and sensing rules; list the tests in stage 3 |
| Versions and the milestone | Saves and digests change | TODO proposes the version to the owner at the flip |
| 3-D positions | `Vec` is N-dimensional, sensing is 2-D | Fixed at 2-D, section 8; owner to say if 3-D was ever wanted |
| Estimates in the budget | Lines marked estimated are not measured | Each stage confirms its line; the target has margin of about 10 ms |

For the TODO thread: the stage list above is now `WORLD.30` to `WORLD.38` in `TODO.md`, each with the owner
and gate in the table; `INFRA.7` (`pytest-benchmark`, `hypothesis`) is used by the conformance and property
tests; `DNA.17` (integer genome distance) goes first as agreed and is superseded inside the array engine by a
row comparison on the genome matrix; the gzip level goes into `STORE.2` as the research said.
