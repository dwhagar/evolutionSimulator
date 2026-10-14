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
- Gene-following crossover, `DNA.7` ([#48](https://github.com/dwhagar/evolutionSimulator/pull/48)); behaviour genes bending what the brain perceives, `BRAIN.14` ([#47](https://github.com/dwhagar/evolutionSimulator/pull/47)); a decision interval, `BRAIN.11` ([#50](https://github.com/dwhagar/evolutionSimulator/pull/50)); diploid genomes, `DNA.13` ([#63](https://github.com/dwhagar/evolutionSimulator/pull/63)); mutation that favours low digits, `DNA.8` ([#58](https://github.com/dwhagar/evolutionSimulator/pull/58)).

Still to build, now that the owner has answered the open questions:
- Plants asexual, slower to mutate and longer lived, `REPRO.3`; animal mate choice by genetic closeness, `REPRO.4`.
- The reproduction genes, `REPRO.5`, built together with longevity traded against reproduction, `TRAIT.6`. The owner's answers changed the gene set (drive, cooldown, fertility with litter size and gestation, parenting, a recovery gene, plant lifespans), so the design is revised first, `REPRO.7` (the first design is `REPRO.6`, [#49](https://github.com/dwhagar/evolutionSimulator/pull/49)), with traits that read clusters of genes, `DNA.14`.
- Prototype quirk fixes, `TRAIT.5`; and one constants config, `TRAIT.3`.

## Next: world, senses and the thinking brain

Not yet given a version; the owner sets milestones.
- The world: built (`WORLD.2` to `WORLD.4`, [#53](https://github.com/dwhagar/evolutionSimulator/pull/53)): bounds, time scales, a spatial index, stand-in senses and the step loop. To come: the day-night cycle (`WORLD.5`), per-second physics for fast speeds (`WORLD.7`, waits on the owner's answer about time scales, question 8 on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36)), plant balance (`WORLD.8`) and speed (`WORLD.9`).
- Senses: research is done (`SENSE.1`, `docs/design/senses.md`); the build items are `SENSE.8` to `SENSE.14`.
- The brain acting and learning: design notes for a shape that evolves and for nightly learning are done (`BRAIN.13`, `BRAIN.15`, [#60](https://github.com/dwhagar/evolutionSimulator/pull/60)); the builds are `BRAIN.23` and `BRAIN.24`, then acting on the decisions, `BRAIN.10`.

## Later

A first runnable simulation: organisms in the world with a step loop that feeds, ages, senses, thinks and
reproduces them, with seeded runs that repeat. Needs the world, senses and `BRAIN.10`.
