# Decisions

A log of the owner's design decisions, with the date, the issue where each was answered, and the
task IDs it created or changed (see [TODO.md](../TODO.md)). Newest first. Kept by the TODO thread.
Where an answer was ambiguous it is marked "to confirm" and collected in a follow-up issue; a newer section (higher up) replaces any "to confirm" in an older one.

## 2026-10-15: owner taps on the colour questions

The owner confirmed all six defaults of [#246](https://github.com/dwhagar/evolutionSimulator/issues/246): (1) colour is its own gene, starting at the diet colour and mutating freely; (2) the camouflage gene stays alongside it; (3) the background an animal sits against is plants and bare ground blended by plant cover; (4) females carry the spots; (5) the colour line runs red, purple, blue, teal, green, so omnivores are purple; (6) the cost of colour is a pigment upkeep that grows with how vivid the coat is. `TRAIT.20` is built as designed; `TRAIT.21` is the build (animal layout 10 with `TRAIT.15` and `SENSE.22`) and `UX.43` can draw with these rules.

## 2026-10-15: how creatures look, and the last cards

The owner answered [#129](https://github.com/dwhagar/evolutionSimulator/issues/129) in their own words: "For how creatures should look, little round creatures with eyes in the front that point in the direction they are focused on within their vision. Color should be a separate trait tied to what they eat (carnivore red herbivore blue), markings will determine gender (ladybug style little spots or no spots), but color of their body should also be its own value as when it's closer to the foliage they are in they are harder to see. Also plants are darker that are tougher."

This replaces the default (triangles coloured by diet). It splits into: `UX.43` (draw round creatures with front eyes that turn toward their target inside the field of vision, colour from diet for now, spots for one sex), `UX.44` (plants darker when tougher, after `TRAIT.13`), `TRAIT.20` (a design note for the colour gene and hiding in foliage) and `TRAIT.21` (the build, in animal layout 10 with `TRAIT.15` and `SENSE.22`, two balancers, the balance gate). The open details are four questions with defaults in [#246](https://github.com/dwhagar/evolutionSimulator/issues/246): colour is its own gene that starts at the diet colour and mutates freely; it sits alongside the camouflage gene; the background is plant green and ground blended by nearby cover; females carry the spots. The gene freeze for the numpy build now also waits for `TRAIT.21`.

The remaining cards were answered with the defaults, all logged in the Done table of TODO.md and closed:

| Issue | Task | Answer |
| --- | --- | --- |
| [#90](https://github.com/dwhagar/evolutionSimulator/issues/90) | SENSE.19 | Predator and prey eyes are only a starting point; evolution is free |
| [#54](https://github.com/dwhagar/evolutionSimulator/issues/54) | BRAIN.18 | All four brain operating settings are genes (gain, reaction time, curiosity, learning rate) |
| [#55](https://github.com/dwhagar/evolutionSimulator/issues/55) | BRAIN.19 | Keep the reward weights |
| [#56](https://github.com/dwhagar/evolutionSimulator/issues/56) | BRAIN.20 | A medium cap on the nightly change |
| [#126](https://github.com/dwhagar/evolutionSimulator/issues/126) | UX.5 | Keep saving, resuming, headless runs and recorded history |
| [#130](https://github.com/dwhagar/evolutionSimulator/issues/130) | UX.24 | Keep all speed presets |
| [#131](https://github.com/dwhagar/evolutionSimulator/issues/131) | UX.25 | Keep the run folder and the 5 GB warning as built |
| [#133](https://github.com/dwhagar/evolutionSimulator/issues/133) | UX.27 | The brain view shows both bars and the network, bars first |

## 2026-10-15: owner taps on the senses questions

The owner answered the senses cards. Every answer except one is the default the builds were already using, so only the last row changes any work.

| Issue | Task | Answer | What follows |
| --- | --- | --- | --- |
| [#40](https://github.com/dwhagar/evolutionSimulator/issues/40) | SENSE.2 | Yes: vision, hearing and smell can be lost completely; touch always works | Nothing, built (SENSE.11) |
| [#41](https://github.com/dwhagar/evolutionSimulator/issues/41) | SENSE.3 | Yes: darkness reduces vision (range times 0.25 + 0.75 x daylight) | Nothing, built |
| [#42](https://github.com/dwhagar/evolutionSimulator/issues/42) | SENSE.4 | Yes: vision nearly exact, hearing and smell noisy | Nothing, built; SENSE.13 calibrates the noise |
| [#43](https://github.com/dwhagar/evolutionSimulator/issues/43) | SENSE.5 | The brain sees the kind and the relative size of the nearest thing | Similarity to a mate with REPRO.4 |
| [#44](https://github.com/dwhagar/evolutionSimulator/issues/44) | SENSE.6 | No: the list of senses is fixed | Nothing |
| [#45](https://github.com/dwhagar/evolutionSimulator/issues/45) | SENSE.7 | Asleep: touch full, hearing and smell half, sight off | Nothing, built (WORLD.5) |
| [#88](https://github.com/dwhagar/evolutionSimulator/issues/88) | SENSE.17 | A hard ceiling: working acuity is the smaller of the acuity gene and one minus the field gene | Nothing, built (SENSE.16) |
| [#89](https://github.com/dwhagar/evolutionSimulator/issues/89) | SENSE.18 | Yes, hearing and smell get separate acuity genes (not the default) | New item SENSE.22: two animal genes, two balancers each, the balance gate, built with the resistance genes in animal layout 10 (TRAIT.15). The cost is a question in [#242](https://github.com/dwhagar/evolutionSimulator/issues/242) |

## 2026-10-15: the first reading of the founders, and the numbering of the numpy build

Foundations 3 measured why seeded founders do not breed (WORLD.15, [#237](https://github.com/dwhagar/evolutionSimulator/pull/237)): they gain 0.04 to 0.10 energy a tick and lose about 0.78, and constants alone do not fix it. The settings that make the starting world forgiving are owner questions with defaults in use, in [#242](https://github.com/dwhagar/evolutionSimulator/issues/242): upkeep a tenth of today's, bite 20, founder plants at 0.3 of today's toxicity, founder fertility 0.3 and parenting 0.1, the world kept at 1,000 by 1,000 with 800 plants started grown and aged. What constants cannot fix became three items: BRAIN.26 (finding plants close up), TRAIT.12 (founder plants, now with ages and growth) and REPRO.10 (newborns and the first litter).

Research 5's numpy note ([#236](https://github.com/dwhagar/evolutionSimulator/pull/236)) numbered its nine stages WORLD.21 to WORLD.29, which clashed with the varied world (WORLD.21, TRAIT.15's follow-up). They are WORLD.30 to WORLD.38 in TODO.md (the note was updated). WORLD.20 stays the umbrella; numpy 2.0 or newer as a core dependency is accepted; the gene freeze is declared (WORLD.15, TRAIT.12 to TRAIT.15 and SENSE.22 first, then any layout or trait change during the build is made in both engines in the same PR); the version proposal goes to the owner at stage 8. Whether positions stay two-dimensional is the last question in [#242](https://github.com/dwhagar/evolutionSimulator/issues/242) (default 2-D for good).

## 2026-10-14: plant trade-offs, effort to eat and animal resistance

The owner asked that toxicity and size are linked, that a bigger plant takes longer to germinate, that every free plant gene gets a balancing trait and all of them interact, that `root_reach` is fixed, that faster seeding makes a plant easier to eat, that tougher and more toxic plants take longer to eat (an effort to eat), and that animals get a resistance gene: more resistance to toxic plants (or poisoned animals) means eating takes longer but more food can be eaten. Design: [design/plant-tradeoffs.md](design/plant-tradeoffs.md). Tasks: `TRAIT.13` (plant genes, new `toughness` gene, germination, `root_reach`), `TRAIT.14` (effort to eat), `TRAIT.15` (animal resistance gene, animal layout version 10), `TRAIT.16` (poisoned animals). A later message made it a general rule: **every gene, plant and animal, needs two balancers**; the first is an inter-gene reaction through auxiliary traits (more seeds, easier to eat), the second was not named. `TRAIT.13` records it for plants and `TRAIT.17` for animals (a balancer table and a test). Four points are open in [#216](https://github.com/dwhagar/evolutionSimulator/issues/216) with defaults in use: how toxicity and size are linked (default: a bigger plant costs more to keep poisonous), whether tough is its own gene (default: yes), what poisoned animals means (default: they carry the poison they ate, and their meat is poisonous), and what the second balancer is (default: a direct cost).

## 2026-10-15: label colours by category

The owner asked for the task tags to be coloured by category: one colour family per area (for example all TRAIT items orange, all WORLD items teal) with different shades for the items, repeats allowed, `needs-owner` bright red and an `in-progress` label in royal blue. `INFRA.12` replaces the rotating palette of `INFRA.8` with this; the scheme is in [labels.md](labels.md).

## 2026-10-15: owner taps on the genetics questions, and toxin types now

On [#231](https://github.com/dwhagar/evolutionSimulator/issues/231): poison as a dose that decays: **yes** (`TRAIT.18`); tougher plants give less food: **yes**; `root_reach`: soil access plus regrowth after grazing (the default); toxin types with matching resistance: **now**, not later. Toxin types therefore ride in plant layout 4 (`toxin_type`) and animal layout 10 (`resistance_type`), with the dose built per type; the design is the "Toxin types" section of [design/plant-tradeoffs.md](design/plant-tradeoffs.md). Two details are open in [#239](https://github.com/dwhagar/evolutionSimulator/issues/239) (the number of types, default four, and the matching rule, default full/half/none on a ring). The rest of [#231](https://github.com/dwhagar/evolutionSimulator/issues/231): a varied world: **yes, later** (`WORLD.21`, after the basics); the balance audit is a **gate** for layout and gene changes (`TRAIT.17`: it must pass before a layout bump or a new gene merges); resistance **slows the animal a little** (`TRAIT.15`). On [#232](https://github.com/dwhagar/evolutionSimulator/issues/232): keep the old files after an import (in `imported/`), warn on a network drive, and **build** the compact action (`STORE.3`, not the "not built" default). #231 and #232 are closed.

## 2026-10-15: Python 3.12 or newer

The owner requires Python 3.12 or higher. It was already the baseline; `INFRA.11` makes sure it is enforced everywhere: `requires-python` and ruff's target in `pyproject.toml`, the CI and package workflows, the README, a clear error when the package is imported on an older Python, and a test (`tests/test_python_version.py`) that keeps them together. The launcher `run.ps1` (`INFRA.10`) refuses an older Python with a message.

## 2026-10-15: a PowerShell launcher in the root

The owner asked for a PowerShell script in the repository root that runs the application and starts Python correctly, because Windows is fiddly. `INFRA.10`: `run.ps1` (with a `run.bat` that calls it) finds Python 3.12 or newer, creates or reuses `.venv`, installs the `gui` extra when needed and starts the viewer. It is the one exception to the rule that scripts live in `scripts/`, because the owner asked for it in the root. The owner tries it with `UX.34`.

## 2026-10-15: all source code goes in `src/`

The owner's rule: all source code goes in the `src` folder, and `scripts` holds only PowerShell or batch files (and bash if the project becomes Linux compatible). Done as `INFRA.9`: the Python tools are the package `src/evolution_tools/` with thin `.ps1` and `.bat` wrappers in `scripts/`, and `tests/test_repo_layout.py` enforces it. Tests stay in `tests/` and the pytest-benchmark tests in `benchmarks/`; the PyInstaller entry shim `packaging/entry.py` stays where the spec expects it (it can move into `src/` if the owner wants).

## 2026-10-15: the genetics research and the run file

The genetics research ([design/gene-balance.md](design/gene-balance.md), `DNA.16`) found that poison damage is the same whatever amount is eaten, so the plan changes: poison becomes a dose that builds up and wears off (`TRAIT.18`, before `TRAIT.14`), resistance works through that load, and a balance audit (`TRAIT.17`, no layout change) starts first and gives the baseline. New items: `TRAIT.17`, `TRAIT.18`, `TRAIT.19` (only as the audit asks), `WORLD.21` (a varied world), `SPECIES.5`, `UX.42`. Seven owner questions are in [#231](https://github.com/dwhagar/evolutionSimulator/issues/231) and three small ones about the run file in [#232](https://github.com/dwhagar/evolutionSimulator/issues/232); builds use the defaults named there until the owner answers. Builders merged `SPECIES.1`, `STORE.1`, `SENSE.21` (animal layout 9, so resistance is layout 10), `UX.39` (world save format 6) and `DNA.17`.

## 2026-10-15: speed: rewrite the core with numpy

The package research ([research/python-packages.md](research/python-packages.md)) found that no drop-in package gets the 4 times needed for a simulated day per real second (today about a quarter of a day at 1,000 animals and 5,000 plants, a tick of about 175 ms); only an array rewrite does. The owner chose **rewrite with numpy** ([#222](https://github.com/dwhagar/evolutionSimulator/issues/222) question 1) over keeping the core pure Python. Consequences: numpy becomes a core dependency and the "no numpy in the core" rule goes; saves and `state_digest` change at a clear version cut (old saves load by migration; runs from the same seed no longer replay bit for bit across the cut); the target is a full world at a day per real second (about 40 ms a tick). Plan: `WORLD.19` (design note and benchmark, Research 5), then `WORLD.20` (the build, in stages), which waits until the code it would rewrite stops changing (WORLD.15, SENSE.21, TRAIT.12 to TRAIT.15, the DNA.16 report). The free wins stay: genome distance as one integer (`DNA.17`), gzip level 1 for checkpoints (in `STORE.2`), and the `dev` extra (`INFRA.7`, default yes). Video export (`UX.40`) stays GIF and PNG sequence until the owner says otherwise.

## 2026-10-15: owner taps on the plant trade-off questions

On [#216](https://github.com/dwhagar/evolutionSimulator/issues/216): bigger plants pay more to stay poisonous (question 1), toughness is its own gene (question 2), a poisoned animal carries the poison and its meat poisons whoever eats it, with no animal toxin gene yet (question 3). All three are the defaults the plan already used. Question 4: the second balancer is a **direct cost** (each gene also pays upkeep, a budget share or a delay), the default the plan used. So every gene, plant and animal, has an inter-gene reaction and a direct cost, in the balancer table (`TRAIT.13`, `TRAIT.17`), with a test. [#216](https://github.com/dwhagar/evolutionSimulator/issues/216) is closed.

## 2026-10-14: genetics research on gene interactions

The owner asked for a research thread on gene interactions and balancing factors in real life, with a design report on how the genome and traits should change. Task `DNA.16` (Research 6). The detailed trade-off numbers for `TRAIT.13` and `TRAIT.17` wait for its report; the plan in [design/plant-tradeoffs.md](design/plant-tradeoffs.md) stands as the first cut and is revised from the report.

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
