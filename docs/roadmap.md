# Roadmap

The plan for the simulator. Major and minor versions track milestones set here; the build number
is bumped automatically on every merge into main (see [versioning](versioning.md)). Work is tracked
as task IDs (`AREA.N`) in [TODO.md](../TODO.md); the owner's decisions are in [decisions.md](decisions.md).

## 0.0 — Pre-release (done)

Scaffold, docs, versioning, research notes, and the first DNA and traits objects (a port of the
owner's prototype). No world or step loop yet, so nothing runs.

## 0.1 — Data models for DNA and traits (current, kept open)

Goal, set by the owner on 2026-10-14: the data models for traits and DNA are set up, with a document
on how the two interact. The owner chose to keep 0.1 open until the refinement is built.

Done:
- DNA and traits objects, `DNA.1` and `TRAIT.1` ([#18](https://github.com/dwhagar/evolutionSimulator/pull/18)).
- Traits as data, with DNA reading genes by ID, `TRAIT.4` and `DNA.10` ([#31](https://github.com/dwhagar/evolutionSimulator/pull/31)).
- The interaction document, `DOCS.5` ([#32](https://github.com/dwhagar/evolutionSimulator/pull/32)).
- The animal brain and its gene blocks, `BRAIN.2`, `DNA.11`, `DNA.12` ([#34](https://github.com/dwhagar/evolutionSimulator/pull/34)).

Still to build, now that the owner has answered the open questions:
- Crossover and mutation as the owner specified, `DNA.7` and `DNA.8`.
- Diploid genomes with dominance, `DNA.13`.
- Plants asexual, slower to mutate and longer lived, `REPRO.3`; animal mate choice by genetic closeness, `REPRO.4`.
- The three reproduction genes replacing `fertility`, `REPRO.5` (design note first).
- Longevity traded against reproduction, `TRAIT.6`; prototype quirk fixes, `TRAIT.5`; and one constants config, `TRAIT.3`.

## Next: world, senses and the thinking brain

Not yet given a version; the owner sets milestones.
- The world: continuous 2D space with user-set bounds, time scales from a minute to a thousand years per second, and a day-night cycle (`WORLD.2` to `WORLD.5`).
- Senses: research on which senses to have and how they feed the brain (`SENSE.1`).
- The brain acting and learning: behaviour genes feeding the brain, random wander when undecided, a shape that evolves, and nightly learning (`BRAIN.13` to `BRAIN.16`, `BRAIN.10`).

## Later

A first runnable simulation: organisms in the world with a step loop that feeds, ages, senses, thinks and
reproduces them, with seeded runs that repeat. Needs the world, senses and `BRAIN.10`.
