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

The owner answered [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) (eleven questions) and [#27](https://github.com/dwhagar/evolutionSimulator/issues/27) on 2026-10-14; both are closed and logged in [docs/decisions.md](docs/decisions.md). Points that stayed unclear are in [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) (six questions after the revised reproduction design added three), each with a default the build threads use until you answer: the meaning of sex digit values 2 and 3 (and whether mating needs one of each sex), whether parenting is its own gene, the default lifespans and tick length, plants against animals in lifespan, feeding young after birth, and pregnancy rules. The senses research added six more, [#40](https://github.com/dwhagar/evolutionSimulator/issues/40) to [#45](https://github.com/dwhagar/evolutionSimulator/issues/45) (SENSE.2 to SENSE.7). The brain notes added five more: [#52](https://github.com/dwhagar/evolutionSimulator/issues/52) (BRAIN.17), [#54](https://github.com/dwhagar/evolutionSimulator/issues/54) (BRAIN.18), [#55](https://github.com/dwhagar/evolutionSimulator/issues/55) (BRAIN.19), [#56](https://github.com/dwhagar/evolutionSimulator/issues/56) (BRAIN.20) and [#57](https://github.com/dwhagar/evolutionSimulator/issues/57) (WORLD.6). All have defaults.

## Milestone 0.1: data models for DNA and traits (kept open)

Goal (set by the owner, 2026-10-14): the data models for traits and DNA are set up, with a document on
how the two interact. The owner chose to keep 0.1 open until the refinement below is built. See
[docs/roadmap.md](docs/roadmap.md).

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| REPRO.3 | Plants (second change, after REPRO.8): reproduce asexually (clone plus mutation), mutate slower (a lower `DNA.8` segment rate); three plant genes `seed_provision`, `seeding_interval` and the plant longevity gene (TRAIT.8: 7 to 365 simulated days, log scale, default about 30.4 days, trades against growth and seed budget), no drive; plant ageing and the seed budget; plant layout version bump. Plants start shorter-lived than animals (a month against a year) and can evolve longer: question 4 on [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) | ready | REPRO.8 |
| REPRO.8 | Build the revised reproduction design (REPRO.7, [#77](https://github.com/dwhagar/evolutionSimulator/pull/77), [docs/design/reproduction-genes.md](docs/design/reproduction-genes.md), section "What to build") on top of REPRO.5 and TRAIT.6 ([#74](https://github.com/dwhagar/evolutionSimulator/pull/74)), in one change because it changes the same functions and the animal layout version: genes `repro_drive`, `repro_cooldown`, `fertility` (conception chance, litter 1 to 8, gestation 2 to 20 days), `parenting` (each parent pays by its own gene, the newborn gets the mean; free-riding is possible) and `recovery` (TRAIT.7: healing half-life 20 days down to 1 day, energy regain at rest, separate from `somatic_maint`) at 3 digits each; the sex digit (DNA.9: value mod 2 is the sex, 0 impregnates and 1 bears, 2 adds 25% drive, 3 subtracts 25%, mating needs one of each sex); a pregnancy list in the world (bearer slower and hungrier, no mating until birth plus cooldown); durations in absolute simulated days; per-second charging with `WEAR_BASE` 0.0362 so a default animal lives about 8,765 ticks, one simulated year at a one-hour tick (the per-second part of WORLD.7); repair multiplies each birth cost by 1 + 2s and the cooldown by 1 + s. First generation: fertility 0.75, parenting 0, the rest 0.5. Defaults apply where the owner has not answered [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) (sex digit reading, pregnancy rules, feeding young). Animal layout version: after Foundations 2's version 4. End with a long-run check that no reproduction gene piles up at an end (fertility and cooldown reached a corner in the design's uncrowded toy) | ready | |
| DNA.9 | Sex is inherited as a digit; built within REPRO.8 using the default reading in question 1 on [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) (value mod 2 is the sex, 2 amplifies the mating drive by 25%, 3 subdues it by 25%, mating needs one of each sex) | ready | REPRO.8 |
| TRAIT.7 | The recovery gene, built within REPRO.8 | ready | REPRO.8 |
| TRAIT.8 | The plant longevity gene, built within REPRO.3 | ready | REPRO.3 |
| TRAIT.3 | Move all tuning constants in `traits.py` into one config object (including the sense costs, see Senses), the sensing constants in `SensingRules` and `sense_genes.py`, and the reproduction and repair constants named in `traits.py` (`READINESS_*`, `DRIVE_*`, `REPAIR_*`, `WEAR_PER_TICK`), including the brain costs `BRAIN_NEURON_COST`, `BRAIN_CONNECTION_COST` and `BRAIN_ACTIVE_THRESHOLD` (a random brain costs about 4% of basal metabolism) | ready | |
| DNA.14 | Traits read clusters of genes: the owner wants both shared costs and trade-offs between traits, and genes that affect each other, with a cluster of genes feeding each trait's expression. Design note first (how `TraitDef` reads several genes, how the clusters sit in the layout so crossover keeps them together, and what 'genes affect each other' means for dominance in DNA.13) | research | Research 2 |

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
| BRAIN.23 | Build the evolving brain shape from the design note ([#60](https://github.com/dwhagar/evolutionSimulator/pull/60), [docs/design/brain-shape.md](docs/design/brain-shape.md)): genome stays fixed length; up to 16 hidden neurons, each a group of values (gate, bias, one weight per input, 6 outputs); a neuron exists if its gate is above 0; weights inside a dead zone (about 0.5) count as off for effect and energy cost, which also gives a weight exactly zero (the old BRAIN.12); reuse `Brain(dead_zone=...)` from BRAIN.21, applied once when the brain is built and not changing the stored numbers, with the new value in place of 0.25; four operating genes (gain, reaction time, curiosity, learning rate) as ordinary trait rows; spare slots; `crossover_by_unit` keeps slots whole. The checklist is under "What changes in the code" in the note. Build together with SENSE.9 (20 inputs make each group 28 values, not 25) | ready | |
| BRAIN.24 | Build learning during life from the design note ([#60](https://github.com/dwhagar/evolutionSimulator/pull/60), [docs/design/brain-learning.md](docs/design/brain-learning.md)): a day log of snapshots, a reward function (weights in the TRAIT.3 config), reward-weighted nightly update on the output layer only with a per-night cap, learned values kept as offsets on the creature (not in DNA; the owner confirmed they are lost when the creature dies, not inherited), curiosity noise from an injected `random.Random`, a `Brain` method returning hidden activations, and a handler on the sleep listener hook that WORLD.5 now provides | blocked | BRAIN.23 |
| BRAIN.9 | Seed the first generation by fitting weights to the current fixed rule (95%+ agreement on random inputs, tested); the seed goes into the first 8 hidden slots and the rest stay off. `BlockSpec.encode` and `DNA.replaced` are ready for it. The fixed rule reads the target size ratio, which the brain has no input for yet. Random founders are juveniles for one reproduction interval and mostly starve before breeding in the new world | blocked | BRAIN.23, SENSE.9 (the owner chose seeded brains plus the wander fallback) |
| BRAIN.10 | Act on the brain's decisions: today the world acts on turn, speed, eat and seek-mating only; add the attack, meat and call flags from `think()`, and retire the fixed rule as a second source of truth | blocked | SENSE.10 |
| BRAIN.22 | Let pain, a new threat or touch interrupt the decision interval, so a creature does not wait up to n ticks to react (needs the pain input from SENSE.9) | blocked | SENSE.9 |

## World

The world is built ([#53](https://github.com/dwhagar/evolutionSimulator/pull/53), [docs/design/world.md](docs/design/world.md)): bounds, the time scale with its presets and a `Pacer` that caps ticks per call, a spatial index, stand-in senses and the step loop. The owner confirmed 1000 by 1000 world units with hard boundaries (no wrap) and a one-second default tick. Placeholders in `world.py` until their items land: a child's energy and a seed's biomass are not taken from the parents (REPRO.5); the 50% energy mating guard is a `WorldConfig` setting (TRAIT.3); any two willing animals mate (REPRO.4, DNA.9); no attack, meat or calls yet (BRAIN.10).

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| WORLD.6 | Owner question: are sleeping creatures vulnerable ([#57](https://github.com/dwhagar/evolutionSimulator/issues/57)). Default: partly | waiting on owner | [#57](https://github.com/dwhagar/evolutionSimulator/issues/57) |
| WORLD.7 | Longer lifespans and a longer tick (the owner chose option C on 2026-10-14). The per-second charging is built within REPRO.8 (per-tick rates become per reference tick of 3,600 seconds times `seconds_per_tick` over 3,600). What remains here: make the one-hour tick the default for the animal-year timescale, keep the one-second tick and the speed presets as options, and check the presets against the new lifespans (REPRO.8 sets a default animal at about 8,765 ticks, a plant at about 730). Defaults to confirm in [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) question 3 | blocked | REPRO.8 |
| WORLD.8 | Plant balance: with the prototype constants 300 random plants reach the 5000 cap in about 200 ticks, because growth and seeding have no food limit. Tune against a limit; soil and light competition exist in `traits.py` but the world does not feed them yet | ready | |
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
| SENSE.9 | Inputs 18 to 20 (pain, daylight, relative size), built together with BRAIN.23: with 20 inputs each hidden slot is 28 values, not 25. `Neighbour` must carry a mass field for the relative size input; pain and daylight come from the body and the clock. Only `build_inputs` and `INPUT_NAMES` in the brain adapter know input positions. For the old fixed 8-hidden brain this was 222 weights and a 509-digit genome (the earlier 214 and 479 were wrong); the evolving shape of BRAIN.23 measured 877 digits at 17 inputs | ready | BRAIN.23 |
| SENSE.12 | Wire the sensing step into the world: the neighbour search and a classifier (diet, size, species similarity) that call `sense()` and `organs_from_traits()` in place of the stand-in `BasicSenses` (cell size from the real maximum range). The inputs differ from the stand-in: surface distance instead of centre distance, closeness scaled by the best range among the organs that can report the class, crowding reference 8 not 10. `Neighbour` carries loudness, scent and call radii that the world must supply (plants: scent from biomass; animals: loudness from speed). `sensing.py` imports `Vec` from the world package, so the world must import `sensing` lazily, as `world/senses.py` already does for `SensingRules`. A loud alarm waking a sleeper (SENSE.7) belongs in the world's sleep code, not the pure step | ready | |
| SENSE.13 | Calibrate sense cost, noise and the light and sleep factors against a running world. Finding from SENSE.11: the design note's two aims cannot both hold with cost on area (a typical animal at 10 to 15% of basal and a one-sense specialist at 30 to 40%), because a mid-range animal across three senses pays about 0.75 of one maxed sense, and touch and taste alone are about 9 points of the typical bill. Cost per area is now vision 1.2e-5, hearing and smell 2.5e-6 per square unit: 19% for a random animal (was 22%), with every other gene at 0 28% for a smell specialist, 22% hearing, 17% wide eye, 7% narrow eye. Open for the owner: should touch and taste also move onto area or be cheaper. Invented placeholders to calibrate: smell reaches prey and threats at half range, loudness and scent as 0 to 1 range multipliers, a call is heard only inside both the listener's hearing range and the caller's call radius | ready | SENSE.12 |
| SENSE.14 | Optional inputs as matching features land: world edge, mate similarity (REPRO.4), own young (REPRO.5), tiredness, clock phase | later | |

Findings that feed TRAIT.3 and SENSE.11, measured on the current code: smell covers about 31,000 square units against
about 1,300 to 3,400 for vision at the same gene and cost, so every population would evolve a nose unless each sense can
only report some classes; `sight_fov` costs almost nothing; the sense bill averages 22% of basal metabolism (target 10 to 15%,
the brain's share is about 4%); neighbour search in plain Python takes about 13 ms per tick at 1,000 animals and 295 ms at
5,000, so it needs cells sized to the maximum range and sensing at the brain's decision interval (BRAIN.11). WORLD.9 then made the sensing and brain pass about 2.7 times faster (62 ms to 23 ms per tick at 300 animals and 3000 plants).

Layout versions: REPRO.5 took animal layout version 3 (466 digits). BRAIN.23 with SENSE.9 (Foundations 2) must take version 4 and shift the brain by the new gene count; the REPRO.8 build takes the next one after that (the design note counts digits from an older layout, so the builder works from the actual layout in `layouts.py`).

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
| WORLD.4 | World bounds set by the user, default 1000 by 1000, hard walls at the edges (confirmed by the owner) | [#53](https://github.com/dwhagar/evolutionSimulator/pull/53) |
| BRAIN.13 | Design note: a brain shape that evolves inside a fixed-length genome ([docs/design/brain-shape.md](docs/design/brain-shape.md)); the build is BRAIN.23 | [#60](https://github.com/dwhagar/evolutionSimulator/pull/60) |
| BRAIN.15 | Design note: learning during life ([docs/design/brain-learning.md](docs/design/brain-learning.md)); the build is BRAIN.24 | [#60](https://github.com/dwhagar/evolutionSimulator/pull/60) |
| BRAIN.12 | Folded into BRAIN.23: weights in a dead zone count as off, which gives an exact zero without a new encoding | [#60](https://github.com/dwhagar/evolutionSimulator/pull/60) |
| DNA.13 | Diploid genomes: `DiploidDNA` (two strands) with a `DominanceModel` (coefficient -1 to 1 per gene, default 0 = codominant average); `reproduce` makes mutated gametes from each parent with the expected mutation count kept per child; a `Genome` protocol lets traits accept `DNA` or `DiploidDNA`; haploid stays plain `DNA` | [#63](https://github.com/dwhagar/evolutionSimulator/pull/63) |
| SENSE.8 | Sense-channel registry: one table of brain inputs (name, range, class, which senses report it) that generates `INPUT_NAMES`, `Percepts` and `build_inputs` | [#61](https://github.com/dwhagar/evolutionSimulator/pull/61) |
| SENSE.10 | The sensing step as a pure function: `sense()` turns position, heading, organs and classified neighbours into `Percepts` (surface distances, the best range that can report each class, bearing from the most precise organ, daylight and sleep factors, touch, calls, crowding, seeded noise); constants in `SensingRules`. Not yet called by the world (SENSE.12) | [#65](https://github.com/dwhagar/evolutionSimulator/pull/65) |
| SENSE.11 | Sense genes: sight, hearing and smell ranges run from 0 so a sense can be lost (touch stays on), noise falls linearly with the gene, cost is charged on the area covered, `organs_from_traits()` hands the organs to the sensing step; constants in `sense_genes.py` for TRAIT.3. No gene or layout change | [#68](https://github.com/dwhagar/evolutionSimulator/pull/68) |
| BRAIN.21 | One threshold for the brain's cost and its decisions: `Brain(dead_zone=...)`, a weight at or below it is off in `decide` and not counted in `active_connections`, so a connection pays energy exactly when it acts | [#72](https://github.com/dwhagar/evolutionSimulator/pull/72) |
| TRAIT.5 | Start-of-life state set at construction (animal drive flags, plant vitality), `consume_mating_cost` cannot push energy below zero, the phenotype of a fixed genome is pinned by tests. The two-parent birth guard moves into the REPRO.5 build | [#66](https://github.com/dwhagar/evolutionSimulator/pull/66) |
| WORLD.5 | Day-night cycle and sleep: daylight from simulated time, plants get it as sunlight, animals see less in the dark, and at night animals that are not starving sleep (no sensing, moving, eating or mating, less energy burned, some regained). A sleep listener hook exists for the nightly learning step (BRAIN.24) and falling asleep resets the wander turn | [#70](https://github.com/dwhagar/evolutionSimulator/pull/70) |
| WORLD.9 | Speed: the sensing and brain pass is about 2.7 times faster (62 ms to 23 ms per tick at 300 animals and 3000 plants) | [#67](https://github.com/dwhagar/evolutionSimulator/pull/67) |
| REPRO.5 | The reproduction genes that replace `fertility`: `caregiving` (newborn starts with a share of its own max energy, parents split the cost), `repro_interval` (a share of expected lifespan, with a juvenile period of one interval) and `repro_drive` (lowers the mate-seeking energy threshold, bends `Temperament.mate_closeness`); animal layout version 3, 466 digits (body 70 digits); `AnimalTraits.give_birth` replaces `consume_mating_cost` and charges nobody unless both parents can pay; the world takes child energy and seed biomass from the parents. Not built: the protective effect of caregiving (needs a young-nearby percept) and the plant genes (REPRO.3). The owner's later answers extend this gene set (REPRO.7) | [#74](https://github.com/dwhagar/evolutionSimulator/pull/74) |
| TRAIT.6 | Longevity trades against reproduction: more repair multiplies the cost of a birth by 1 + s, stretches the interval by 1 + 0.5 s, and costs upkeep 0.20 s squared; constants are named in `traits.py` for TRAIT.3. Plants wait for TRAIT.8 | [#74](https://github.com/dwhagar/evolutionSimulator/pull/74) |
| REPRO.4 | Animal mate choice: animals prefer the mate with the closest genome | [#76](https://github.com/dwhagar/evolutionSimulator/pull/76) |
| REPRO.7 | Design: the reproduction genes revised to the owner's answers (four genes plus the sex digit, the recovery gene, plant longevity, absolute durations); the build is REPRO.8 | [#77](https://github.com/dwhagar/evolutionSimulator/pull/77) |
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
| DNA.2 | Decided: traits interact both ways (shared costs and trade-offs, and genes that affect each other), with clusters of genes feeding each trait; design note is DNA.14 | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) |
| REPRO.1 | Decided: plants asexual, animals sexual with two sexes (digit 0 or 1); values 2 and 3 modify the mating drive, to confirm in [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) |
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
