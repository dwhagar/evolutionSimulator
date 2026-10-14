# Changelog

All notable changes are recorded here, newest first, grouped by `MAJOR.minor` line. The build
number changes with every merge, so entries reference the line rather than each build. Each entry
carries the task ID(s) from [TODO.md](TODO.md) and links the PR. See [docs/versioning.md](docs/versioning.md).

## 0.1 — Data models for DNA and traits

### Changed
- `DOCS.4`: Milestone 0.1 set by the owner: data models for traits and DNA, with a document on how they interact. The version line moves from 0.0 to 0.1 ([docs/versioning.md](docs/versioning.md)). [#PRN](https://github.com/dwhagar/evolutionSimulator/pull/PRN)
- `DOCS.1`: TODO items have `AREA.N` task IDs, and issues and PRs are labelled with them (see [TODO.md](TODO.md)). [#19](https://github.com/dwhagar/evolutionSimulator/pull/19)

## 0.0 — Pre-release

### Added
- `TRAIT.1`, `DNA.1`: DNA and traits objects: immutable base-4 `AnimalDNA` / `PlantDNA` with seedable mutation, crossover and reproduction, and `AnimalTraits` / `PlantTraits` phenotypes, ported from the owner's prototype (see [docs/design/dna-and-traits.md](docs/design/dna-and-traits.md)). [#18](https://github.com/dwhagar/evolutionSimulator/pull/18)
- `DOCS.3`: Research note on basic life-form traits (`docs/research/basic-traits.md`), including a review of the owner's trait prototype and the DNA/trait contract. [#12](https://github.com/dwhagar/evolutionSimulator/pull/12)
- `DOCS.2`: Research note on DNA and reproduction (`docs/research/dna-and-reproduction.md`), including a review of the owner's DNA and trait prototypes. [#13](https://github.com/dwhagar/evolutionSimulator/pull/13)
- `DOCS.1`: Docs tree (`docs/design`, `docs/research`, `docs/archive`), roadmap, and TODO list. [#1](https://github.com/dwhagar/evolutionSimulator/pull/1)
- `INFRA.1`: Automatic `MAJOR.minor.build` versioning: the build counts merges into main. [#1](https://github.com/dwhagar/evolutionSimulator/pull/1)
- `INFRA.2`: Project scaffold: Python 3.12+ package, pytest, ruff, and weekly scheduled CI (Mondays 07:00 UTC). [#1](https://github.com/dwhagar/evolutionSimulator/pull/1)
