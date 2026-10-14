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
The senses research added six more, [#40](https://github.com/dwhagar/evolutionSimulator/issues/40) to [#45](https://github.com/dwhagar/evolutionSimulator/issues/45) (SENSE.2 to SENSE.7), also with defaults. More owner questions (BRAIN.17 to BRAIN.20, WORLD.6) are being filed by Research 1.

## Milestone 0.1: data models for DNA and traits (kept open)

Goal (set by the owner, 2026-10-14): the data models for traits and DNA are set up, with a document on
how the two interact. The owner chose to keep 0.1 open until the refinement below is built. See
[docs/roadmap.md](docs/roadmap.md).

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| DNA.8 | Mutation: expected changes per genome, per-position weights that mutate low digits more often (option B), a separate mutation setting for how random it is (default random, with occasional big jumps, especially in plants), and a mutation operator that reads `TraitDef.mutation_step` | ready | |
| DNA.13 | Diploid genomes: two copies of every gene, with a simple dominance model (default codominant, averaged); haploid kept as an option | ready | |
| REPRO.3 | Plants reproduce asexually (clone plus mutation), mutate slower and live longer; genes `seed_provision` and `seeding_interval`, no drive, plant layout version bump (design in the REPRO.5 note). `seeding_interval` needs a plant lifespan first (owner question 10; default a configured constant several times the animal one, no repair gene) | ready | DNA.8 |
| REPRO.4 | Animal mate choice: prefer the closest genome (`distance`), allow cross-breeding as the least preferred | ready | |
| REPRO.5 | Build the three reproduction genes that replace `fertility`: `caregiving` (newborn starts with 0.10 to 0.80 of its own max energy, parents split the cost), `repro_interval` (0.01 to 0.25 of expected lifespan, log scale) and `repro_drive` (lowers the mate-seeking energy threshold from 0.85 to 0.35). Design note done ([#49](https://github.com/dwhagar/evolutionSimulator/pull/49), [docs/design/reproduction-genes.md](docs/design/reproduction-genes.md)); build with TRAIT.6 in one change (same functions and layout version). Animal layout version bumps, `fertility` goes, 9 digits are added; `Temperament` gets `repro_drive` | ready | Foundations 1 |
| TRAIT.6 | Longevity (`somatic_maint`) trades against reproduction: more repair multiplies the cost of a birth by 1 + s, stretches the interval by 1 + 0.5 s, and costs upkeep 0.20 s² (convex). Build with REPRO.5. Plants need a lifespan first (owner question 10 on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36)) | ready | Foundations 1 |
| TRAIT.5 | The mating-cost guard (neither parent is charged unless both can afford the birth) is part of the REPRO.5 build. Still to do here: fix the prototype's initial-state quirks (reapply from `refs/pull/20/head`) | ready | |
| TRAIT.3 | Move all tuning constants in `traits.py` into one config object (including the sense costs, see Senses), including the brain costs `BRAIN_NEURON_COST`, `BRAIN_CONNECTION_COST` and `BRAIN_ACTIVE_THRESHOLD` (a random brain costs about 4% of basal metabolism) | blocked | REPRO.5, TRAIT.6, WORLD.2 |
| DNA.9 | Decide sex at birth versus inherited (sex types to confirm, [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 2) | blocked | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) |

Items DNA.7, DNA.8, TRAIT.3 and TRAIT.5 come from section 9.5 of
[docs/research/basic-traits.md](docs/research/basic-traits.md). Foundations 1 prototyped DNA.7, DNA.8,
TRAIT.5 and the `fertility` removal in [#20](https://github.com/dwhagar/evolutionSimulator/pull/20), then closed it unmerged when TRAIT.4 ([#31](https://github.com/dwhagar/evolutionSimulator/pull/31)) changed the
DNA API; the code stays at `refs/pull/20/head`.

## Brain

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| BRAIN.13 | Brain shape evolves: genes control the network and how it operates; the structure is fixed at birth. Design note first, since the genome length stays fixed (a maximum brain plus genes that switch neurons and connections on or off; [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 6) | research | Research 1 |
| BRAIN.15 | Learning during life: creatures sleep at night to regain energy and their weights update (this is also their memory). Design note first: the learning rule, what counts as reward, and whether changes are inherited ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 5) | research | Research 1 |
| BRAIN.17 | Owner question (filed by Research 1): maximum brain size and dormant neurons | waiting on owner | Research 1 files the issue |
| BRAIN.18 | Owner question: which brain operating settings are genes (gain, reaction speed, learning rate, curiosity, sleep need) | waiting on owner | Research 1 files the issue |
| BRAIN.19 | Owner question: what counts as reward in learning | waiting on owner | Research 1 files the issue |
| BRAIN.20 | Owner question: how large a nightly change may be | waiting on owner | Research 1 files the issue |
| BRAIN.21 | Use one threshold for both the brain's energy cost and `Brain.decide` (cost counts only weights above `BRAIN_ACTIVE_THRESHOLD` 0.25 while `decide` uses every weight, so small weights act for free) | ready | |
| BRAIN.9 | Seed the first generation by fitting weights to the current fixed rule (95%+ agreement on random inputs, tested); `BlockSpec.encode` and `DNA.replaced` are ready for it. The fixed rule reads the target size ratio, which the brain has no input for yet | blocked | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 4, SENSE.9 |
| BRAIN.10 | Act on the brain's decisions: set the attack, mate and signal flags and the movement and feeding from `think()`, and retire the fixed rule as a second source of truth | blocked | WORLD.2, SENSE.10 |
| BRAIN.12 | Weight encoding with an exact zero (2-digit weights have no zero, nearest are ±0.133), so a brain can switch a connection off completely. Deliberately not done yet: follow the BRAIN.13 shape note | blocked | BRAIN.13 |
| BRAIN.22 | Let pain, a new threat or touch interrupt the decision interval, so a creature does not wait up to n ticks to react (needs the pain input from SENSE.9) | blocked | SENSE.9 |

## World

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| WORLD.2 | First world and step loop: continuous 2D space (positions kept as vectors so 3D can follow), place organisms, run ticks, feed, reproduce | ready | |
| WORLD.3 | Time scale: a tick is 1 second by default; selectable speeds where one second of real time equals 1 minute, 1 hour, 1 day, 7 days, 1 month, 1 year, 10 years, 100 years or 1000 years. 1000 years per real second is about 3.2 x 10^10 ticks per second at one second per tick, which cannot run tick by tick, and animal lifespans are only 22 minutes to 3.3 hours of simulated time. Wait for the owner's answer to question 8 on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) (keep one-second ticks and offer only the speeds that run, let the tick grow at fast speeds, or make lifespans much longer) | blocked | WORLD.2, [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 8 |
| WORLD.4 | World bounds set by the user, default 1000 by 1000 (edges to confirm, [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 3) | ready | WORLD.2 |
| WORLD.5 | Day-night cycle: creatures sleep at night to regain energy; ties to BRAIN.15. Reset the wander state (`Wanderer`) when a creature falls asleep | blocked | WORLD.3, BRAIN.15 |
| WORLD.6 | Owner question (filed by Research 1): are sleeping creatures vulnerable | waiting on owner | Research 1 files the issue |

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
| SENSE.9 | Inputs 18 to 20 (pain, daylight, relative size): brain shape 17 to 20, `ANIMAL_LAYOUT` version bump, tests. With 20 inputs the 8-hidden brain has 8 x (20 + 1 + 6) + 6 = 222 weights, a 444-digit brain block and a 509-digit animal genome (the earlier 214 weights and 479 digits were wrong). Only `build_inputs` and `INPUT_NAMES` in the brain adapter know input positions. The layout version bump must be sequenced with REPRO.5: whichever lands second takes the next number | blocked | BRAIN.13 (shape decision) |
| SENSE.10 | The sensing step as a pure function (position, heading, sense genes, neighbour list to `Percepts`): encoding rules, light and sleep factors, seeded noise, vectors internally | ready | SENSE.8 |
| SENSE.11 | Sense genes: range floor at 0 (per SENSE.2), noise as a function of the gene, cost on covered area instead of range, constants into the TRAIT.3 config | ready | |
| SENSE.12 | World neighbour search and classifier (part of WORLD.2): grid cells sized to the real maximum range, class rules (diet, size, species similarity) | blocked | WORLD.2 |
| SENSE.13 | Calibrate sense cost, noise and the light and sleep factors against a running world | blocked | WORLD.2, WORLD.5 |
| SENSE.14 | Optional inputs as matching features land: world edge, mate similarity (REPRO.4), own young (REPRO.5), tiredness, clock phase | later | |

Findings that feed TRAIT.3 and SENSE.11, measured on the current code: smell covers about 31,000 square units against
about 1,300 to 3,400 for vision at the same gene and cost, so every population would evolve a nose unless each sense can
only report some classes; `sight_fov` costs almost nothing; the sense bill averages 22% of basal metabolism (target 10 to 15%,
the brain's share is about 4%); neighbour search in plain Python takes about 13 ms per tick at 1,000 animals and 295 ms at
5,000, so it needs cells sized to the maximum range and sensing at the brain's decision interval (BRAIN.11).

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
| BRAIN.11 | Decision interval: `AnimalTraits(dna, decision_interval=n)` (default 1) runs the brain on every n-th `think`, and the brain cost per tick is divided by n | [#50](https://github.com/dwhagar/evolutionSimulator/pull/50) |
| REPRO.6 | Design note: reproduction genes and the longevity trade-off ([docs/design/reproduction-genes.md](docs/design/reproduction-genes.md)); owner questions 7 to 11 posted on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) | [#49](https://github.com/dwhagar/evolutionSimulator/pull/49) |
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
