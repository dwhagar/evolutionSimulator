# Where we stopped, and how to restart

Written by the TODO thread on 2026-10-15, when the owner paused the project ("let all threads finish their
current task, TODO updates GitHub with everything, then go idle"). Every thread finished and merged its work;
no thread has an open branch or pull request with unmerged commits. This note is the handover: what exists,
what is ready next, what each thread was doing and how to bring it back. [TODO.md](../TODO.md) has the full
item list and the "Order of work" tree, [decisions.md](decisions.md) the owner's answers, and
[CHANGELOG.md](../CHANGELOG.md) what changed.

## The state of the project

- **Version** 0.1.x (milestone 0.1 is kept open by the owner; the build number counts merges into main,
  `python -m evolution_tools.version`).
- **It runs.** `run.ps1` (or `run.bat`, or `python -m evolution_simulator.viewer --world` with the `gui` extra) opens
  the viewer on the real world: round creatures with eyes, colour by diet, spots on females, charts including the
  Species tab, an inspector with the brain and senses view, a family tree, saved runs in one `run.sqlite` per run
  with a Compact button, and a Windows package built by hand-started workflow. About 1,900 tests pass.
- **The founders now breed.** The default run (100 animals, 800 plants, 1,000 by 1,000) keeps breeding for 6,000
  ticks: 31 to 36 births, 37 to 46 animals alive at the end (`docs/design/world.md`, "The default founder run").
  The upkeep is a tenth of what the body tables say, a bite is 20, founder plants are 30% as poisonous and start
  grown with spread ages, founder fertility 0.3 and parenting 0.1 (all confirmed by the owner, issue 242).
- **Formats in force:** animal layout 9 (1,264 digits, `camouflage` last), plant layout 3, world save format 7,
  history format 3, run file schema 2, frame format 3. Next layout change: animal layout 10 (resistance genes,
  hearing and smell acuity, `colour`) and plant layout 4 (`toughness`, `toxin_type`), in one bump each.
- **CI** runs weekly only (Mondays 07:00 UTC); the first run is Monday 2026-10-19 (INFRA.4). Run `ruff check .`,
  `ruff format --check .` and `pytest` (or `pytest -n auto` with the `dev` extra) locally before every merge.

## What is ready to start, in the order we would do it

1. **TRAIT.22** (Foundations 1): retune the balance audit to the new economy, add the world audit for the blind
   sense and brain genes. Do this before any layout bump.
2. **BRAIN.26** (Foundations 2): animals find plants close up (a seed-table refit; the command is in
   `docs/design/brain.md`). Then **TRAIT.12** (plants live longer, soil capacity).
3. **REPRO.10** and **REPRO.9** (Foundations 1): newborns starve (11 to 21 of 31 to 36 young), the first litter
   comes at tick 1,000 to 1,500; then the long-run check of the reproduction genes.
4. **WORLD.18** (Foundations 4): compare the brain speed options on a breeding population, change a default only
   if the numbers say it is safe.
5. **SPECIES.5** (Viewer 2): recheck the species rules on real animals.
6. Then the gene chain: **TRAIT.18** (poison as a dose, per-type load; waits for the owner's answer on toxin types
   count, issue 239, default four), **TRAIT.13**, **TRAIT.14**, **TRAIT.15** with **SENSE.22** and **TRAIT.21** in
   animal layout 10, **UX.44** (plants darker when tougher), **TRAIT.16**, **SENSE.24**.
7. **WORLD.20** (the numpy core, stages WORLD.30 to WORLD.38) starts only after the gene chain (the gene freeze).

Unassigned: **WORLD.10** (diploid organisms). Owner-driven: **UX.34** (the Windows package and `run.ps1` check on a
real machine), **UX.40** extras (watch a headless run, compare runs, video, several runs) when the owner asks.

## Open owner questions (defaults in use)

- [#69](https://github.com/dwhagar/evolutionSimulator/issues/69): follow-up on reproduction and time answers (three short questions).
- [#222](https://github.com/dwhagar/evolutionSimulator/issues/222): video export format (default GIF and PNG sequence); the rest of the card is answered.
- [#239](https://github.com/dwhagar/evolutionSimulator/issues/239): how many toxin types (default four) and how resistance matches them (full, half, none on a ring).

Every other question is answered and its issue closed.

## The threads and where each stopped

Session ids are for `send_message`; a thread restarts from `origin/main` when given an item.

| Thread | Session | Did | Was doing | To resume |
| --- | --- | --- | --- | --- |
| TODO | `session_019H8Bssh8RESEgBRHpLDe2u` | TODO.md, CHANGELOG, decisions, roadmap, labels, owner questions | this handover | message it with new owner answers or merged work to record |
| Foundations 1 | `session_01EERrMFBPvUM1cVBaQ8ViUr` | reproduction and trait work (see the Done table), TRAIT.17 (balance audit, #261) | nothing in flight | TRAIT.22, then REPRO.10, REPRO.9, later TRAIT.15 |
| Foundations 2 | `session_016AaT5MFR4LkooNWTpHLVoN` | brain work (see the Done table), BRAIN.25 (#259) | nothing in flight | BRAIN.26 (refit: `python -m evolution_tools.fit_seed_brain --warm --robust 6 --max-cost 0.01 --seconds 0 --anneal 1200 --temperature 0.003`, several seeds in parallel with `OMP_NUM_THREADS=1`, then `--report-only` and `tests/test_fit_seed_brain.py`), then TRAIT.12 |
| Foundations 3 | `session_01Pt7T82bgc5AtorLhdnrGLn` | WORLD.15 (#237, #262), SENSE.13 (#248), world work (see the Done table) | nothing in flight | later WORLD.32/WORLD.34/WORLD.38 (numpy stages 3, 5a, 8) |
| Foundations 4 | `session_01LuttcqyVpi9rg72QYa91Q8` | save and history work, SENSE.20 (#217) | nothing in flight; WORLD.18 unstarted (no branch; scratch benchmark scripts not saved) | WORLD.18 now that founders breed; WORLD.37 (saves) later |
| Foundations 5 | `session_015sDAqSZdHdwQNZGuhAe6uB` | process host work, STORE.2 (#243), STORE.3 (#253) | nothing in flight | WORLD.36 (facade) and WORLD.37 (saves) when WORLD.20 starts; start from `persistence.dump_world` and `load_world_bytes` and the `checkpoints.world_format` and `encoding` columns (`docs/design/ux.md`, "As built: the SQLite run file") |
| Viewer 1 | `session_014Pwmw5FxGmXLTEGAsTct3c` | viewer work (see the Done table), UX.43 (#258) | nothing in flight | UX.44 when TRAIT.13 lands (`palette.plant_shades` is ready), UX.42 extras |
| Viewer 2 | `session_01FPqZutg9QMamfijqChfTZ4` | SPECIES.1 (#223), SPECIES.2 (#254) | nothing in flight | SPECIES.5, SPECIES.6 |
| Viewer 3 | `session_01QJQz4Wv5sWZYcbzB8ZwZQ2` | DNA.17, UX.16, UX.21, INFRA.10 (#244), UX.41 (#260) | nothing in flight | UX.34 follow-ups from the owner's Windows check |
| Viewer 4 | `session_01Mn2pgiHbtPqAPtTxvWinxr` | UX.17, UX.35, INFRA.7 (#233) | nothing in flight | known leftover: when a new run is built the old run is detached first, so a failed build leaves the old world unsaved in the viewer-side manager (UX.17) |
| Viewer 5 | `session_01JdKoj8HX9v7U3VqE9nRn2f` | viewer work (see the Done table) | finished earlier | free |
| Research 1 to 4 | `session_01AUv1wp36ogbXyLr5EafTUf`, `session_01WDUeYAQBKSN8g9EqgrvyEo`, `session_015SDqS4YMAzcmBKBAY4ycsr`, `session_01DvcFE1CWUtY4ogcVGtvrFt` | the first research notes | finished earlier; Research 3 was last marked "needs input", read its thread before reusing it | research only |
| Research 5 | `session_012cxmABPnLoujhe566bmyqS` | Python packages, the numpy core note (WORLD.19, #236, #240) | finished | amend `docs/design/numpy-core.md` only if the owner's answers change it |
| Research 6 | `session_013LQXeHzkRhoLji8pTMr7zB` | genetics report (DNA.16), colour note (TRAIT.20, #251) | finished | none |
| Coordinator | `session_01MEiU896iwwgarBf5TAXghc` | starts threads, relays the owner | | only it can start new threads |

## Things to know before restarting

- **Workflow per change:** `git fetch origin main`, branch from it, `ruff check .`, `ruff format --check .`,
  `pytest`, a pull request whose body has Before, After, How and the task IDs, labels named after the task IDs,
  squash merge. Builders merge as soon as it is clean (the owner's standing rule). The label scheme (colour by
  category, `needs-owner` red, `in-progress` blue) is in [labels.md](labels.md); `python -m evolution_tools.sync_labels --apply`
  creates labels for new task IDs.
- **All Python is under `src/`** (`src/evolution_simulator`, `src/evolution_tools`); `scripts/` holds only
  PowerShell and batch wrappers, one per tool (a test enforces both).
- **Every gene needs two balancers** (a link to another gene through an auxiliary trait, and a direct cost) and
  must pass the balance audit ([gene-balancers.md](design/gene-balancers.md)) before its layout bump merges.
- **Gene freeze for the numpy build:** while WORLD.30 to WORLD.38 are open, a change to a layout, a trait table, a
  derived quantity or a rules field is made in both engines in the same PR or waits. Positions stay 2-D.
- **Nothing is published except through GitHub**: the dependency tree is text in TODO.md.
- **Branches left in the repository** (not deleted, they hold no unmerged work): `claude/trait-4-traits-as-data`
  (very old) and `claude/project-thread-kpiv5p` (Foundations 1, reset to main). Delete them if the owner agrees.
- **Small known gaps:** the viewer-side `Run` of a hosted run is opened in write mode; a local viewer world saved
  late has no setup counts; the cosmetic merge fix is SPECIES.6; the one remaining cliff in the seed brain (the
  threat neuron's bias, about 1 founder in 80); `test_core_isolation` fails in this cloud container with or
  without changes (an environment difference).
