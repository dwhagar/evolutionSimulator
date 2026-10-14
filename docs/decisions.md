# Decisions

A log of the owner's design decisions, with the date, the issue where each was answered, and the
task IDs it created or changed (see [TODO.md](../TODO.md)). Newest first. Kept by the TODO thread.
Where an answer was ambiguous it is marked "to confirm" and collected in a follow-up issue; a newer section (higher up) replaces any "to confirm" in an older one.

## 2026-10-14: data storage is SQLite

The owner decided that data storage is SQLite, not a database server. The Python standard library `sqlite3` is used, so the core stays dependency-free. Plan: one `run.sqlite` file per run holding the manifest, the checkpoints (still the JSON world save, compressed), the history tiers appended as they are taken, and later the species and lineage tables. `STORE.1` is the design note, `STORE.2` the build; `UX.32`, `SPECIES.2`, `UX.35` and `UX.40` wait for it so the recorder format changes once.

## 2026-10-14: request for species graphs

The owner asked for population graphs of plants and animals and, as lines diverge, separate population graphs for the most divergent species of each kind. The totals exist already (charts, Population tab, `UX.16`). The per-species graphs need a working definition of a species (a cluster of close genomes that stays separated), tracked by the history recorder: `SPECIES.1` tracker, `SPECIES.2` recording, `UX.41` charts. The owner confirmed the defaults on the same day: a clear gap counts ([#206](https://github.com/dwhagar/evolutionSimulator/issues/206), `SPECIES.3`: centres more than twice the spread apart, never under 4% of the digits) and the top 5 lines per kind, ranked by distance from the founding genome ([#207](https://github.com/dwhagar/evolutionSimulator/issues/207), `SPECIES.4`).

## 2026-10-14: owner taps on the decision cards

The owner answered ten open questions with taps on cards in the project chat. Answers beyond the working defaults are marked **changes the default**.

| Question | Task | Decision | What follows |
| --- | --- | --- | --- |
| [#123](https://github.com/dwhagar/evolutionSimulator/issues/123), native window or web | UX.2, UX.28 | Native desktop only (the default). The web viewer is dropped. | Nothing to build for the web. |
| [#124](https://github.com/dwhagar/evolutionSimulator/issues/124), which computers | UX.3 | Windows first (the default). | `UX.19` package, `UX.34` owner check. |
| [#125](https://github.com/dwhagar/evolutionSimulator/issues/125), watch or intervene | UX.4, UX.20 | "Watch only first": the viewer stays read-only. | `UX.20` stays parked; commands keep going through the one session interface. |
| [#132](https://github.com/dwhagar/evolutionSimulator/issues/132), how the Windows program is handed over | UX.26 | An unsigned zip with the warning explained in the README (the default). | Built in `UX.19`. |
| [#134](https://github.com/dwhagar/evolutionSimulator/issues/134), which extras and when | UX.28 | "Pick some now", and the first extra is the family tree view. The others (compare two runs, watch a headless run, video export, several runs at once) stay queued. | `UX.39` family tree; `UX.40` holds the queued extras. |
| [#91](https://github.com/dwhagar/evolutionSimulator/issues/91), smell trails | SENSE.20 | **Changes the default: yes.** Smell leaves fading trails (a scent field in the world). | `SENSE.20` is a go. |
| [#92](https://github.com/dwhagar/evolutionSimulator/issues/92), visibility | SENSE.21 | **Changes the default: yes.** Add visibility traits (size, movement, camouflage or stealth). | `SENSE.21` is a go. |
| [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) 4, plants against animals in lifespan | TRAIT.12 | **Changes the default.** Plants start longer-lived than animals, as the owner first said (not a month against an animal year); they can still evolve. Watch for plants crowding the world and tune the balance. | `TRAIT.12`, after `WORLD.15`. |
| [#57](https://github.com/dwhagar/evolutionSimulator/issues/57), sleeping creatures | WORLD.6 | Partly vulnerable (the default): a sleeper is slower to sense and to flee but not deaf. | `brain-learning.md` wording fixed to match. |
| [#52](https://github.com/dwhagar/evolutionSimulator/issues/52), brain size | BRAIN.17 | Up to 16 hidden neurons, unused slots allowed (the default). | Already built. |

## 2026-10-14: request for a graphical interface

The owner asked how an interface should be made, wanted a graphical one, and asked whether it should be web or native Windows, then asked for it to be broken into TODO items with questions as issues, under the task area `UX`. Working default until answered: a native desktop program (PySide6 with pyqtgraph), a headless simulation core with the viewer as a separate layer and the simulation in its own process, Windows first.

| Question | Task | Decision | What follows |
| --- | --- | --- | --- |
| Web or native window? ([#123](https://github.com/dwhagar/evolutionSimulator/issues/123)) | UX.2 | Open. Default: native desktop | `UX.1` design note recommends; builds `UX.6` to `UX.21` wait for it. |
| Which computers? ([#124](https://github.com/dwhagar/evolutionSimulator/issues/124)) | UX.3 | Open. Default: Windows first | `UX.19`. |
| Watch only or intervene? ([#125](https://github.com/dwhagar/evolutionSimulator/issues/125)) | UX.4 | Open. Default: watch and inspect first | `UX.13`, `UX.14`, `UX.20`. |
| Save, resume, headless runs? ([#126](https://github.com/dwhagar/evolutionSimulator/issues/126)) | UX.5 | Open. Default: yes to all | `UX.9`, `UX.10`, `UX.18`. |

## 2026-10-14: request for sense genes

The owner asked for new genes: a field of vision (degrees from the direction of movement in either direction) with an acuity (how accurately they see), and a gene for how well each sense works, each starting middle of the road. Predators default to narrow, high-acuity vision and prey to lower acuity with a wider field; a lower acuity trades off with a wider field and a higher acuity with a narrower one. The owner also asked for an evaluation of what properties the world needs to support each sense. Task `SENSE.15` (design, [#95](https://github.com/dwhagar/evolutionSimulator/pull/95)), builds `SENSE.16` and `WORLD.12`; the open questions are `SENSE.17` to `SENSE.21` ([#88](https://github.com/dwhagar/evolutionSimulator/issues/88) to [#92](https://github.com/dwhagar/evolutionSimulator/issues/92)).

## 2026-10-14: answers to the clarification issues

Issue [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) and [#27](https://github.com/dwhagar/evolutionSimulator/issues/27) are answered and closed. Points that stayed unclear are in [#69](https://github.com/dwhagar/evolutionSimulator/issues/69).

| Question | Task | Decision | What follows |
| --- | --- | --- | --- |
| [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) 1, gene interaction | DNA.2 | Both: traits interact through shared costs and trade-offs, and genes affect each other, with clusters of genes feeding each trait's expression. | `DNA.14` design note. |
| 2, sexes | DNA.9 | The sex digit is fine, 0 or 1. Values 2 and 3 are used for something else sex related: they amplify or subdue (only by a fraction) the drive for mating, in addition to the specific genes for mating and child rearing. | `DNA.9`; the digit reading and whether mating needs one of each sex are question 1 on [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) (default: value mod 2 is the sex, 2 amplifies and 3 subdues by about 25%). |
| 3, world edges and time | WORLD.4 | 1000 by 1000 world units. Edges do not wrap; they are hard boundaries. A tick is a fixed simulated second and the speed setting sets ticks per real second. | Already built as `WORLD.4` (walls). |
| 4, first brains ([#27](https://github.com/dwhagar/evolutionSimulator/issues/27)) | BRAIN.9 | Option A: seeded brains plus the random wander fallback. | `BRAIN.9` after `BRAIN.23`. |
| 5, learning | BRAIN.15 | Lost when the creature dies; children start from the inherited weights. | `BRAIN.24`. |
| 6, brain shape | BRAIN.13 | Yes: a maximum-size brain in the genome plus genes that switch neurons and connections on or off. | `BRAIN.23`. |
| 7, reproduction genes | REPRO.7 | Three reproduction genes other than sex: a drive that sets the threshold for looking for a mate, a cooldown for how often they can mate, and a fertility (impregnating or becoming impregnated). Trade-offs: strong drive against short life; more offspring per birth against longer gestation; easy reproduction against energy cost; parenting (stays near and protects, at risk) against none. | `REPRO.7` revises the design before `REPRO.5` and `TRAIT.6` are built. |
| 8, time scales | WORLD.7, TRAIT.7 | Option C: much longer lifespans in simulated time with a longer tick, and a gene for how well the body recoups and recovers energy and health. | `WORLD.7`, `TRAIT.7`; defaults in [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) question 3. |
| 9, who pays for a child | REPRO.7 | The caregiving genes decide; the owner wants to see whether a pattern emerges. | In the `REPRO.7` design. |
| 10, plant lifespan | TRAIT.8 | Plants have lifespans that are genetic. A plant that is not eaten lives a default of one month, and this should evolve. | `TRAIT.8`. |
| 11, litters | REPRO.7 | Litter size comes from the genes in answer 7. The default starts with a large litter and no parenting skill. | In the `REPRO.7` design. |

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
