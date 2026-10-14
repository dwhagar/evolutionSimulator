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
| DNA.5 | Decide crossover ([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)) | waiting on owner | |
| DNA.6 | Decide mutation size and encoding ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)) | waiting on owner | |
| TRAIT.2 | Decide whether longevity carries a cost ([#16](https://github.com/dwhagar/evolutionSimulator/issues/16)) | waiting on owner | |
| REPRO.2 | Decide what `fertility` does, or remove it; `TraitSet.unread_genes()` reports it as unread ([#17](https://github.com/dwhagar/evolutionSimulator/issues/17)) | waiting on owner | |
| WORLD.1 | Decide the world model, so trait ranges stop being guesses ([#10](https://github.com/dwhagar/evolutionSimulator/issues/10)) | waiting on owner | |
| DNA.7 | Make gene-boundary crossover the default | not built: [#20](https://github.com/dwhagar/evolutionSimulator/pull/20) closed unmerged, code at `refs/pull/20/head` to reapply on the new layout API | DNA.5 |
| DNA.8 | Per-position mutation weight, mutation rate as expected changes per genome, and a mutation operator that reads `TraitDef.mutation_step` (stored, unused) | not built: [#20](https://github.com/dwhagar/evolutionSimulator/pull/20) closed unmerged, code at `refs/pull/20/head` to reapply on the new layout API | DNA.6 |
| TRAIT.3 | Move all tuning constants in `traits.py` into one config object | blocked | TRAIT.2, REPRO.2, WORLD.1 |
| TRAIT.5 | Fix the prototype's initial-state quirks and add a mating-cost guard | not built: [#20](https://github.com/dwhagar/evolutionSimulator/pull/20) closed unmerged, code at `refs/pull/20/head` to reapply on the new layout API | REPRO.2, WORLD.1 |

Items DNA.7, DNA.8 and TRAIT.3 to TRAIT.5 come from section 9.5 of
[docs/research/basic-traits.md](docs/research/basic-traits.md). Foundations 1 built the research threads' defaults for DNA.7, DNA.8, TRAIT.5 and the removal of the unused `fertility` gene (REPRO.2) in [#20](https://github.com/dwhagar/evolutionSimulator/pull/20), then closed it unmerged when TRAIT.4 ([#31](https://github.com/dwhagar/evolutionSimulator/pull/31)) changed the DNA API. The code stays at `refs/pull/20/head`; reapply it once the owner answers [#14](https://github.com/dwhagar/evolutionSimulator/issues/14), [#15](https://github.com/dwhagar/evolutionSimulator/issues/15) and [#17](https://github.com/dwhagar/evolutionSimulator/issues/17).

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
| BRAIN.2 | Foundations 2: build the `Brain` object (`decide(inputs) -> outputs`, pure function) and hook it into animals | blocked | BRAIN.3 at least (default: network), DNA.11, DNA.12, WORLD.1 |
| BRAIN.9 | Seed the first generation by fitting weights to the current fixed rule (95%+ agreement on random inputs, tested) | blocked | BRAIN.2, BRAIN.7 |
| DNA.11 | Gene-block descriptor for arrays of brain weights, as a `GeneSpec` block in `GenomeLayout` (2-digit genes, about 396 digits, animal genome about 461) | blocked | BRAIN.3 |
| DNA.12 | Mutation set per segment as expected changes, and per-neuron block crossover, so brain genes do not take over the mutation rate | blocked | BRAIN.3, DNA.8 |
| BRAIN.3 | Decide: neural network or a fixed decision rule ([#23](https://github.com/dwhagar/evolutionSimulator/issues/23)) | waiting on owner | |
| BRAIN.4 | Decide: does a creature have memory ([#24](https://github.com/dwhagar/evolutionSimulator/issues/24)) | waiting on owner | |
| BRAIN.5 | Decide: energy cost of thinking ([#25](https://github.com/dwhagar/evolutionSimulator/issues/25)) | waiting on owner | |
| BRAIN.6 | Decide: learning during a creature's life ([#26](https://github.com/dwhagar/evolutionSimulator/issues/26)) | waiting on owner | |
| BRAIN.7 | Decide: starting brains (random, hand-made, or inherited) ([#27](https://github.com/dwhagar/evolutionSimulator/issues/27)) | waiting on owner | |
| BRAIN.8 | Decide: fixed or evolvable brain size ([#28](https://github.com/dwhagar/evolutionSimulator/issues/28)) | waiting on owner | |
| DNA.9 | Decide sex at birth versus inherited | blocked | REPRO.1 |
| WORLD.2 | First world and step loop: place organisms, run ticks, feed, reproduce | blocked | WORLD.1 |

Behaviour as genes or a brain was closed for now in [#9](https://github.com/dwhagar/evolutionSimulator/issues/9); BRAIN.1 reopened the question in depth.

The energy cost per neuron (BRAIN.5) feeds the constants config, TRAIT.3. DOCS.5 should describe the brain as a third piece next to DNA and traits once BRAIN.2 exists.

## Done

| ID | Item | Link |
| --- | --- | --- |
| DOCS.1 | Docs tree, roadmap, TODO and changelog | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| DOCS.2 | Research: DNA and reproduction | [#13](https://github.com/dwhagar/evolutionSimulator/pull/13) |
| DOCS.3 | Research: basic life-form traits | [#12](https://github.com/dwhagar/evolutionSimulator/pull/12) |
| BRAIN.1 | Brain research: a small neural network for animals ([docs/design/brain.md](docs/design/brain.md)); owner decisions filed as BRAIN.3 to BRAIN.8 | [#29](https://github.com/dwhagar/evolutionSimulator/pull/29) |
| DOCS.5 | Document how DNA and traits interact ([docs/design/dna-traits-interaction.md](docs/design/dna-traits-interaction.md)) | [#32](https://github.com/dwhagar/evolutionSimulator/pull/32) |
| TRAIT.4 | Traits as data: `GenomeLayout`/`GeneSpec` in `dna.py`, `layouts.py`, `TraitDef`/`TraitSet` in `trait_defs.py`; DNA is one generic class that reads genes by ID | [#31](https://github.com/dwhagar/evolutionSimulator/pull/31) |
| DNA.10 | Layouts carry a name and version; saved genomes check the version | [#31](https://github.com/dwhagar/evolutionSimulator/pull/31) |
| DOCS.4 | Set the first milestone: 0.1, data models for DNA and traits | [#21](https://github.com/dwhagar/evolutionSimulator/pull/21) |
| INFRA.1 | Automatic `MAJOR.minor.build` versioning ([docs/versioning.md](docs/versioning.md)) | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| INFRA.2 | Weekly scheduled CI (Mondays 07:00 UTC) | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| DNA.1 | DNA objects ported from the prototype | [#18](https://github.com/dwhagar/evolutionSimulator/pull/18) |
| TRAIT.1 | Traits objects ported from the prototype | [#18](https://github.com/dwhagar/evolutionSimulator/pull/18) |

Traits decisions already settled and closed: fixed trait set ([#6](https://github.com/dwhagar/evolutionSimulator/issues/6)), allometric coupling ([#7](https://github.com/dwhagar/evolutionSimulator/issues/7)),
predators and diet ([#8](https://github.com/dwhagar/evolutionSimulator/issues/8)), behaviour as genes or brain ([#9](https://github.com/dwhagar/evolutionSimulator/issues/9)), aging ([#11](https://github.com/dwhagar/evolutionSimulator/issues/11)). All are tagged `TRAIT.1`.
