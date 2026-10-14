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

A new area is added here first. Status is one of: open, blocked (on a decision or another item), done.

## Waiting on the owner

Decisions the owner needs to make. Each has a recommended default in its issue.

| ID | Decision | Issue | Blocks |
| --- | --- | --- | --- |
| DNA.2 | Genome level of detail | [#2](https://github.com/dwhagar/evolutionSimulator/issues/2) | DNA.4 |
| DNA.3 | Haploid or diploid | [#3](https://github.com/dwhagar/evolutionSimulator/issues/3) | |
| DNA.4 | Fixed or variable-length genomes | [#5](https://github.com/dwhagar/evolutionSimulator/issues/5) | |
| DNA.5 | Crossover: whole genes, cut points, or per-digit | [#14](https://github.com/dwhagar/evolutionSimulator/issues/14) | DNA.7 |
| DNA.6 | Mutation size: keep first-digit-matters-most encoding, Gray code | [#15](https://github.com/dwhagar/evolutionSimulator/issues/15) | DNA.8 |
| REPRO.1 | Reproduction modes (asexual, sexual, both) | [#4](https://github.com/dwhagar/evolutionSimulator/issues/4) | DNA.9 |
| REPRO.2 | What `fertility` does; reproduction genes | [#17](https://github.com/dwhagar/evolutionSimulator/issues/17) | TRAIT.3, TRAIT.5 |
| TRAIT.2 | Whether longevity (`somatic_maint`) carries a real cost | [#16](https://github.com/dwhagar/evolutionSimulator/issues/16) | TRAIT.3 |
| WORLD.1 | Grid or continuous space; what one tick is | [#10](https://github.com/dwhagar/evolutionSimulator/issues/10) | TRAIT.3, TRAIT.5, WORLD.2 |

## Open and blocked

| ID | Item | Status | Needs |
| --- | --- | --- | --- |
| DOCS.4 | Set the first milestone in [docs/roadmap.md](docs/roadmap.md) | open | Owner |
| DNA.7 | Make per-gene crossover the default (`crossover_by_gene` exists, default is still per-digit) | blocked | DNA.5 |
| DNA.8 | Per-position mutation weight, and a mutation rate expressed as expected changes per genome | blocked | DNA.6 |
| DNA.9 | Decide sex at birth versus inherited | blocked | REPRO.1 |
| TRAIT.3 | Move all tuning constants in `traits.py` into one config object | blocked | TRAIT.2, REPRO.2, WORLD.1 |
| TRAIT.4 | Define traits as data (gene IDs, range, scale, mutation step) so DNA does not know trait names | open | |
| TRAIT.5 | Fix the prototype's initial-state quirks and add a mating-cost guard | blocked | REPRO.2, WORLD.1 |
| WORLD.2 | First world and step loop: place organisms, run ticks, feed, reproduce | blocked | WORLD.1 |

Items TRAIT.3 to TRAIT.5, DNA.7 and DNA.8 come from section 9.5 of
[docs/research/basic-traits.md](docs/research/basic-traits.md).

## Done

| ID | Item | Link |
| --- | --- | --- |
| DOCS.1 | Docs tree, roadmap, TODO and changelog | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| DOCS.2 | Research: DNA and reproduction | [#13](https://github.com/dwhagar/evolutionSimulator/pull/13) |
| DOCS.3 | Research: basic life-form traits | [#12](https://github.com/dwhagar/evolutionSimulator/pull/12) |
| INFRA.1 | Automatic `MAJOR.minor.build` versioning ([docs/versioning.md](docs/versioning.md)) | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| INFRA.2 | Weekly scheduled CI (Mondays 07:00 UTC) | [#1](https://github.com/dwhagar/evolutionSimulator/pull/1) |
| DNA.1 | DNA objects ported from the prototype | [#18](https://github.com/dwhagar/evolutionSimulator/pull/18) |
| TRAIT.1 | Traits objects ported from the prototype | [#18](https://github.com/dwhagar/evolutionSimulator/pull/18) |

Traits decisions already settled and closed: fixed trait set ([#6](https://github.com/dwhagar/evolutionSimulator/issues/6)), allometric coupling ([#7](https://github.com/dwhagar/evolutionSimulator/issues/7)),
predators and diet ([#8](https://github.com/dwhagar/evolutionSimulator/issues/8)), behaviour as genes or brain ([#9](https://github.com/dwhagar/evolutionSimulator/issues/9)), aging ([#11](https://github.com/dwhagar/evolutionSimulator/issues/11)). All are tagged `TRAIT.1`.
