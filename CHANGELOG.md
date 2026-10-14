# Changelog

All notable changes are recorded here, newest first, grouped by `MAJOR.minor` line. The build
number changes with every merge, so entries reference the line rather than each build. Each entry
carries the task ID(s) from [TODO.md](TODO.md) and links the PR. See [docs/versioning.md](docs/versioning.md).

## 0.1 — Data models for DNA and traits

### Added
- `DNA.8`: Mutation favours low digits (`position_bias`, default 0.5, plants 0.75) with a separate `locality` setting for how random a change is (default fully random) and per-gene biases from `TraitDef.mutation_step`. [#58](https://github.com/dwhagar/evolutionSimulator/pull/58)
- `REPRO.6`: Design note on the reproduction genes (caregiving, reproduction interval, reproductive drive) and the longevity trade-off (`docs/design/reproduction-genes.md`); owner questions 7 to 11 added to [#36](https://github.com/dwhagar/evolutionSimulator/issues/36). The build is `REPRO.5` and `TRAIT.6`. [#49](https://github.com/dwhagar/evolutionSimulator/pull/49)
- `BRAIN.11`: Decision interval: the brain runs every n-th `think` (`decision_interval`, default 1) and its energy cost per tick is divided by n. [#50](https://github.com/dwhagar/evolutionSimulator/pull/50)
- `DNA.7`: Crossover now defaults to `DNA.crossover_linked`: a few cut points that follow whole genes and brain neurons, with `gene_fidelity` and `mean_cuts` settings. [#48](https://github.com/dwhagar/evolutionSimulator/pull/48)
- `BRAIN.14`: Behaviour genes (aggression, fear) bend what the brain perceives through a `Temperament` in the brain adapter. [#47](https://github.com/dwhagar/evolutionSimulator/pull/47)
- `SENSE.1`: Design note on senses and how they feed the brain (`docs/design/senses.md`); owner questions filed as [#40](https://github.com/dwhagar/evolutionSimulator/issues/40) to [#45](https://github.com/dwhagar/evolutionSimulator/issues/45). [#46](https://github.com/dwhagar/evolutionSimulator/pull/46)
- `BRAIN.16`: Random wander fallback for creatures that cannot decide. [#39](https://github.com/dwhagar/evolutionSimulator/pull/39)
- `DOCS.6`: Decisions log (`docs/decisions.md`) recording the owner's answers to the first round of issues and the tasks they created. Open clarifications are in [#36](https://github.com/dwhagar/evolutionSimulator/issues/36).
- `BRAIN.2`, `DNA.11`, `DNA.12`: The animal brain. A pure 17-8-6 feedforward `Brain` (198 weights) with an adapter from percepts to decisions, a `BlockSpec` gene block for weight arrays stored in the DNA (the animal genome is now 461 digits, layout version 2), per-segment expected-change mutation, whole-neuron crossover (`crossover_by_unit`), and brain upkeep added to basal metabolism. `AnimalTraits.think()` returns the decision; acting on it is not built yet. [#34](https://github.com/dwhagar/evolutionSimulator/pull/34)
- `DOCS.5`: Document on how DNA and traits interact (`docs/design/dna-traits-interaction.md`). [#32](https://github.com/dwhagar/evolutionSimulator/pull/32)
- `TRAIT.4`, `DNA.10`: Traits as data. A genome layout (`GenomeLayout`, `GeneSpec`) lists the genes by ID, with a name and version that saved genomes check on load; trait definitions (`TraitDef`, `TraitSet`) say how each trait reads genes. DNA is now one generic class and no longer knows trait names. [#31](https://github.com/dwhagar/evolutionSimulator/pull/31)
- `BRAIN.1`: Design note on a small feedforward neural network brain for animals (`docs/design/brain.md`): 17 inputs, 8 hidden neurons, 6 outputs, weights stored in the DNA, with six owner decisions filed as issues ([#23](https://github.com/dwhagar/evolutionSimulator/issues/23) to [#28](https://github.com/dwhagar/evolutionSimulator/issues/28), `BRAIN.3` to `BRAIN.8`). [#29](https://github.com/dwhagar/evolutionSimulator/pull/29)

### Changed
- `DOCS.4`: Milestone 0.1 set by the owner: data models for traits and DNA, with a document on how they interact. The version line moves from 0.0 to 0.1 ([docs/versioning.md](docs/versioning.md)). [#21](https://github.com/dwhagar/evolutionSimulator/pull/21)
- `DOCS.1`: TODO items have `AREA.N` task IDs, and issues and PRs are labelled with them (see [TODO.md](TODO.md)). [#19](https://github.com/dwhagar/evolutionSimulator/pull/19)

## 0.0 — Pre-release

### Added
- `TRAIT.1`, `DNA.1`: DNA and traits objects: immutable base-4 `AnimalDNA` / `PlantDNA` with seedable mutation, crossover and reproduction, and `AnimalTraits` / `PlantTraits` phenotypes, ported from the owner's prototype (see [docs/design/dna-and-traits.md](docs/design/dna-and-traits.md)). [#18](https://github.com/dwhagar/evolutionSimulator/pull/18)
- `DOCS.3`: Research note on basic life-form traits (`docs/research/basic-traits.md`), including a review of the owner's trait prototype and the DNA/trait contract. [#12](https://github.com/dwhagar/evolutionSimulator/pull/12)
- `DOCS.2`: Research note on DNA and reproduction (`docs/research/dna-and-reproduction.md`), including a review of the owner's DNA and trait prototypes. [#13](https://github.com/dwhagar/evolutionSimulator/pull/13)
- `DOCS.1`: Docs tree (`docs/design`, `docs/research`, `docs/archive`), roadmap, and TODO list. [#1](https://github.com/dwhagar/evolutionSimulator/pull/1)
- `INFRA.1`: Automatic `MAJOR.minor.build` versioning: the build counts merges into main. [#1](https://github.com/dwhagar/evolutionSimulator/pull/1)
- `INFRA.2`: Project scaffold: Python 3.12+ package, pytest, ruff, and weekly scheduled CI (Mondays 07:00 UTC). [#1](https://github.com/dwhagar/evolutionSimulator/pull/1)
