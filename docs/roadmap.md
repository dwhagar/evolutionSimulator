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
- The reproduction genes: the first three are built (`REPRO.5`, `TRAIT.6`, [#74](https://github.com/dwhagar/evolutionSimulator/pull/74)) and mate choice by genetic closeness (`REPRO.4`). The owner's answers changed the gene set, so the design was revised (`REPRO.7`, [#77](https://github.com/dwhagar/evolutionSimulator/pull/77)); the build is done (`REPRO.8`, `DNA.9`, `TRAIT.7`, [#101](https://github.com/dwhagar/evolutionSimulator/pull/101): drive, cooldown, fertility with litters and gestation, parenting, the sex digit, a recovery gene, per-hour charging); the plant lifespan gene is built (`TRAIT.8`, [#112](https://github.com/dwhagar/evolutionSimulator/pull/112)), and a re-check in the real world `REPRO.9`. Traits that read clusters of genes: design done (`DNA.14`, [#80](https://github.com/dwhagar/evolutionSimulator/pull/80)), built (`DNA.15`, [#110](https://github.com/dwhagar/evolutionSimulator/pull/110)).
- Prototype quirk fixes, `TRAIT.5`; and one constants config, `TRAIT.3` ([#114](https://github.com/dwhagar/evolutionSimulator/pull/114)), are built.

## Next: world, senses and the thinking brain

Not yet given a version; the owner sets milestones.
- The world: built (`WORLD.2` to `WORLD.4`, [#53](https://github.com/dwhagar/evolutionSimulator/pull/53)): bounds, time scales, a spatial index, stand-in senses and the step loop. Also built: the day-night cycle (`WORLD.5`), an hourly default tick with a 24-hour day and physics that follows the tick (`WORLD.7`, [#116](https://github.com/dwhagar/evolutionSimulator/pull/116)), plant balance (`WORLD.8`) and speed (`WORLD.9`, `WORLD.13`). To come: a world where founders breed (`WORLD.15`) and seedling survival (`WORLD.11`).
- Senses: research is done (`SENSE.1`, `docs/design/senses.md`); the build items are `SENSE.8` to `SENSE.14` (the extra brain inputs of `SENSE.14` are built, [#139](https://github.com/dwhagar/evolutionSimulator/pull/139)); the sense genes (field of vision, acuity) are built (`SENSE.16`, [#103](https://github.com/dwhagar/evolutionSimulator/pull/103)).
- The brain acting and learning: design notes for a shape that evolves and for nightly learning are done (`BRAIN.13`, `BRAIN.15`, [#60](https://github.com/dwhagar/evolutionSimulator/pull/60)); the builds are done (`BRAIN.23`, `BRAIN.24`), and the first generation now carries a seeded brain (`BRAIN.9`, [#106](https://github.com/dwhagar/evolutionSimulator/pull/106)). The world now acts on every brain decision (`BRAIN.10`, [#118](https://github.com/dwhagar/evolutionSimulator/pull/118)). Next: a world calibrated so that founders breed, `WORLD.15`.

## Next: the interface

Asked for by the owner on 2026-10-14 (task area `UX`): a graphical viewer with a world view, speed and time controls, a creature inspector, population and gene charts, run setup and save and load. The design note is done (`UX.1`, [docs/design/ux.md](design/ux.md), [#135](https://github.com/dwhagar/evolutionSimulator/pull/135)): a native desktop program (PySide6, pyqtgraph) with the simulation kept as a headless core in its own process. Owner questions are [#123](https://github.com/dwhagar/evolutionSimulator/issues/123) to [#126](https://github.com/dwhagar/evolutionSimulator/issues/126) and [#129](https://github.com/dwhagar/evolutionSimulator/issues/129) to [#134](https://github.com/dwhagar/evolutionSimulator/issues/134). The builds (`UX.6` to `UX.22`) run in four waves, starting with the simulation session (`UX.6`).

Built so far: world save and load in the core (`UX.9`, [#142](https://github.com/dwhagar/evolutionSimulator/pull/142)) the simulation session (`UX.6`, [#148](https://github.com/dwhagar/evolutionSimulator/pull/148)) and the statistics recorder (`UX.8`, [#152](https://github.com/dwhagar/evolutionSimulator/pull/152)). the app shell (`UX.11`, [#153](https://github.com/dwhagar/evolutionSimulator/pull/153)). Next: the process host (`UX.7`), the run store (`UX.10`), and wave 3, the screens (`UX.12` to `UX.17`), with the core additions for the inspector (`UX.29`).

## Next: storage, species and the order of work

Decided by the owner on 2026-10-14: data storage is SQLite (one `run.sqlite` per run, standard library only; `STORE.1`, `STORE.2`), and the viewer gets population graphs by species (`SPECIES.1`, `SPECIES.2`, `UX.41`) and a family tree view (`UX.39`). The first release of the interface is built apart from polish (`UX.21`): world view, controls, inspector with the brain and senses view, charts, run setup, saved runs and the Windows package, with the real world as the default launch. What blocks what, and what is ready now, is the "Order of work" tree in [TODO.md](../TODO.md).

## Later

A first runnable simulation: organisms in the world with a step loop that feeds, ages, senses, thinks and
reproduces them, with seeded runs that repeat. Needs the world, senses and the founders breeding (`WORLD.15`).
