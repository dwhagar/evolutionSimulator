# Decisions

A log of the owner's design decisions, with the date, the issue where each was answered, and the
task IDs it created or changed (see [TODO.md](../TODO.md)). Newest first. Kept by the TODO thread.
Where an answer was ambiguous it is marked "to confirm" and collected in [#36](https://github.com/dwhagar/evolutionSimulator/issues/36).

## 2026-10-14: answers to the first round of issues

| Issue | Task | Decision | What follows |
| --- | --- | --- | --- |
| [#2](https://github.com/dwhagar/evolutionSimulator/issues/2) | DNA.2 | Genome is a chain of base-4 numbers; a gene can be 1 digit, 2 digits, and so on, sized to the variation it needs. "DNA traits should also interact" (to confirm, [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 1). | Already how the layouts work (`DNA.1`, `TRAIT.4`). |
| [#3](https://github.com/dwhagar/evolutionSimulator/issues/3) | DNA.3 | Diploid: two copies of every gene. | `DNA.13` diploid genomes with a simple dominance model (default codominant, averaged). |
| [#4](https://github.com/dwhagar/evolutionSimulator/issues/4) | REPRO.1 | Plants are asexual; animals are sexual with two parents and crossover. Plants mutate slower and live longer. Animals can cross-breed but should always prefer their own species or as close as possible. Sex types to confirm ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 2). | `REPRO.3` plants, `REPRO.4` animal mate choice by genetic closeness. `DNA.9` stays open. |
| [#5](https://github.com/dwhagar/evolutionSimulator/issues/5) | DNA.4 | Fixed-length genome. | No variable-length work. Brain shape question in [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 6. |
| [#10](https://github.com/dwhagar/evolutionSimulator/issues/10) | WORLD.1 | Continuous 2D space, left open to 3D later. One tick defaults to 1 second. Time-scale settings: 1 second of real time equals 1 minute, 1 hour, 1 day, 7 days, 1 month, 1 year, 10 years, 100 years or 1000 years. World bounds set by the user, default 1000 by 1000. Edges and tick meaning to confirm ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 3). | `WORLD.2` world and step loop, `WORLD.3` time scale, `WORLD.4` bounds and dimensions. |
| [#14](https://github.com/dwhagar/evolutionSimulator/issues/14) | DNA.5 | Option B: whole-gene crossover with cut points. Add a setting for how closely crossover and mutation follow the gene sequence rather than just the number, as two separate values. Crossover defaults to staying close to whole genes but slightly off; mutation defaults to random. | `DNA.7` builds it with the two settings. |
| [#15](https://github.com/dwhagar/evolutionSimulator/issues/15) | DNA.6 | Option B: mutate low digits more often than high ones. Keep some randomness so big changes still happen, especially in plants, which evolve slower. | `DNA.8` builds it. |
| [#16](https://github.com/dwhagar/evolutionSimulator/issues/16) | TRAIT.2 | Option C (longevity trades against reproduction) as the main mechanism, with a hint of option B (upkeep cost grows faster than the benefit). | `TRAIT.6`. |
| [#17](https://github.com/dwhagar/evolutionSimulator/issues/17) | REPRO.2 | Two tiers. Three separate genes: caregiving (energy invested per offspring), a limit on how often reproduction can happen, and a drive to reproduce (not the drive to care for offspring). All three affect behaviour. `fertility` goes away. | `REPRO.5` design and build. |
| [#23](https://github.com/dwhagar/evolutionSimulator/issues/23) | BRAIN.3 | Neural network (option B). Behaviour comes from genetic factors as well as an evolving network. The network also learns during life (see below). | `BRAIN.14` behaviour genes feed the brain. |
| [#24](https://github.com/dwhagar/evolutionSimulator/issues/24) | BRAIN.4 | No memory neurons at the start (option A). Creatures gain memory over their life, altering their neurons every night. | Covered by `BRAIN.15`. |
| [#25](https://github.com/dwhagar/evolutionSimulator/issues/25) | BRAIN.5 | Yes, thinking costs energy (option A). | Constants move into the `TRAIT.3` config. |
| [#26](https://github.com/dwhagar/evolutionSimulator/issues/26) | BRAIN.6 | Yes, the brain changes during life. A day-night cycle: at night creatures sleep to regain energy and their weights update. Whether learning is inherited is to confirm ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 5). | `BRAIN.15` learning design and build, `WORLD.5` day-night cycle and sleep. |
| [#28](https://github.com/dwhagar/evolutionSimulator/issues/28) | BRAIN.8 | Option C: the brain's shape can evolve. Genes control the network and how it operates. Once born, a creature cannot change its network structure; that is set at birth by genetics. Fit with fixed-length DNA to confirm ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 6). | `BRAIN.13` design and build. |
| [#27](https://github.com/dwhagar/evolutionSimulator/issues/27) | BRAIN.7 | Without memory, a creature that cannot decide moves in a random direction or turns, so its senses start giving it information. Seeded or random first brains to confirm ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 4); still open. | `BRAIN.16` random wander fallback. `BRAIN.9` waits. |

## 2026-10-14: earlier

- Milestone 0.1 is the DNA and traits data models plus a document on how they interact. Kept open (the owner chose "Keep open") until the refinement under it is built.
- All threads merge their PRs automatically once checks are green.
- Weekly CI, Mondays 07:00 UTC. Build number counts merges into main.
- Senses are the next research topic (`SENSE.1`): which senses to have and how they feed the brain.
