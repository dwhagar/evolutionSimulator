# Reproduction genes and the cost of long life

Design note for `REPRO.5` (replace `fertility` with three reproduction genes) and `TRAIT.6` (longevity
trades against reproduction). Written 2026-10-14 by the Research 2 thread. It builds on the owner's
answers in [#16](https://github.com/dwhagar/evolutionSimulator/issues/16) and
[#17](https://github.com/dwhagar/evolutionSimulator/issues/17) (logged in [decisions.md](../decisions.md)).

The numbers below are starting values to be tuned, not measurements of the real simulator, which has no
world yet. The two small calculations in [Does the trade-off work?](#does-the-trade-off-work) were run as
a toy model, with the model stated.

## Summary

- `fertility` is removed. Three genes replace it, in two tiers:
  - **Tier 1, capacity (energy and time):** `caregiving` (energy put into each offspring) and
    `repro_interval` (the shortest gap between births, as a share of the animal's lifespan).
  - **Tier 2, motivation (behaviour):** `repro_drive` (how strongly the animal wants to reproduce).
- All three also reach behaviour, each for its own reason: caregiving through protective behaviour
  around young, the interval through the "not ready" gate on all mating behaviour, and the drive through
  when and how boldly the animal looks for a mate. The brain gets all three as inputs
  ([BRAIN.14](../../TODO.md)).
- Offspring survival is not a separate number. A newborn starts with the energy its parents gave it, so
  it lives or starves according to the same energy rules as everyone else.
- Longevity (`somatic_maint`) pays for itself by competing with reproduction: more repair means a more
  expensive birth and a longer gap between births (the disposable-soma trade-off), plus an upkeep cost
  that grows faster than the benefit.
- Every time is a **share of the animal's own lifespan**, so none of it depends on how long a tick is.
  That matters because of a problem with the fastest time scales, raised as question 2 below.
- The layout changes (version 3), so saved animal genomes stop loading. The brain gains 2 inputs.

## What exists today

| Thing | Where | Current behaviour |
| --- | --- | --- |
| `fertility` | `layouts.py` (gene 56 to 59) | Decoded, never read: it drifts neutrally ([#17](https://github.com/dwhagar/evolutionSimulator/issues/17)) |
| Mating cost | `AnimalTraits.consume_mating_cost` | 25% of max energy for `sex_strategy` 0 and 1, 45% for 2 and 3; no check that the energy is there |
| Cooldown | same | 40 ticks (types 0, 1) or 100 ticks (types 2, 3), regardless of body size or lifespan |
| Wants to mate | `_update_needs_and_drives` | energy ratio at least `0.35 + 0.35 * vitality`, cooldown over, not afraid |
| Repair cost | `AnimalTraits.__init__` | `0.12 * somatic_maint` per tick, in basal metabolism |
| Wear | `update_metabolism_and_aging` | `0.075 / (1 + 3.5 * somatic_maint)` per tick; death when accumulated damage reaches `max_damage_capacity` (`100 * (1 + size)`) |
| Seeds | `PlantTraits.consume_reproduction_cost` | 35% of current biomass, fixed |

Lifespan is `max_damage_capacity / wear` ticks. Computed from the formulas above: 1,333 ticks (size 0,
no repair) up to 12,000 ticks (size 1, full repair), which at one second per tick is 22 minutes to 3.3
hours of simulated time. The fixed cooldowns of 40 and 100 ticks are 0.8% to 2% of a mid-size animal's
lifespan, and are the same for a short-lived small animal and a long-lived large one.

## The genes (animals)

All gene values are 0 to 1, read by the existing `TraitDef` mechanism. Width is a suggestion:
three digits gives 64 levels, about 1.6% per step, plenty for a trait with this little detail, and fewer
digits means fewer neutral places for mutations to land.

| Gene | Width | Trait | Range | Scale | Meaning |
| --- | --- | --- | --- | --- | --- |
| `caregiving` | 3 digits | `care_fraction` | 0.10 to 0.80 | linear | Newborn's starting energy as a share of the newborn's own `max_energy` |
| `repro_interval` | 3 digits | `interval_fraction` | 0.01 to 0.25 | log | Minimum gap between births as a share of the animal's expected lifespan |
| `repro_drive` | 3 digits | `repro_drive` | 0 to 1 | linear | Strength of the urge to find a mate and reproduce |

`fertility` (4 digits) goes. Net change: the 65 digits before the brain become 70 (4 removed, 9
added), so `sex_strategy` and the brain block move along by five. `ANIMAL_LAYOUT.version` goes to 3.

### Caregiving: energy per offspring (tier 1)

- A newborn starts with `care_fraction * max_energy(newborn)`. The old fixed start was
  `0.75 * max_energy`, which is the middle of the range.
- With two parents, the newborn's start is the mean of both parents' `care_fraction`, and each parent
  pays half of it (`care_fraction_i / 2 * max_energy(newborn)`, times the repair surcharge below). This
  keeps the cost shared by genes rather than by sex type, so it works whether or not sex types stay
  ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 2).
- Survival comes from the energy rules: a newborn lasts about `start_energy / basal_metabolism` ticks
  before it must eat. Low caregiving means many cheap births but the young often starve before their
  first meal; high caregiving means few expensive ones that nearly all survive. This is the Smith and
  Fretwell offspring size against number trade-off from the
  [traits research](../research/basic-traits.md#35-reproduction-and-life-history), with no survival
  curve written in by hand.
- One offspring per birth to begin with. Litter size can come later as the number the parent's
  spare energy can pay for.
- **Behaviour:** an animal with dependent young nearby is more protective: aggression times
  `1 + 0.5 * care_fraction_norm`, fear times `1 - 0.4 * care_fraction_norm`, where `care_fraction_norm`
  is the gene value 0 to 1. This needs "young nearby" from the senses, so it waits for `SENSE.1`;
  until then the modifier is zero. The gene value is also a brain input.

### Interval: a limit on how often (tier 1)

- After a birth, the animal cannot reproduce for `interval_fraction * lifespan_ticks`, where
  `lifespan_ticks = max_damage_capacity / wear_per_tick`. The first birth is allowed once the animal
  reaches the same age (the same gene sets the juvenile period, so there is no extra gene).
- With the ranges above, a mid-size animal (expected lifespan about 4,800 ticks) can breed as often as
  every 48 ticks or as rarely as every 1,200. The old fixed 40 and 100 ticks sit at the short end.
- The cost of a short interval is a standing upkeep for staying ready (gonads, milk, hormones):
  `0.03 * (0.05 / interval_fraction) ** 0.5` energy per tick. That is 0.067 at 0.01, 0.030 at 0.05 and
  0.013 at 0.25, against a basal metabolism around 0.5 for a mid-size animal.
- A short interval also means more births from the same body, each paying the full cost, so a fast
  breeder is limited by its food supply, not by the gene.
- **Behaviour:** while the cooldown runs, the animal does not seek a mate, does not mating-call, and
  the brain sees `ready_to_mate = 0` (already an input) plus the time left as a share of the interval.

### Drive: the urge to reproduce (tier 2)

- The drive does not change what a birth costs or how long the gap is. It changes **when the animal
  tries and how much it risks to do it**:
  - Energy threshold to start looking: `threshold = clamp(0.85 - 0.5 * drive - 0.2 * (1 - vitality),
    0.10, 0.95)` of `max_energy`. At drive 0 a healthy animal needs 85% of its energy; at drive 1 it
    needs 35%. This replaces `0.35 + 0.35 * vitality` and keeps the old idea that failing health lowers
    the bar.
  - Boldness: while a mate is in view, `effective_fear` is multiplied by `1 - 0.3 * drive`.
  - Upkeep: `0.05 * drive ** 2` per tick (search, display, hormones). At drive 1 that is about 10% of a
    mid-size animal's basal metabolism.
- The brain input `repro_urge` is `0` during a cooldown, otherwise `drive * min(1, energy_ratio /
  threshold)`: it rises as the animal gets fed.
- The reason it is separate from caregiving: a high-drive, low-caregiving animal is a fast, careless
  breeder; low-drive, high-caregiving is a slow, devoted one; and the two other combinations are also
  coherent strategies.

### Trade-off structure

| Gene | Gain | Cost | Pushes against |
| --- | --- | --- | --- |
| `caregiving` up | Young survive (diminishing returns) | Bigger energy bill per birth, so fewer births | Number of offspring |
| `repro_interval` down | More births in a lifetime | Readiness upkeep, more total spending | Food supply, the body's own repair |
| `repro_drive` up | Earlier and bolder mating | Upkeep, more risk while courting | Safety and the animal's own reserves |
| `somatic_maint` up | Longer life, more years to breed | Bigger and slower births, upkeep | All three above |

## Longevity trades against reproduction (`TRAIT.6`)

The owner's choice is mainly option C of #16 (longevity against reproduction), with a hint of option B
(upkeep that grows faster than the benefit).

**Main mechanism (disposable soma).** Repair and breeding draw on one energy supply, so an animal that
invests in repair has less to give each birth:

- Cost per birth to each parent: `care_fraction_i / 2 * max_energy(newborn) * (1 + 1.0 * somatic_maint)`.
  Full repair doubles what a birth costs the parent. The newborn still receives the unsurcharged amount.
- The shortest gap is stretched by the same investment:
  `interval_ticks = interval_fraction * lifespan_ticks * (1 + 0.5 * somatic_maint)`.

**Hint of option B.** Today the repair cost is `0.12 * somatic_maint`, linear, against a benefit that
saturates (lifespan `x (1 + 3.5 * somatic_maint)`, so each extra bit of repair buys less). The cost
becomes `0.20 * somatic_maint ** 2`: cheaper at low values (0.013 against 0.03 at 0.25) and dearer at
the top (0.20 against 0.12 at 1.0), so it grows faster than the benefit where the benefit is smallest.

## Does the trade-off work?

A small model, not the simulator: a mid-size animal (size 0.5), constant food intake per tick, the
lifespan and costs above, `caregiving 0.4`, `interval 0.05`, base upkeep 0.53 per tick (body, senses,
gut and brain, taken as a guess) plus the repair and readiness upkeep above, the animal paying the
whole birth bill itself (in a pair each pays half, which moves the numbers, not the shape), and newborn survival `1 - exp(-care_fraction / 0.15)`. It counts the
surviving young one animal produces in a lifetime, taking the smaller of what its energy allows and
what its interval allows. `somatic_maint` is `s`.

| `s` | Lifespan (ticks) | Surviving young, intake 1.0 | intake 0.8 | intake 0.7 |
| --- | --- | --- | --- | --- |
| 0.0 | 2,000 | 9.8 | 5.4 | 3.1 |
| 0.2 | 3,400 | 13.6 | 7.3 | 4.2 |
| 0.4 | 4,800 | 15.5 | 8.0 | 4.2 |
| 0.6 | 6,200 | 15.8 | 7.3 | 3.0 |
| 0.8 | 7,600 | 14.7 | 5.3 | 0.7 |
| 1.0 | 9,000 | 12.0 | 2.1 | 0.0 |

Under this model the best repair level is in the middle (about 0.4 to 0.6, lower when food is
scarce), so selection does not push `somatic_maint` to its maximum, which was the worry in #16. The
table counts offspring per lifetime only: when food is plentiful, a shorter-lived animal also turns
over generations faster, so population growth is a further pull toward low repair. The second
calculation, varying `caregiving` at `s = 0.4` and intake 0.8, gives a best value near 0.2:

| `caregiving` | Births | Newborn survival | Surviving young |
| --- | --- | --- | --- |
| 0.1 | 19.0 | 0.49 | 9.2 |
| 0.2 | 17.1 | 0.74 | 12.6 |
| 0.4 | 8.6 | 0.93 | 8.0 |
| 0.6 | 5.7 | 0.98 | 5.6 |
| 0.8 | 4.3 | 1.00 | 4.3 |

The toy model's optimum depends on its guessed constants and on assuming steady intake; real
results will move once food is patchy. What it does show is that the structure produces an interior
optimum for both genes, not a runaway to a corner.

## Units and time

- One tick is 1 simulated second ([WORLD.3](../../TODO.md)). Every per-tick number here (upkeep rates,
  wear) is "per reference tick"; if the tick length ever changes, multiply by it.
- Intervals, juvenile period and anything else that is a duration are stored as **shares of the animal's
  own lifespan** and turned into ticks at birth (`interval_ticks`). Nothing here is a fixed count of
  ticks, so the genes mean the same for a 22-minute animal and a 3-hour one, and for any time scale.
- **A problem for the owner.** Lifespans come out at 22 minutes to 3.3 hours of simulated time, and
  "1000 years per real second" is 3.2 x 10^10 ticks per real second at one second per tick. The brain
  decides in about 20 microseconds ([brain.md](brain.md)), so Python manages roughly 50,000 decisions a
  second for one animal. The fastest settings therefore cannot be run tick by tick. See question 2.

## Plants (REPRO.3)

Plants are asexual, mutate slower and live longer, and have no brain, so:

| Animal gene | Plant equivalent |
| --- | --- |
| `caregiving` | `seed_provision`: energy per seed as a share of the seed's own `max_biomass`; the seed count is what the 35% seed budget can pay for, so `seed_clutch` becomes the upper limit rather than a free number |
| `repro_interval` | `seeding_interval`: share of the plant's lifespan between seed bursts, stored the same way |
| `repro_drive` | None: a plant has no behaviour to motivate. The seeding trigger stays "at 85% of capacity" |

- Plants have no ageing today, so there is no lifespan to take a share of. `TRAIT.6` for plants needs a
  plant lifespan first (question 4). Until then `seeding_interval` is a share of a configured plant
  lifespan constant, set several times the animal one to match "live longer".
- Slower mutation is a `DNA.8` setting, not a trait: the plant layout gets a lower segment rate than the
  animal body.
- No sexual cost or mate search applies, so there is no repair surcharge on a "birth" other than the
  seed budget itself.

## What to build

`REPRO.5` and `TRAIT.6` change the same functions and the same layout version, so one builder should
take both.

1. `layouts.py`: drop `fertility`; add `caregiving`, `repro_interval`, `repro_drive` (3 digits each);
   `ANIMAL_LAYOUT.version = 3`. Plant layout gets `seed_provision` and `seeding_interval`
   (`PLANT_LAYOUT.version = 2`).
2. `trait_defs.py`: the three `TraitDef` rows above, and the plant rows. `unread_genes()` stays empty.
3. `traits.py`:
   - `lifespan_ticks` (property), `interval_ticks`, and the energy rules above;
   - replace `consume_mating_cost` with a two-parent birth step that checks both parents can afford it
     before taking anything (this is also `TRAIT.5`'s mating-cost guard), sets both cooldowns, and
     returns the newborn's starting energy;
   - replace the `0.35 + 0.35 * vitality` threshold with the drive formula;
   - basal metabolism gains the readiness and drive upkeep and the new repair cost.
4. `brain_adapter.py`: add `repro_urge` and `caregiving` to `INPUT_NAMES` (17 to 19 inputs, brain
   weights 198 to 214), which bumps the layout again if both changes land together.
5. Tests: the newborn's energy equals the parents' mean `care_fraction` times its `max_energy`; neither
   parent is charged if one cannot afford the birth; cooldown ticks scale with lifespan; full repair
   makes a birth cost double; and repair cost is convex.
6. Constants go in the `TRAIT.3` config object, with the names below.

## Constants for the TRAIT.3 config

| Name | Value | Used in |
| --- | --- | --- |
| `CARE_FRACTION_RANGE` | 0.10 to 0.80 | `caregiving` trait |
| `INTERVAL_FRACTION_RANGE` | 0.01 to 0.25 (log) | `repro_interval` trait |
| `READINESS_UPKEEP` | 0.03, reference interval 0.05, exponent 0.5 | basal metabolism |
| `DRIVE_UPKEEP` | 0.05, exponent 2 | basal metabolism |
| `DRIVE_THRESHOLD` | 0.85, slope 0.5, vitality weight 0.2, clamp 0.10 to 0.95 | wants-to-mate rule |
| `DRIVE_BOLDNESS` | 0.3 | fear modifier while a mate is in view |
| `CARE_PROTECTION` | aggression 0.5, fear 0.4 | modifiers near dependent young |
| `REPAIR_COST` | 0.20, exponent 2 | basal metabolism |
| `REPAIR_BIRTH_SURCHARGE` | 1.0 | cost per birth |
| `REPAIR_INTERVAL_STRETCH` | 0.5 | `interval_ticks` |
| `PLANT_LIFESPAN_TICKS` | to set with question 4 | `seeding_interval` |

## Questions for the owner

Raised as comments on [#36](https://github.com/dwhagar/evolutionSimulator/issues/36); each has a default
this note assumes until answered.

1. **Two tiers.** I read "two tiers" as tier 1 = the two capacity genes (caregiving, interval) and
   tier 2 = the drive. Right? Default: yes.
2. **Time scales.** A tick of one second and lifespans of hours cannot run at "1000 years per real
   second". Options: (A) keep one-second ticks and offer only the speeds that can run; (B) let the tick
   grow at fast speeds, with ageing, metabolism and reproduction summed over it and the brain deciding
   at a fixed interval; (C) make lifespans much longer in simulated time and the tick longer to match.
   Default: all durations are shares of lifespan (done here), decide when `WORLD.3` is built.
3. **Who pays for a child.** Shared by the two parents' genes (this note), or the one with sex type 2
   or 3 as in the prototype? Default: shared.
4. **Plant lifespan.** Plants have no ageing, so "live longer" and `TRAIT.6` for plants need a lifespan
   model. Add one (a simple maximum age, or wear like animals)? Default: a configured constant, no
   repair gene.
5. **Litters.** One offspring per birth, or several when the parent can afford it? Default: one.
