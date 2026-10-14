# Reproduction genes, recovery, plant lifespan and the cost of long life

Design note for `REPRO.7` (the reproduction genes, revised to the owner's answers), `TRAIT.6`
(longevity trades against reproduction), `TRAIT.7` (a recovery gene) and `TRAIT.8` (a plant lifespan
gene). Written 2026-10-14 by the Research 2 thread. The first version ([#49](https://github.com/dwhagar/evolutionSimulator/pull/49)) was
written before the owner answered [#36](https://github.com/dwhagar/evolutionSimulator/issues/36); this
revision replaces it in place and follows the answers logged in [decisions.md](../decisions.md).

The numbers are starting values to tune, not measurements of the running simulator. The small model in
[Does the trade-off work?](#does-the-trade-off-work) is a toy, with its assumptions stated.

> **Built (animals).** `REPRO.8` built everything for animals in this note on top of
> [#74](https://github.com/dwhagar/evolutionSimulator/pull/74): the four genes and the sex digit, `recovery`
> (`TRAIT.7`), pregnancies, absolute-day durations and per-hour charging, with the constants named as in the
> table at the end. Animal layout version 5 then (1,000 digits; version 7 and 1,004 digits after `SENSE.16` and `DNA.15`, which also made the litter size follow the `litter_capacity` cluster). Differences from the note: the pregnancy list is
> kept on the bearers, not in a separate world list; the protective effect of `parenting` and the "own young"
> channel wait for `SENSE.14`; a father who has died pays nothing and gives nothing at the birth; the
> costs of drive (wear, upkeep) follow the gene, while the threshold, boldness and brain input follow the
> sex-modified drive. The plant genes are `REPRO.3` and `TRAIT.8` (the seed genes are built, the longevity gene
> is not). See [dna-and-traits.md](dna-and-traits.md#reproduction-and-longevity) and the
> [long-run check](#long-run-check) below.

## Summary

- **Four reproduction genes plus the sex digit** (the owner's three, and parenting as its own gene, the
  default in [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) question 2):
  - `repro_drive`: how much the animal wants to mate. Sets the energy threshold for looking for a mate.
    Strong drive shortens life.
  - `repro_cooldown`: how often it can mate. A short cooldown costs standing upkeep.
  - `fertility`: how fertile it is, impregnating or becoming impregnated. It sets the chance a mating
    works, the litter size, how long gestation takes and what carrying a litter costs.
  - `parenting`: energy given to each child, and how closely the parent stays near and protects its
    young, at risk to itself.
- **The sex digit** is 0 or 1 by its value mod 2 (0 impregnates, 1 bears). The values 2 and 3 amplify or
  subdue the drive by 25% (the default for [#69](https://github.com/dwhagar/evolutionSimulator/issues/69)
  question 1). Mating needs one of each sex.
- **Who pays for a child** is decided by the parents' own `parenting` genes: each parent pays in
  proportion to its own gene, and the newborn starts with the mean of both. A low-parenting animal that
  mates with a high-parenting one pays less and its child still gets energy, so cheating is possible,
  which is the pattern the owner wants to see.
- **The first generation** starts with a large litter (fertility 0.75, six young) and no parenting.
- **Recovery** (`recovery`, `TRAIT.7`): how fast the body heals lost health and regains energy at rest.
- **Plant lifespan** (`longevity`, `TRAIT.8`): a plant lives one simulated month by default if nothing
  eats it, and the gene lets that evolve, traded against growth and seed output.
- **Longevity** (`TRAIT.6`) keeps its place in the same system: more repair makes every birth dearer and
  every gap longer, and the drive shortens life, so the two trade-offs the owner asked for share one
  lifespan.
- **Time**: durations are in simulated time (days), not shares of lifespan. The first version used
  shares of lifespan, which meant a longer life gave no extra births at all and so removed the reason to
  live longer. With absolute times, lifespan, drive and cooldown pull against each other as intended.
- The animal layout changes (fertility rewritten, four more genes, so version 3 or later) and the plant
  layout gains three genes.

## What the owner decided

| Words | Where | In this design |
| --- | --- | --- |
| Three genes besides sex: desire, cooldown, fertility | [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) 7, [#17](https://github.com/dwhagar/evolutionSimulator/issues/17) | `repro_drive`, `repro_cooldown`, `fertility` |
| Strong drive / shorter life against weak drive / longer life | 7 | Wear rate rises with drive ([Drive](#drive-repro_drive)) |
| More offspring, longer gestation against fewer, shorter | 7 | Litter size and gestation both rise with `fertility` |
| Easy reproduction / more energy against less easily / less energy | 7 | Conception chance and fertility upkeep both rise with `fertility` |
| No parenting, no danger against stays near and protects, in danger | 7 | `parenting` gene |
| Caregiving genes decide who pays; see if a pattern emerges | 9 | Each parent pays by its own `parenting` gene |
| Litter size is genetic; start with a large litter and no parenting | 11 | `fertility` start 0.75, `parenting` start 0 |
| Sex digit 0 or 1; 2 and 3 amplify or subdue the mating drive by a fraction | 2 | Mod 2 is the sex; 2 is +25%, 3 is -25% |
| Much longer lifespans, longer tick, a gene for recoup and recovery | 8 | [Time](#units-and-time), `recovery` |
| Plant lifespan genetic, default a month, evolves | 10 | `longevity` |

## What exists today

**Update.** `REPRO.5` and `TRAIT.6` were built from the first version of this note
([#74](https://github.com/dwhagar/evolutionSimulator/pull/74)) before this revision merged. Animal layout
version 3 already has `caregiving`, `repro_interval` and `repro_drive` (3 digits each, body 70 digits),
`AnimalTraits.give_birth` (both parents pay, or nobody does), the repair surcharge, stretch and `0.20 s^2`
upkeep, and the drive threshold and `Temperament` field. The table below is the state before #74; the
[delta to build](#delta-from-the-code-after-74) says what is left.

| Thing | Where | Current behaviour |
| --- | --- | --- |
| `fertility` | `layouts.py` (4 digits) | Decoded, never read |
| Mating cost and cooldown | `AnimalTraits.consume_mating_cost` | 25% of max energy for `sex_strategy` 0 and 1, 45% for 2 and 3; cooldown 40 or 100 ticks; energy floored at zero |
| Who may mate | `World._mate` | Any two willing animals; one child per pair at once; the energy guard is `WorldConfig.min_mating_energy_ratio` (0.5) |
| Wants to mate | `_update_needs_and_drives` | energy ratio at least `0.35 + 0.35 * vitality`, cooldown over, not afraid |
| Repair | `AnimalTraits` | cost `0.12 * somatic_maint` per tick; wear `0.075 / (1 + 3.5 * somatic_maint)` per tick |
| Sleep | `SleepRules` | `energy_regain` 0.002 of the store per tick of sleep, metabolism 0.4 |
| Passive healing | `AnimalTraits.feed` | when above 80% energy, up to 4 health per feeding, at 0.5 energy per point |
| Seeds | `PlantTraits.consume_reproduction_cost` | 35% of biomass, fixed; no plant ageing |
| Time | `TimeScale` | `seconds_per_tick` only changes the clock; costs are charged per tick |

## The genes (animals)

All gene values are 0 to 1, read by the existing `TraitDef` mechanism. Three digits (64 levels) each.

| Gene | Trait | Range | Scale | Meaning |
| --- | --- | --- | --- | --- |
| `repro_drive` | `drive` | 0 to 1 | linear | Desire to mate |
| `repro_cooldown` | `cooldown_days` | 2 to 90 days | log | Gap between matings |
| `fertility` | `fertility` | 0 to 1, then derived (below) | linear | Fertility of either sex |
| `parenting` | `care_fraction` | 0.10 to 0.80 | linear | Newborn energy as a share of its own max energy; also how closely the parent stays near and protects |
| `recovery` | `recovery` | 0 to 1, then derived | linear | Healing and energy regain ([Recovery](#recovery-recovery)) |
| `sex_strategy` | `sex`, `drive_modifier` | digit 0 to 3 | category | `sex = digit % 2`; digit 2 is +25% drive, 3 is -25% |

Counted from the layout after #74 (70 digits before the brain): `caregiving` becomes `parenting`,
`repro_interval` becomes `repro_cooldown`, `repro_drive` stays, and `fertility` (3 digits) and
`recovery` (3 digits) are added, so the digits before the brain become 76 and `sex_strategy` and the
brain block move along by 6. `ANIMAL_LAYOUT.version` goes to 5 (Foundations 2 takes 4 for the brain; use the next free number if that changes). The sex digit keeps its single digit.

### Drive (`repro_drive`)

- **Effective drive** is `clamp(drive * (1 + 0.25 if digit == 2, 1 - 0.25 if digit == 3, else 1), 0, 1)`.
- **Threshold.** The animal looks for a mate once its energy ratio is at least
  `clamp(0.85 - 0.5 * effective_drive - 0.2 * (1 - vitality), 0.10, 0.95)`. At drive 0 a healthy animal
  needs 85% of its energy; at 1 it needs 35%. This replaces `0.35 + 0.35 * vitality` and
  `WorldConfig.min_mating_energy_ratio`.
- **Boldness.** While a mate is in view, `effective_fear` is multiplied by `1 - 0.3 * effective_drive`.
- **Brain.** `Temperament` gets a `repro_drive` field that bends the `mate_closeness` input with the
  usual factor (0.4 to 1.6, 0.5 neutral). A cooldown or pregnancy makes it 0.
- **Costs (strong drive, shorter life).** Wear per tick is multiplied by `1 + 0.6 * drive`, so drive 1
  cuts expected life to 62% of drive 0. Plus upkeep `0.05 * drive ** 2`.
- A low-drive animal waits for a full belly before looking; a high-drive one reproduces sooner and in
  leaner times, which only pays off where mates are scarce ([toy results](#does-the-trade-off-work)).

### Cooldown (`repro_cooldown`)

- After a mating the animal cannot mate again for `cooldown_days * (1 + 1.0 * somatic_maint)` of
  simulated time. A bearer's cooldown starts at the birth, so her gap is gestation plus cooldown.
- The cost of a short cooldown is standing upkeep for staying ready: `0.03 * (5 / cooldown_days) ** 0.5`
  per tick, 0.047 at 2 days, 0.03 at 5, 0.007 at 90, against a basal metabolism around 0.5.
- **Behaviour.** While the cooldown or a pregnancy runs the animal does not seek a mate or mating-call
  (the existing `ready_to_mate` input is 0), so it spends the time feeding and recovering.
- An animal first becomes able to mate at 6% of its expected lifespan (a fixed share, not a gene), so
  bigger, longer-lived animals mature later, as in nature.

### Fertility (`fertility`)

Both sexes carry the gene. For a mating between an impregnating animal `i` and a bearing animal `b`:

| What | Formula | Range |
| --- | --- | --- |
| Chance the mating takes | `0.30 + 0.60 * (f_i + f_b) / 2` | 0.30 to 0.90 |
| Litter size (bearer's gene) | `1 + round(f_b * 7)` | 1 to 8 |
| Gestation (bearer's gene) | `2 + 18 * f_b` days | 2 to 20 days |
| Upkeep, either sex | `0.04 * f ** 2` per tick | up to 0.04 |
| Carrying a litter (bearer, during gestation) | extra upkeep `0.5 * basal * litter / 8`; speed times `1 - 0.3 * litter / 8` | |

- A failed mating still costs the **mating effort**, 3% of max energy for each (replacing the old 25% and
  45%). The real cost is paid at birth.
- **Behaviour.** A pregnant bearer is slower, hungrier and (through the existing hunger rule) forages
  more; a heavy litter makes this stronger. This is how fertility reaches behaviour.
- The trade-offs: easy to reproduce costs energy (chance and upkeep rise together), and more young
  means a longer gestation, which lengthens the bearer's gap.

### Parenting (`parenting`)

- `care_fraction = 0.10 + 0.70 * parenting`. At birth each young starts with
  `mean(care_fraction_a, care_fraction_b) * max_energy(young)`.
- **Who pays.** Each parent pays `litter * care_fraction_own / 2 * max_energy(young) *
  (1 + 2.0 * somatic_maint)`. A parent with a high gene pays more; one with a low gene pays less. If
  either cannot afford it, the birth waits (this is the `TRAIT.5` guard).
- **Survival** comes from the energy rules: a newborn lasts about `start_energy / basal_metabolism`
  ticks before it must eat, so low parenting means many young that often starve, and high parenting
  means few well-provisioned ones.
- **Staying near and protecting.** Young depend on their parent for `parenting * 6%` of the parent's
  lifespan after birth. While they are dependent and close:
  - the parent sees them through a new sense channel, "own young" (direction and closeness), the
    optional input already listed as `SENSE.14`; `Temperament.parenting` bends its closeness by the usual
    0.4 to 1.6, so high-parenting animals are drawn to their young;
  - a threat near the young is treated as dangerous to them: aggression is multiplied by
    `1 + 0.5 * parenting` and fear by `1 - 0.4 * parenting`, which makes the parent fight instead of
    flee and so puts itself in danger. Low-parenting animals ignore the young and keep their normal fear.
- Until `SENSE.14` provides the percept, parenting acts through energy only.
- **First generation:** `parenting = 0` (care fraction 0.10, no protection), `fertility = 0.75`.

### Longevity trades against reproduction (`TRAIT.6`)

The owner's choice is mainly #16 option C (longevity against reproduction), with a hint of option B.
It lives alongside the owner's strong drive against short life:

- **Main mechanism (disposable soma).** Repair and breeding draw on one energy supply:
  - cost per birth to each parent is multiplied by `1 + 2.0 * somatic_maint` (full repair triples it);
  - the cooldown is stretched by `1 + 1.0 * somatic_maint` (full repair doubles it).
  The newborn still receives the unsurcharged amount.
- **Hint of option B.** Repair upkeep becomes `0.20 * somatic_maint ** 2` (was `0.12 * somatic_maint`):
  cheaper below about 0.6, dearer above, so it grows faster than the benefit at the top.
- **Drive** adds to the same budget: a high drive shortens life as in [Drive](#drive-repro_drive), so a
  short-lived animal is not simply a low-repair one.

### Recovery (`recovery`)

`TRAIT.7`: the owner asked for a gene for how well the body recoups and recovers energy and health. It is
**different from `somatic_maint`**: repair slows wear (slow ageing, which cannot be undone), recovery
heals acute damage and refills energy.

- **Healing.** Lost health heals with a half-life of `20 * (1 / 20) ** recovery` days, 20 days at 0 and 1
  day at 1 (log scale). It only heals while the energy ratio is at least 0.5, and each point healed
  costs 0.5 energy (as now). This replaces the "4 health per feeding above 80%" rule.
- **Energy regain at rest.** `SleepRules.energy_regain` is multiplied by `0.5 + 1.5 * recovery`, 0.5 to 2.
- **Cost.** Upkeep `0.10 * recovery ** 2` per tick. A fast healer burns more even when healthy.
- **Not covered:** accumulated wear (ageing) is not healed.
- Behaviour: a quick healer can afford more risks; it reaches the brain through the existing
  `health_ratio` and `energy_ratio` inputs, with no change to the brain.

## Units and time

The owner chose option C of #36 question 8: much longer lifespans in simulated time, with a longer
tick. The defaults in [#69](https://github.com/dwhagar/evolutionSimulator/issues/69) question 3 are one
simulated year of life and a tick of about an hour, so a life is roughly 8,800 ticks and a plant's
month roughly 730.

- **Reference tick.** Every per-tick rate in this note and in `traits.py` is "per reference tick",
  `REFERENCE_TICK_SECONDS = 3600`. The world multiplies each by `dt = seconds_per_tick / 3600`, so a
  one-second tick still works, just slowly (`WORLD.7`). Durations in days are converted to ticks with
  `ceil(days * 86400 / seconds_per_tick)`.
- **Calibration.** With the wear changed from 0.075 to `WEAR_BASE = 0.0362` per reference tick, an
  animal with size 0.5, repair 0.5 and drive 0.5 lives 8,765 ticks, about a simulated year. Across the
  range of genes lifespan runs from 2,762 ticks (115 days: size 0, no repair, no drive) to 24,862
  (2.8 years: size 1, full repair, no drive), and a full-drive animal lives 62% as long as a no-drive
  one.
- **Why absolute times.** The first version of this note stored cooldown and gestation as shares of
  lifespan. That made the number of matings per lifetime independent of lifespan, so living longer
  earned no extra young and the drive-against-longevity trade-off the owner asked for had nothing on
  the other side of the scale. In days, a long life means more cycles.
- The brain keeps deciding on its own interval (`BRAIN.11`); ageing, metabolism and reproduction are
  summed over the tick.

## Plants (REPRO.3 and TRAIT.8)

Plants are asexual, mutate slower (a `DNA.8` setting) and have no brain, so no drive and no sex.

| Gene (3 digits) | Trait | Range | Meaning |
| --- | --- | --- | --- |
| `longevity` | `lifespan_days` | 7 to 365 days, log | `TRAIT.8`: age at which an uneaten plant dies |
| `seed_provision` | `seed_fraction` | 0.05 to 0.50 | Energy per seed as a share of the seed's own max biomass (`seed_clutch` still caps the count) |
| `seeding_interval` | `seeding_days` | 2 to 60 days, log | Gap between seed bursts (the "ready to seed" trigger at 85% stays) |

- **Default lifespan:** one simulated month, 30.4 days, which is `longevity = 0.371` on that scale. Plants
  die when their age reaches the lifespan, or earlier from damage or starvation. A plant first seeds at
  6% of its lifespan.
- **Trade-offs (so it does not run to the maximum).** Growth rate is multiplied by `1 - 0.3 * g` and the
  share of biomass available for seeds is `0.35 * (1 - 0.4 * g)` where `g` is the gene value: a long-lived
  perennial grows slower and seeds less, a short-lived annual grows fast and seeds heavily. Crowding
  adds the usual pressure from the world (shade, roots).
- **Seed count** is what the budget can pay for: `min(seed_clutch, budget / (seed_fraction * max_biomass))`.
- **The earlier notes said plants live longer.** With the owner's numbers plants default to a month and
  animals to a year, so plants now start short-lived; the lifespan gene lets them evolve longer. The
  TODO text for `REPRO.3` ("live longer") needs updating; see question 12.

## Does the trade-off work?

A toy, not the simulator: a mid-size animal (size 0.5, tick one hour), constant food intake per tick,
the formulas above, newborn survival `1 - exp(-care_fraction / 0.15)`, and a count of surviving young
(half of them credited to this parent). The number of matings is the smaller of what its time and what
its energy allow. There is no crowding, so food does not get scarcer as young pile up.

| Gene varied | Values and surviving young | What it shows |
| --- | --- | --- |
| Parenting 0, .2, .4, .6, .8, 1 | 9.0, 14.7, 17.0, 14.0, 11.3, 9.4 (intake 1.0); 9.0, 7.9, 5.8, 4.5, 3.6, 3.0 (intake 0.75) | Interior optimum (about 0.4) when food is plentiful; none at all pays best when it is scarce |
| Repair 0, .2, .4, .6, .8, 1 (parenting 0.3) | 7.0, 11.0, 14.5, 17.6, 17.6, 13.7 (intake 1.0); 6.8, 8.0, 7.5, 5.6, 2.5, 0.0 (intake 0.75) | Interior optimum that moves down as food gets scarce |
| Drive 0, .25, .5, .75, 1, mates common (wait 100 ticks) | 12.3, 11.0, 10.0, 9.2, 8.6 | Low drive wins |
| Drive, mates scarce (wait 600 ticks) | 8.1, 7.8, 7.8, 8.0, 8.6 | High drive wins slightly |
| Fertility 0, .25, .5, .75, 1 | 0.9, 3.4, 6.7, 9.0, 13.0 (intake 1.0); same up to .75, then 9.7 at 1 (intake 0.75) | Rises to the top when food is plentiful, bends over when it is not |
| Cooldown gene 0, .25, .5, .75, 1 (2 to 90 days) | 15.2, 12.7, 9.0, 5.1, 2.4 (intake 1.0); 8.4, 10.1, 9.0, 5.1, 2.4 (intake 0.75) | Shortest wins when food is plentiful; an interior optimum appears when it is scarce |

What this says: parenting, repair and cooldown have optima that move with food, and drive's best value
depends on how hard mates are to find, which is the point of making them genes. Fertility and
cooldown run to an end when food is plentiful because the toy has no crowding; in the world, many young
share the same food, which is what must stop them. This is the main risk of the design and needs
a check once births work: run many generations and see where `fertility`, `repro_cooldown` and
`parenting` settle. If they pile up at an end, raise `GESTATION_UPKEEP`, `FERTILITY_UPKEEP` or the
mating effort. The repair birth surcharge (2.0) and cooldown stretch (1.0) were chosen from a small grid, because
the first values (1.0 and 0.5) let full repair win whenever food was plentiful.

## Delta from the code after #74

| Built in #74 | Change to the revised design |
| --- | --- |
| `caregiving` (newborn energy share 0.10 to 0.80) | Rename to `parenting`; same range; later adds the protection behaviour |
| `repro_interval`, a log share of lifespan (0.01 to 0.25) | Becomes `repro_cooldown` in simulated days (2 to 90, log); the juvenile period becomes 6% of lifespan (was one interval) |
| `repro_drive`, threshold and `Temperament` field | Keep; add the wear multiplier, the sex-digit modifier and the 0 factor in a cooldown or pregnancy |
| `give_birth`: one child per pair, paid at once | Conception chance, litter, pregnancy list in the world, each parent paying `litter * care_fraction_own / 2` |
| `REPAIR_BIRTH_SURCHARGE` 1.0, stretch 0.5 (share-of-lifespan interval) | 2.0 and 1.0, applied to the cooldown in days |
| Wear `0.075` per tick, charged per tick | `WEAR_BASE` 0.0362 per reference tick, charged by `dt` (`WORLD.7`) |
| `fertility` removed | Reinstated with a job (above); `recovery` added |
| `sex_strategy` costs and cooldowns of the prototype | Mod 2 is the sex, 2 and 3 modify the drive |

## What to build

One builder should take the delta above (the rest of `REPRO.7`'s genes, `TRAIT.7` and `WORLD.7`'s
per-second charging) together, because they change the same functions and the same layout version. The
list is written against the code after #74. Plant work (`REPRO.3`, `TRAIT.8`) can follow as a second
change.

1. `layouts.py` (animals): rename `caregiving` to `parenting` and `repro_interval` to `repro_cooldown`,
   add `fertility` and `recovery` (3 digits each), bump `ANIMAL_LAYOUT.version` to 5 (4 is taken by the brain work); set the first
   generation's values (`fertility` 0.75, `parenting` 0, the rest 0.5) with `DNA.replaced` or the
   world's seeding code.
2. `trait_defs.py`: the traits in the tables above; `sex_strategy` yields `sex` (mod 2) and
   `drive_modifier`.
3. `traits.py`:
   - `lifespan_ticks`, cooldown ticks, gestation ticks, litter size, conception chance, care fraction;
   - the drive threshold and boldness; wear and upkeep terms (drive, cooldown, fertility, repair,
     recovery); `WEAR_BASE` 0.0362;
   - replace `consume_mating_cost` with a mating step (effort, conception check, begin pregnancy) and
     a birth step that checks both parents can pay before taking anything and returns the newborns'
     starting energy;
   - healing by half-life; scale `SleepRules.energy_regain` by recovery.
4. `world/world.py`: `_mate` pairs one of each sex (the rule stays in one function, with `REPRO.4`'s
   closeness preference); a pregnancy list (bearer, litter, due tick); births at the due tick, placing the
   litter near the bearer; `dt`-scaled charging.
5. `brain_adapter.py`: `Temperament.repro_drive` bending `mate_closeness`; `Temperament.parenting` and
   the "own young" channel when `SENSE.14` lands.
6. Plants (second change): three plant genes, plant ageing, the seed budget, plant layout version bump.
7. Tests: care fraction and who pays; neither parent charged if one cannot pay; litter size and gestation
   from the bearer; pregnancy blocks mating; cooldown scales with repair; drive shortens lifespan by
   the stated factor; healing half-life; a plant dies at its lifespan; same seed gives the same births;
   and a long run that checks no reproduction gene has piled up at an end.
8. Constants go in the `TRAIT.3` config object, with the names below.

## Constants for the TRAIT.3 config

| Name | Value | Used in |
| --- | --- | --- |
| `REFERENCE_TICK_SECONDS` | 3600 | converting per-tick rates |
| `WEAR_BASE` | 0.0362 | wear per reference tick (was 0.075) |
| `DRIVE_WEAR` | 0.6 | wear times `1 + 0.6 * drive` |
| `DRIVE_UPKEEP` | 0.05, exponent 2 | basal metabolism |
| `DRIVE_THRESHOLD` | 0.85, slope 0.5, vitality weight 0.2, clamp 0.10 to 0.95 | when to look for a mate |
| `DRIVE_BOLDNESS` | 0.3 | fear modifier with a mate in view |
| `SEX_DRIVE_MODIFIER` | +0.25 (digit 2), -0.25 (digit 3) | effective drive |
| `COOLDOWN_DAYS` | 2 to 90, log | cooldown trait |
| `READINESS_UPKEEP` | 0.03, reference 5 days, exponent 0.5 | basal metabolism |
| `MATURITY_SHARE` | 0.06 of lifespan | first mating, first seeding |
| `FERTILITY_CONCEPTION` | 0.30 + 0.60 * mean fertility | whether a mating takes |
| `LITTER_MAX` | 8 | litter size |
| `GESTATION_DAYS` | 2 + 18 * fertility | gestation |
| `FERTILITY_UPKEEP` | 0.04, exponent 2 | basal metabolism |
| `GESTATION_UPKEEP` | 0.5 of basal times litter / 8 | bearer during gestation |
| `GESTATION_SLOWING` | 0.3 times litter / 8 | speed |
| `MATING_EFFORT` | 0.03 of max energy | each parent per mating |
| `CARE_FRACTION_RANGE` | 0.10 to 0.80 | newborn energy and cost per young |
| `DEPENDENCY_SHARE` | 0.06 of lifespan times parenting | how long young depend on the parent |
| `PARENT_PROTECTION` | aggression +0.5, fear -0.4 times parenting | near dependent young |
| `REPAIR_COST` | 0.20, exponent 2 | basal metabolism |
| `REPAIR_BIRTH_SURCHARGE` | 2.0 | cost per birth |
| `REPAIR_COOLDOWN_STRETCH` | 1.0 | cooldown |
| `HEAL_HALFLIFE_DAYS` | 20 down to 1, log | healing |
| `HEAL_ENERGY_COST` | 0.5 per health point; needs energy ratio at least 0.5 | healing |
| `RECOVERY_REGAIN` | 0.5 to 2 times `SleepRules.energy_regain` | sleep and rest |
| `RECOVERY_UPKEEP` | 0.10, exponent 2 | basal metabolism |
| `PLANT_LIFESPAN_DAYS` | 7 to 365, log; default 30.4 | `longevity` |
| `PLANT_LONGEVITY_GROWTH` | growth times `1 - 0.3 * g` | plant growth |
| `PLANT_LONGEVITY_SEEDS` | seed budget `0.35 * (1 - 0.4 * g)` | seeds |
| `SEED_FRACTION_RANGE` | 0.05 to 0.50 | `seed_provision` |
| `SEEDING_DAYS` | 2 to 60, log | `seeding_interval` |

## Long-run check

`scripts/reproduction_check.py` (`REPRO.8`) runs the real `AnimalTraits` (upkeep, wear, healing, matings,
pregnancies and paid births, one hour per tick) in a chemostat: 80 founders, a fixed 45 biomass per tick
shared by everyone alive (3 at most each), a 5% chance per tick that a willing pair meets, a 0.2% chance
per tick of an injury of 5 to 40 health, and a newborn that cannot eat for its first 18 hours. It has no
space, plants or brains. The world cannot yet host this check: random founders still starve before they
breed (`BRAIN.9`) and the plants' soil is not tuned, so a full-world run waits for that. A gene "piles up at
an end" when its population mean over the last fifth of the run is within 0.08 of 0 or 1.

Three runs of 60,000 ticks (about 7 years), founders at the levels in `FOUNDER_LEVELS`:

| Run | `fertility` | `repro_cooldown` | `repro_drive` | `recovery` | `parenting` | `somatic_maint` | Population |
|---|---|---|---|---|---|---|---|
| seed 1, defaults | 0.75 to 0.23 | 0.51 | 0.52 | 0.51 to 0.26 | 0.00 to 0.04 | 0.48 to 0.05 | 129 |
| seed 2, defaults | 0.75 to 0.44 | 0.51 to 0.58 | 0.51 | 0.51 to 0.26 | 0.00 to 0.01 | 0.44 to 0.10 | 163 |
| seed 1, injury 0.01, newborn fast 30 h | 0.75 to 0.22 | 0.51 | 0.52 | 0.51 | 0.00 to 0.01 | 0.48 to 0.22 | 95 |

What it shows:

- **The main risk did not happen.** `fertility` and a short `repro_cooldown` do not run to the top. Crowding
  makes each extra young animal cost the others food, so fertility falls (to 0.2 to 0.45) and the cooldown
  stays in the middle or drifts longer. The toy model's runaway needed a world without crowding.
- **`somatic_maint` falls, then holds** at 0.05 to 0.2, where its upkeep (0.20 times the square) balances
  the wear it removes. Heavy injury keeps it higher (0.22).
- **`repro_drive` stays near the middle.** With no real mate scarcity its wear and upkeep cancel against
  the matings it buys.
- **`recovery` drifts down to about 0.26** when injuries are mild (it costs 0.10 times the square in
  upkeep) and holds at 0.51 when they are frequent (0.01 per tick). It is not at an end in either case.
- **`parenting` stays at the bottom (the script reports it as "at an end")** and is the one open item.
  Founders start at 0, and the chemostat gives a newborn little to lose: it has a short fast and no
  predators, no cold, no distance to cover. Without that cost to lack of parental energy, the gene has
  nothing to pay for. The design starts parenting at 0 on purpose, so that evolution has to find the
  benefit. This check cannot show whether it does; it needs predation, newborn vulnerability and the
  parent staying near its young (`SENSE.14`).

### Re-check after the clusters (`DNA.15`)

`DNA.15` regrouped the genes, so the genome is read in a different order and crossover keeps the
reproduction genes more closely linked. Four runs of 36,000 ticks on the clustered layout (before `SENSE.16`'s acuity gene and seeded senses, which the chemostat does not use), and two on the unclustered layout
with the same seeds for comparison (the seeds give different founders on the two layouts, so only the pattern
compares). `litter_capacity` also makes the litter follow body size and recovery now.

| Layout and seed | `fertility` | `repro_cooldown` | `repro_drive` | `recovery` | `parenting` | `somatic_maint` | Population |
|---|---|---|---|---|---|---|---|
| clustered, seed 1 | 0.75 to 0.57 | 0.51 to 0.59 | 0.52 | 0.51 to 0.26 | 0.01 | 0.48 to 0.09 | 114 |
| clustered, seed 2 | 0.75 to 0.70 | 0.51 to 0.52 | 0.51 to **0.04** | 0.51 to 0.25 | 0.01 | 0.44 to 0.22 | 168 |
| clustered, seed 3 | 0.75 to 0.55 | 0.51 | 0.47 | 0.51 to 0.28 | 0.01 | 0.38 | 119 |
| clustered, seed 4 | 0.75 to 0.58 | 0.51 to 0.59 | 0.55 | 0.51 to **0.02** | 0.01 | 0.16 | 178 |
| unclustered, seed 3 | 0.75 to 0.60 | 0.53 | 0.51 to 0.29 | 0.51 | 0.02 | 0.13 | 131 |
| unclustered, seed 4 | 0.75 to 0.24 | 0.52 | 0.52 | 0.51 to 0.24 | 0.01 | 0.17 | 149 |

The pattern holds: `fertility` and `repro_cooldown` stay clear of the ends in every run. What changes from
run to run is which of the two genes that are only a cost here, `repro_drive` and `recovery`, drifts down, and
how far. In two of the four new runs one of them reached the bottom (`repro_drive` in seed 2 within about 6,000
ticks, `recovery` in seed 4), where the old layout only got as far as 0.29 and 0.24 in its two runs. That fits
selection on one gene dragging its neighbours along when they are inherited together, but six runs do not prove
it. In the chemostat both genes are only a cost (upkeep and wear for the drive, upkeep for healing), because
a meeting happens at a fixed chance whatever the drive, and injuries are rare. In the world, mate scarcity and
real injury should pay for them; this is the first thing to read when the check can run there. If it still
happens, the first remedy is to leave the clusters as tags (as built) and not set `cluster_units`, and the
second is a floor on the gene's cost.

So the result is: nothing runs to the top, and the one gene at the bottom is there because the chemostat
only stands in for the pressures that should hold it up. Repeat the check in the world once populations
survive, and read `parenting`, `recovery` and `repro_drive` first. To explore, change the pressures:
`python scripts/reproduction_check.py [ticks] [seed] [injury_chance] [newborn_fast_ticks]`.

## Questions for the owner

Raised as a comment on [#69](https://github.com/dwhagar/evolutionSimulator/issues/69), numbered 4 to 6
after its three. Each has a default this note assumes.

4. **Plant lifespan against animal lifespan.** With a month for plants and a year for animals, plants now
   start shorter-lived than animals, where an earlier answer said plants should live longer. Keep the
   month and let plants evolve longer? Default: yes.
5. **After birth.** Parenting here is energy at birth plus staying near and protecting. Should parents
   also feed their young afterwards (needs a "give food" action in the brain)? Default: no, later.
6. **Pregnancy.** The bearer carries the litter for the gestation time, is slower and hungrier, and cannot
   mate again until birth plus cooldown. Right? Default: yes.
