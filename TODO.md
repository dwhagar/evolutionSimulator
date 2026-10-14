# TODO

The task list for the project. Kept by the TODO thread; other threads send bugs and non-quick findings
there to be turned into items and issues.

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
| `WORLD` | World model and the simulation loop |
| `BRAIN` | Neural-network brain and behaviour |

A new area is added here first. Status is one of: open, blocked (on a decision or another item), done.

## Milestone 0.1: data models for DNA and traits

Goal (set by the owner, 2026-10-14): the data models for traits and DNA are set up, with a document on
how the two interact. See [docs/roadmap.md](docs/roadmap.md).

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| DNA.1 | DNA objects ported from the prototype ([#18](https://github.com/dwhagar/evolutionSimulator/pull/18)) | done | |
| TRAIT.1 | Traits objects ported from the prototype ([#18](https://github.com/dwhagar/evolutionSimulator/pull/18)) | done | |
| DOCS.5 | Document how DNA and traits interact (`docs/design`), from the contract in section 9.4 of [basic-traits.md](docs/research/basic-traits.md) and the design note | open | Foundations 1 follow-up |
| DNA.5 | Decide crossover ([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)) | waiting on owner | |
| DNA.6 | Decide mutation size and encoding ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)) | waiting on owner | |
| TRAIT.2 | Decide whether longevity carries a cost ([#16](https://github.com/dwhagar/evolutionSimulator/issues/16)) | waiting on owner | |
| REPRO.2 | Decide what `fertility` does ([#17](https://github.com/dwhagar/evolutionSimulator/issues/17)) | waiting on owner | |
| WORLD.1 | Decide the world model, so trait ranges stop being guesses ([#10](https://github.com/dwhagar/evolutionSimulator/issues/10)) | waiting on owner | |
| DNA.7 | Make gene-boundary crossover the default | built in [#20](https://github.com/dwhagar/evolutionSimulator/pull/20), held for owner | DNA.5 |
| DNA.8 | Per-position mutation weight, and mutation rate as expected changes per genome | built in [#20](https://github.com/dwhagar/evolutionSimulator/pull/20), held for owner | DNA.6 |
| TRAIT.3 | Move all tuning constants in `traits.py` into one config object | blocked | TRAIT.2, REPRO.2, WORLD.1 |
| TRAIT.4 | Define traits as data (gene IDs, range, scale, mutation step) so DNA does not know trait names | open | |
| TRAIT.5 | Fix the prototype's initial-state quirks and add a mating-cost guard | built in [#20](https://github.com/dwhagar/evolutionSimulator/pull/20), held for owner | REPRO.2, WORLD.1 |
| DNA.10 | Genome `LAYOUT_VERSION` on every DNA class, saved and checked on load (animal genome becomes 61 digits when `fertility` is removed) | built in [#20](https://github.com/dwhagar/evolutionSimulator/pull/20), held for owner | REPRO.2 |

Items DNA.7, DNA.8 and TRAIT.3 to TRAIT.5 come from section 9.5 of
[docs/research/basic-traits.md](docs/research/basic-traits.md). Foundations 1 built the research threads' defaults for DNA.7, DNA.8, TRAIT.5 and the removal of the unused `fertility` gene (REPRO.2) in [#20](https://github.com/dwhagar/evolutionSimulator/pull/20); it is held until the owner answers or says to merge. These items turn to done when it merges.

## Waiting on the owner

Decisions the owner needs to make. Each has a recommended default in its issue. The ones that
shape 0.1 are in the table above; these are the rest.

| ID | Decision | Issue | Blocks |
| --- | --- | --- | --- |
| DNA.2 | Genome level of detail | [#2](https://github.com/dwhagar/evolutionSimulator/issues/2) | DNA.4 |
| DNA.3 | Haploid or diploid | [#3](https://github.com/dwhagar/evolutionSimulator/issues/3) | |
| DNA.4 | Fixed or variable-length genomes | [#5](https://github.com/dwhagar/evolutionSimulator/issues/5) | |
| REPRO.1 | Reproduction modes (asexual, sexual, both) | [#4](https://github.com/dwhagar/evolutionSimulator/issues/4) | DNA.9 |

## After 0.1

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| BRAIN.1 | Brain research: a simple neural network, written for a reader new to the topic (`docs/design`), with questions for the owner raised as issues BRAIN.3 to BRAIN.8 | in progress | Research 1 |
| BRAIN.2 | Foundations 2: build the brain | blocked | BRAIN.1, owner's answers to BRAIN.3 to BRAIN.8 |
| BRAIN.3 | Decide: neural network or a fixed decision rule | waiting on owner | BRAIN.1 |
| BRAIN.4 | Decide: does a creature have memory | waiting on owner | BRAIN.1 |
| BRAIN.5 | Decide: energy cost of thinking | waiting on owner | BRAIN.1 |
| BRAIN.6 | Decide: learning during a creature's life | waiting on owner | BRAIN.1 |
| BRAIN.7 | Decide: starting brains (random, hand-made, or inherited) | waiting on owner | BRAIN.1 |
| BRAIN.8 | Decide: fixed or evolvable brain size | waiting on owner | BRAIN.1 |
| DNA.9 | Decide sex at birth versus inherited | blocked | REPRO.1 |
| WORLD.2 | First world and step loop: place organisms, run ticks, feed, reproduce | blocked | WORLD.1 |

Behaviour as genes or a brain was closed for now in [#9](https://github.com/dwhagar/evolutionSimulator/issues/9); BRAIN.1 reopens the question in depth.

## Done

| ID | Item | Link |
| --- | --- | --- |
| DOCS.1 | Docs tree, roadmap, TODO and changelog | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| DOCS.2 | Research: DNA and reproduction | [#13](https://github.com/dwhagar/evolutionSimulator/pull/13) |
| DOCS.3 | Research: basic life-form traits | [#12](https://github.com/dwhagar/evolutionSimulator/pull/12) |
| DOCS.4 | Set the first milestone: 0.1, data models for DNA and traits | [#21](https://github.com/dwhagar/evolutionSimulator/pull/21) |
| INFRA.1 | Automatic `MAJOR.minor.build` versioning ([docs/versioning.md](docs/versioning.md)) | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| INFRA.2 | Weekly scheduled CI (Mondays 07:00 UTC) | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| DNA.1 | DNA objects ported from the prototype | [#18](https://github.com/dwhagar/evolutionSimulator/pull/18) |
| TRAIT.1 | Traits objects ported from the prototype | [#18](https://github.com/dwhagar/evolutionSimulator/pull/18) |

Traits decisions already settled and closed: fixed trait set ([#6](https://github.com/dwhagar/evolutionSimulator/issues/6)), allometric coupling ([#7](https://github.com/dwhagar/evolutionSimulator/issues/7)),
predators and diet ([#8](https://github.com/dwhagar/evolutionSimulator/issues/8)), behaviour as genes or brain ([#9](https://github.com/dwhagar/evolutionSimulator/issues/9)), aging ([#11](https://github.com/dwhagar/evolutionSimulator/issues/11)). All are tagged `TRAIT.1`.
