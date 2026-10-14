# TODO

The task list for the project. Kept by the TODO thread; other threads send bugs and non-quick findings
there to be turned into items and issues. Owner decisions are logged in [docs/decisions.md](docs/decisions.md).

## Task IDs

Every item has an ID in the form `AREA.N` (area, then a number, no zero padding). IDs are never
reused or renumbered. GitHub issues and PRs carry a label with the ID of each item they require or
relate to, and this file and [CHANGELOG.md](CHANGELOG.md) link IDs to their issues and PRs.

| Area | Covers |
| --- | --- |
| `DOCS` | Documentation, research notes, roadmap |
| `INFRA` | Versioning, CI, tooling, repo setup |
| `DNA` | Genome model, mutation, crossover |
| `REPRO` | Reproduction modes and life history |
| `TRAIT` | Traits (phenotype) and their costs |
| `WORLD` | World model, time and the simulation loop |
| `BRAIN` | Neural-network brain, learning and behaviour |
| `SENSE` | Senses and how they feed the brain |

A new area is added here first. Status is one of: ready (can be built now), research (needs a design note
first), blocked (on another item or an answer), done.

## Waiting on the owner

One issue holds the open questions: [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) (eleven short questions, each with a default the build threads use
until you answer; questions 7 to 11 come from the reproduction genes note: two tiers, time scales, who pays for a child, plant lifespan, litters). Issue [#27](https://github.com/dwhagar/evolutionSimulator/issues/27) (first-generation brains) is part of it and stays open.
The senses research added six more, [#40](https://github.com/dwhagar/evolutionSimulator/issues/40) to [#45](https://github.com/dwhagar/evolutionSimulator/issues/45) (SENSE.2 to SENSE.7), also with defaults. The brain notes added five more: [#52](https://github.com/dwhagar/evolutionSimulator/issues/52) (BRAIN.17), [#54](https://github.com/dwhagar/evolutionSimulator/issues/54) (BRAIN.18), [#55](https://github.com/dwhagar/evolutionSimulator/issues/55) (BRAIN.19), [#56](https://github.com/dwhagar/evolutionSimulator/issues/56) (BRAIN.20) and [#57](https://github.com/dwhagar/evolutionSimulator/issues/57) (WORLD.6), also with defaults.

## Milestone 0.1: data models for DNA and traits (kept open)

Goal (set by the owner, 2026-10-14): the data models for traits and DNA are set up, with a document on
how the two interact. The owner chose to keep 0.1 open until the refinement below is built. See
[docs/roadmap.md](docs/roadmap.md).

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| REPRO.3 | Plants reproduce asexually (clone plus mutation), mutate slower (a lower `DNA.8` segment rate) and live longer; genes `seed_provision` and `seeding_interval`, no drive, plant layout version bump (design in the REPRO.5 note). `seeding_interval` needs a plant lifespan first (owner question 10; default a configured constant several times the animal one, no repair gene) | ready | |
| REPRO.4 | Animal mate choice: prefer the closest genome (`distance`), allow cross-breeding as the least preferred | ready | |
| REPRO.5 | Build the three reproduction genes that replace `fertility`: `caregiving` (newborn starts with 0.10 to 0.80 of its own max energy, parents split the cost), `repro_interval` (0.01 to 0.25 of expected lifespan, log scale) and `repro_drive` (lowers the mate-seeking energy threshold from 0.85 to 0.35). Wire the births into `world.py` too (child energy and seed biomass come from the parents instead of the placeholders). Design note done ([#49](https://github.com/dwhagar/evolutionSimulator/pull/49), [docs/design/reproduction-genes.md](docs/design/reproduction-genes.md)); build with TRAIT.6 in one change (same functions and layout version). Animal layout version bumps, `fertility` goes, 9 digits are added; `Temperament` gets `repro_drive` | ready | Foundations 1 |
| TRAIT.6 | Longevity (`somatic_maint`) trades against reproduction: more repair multiplies the cost of a birth by 1 + s, stretches the interval by 1 + 0.5 s, and costs upkeep 0.20 s² (convex). Build with REPRO.5. Plants need a lifespan first (owner question 10 on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36)) | ready | Foundations 1 |
| TRAIT.5 | The mating-cost guard (neither parent is charged unless both can afford the birth) is part of the REPRO.5 build. Still to do here: fix the prototype's initial-state quirks (reapply from `refs/pull/20/head`) | ready | |
| TRAIT.3 | Move all tuning constants in `traits.py` into one config object (including the sense costs, see Senses), including the brain costs `BRAIN_NEURON_COST`, `BRAIN_CONNECTION_COST` and `BRAIN_ACTIVE_THRESHOLD` (a random brain costs about 4% of basal metabolism) | blocked | REPRO.5, TRAIT.6 |
| DNA.9 | Decide sex at birth versus inherited (sex types to confirm, [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 2) | blocked | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) |

Items DNA.7, DNA.8, TRAIT.3 and TRAIT.5 come from section 9.5 of
[docs/research/basic-traits.md](docs/research/basic-traits.md). Foundations 1 prototyped DNA.7, DNA.8,
TRAIT.5 and the `fertility` removal in [#20](https://github.com/dwhagar/evolutionSimulator/pull/20), then closed it unmerged when TRAIT.4 ([#31](https://github.com/dwhagar/evolutionSimulator/pull/31)) changed the
DNA API; the code stays at `refs/pull/20/head`.

## Brain

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| BRAIN.17 | Owner question: maximum brain size and dormant neurons ([#52](https://github.com/dwhagar/evolutionSimulator/issues/52)). Default: 16 hidden slots, unused slots allowed | waiting on owner | [#52](https://github.com/dwhagar/evolutionSimulator/issues/52) |
| BRAIN.18 | Owner question: which brain operating settings are genes ([#54](https://github.com/dwhagar/evolutionSimulator/issues/54)). Default: gain, reaction time, curiosity, learning rate; sleep need is left to WORLD.5 | waiting on owner | [#54](https://github.com/dwhagar/evolutionSimulator/issues/54) |
| BRAIN.19 | Owner question: what counts as reward in learning ([#55](https://github.com/dwhagar/evolutionSimulator/issues/55)). Default: energy gained 1, health lost 2, mating 1, safety 0.5 | waiting on owner | [#55](https://github.com/dwhagar/evolutionSimulator/issues/55) |
| BRAIN.20 | Owner question: how large a nightly change may be ([#56](https://github.com/dwhagar/evolutionSimulator/issues/56)). Default: a cap of 0.5 per night | waiting on owner | [#56](https://github.com/dwhagar/evolutionSimulator/issues/56) |
| BRAIN.21 | Use one threshold for both the brain's energy cost and `Brain.decide` (cost counts only weights above `BRAIN_ACTIVE_THRESHOLD` 0.25 while `decide` uses every weight, so small weights act for free). Small, so do it before BRAIN.23; the dead zone in BRAIN.23 then makes it permanent | ready | |
| BRAIN.23 | Build the evolving brain shape from the design note ([#60](https://github.com/dwhagar/evolutionSimulator/pull/60), [docs/design/brain-shape.md](docs/design/brain-shape.md)): genome stays fixed length; up to 16 hidden neurons, each a group of values (gate, bias, one weight per input, 6 outputs); a neuron exists if its gate is above 0; weights inside a dead zone (about 0.5) count as off for effect and energy cost, which also gives a weight exactly zero (the old BRAIN.12) and fixes BRAIN.21; four operating genes (gain, reaction time, curiosity, learning rate) as ordinary trait rows; spare slots; `crossover_by_unit` keeps slots whole. The checklist is under "What changes in the code" in the note. Build together with SENSE.9 (20 inputs make each group 28 values, not 25) | ready | BRAIN.21 |
| BRAIN.24 | Build learning during life from the design note ([#60](https://github.com/dwhagar/evolutionSimulator/pull/60), [docs/design/brain-learning.md](docs/design/brain-learning.md)): a day log of snapshots, a reward function (weights in the TRAIT.3 config), reward-weighted nightly update on the output layer only with a per-night cap, learned values kept as offsets on the creature (not in DNA, not inherited), curiosity noise from an injected `random.Random`, a `Brain` method returning hidden activations, and a sleep hook for WORLD.5 | blocked | BRAIN.23, WORLD.5 |
| BRAIN.9 | Seed the first generation by fitting weights to the current fixed rule (95%+ agreement on random inputs, tested); the seed goes into the first 8 hidden slots and the rest stay off. `BlockSpec.encode` and `DNA.replaced` are ready for it. The fixed rule reads the target size ratio, which the brain has no input for yet. Random first-generation animals mostly starve before breeding in the new world | blocked | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 4, BRAIN.23, SENSE.9 |
| BRAIN.10 | Act on the brain's decisions: today the world acts on turn, speed, eat and seek-mating only; add the attack, meat and call flags from `think()`, and retire the fixed rule as a second source of truth | blocked | SENSE.10 |
| BRAIN.22 | Let pain, a new threat or touch interrupt the decision interval, so a creature does not wait up to n ticks to react (needs the pain input from SENSE.9) | blocked | SENSE.9 |

## World

The world is built ([#53](https://github.com/dwhagar/evolutionSimulator/pull/53), [docs/design/world.md](docs/design/world.md)): bounds, the time scale with its presets and a `Pacer` that caps ticks per call, a spatial index, stand-in senses and the step loop. Edges are walls until the owner answers question 3 on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36); wrapping or open space would go in `Bounds`, with wrapped distances in the senses. Placeholders in `world.py` until their items land: a child's energy and a seed's biomass are not taken from the parents (REPRO.5); the 50% energy mating guard is a `WorldConfig` setting (TRAIT.5, TRAIT.3); any two willing animals mate (REPRO.4, DNA.9); no attack, meat or calls yet (BRAIN.10).

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| WORLD.5 | Day-night cycle: creatures sleep at night to regain energy (the sleep hook BRAIN.24 needs); owner questions SENSE.3, SENSE.7 and WORLD.6 have defaults. Reset the wander state (`Wanderer`) when a creature falls asleep | ready | |
| WORLD.6 | Owner question: are sleeping creatures vulnerable ([#57](https://github.com/dwhagar/evolutionSimulator/issues/57)). Default: partly | waiting on owner | [#57](https://github.com/dwhagar/evolutionSimulator/issues/57) |
| WORLD.7 | Per-second physics: `seconds_per_tick` only changes the clock, because metabolism, ageing and speed are charged per tick in `traits.py`. To let the tick grow at fast speeds, charge them per second and sum over the tick, with the brain on `decision_interval` (BRAIN.11). Needs the owner's answer on time scales (question 8 on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36)) | blocked | TRAIT.3, [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 8 |
| WORLD.8 | Plant balance: with the prototype constants 300 random plants reach the 5000 cap in about 200 ticks, because growth and seeding have no food limit. Tune against a limit; soil and light competition exist in `traits.py` but the world does not feed them yet | ready | |
| WORLD.9 | Speed: about 60 ms per tick at 300 animals and 3000 plants (about 5 ms at 60 animals), so the fast presets cannot be met at that size. Profile the sensing and the brain pass | ready | SENSE.10 |
| WORLD.10 | Use diploid organisms in the world: choose `DNA` (haploid) or `DiploidDNA` per species when creating organisms and in `reproduce`; nothing creates diploid organisms yet. Default for animals and plants to confirm against the owner's diploid decision ([#3](https://github.com/dwhagar/evolutionSimulator/issues/3)) | ready | |

## Senses

Research is done ([#46](https://github.com/dwhagar/evolutionSimulator/pull/46), [docs/design/senses.md](docs/design/senses.md)): four outer senses (vision, hearing, smell,
touch; taste stays the `inspect_food` action), body state with a new pain input, and daylight. Brain inputs go from 17 to 20
(adding pain, daylight and relative size of the nearest animal). Inputs are grouped by what is sensed, not by organ.

Owner questions, each with a default the build threads use until answered:

| ID | Question | Issue | Default |
| --- | --- | --- | --- |
| SENSE.2 | Can a sense be lost completely? | [#40](https://github.com/dwhagar/evolutionSimulator/issues/40) | Vision, hearing and smell can reach 0; touch is always on |
| SENSE.3 | Does darkness reduce vision? (also WORLD.5) | [#41](https://github.com/dwhagar/evolutionSimulator/issues/41) | Yes, range times (0.25 + 0.75 × daylight) |
| SENSE.4 | Imperfect senses and noise? | [#42](https://github.com/dwhagar/evolutionSimulator/issues/42) | Yes; vision near exact, hearing and smell noisy |
| SENSE.5 | Does the brain see relative size and mate similarity? | [#43](https://github.com/dwhagar/evolutionSimulator/issues/43) | Relative size now, similarity when REPRO.4 is built |
| SENSE.6 | Can new sense kinds evolve mid-run? | [#44](https://github.com/dwhagar/evolutionSimulator/issues/44) | No, a fixed list |
| SENSE.7 | Which senses work while asleep? (also WORLD.5) | [#45](https://github.com/dwhagar/evolutionSimulator/issues/45) | Touch full, hearing and smell half, vision off |

Build items, in order (the first four need no world):

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| SENSE.8 | Sense-channel registry: one table of brain inputs (name, range, class, which senses report it) that generates `INPUT_NAMES`, `Percepts` and `build_inputs` | ready | |
| SENSE.9 | Inputs 18 to 20 (pain, daylight, relative size), built together with BRAIN.23: with 20 inputs each hidden slot is 28 values, not 25. Only `build_inputs` and `INPUT_NAMES` in the brain adapter know input positions. For the old fixed 8-hidden brain this was 222 weights and a 509-digit genome (the earlier 214 and 479 were wrong); the evolving shape of BRAIN.23 measured 877 digits at 17 inputs | ready | BRAIN.23 |
| SENSE.10 | The sensing step as a pure function (position, heading, sense genes, neighbour list to `Percepts`): encoding rules, light and sleep factors, seeded noise, vectors internally. It replaces the world's stand-in `BasicSenses` (prey lighter than 0.8 of its own mass, threat heavier than 1.25, mate the rest) through the `Senses` interface (`perceive(world, animal) -> Percepts`, passed as `World(config, senses=...)`), so the step loop does not change | ready | SENSE.8 |
| SENSE.11 | Sense genes: range floor at 0 (per SENSE.2), noise as a function of the gene, cost on covered area instead of range, constants into the TRAIT.3 config | ready | |
| SENSE.12 | Neighbour classifier: the neighbour search is built (`SpatialIndex`, fixed 64-unit grid cells, [#53](https://github.com/dwhagar/evolutionSimulator/pull/53)). Still to do: cell size from the real maximum range, and the class rules (diet, size, species similarity) in place of the stand-in | ready | SENSE.10 |
| SENSE.13 | Calibrate sense cost, noise and the light and sleep factors against a running world | blocked | WORLD.5 |
| SENSE.14 | Optional inputs as matching features land: world edge, mate similarity (REPRO.4), own young (REPRO.5), tiredness, clock phase | later | |

Findings that feed TRAIT.3 and SENSE.11, measured on the current code: smell covers about 31,000 square units against
about 1,300 to 3,400 for vision at the same gene and cost, so every population would evolve a nose unless each sense can
only report some classes; `sight_fov` costs almost nothing; the sense bill averages 22% of basal metabolism (target 10 to 15%,
the brain's share is about 4%); neighbour search in plain Python takes about 13 ms per tick at 1,000 animals and 295 ms at
5,000, so it needs cells sized to the maximum range and sensing at the brain's decision interval (BRAIN.11).

Layout versions: REPRO.5 (Foundations 1) and BRAIN.23 with SENSE.9 (Foundations 2) both change the animal layout. Whichever merges second brings in main and takes the next layout version; gene positions shift by the amounts in each note.

## Open design questions that do not block anything

| ID | Question | Issue |
| --- | --- | --- |
| DNA.2 | Genome level of detail: decided (base-4 genes of 1 or more digits); "traits should interact" to confirm | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) |
| REPRO.1 | Reproduction modes: decided (plants asexual, animals sexual); sex types to confirm | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) |

## Done

| ID | Item | Link |
| --- | --- | --- |
| DOCS.1 | Docs tree, roadmap, TODO and changelog | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| DOCS.2 | Research: DNA and reproduction | [#13](https://github.com/dwhagar/evolutionSimulator/pull/13) |
| DOCS.3 | Research: basic life-form traits | [#12](https://github.com/dwhagar/evolutionSimulator/pull/12) |
| DOCS.4 | Set the first milestone: 0.1, data models for DNA and traits | [#21](https://github.com/dwhagar/evolutionSimulator/pull/21) |
| DOCS.5 | Document how DNA and traits interact ([docs/design/dna-traits-interaction.md](docs/design/dna-traits-interaction.md)) | [#32](https://github.com/dwhagar/evolutionSimulator/pull/32) |
| SENSE.1 | Research: senses and how they feed the brain ([docs/design/senses.md](docs/design/senses.md)); owner questions filed as SENSE.2 to SENSE.7 | [#46](https://github.com/dwhagar/evolutionSimulator/pull/46) |
| DNA.7 | Crossover: `reproduce` defaults to `DNA.crossover_linked` (a few cut points that follow whole genes and brain neurons; `gene_fidelity` 0.9 and `mean_cuts` 1.0 are settings). The mutation counterpart is DNA.8 | [#48](https://github.com/dwhagar/evolutionSimulator/pull/48) |
| WORLD.2 | First world and step loop: continuous 2D space, placing organisms, running ticks, feeding, reproduction (`evolution_simulator.world`, [docs/design/world.md](docs/design/world.md)) | [#53](https://github.com/dwhagar/evolutionSimulator/pull/53) |
| WORLD.3 | Time scale (built part): `TimeScale` with all the presets and a `Pacer` that caps ticks per call, so fast presets run slower than their label. The per-second physics for fast speeds is WORLD.7 | [#53](https://github.com/dwhagar/evolutionSimulator/pull/53) |
| WORLD.4 | World bounds set by the user, default 1000 by 1000, edges are walls until question 3 on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) is answered | [#53](https://github.com/dwhagar/evolutionSimulator/pull/53) |
| BRAIN.13 | Design note: a brain shape that evolves inside a fixed-length genome ([docs/design/brain-shape.md](docs/design/brain-shape.md)); the build is BRAIN.23 | [#60](https://github.com/dwhagar/evolutionSimulator/pull/60) |
| BRAIN.15 | Design note: learning during life ([docs/design/brain-learning.md](docs/design/brain-learning.md)); the build is BRAIN.24 | [#60](https://github.com/dwhagar/evolutionSimulator/pull/60) |
| BRAIN.12 | Folded into BRAIN.23: weights in a dead zone count as off, which gives an exact zero without a new encoding | [#60](https://github.com/dwhagar/evolutionSimulator/pull/60) |
| DNA.13 | Diploid genomes: `DiploidDNA` (two strands) with a `DominanceModel` (coefficient -1 to 1 per gene, default 0 = codominant average); `reproduce` makes mutated gametes from each parent with the expected mutation count kept per child; a `Genome` protocol lets traits accept `DNA` or `DiploidDNA`; haploid stays plain `DNA` | [#63](https://github.com/dwhagar/evolutionSimulator/pull/63) |
| BRAIN.11 | Decision interval: `AnimalTraits(dna, decision_interval=n)` (default 1) runs the brain on every n-th `think`, and the brain cost per tick is divided by n | [#50](https://github.com/dwhagar/evolutionSimulator/pull/50) |
| REPRO.6 | Design note: reproduction genes and the longevity trade-off ([docs/design/reproduction-genes.md](docs/design/reproduction-genes.md)); owner questions 7 to 11 posted on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) | [#49](https://github.com/dwhagar/evolutionSimulator/pull/49) |
| DNA.8 | Mutation favours low digits: `position_bias` (default 0.5, plants 0.75) makes more significant digits rarer to change, `locality` (default 0, fully random) is the chance a changed digit moves to a neighbour, `gene_biases` sets it per gene and `TraitSet.position_biases()` derives it from `mutation_step`. Nothing in the simulation passes `gene_biases` yet | [#58](https://github.com/dwhagar/evolutionSimulator/pull/58) |
| BRAIN.14 | Behaviour genes bend what the brain perceives: aggression scales the prey-closeness input and fear the threat-closeness input (0.4 to 1.6) through a `Temperament` in the brain adapter; the REPRO.5 genes become more fields on it | [#47](https://github.com/dwhagar/evolutionSimulator/pull/47) |
| BRAIN.16 | Random wander fallback: a creature that senses nothing or whose outputs are all quiet turns randomly with a minimum speed (`Wanderer`, `WanderPolicy`; seeded) | [#39](https://github.com/dwhagar/evolutionSimulator/pull/39) |
| DOCS.6 | Decisions log ([docs/decisions.md](docs/decisions.md)) | this change |
| BRAIN.1 | Brain research: a small neural network for animals ([docs/design/brain.md](docs/design/brain.md)) | [#29](https://github.com/dwhagar/evolutionSimulator/pull/29) |
| BRAIN.2 | The `Brain` object (pure 17-8-6 network, 198 weights), `brain_adapter.py`, `AnimalTraits.think()`, brain upkeep in basal metabolism | [#34](https://github.com/dwhagar/evolutionSimulator/pull/34) |
| BRAIN.3 | Decided: neural network plus genetic factors | [#23](https://github.com/dwhagar/evolutionSimulator/issues/23) |
| BRAIN.4 | Decided: no memory neurons at the start; memory comes from nightly learning (BRAIN.15) | [#24](https://github.com/dwhagar/evolutionSimulator/issues/24) |
| BRAIN.5 | Decided: thinking costs energy | [#25](https://github.com/dwhagar/evolutionSimulator/issues/25) |
| BRAIN.6 | Decided: the brain learns during life, updated at night | [#26](https://github.com/dwhagar/evolutionSimulator/issues/26) |
| BRAIN.8 | Decided: brain shape evolves (BRAIN.13) | [#28](https://github.com/dwhagar/evolutionSimulator/issues/28) |
| DNA.1 | DNA objects ported from the prototype | [#18](https://github.com/dwhagar/evolutionSimulator/pull/18) |
| DNA.3 | Decided: diploid (DNA.13) | [#3](https://github.com/dwhagar/evolutionSimulator/issues/3) |
| DNA.4 | Decided: fixed-length genome | [#5](https://github.com/dwhagar/evolutionSimulator/issues/5) |
| DNA.5 | Decided: whole-gene crossover with cut points (DNA.7) | [#14](https://github.com/dwhagar/evolutionSimulator/issues/14) |
| DNA.6 | Decided: mutate low digits more often, keep some randomness (DNA.8) | [#15](https://github.com/dwhagar/evolutionSimulator/issues/15) |
| DNA.10 | Layouts carry a name and version; saved genomes check the version | [#31](https://github.com/dwhagar/evolutionSimulator/pull/31) |
| DNA.11 | `BlockSpec` gene block for arrays of weights; `ANIMAL_LAYOUT` is 461 digits at layout version 2 | [#34](https://github.com/dwhagar/evolutionSimulator/pull/34) |
| DNA.12 | Per-segment expected-change mutation and `crossover_by_unit` (whole neurons) | [#34](https://github.com/dwhagar/evolutionSimulator/pull/34) |
| REPRO.2 | Decided: three reproduction genes (REPRO.5) | [#17](https://github.com/dwhagar/evolutionSimulator/issues/17) |
| TRAIT.1 | Traits objects ported from the prototype | [#18](https://github.com/dwhagar/evolutionSimulator/pull/18) |
| TRAIT.2 | Decided: longevity trades against reproduction (TRAIT.6) | [#16](https://github.com/dwhagar/evolutionSimulator/issues/16) |
| TRAIT.4 | Traits as data: `GenomeLayout`/`GeneSpec` in `dna.py`, `layouts.py`, `TraitDef`/`TraitSet` in `trait_defs.py` | [#31](https://github.com/dwhagar/evolutionSimulator/pull/31) |
| WORLD.1 | Decided: continuous 2D, user-set bounds, default 1000 by 1000 (WORLD.2 to WORLD.4) | [#10](https://github.com/dwhagar/evolutionSimulator/issues/10) |
| INFRA.1 | Automatic `MAJOR.minor.build` versioning ([docs/versioning.md](docs/versioning.md)) | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| INFRA.2 | Weekly scheduled CI (Mondays 07:00 UTC) | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |

Traits decisions already settled and closed: fixed trait set ([#6](https://github.com/dwhagar/evolutionSimulator/issues/6)), allometric coupling ([#7](https://github.com/dwhagar/evolutionSimulator/issues/7)),
predators and diet ([#8](https://github.com/dwhagar/evolutionSimulator/issues/8)), behaviour as genes or brain ([#9](https://github.com/dwhagar/evolutionSimulator/issues/9)), aging ([#11](https://github.com/dwhagar/evolutionSimulator/issues/11)). All are tagged `TRAIT.1`.
