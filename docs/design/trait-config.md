# The tuning constants (TRAIT.3)

Every number that `traits.py` and `sense_genes.py` use to turn genes into a living organism, and the
sensing step's constants, are in one frozen dataclass tree in
[`config.py`](../../src/evolution_simulator/config.py): `TraitRules`, with the starting values in
`DEFAULT_RULES`. Before this item they were module constants (`WEAR_BASE`, `LITTER_MAX`, ...) and
inline numbers inside the formulas (`0.18 * mass ** 0.75`); the defaults reproduce them exactly (a
test pins the numbers of a reference animal and plant, and the old and new code gave identical values
on 60 random genomes over 40 ticks).

## How it is used

- `AnimalTraits(dna, rules=...)` and `PlantTraits(dna, rules)` keep the rules they were built with
  (`traits.rules`) and read every constant from there. Without `rules` they use `DEFAULT_RULES`.
- `WorldConfig.traits` is the rules of a run; the world hands them to every animal and plant it makes
  (founders, births, seeds) and takes its `dt` from `traits.time`. `WorldConfig.sensing` is the same
  object's `sensing` section.
- The rules are values: frozen, hashable, compared by content. A test or a run changes one number with
  `replace(DEFAULT_RULES, life=replace(DEFAULT_RULES.life, wear_base=0.05))`; the default is never
  mutated, so two runs with different rules can sit side by side.
- Time is in **reference ticks** (one simulated hour, `time.reference_tick_seconds`); a rate is per
  reference tick and the world multiplies it by its `dt`.

## What is not in the tree

- **The ranges of the traits**: how far a gene stretches a trait (`SIGHT_REACH`, `COOLDOWN_DAYS_RANGE`,
  `LIFESPAN_DAYS_RANGE`, the fov range, `CARE_FRACTION_RANGE`) stay in the trait table
  (`trait_defs.py`, `sense_genes.py`). They are the definition of what a gene means, and the genome
  layout depends on them. Changing a range is a decision about the genes, not a tuning of a run.
- **The fixed shape of a formula**: half of a care fraction per parent, the one half in a half-life, a
  square in the cost of a sense. Only numbers somebody might want to retune are fields.
- **Settings that already have their own object**: `LearningRules` (`learning.py`), `SleepRules`
  (`world/sleep.py`), `DayCycle`, `TimeScale`, `PlantRules` (the world's seeding rules) and the
  `WorldConfig` fields such as `graze_amount`. They keep their own place; moving them is a later,
  separate decision.

## Where each old name went

| Old name | Field |
| --- | --- |
| `BRAIN_NEURON_COST`, `BRAIN_CONNECTION_COST` | `brain.neuron_cost`, `brain.connection_cost` |
| `BRAIN_DEAD_ZONE` (a weight at or below it is off, the "active threshold") | `brain.dead_zone` |
| `INTERRUPT_PAIN`, `PAIN_FULL_FRACTION` | `brain.interrupt_pain`, `brain.pain_full_fraction` |
| `WEAR_BASE`, `DRIVE_WEAR`, `REPAIR_*` | `life.wear_base`, `life.drive_wear`, `life.repair_*` |
| `READINESS_*`, `DRIVE_*`, `SEX_DRIVE_MODIFIER`, `MATURITY_SHARE`, `MATING_EFFORT`, `FERTILITY_*`, `LITTER_MAX`, `GESTATION_*` | `reproduction.*` |
| `HEAL_*`, `RECOVERY_*` | `recovery.*` |
| `REFERENCE_TICK_SECONDS`, `TICKS_PER_DAY` | `time.reference_tick_seconds`, `time.ticks_per_day` |
| `PLANT_LONGEVITY_*`, `SEED_*`, the plant numbers | `plant.*` |
| `COST_PER_AREA`, `TOUCH_COST`, `TASTE_COST`, `NOISE_AT_GENE`, the acuity effects (`sense_genes.py`) | `organs.*` |
| `SensingRules` (`sensing.py`) | `sensing` (the class now lives in `config.py` and is re-exported by `sensing.py`) |
| the inline numbers (`0.18`, `0.75`, `0.06`, `0.35`, `1.6`, `25.0`, ...) | `body.*`, `behaviour.*`, `plant.*` |

The brain costs are the ones the brain threads tune: a random brain costs about 4% of basal metabolism
(2% to 8% over 60 random genomes, a test checks it). `Foundations 2` owns changing them.

## Every field

### `time` (`TimeRules`)

The reference tick every per-tick rate is written for.

| Field | Default | Meaning |
| --- | --- | --- |
| `reference_tick_seconds` | `3600.0` | Simulated seconds in one reference tick. The world's `dt` is its tick length over this. |
| `ticks_per_day` | `24.0` | Reference ticks in a simulated day. |

### `body` (`BodyRules`)

What a body is, costs to keep and does as it wears down (animals).

| Field | Default | Meaning |
| --- | --- | --- |
| `damage_capacity` | `100.0` | Health at size 0; times `1 + size`. |
| `energy_capacity` | `100.0` | Energy store at size 0; times `1 + energy_size_gain * size`. |
| `energy_size_gain` | `2.0` |  |
| `start_energy` | `0.75` | A newborn without parental energy starts with this share of its store. |
| `speed_base` | `2.0` |  |
| `speed_span` | `6.0` |  |
| `speed_size_drag` | `0.8` | Top speed is `(speed_base + speed_span * speed) / (1 + speed_size_drag * size)`. |
| `turn_base` | `0.05` |  |
| `turn_span` | `0.25` |  |
| `turn_size_drag` | `0.5` | Turn rate is `(turn_base + turn_span * agility) / (1 + turn_size_drag * size)`. |
| `body_radius_scale` | `0.5` |  |
| `body_radius_exponent` | `0.33` | Body radius is `scale * mass ** exponent`. |
| `basal_scale` | `0.18` |  |
| `basal_exponent` | `0.75` | Upkeep of the body itself is `scale * mass ** exponent` (Kleiber's law). |
| `gut_cost` | `0.06` | Upkeep of the gut: `gut_cost * (herbivore_eff ** 2 + carnivore_eff ** 2)`. |
| `kinetic_burn` | `0.35` | Energy per tick moving at full speed per unit of mass, times the speed ratio squared. |
| `speed_floor` | `0.3` | Top speed at no vitality is this share of the base speed (the rest scales with vitality). |
| `sense_floor` | `0.4` | Sight and hearing at no vitality are this share of their ranges. |
| `health_floor` | `0.35` | Physical condition at no health is this share of vitality (the rest scales with health). |

### `behaviour` (`BehaviourRules`)

Drives, temperament, feeding and calling (animals).

| Field | Default | Meaning |
| --- | --- | --- |
| `hunger_threshold` | `0.5` | Below this share of the energy store an animal wants food. |
| `forage_efficiency` | `0.1` | It only targets plants (or prey) it digests at least this well. |
| `prey_aggression` | `0.2` | It only targets prey if its aggression is above this. |
| `hunt_aggression` | `0.4` |  |
| `hunt_starvation` | `0.3` | Without a threat in view it wants to attack when aggression and starvation pass these (and it can digest meat). |
| `hunger_aggression_gain` | `1.6` | Aggression is multiplied by `1 + gain * starvation ** 2`. |
| `crowd_aggression_gain` | `0.4` | Aggression is multiplied by `1 + gain * local density`. |
| `size_confidence_range` | `(0.2, 2.0)` | The target-to-own size ratio, clamped, scales aggression and the fight-or-flight test. |
| `min_target_size_ratio` | `0.1` |  |
| `fear_wear_base` | `1.2` |  |
| `fear_wear_slope` | `0.5` | Fear acts as `gene * (base - slope * vitality)`: stronger when worn down. |
| `tactile_threshold` | `0.1` | The touch gene must be above this for a tactile reflex. |
| `tournament_male_aggression` | `1.35` |  |
| `tournament_male_fear` | `0.65` |  |
| `brooding_female_fear` | `1.3` | The sex digit's behaviour offsets (digit 0 and digit 3); the prototype's. |
| `signal_gene_threshold` | `0.05` | The encoder gene must be above this to call at all. |
| `mating_call_wear` | `0.3` | A wanting animal calls for a mate once it has lost this much vitality. |
| `taste_detection_base` | `0.2` |  |
| `taste_detection_gain` | `0.8` | Chance to notice toxin: `toxicity * (base + gain * taste)`. |
| `poison_damage` | `25.0` |  |
| `poison_taste_shield` | `0.5` | Eating toxin hurts `toxicity * (1 - shield * taste) * poison_damage`. |
| `diet_penalty` | `0.4` | Meat is digested `1 - penalty * herbivore_eff` as well, and plants `1 - penalty * carnivore_eff` (the generalist's cost). |

### `brain` (`BrainRules`)

What thinking costs and how often it happens.

| Field | Default | Meaning |
| --- | --- | --- |
| `neuron_cost` | `0.0005` | Energy per tick per hidden or output neuron (a placeholder, `BRAIN.5`). |
| `connection_cost` | `0.0001` | Per active connection, a weight whose absolute value is above `dead_zone`. |
| `dead_zone` | `0.5` | A weight at or below this is off, for cost and in `Brain.decide` (`BRAIN.21`): at 0.5 a quarter of random weights are off. |
| `interrupt_pain` | `0.05` | Pain at or above this cuts the decision interval short (`BRAIN.22`). |
| `pain_full_fraction` | `0.2` | Losing this fraction of maximum health since the last decision reads as full pain. |

### `life` (`LifeRules`)

Wear and repair: how long an animal lives and what it gives up for a longer life.

| Field | Default | Meaning |
| --- | --- | --- |
| `wear_base` | `0.0362` | Damage per reference tick with no repair and no drive. A default animal (size 0.5, repair 0.5, drive 0.5) lives 8,765 reference ticks, about a simulated year. |
| `repair_wear_damping` | `3.5` | Wear is divided by `1 + damping * somatic_maint`. |
| `drive_wear` | `0.6` | Wear is multiplied by `1 + drive_wear * repro_drive`. |
| `repair_cost` | `0.2` |  |
| `repair_cost_exponent` | `2.0` | Upkeep of repair: `repair_cost * somatic_maint ** exponent` (convex). |
| `repair_birth_surcharge` | `2.0` | A parent's cost of a birth is multiplied by `1 + surcharge * somatic_maint`. |
| `repair_cooldown_stretch` | `1.0` | The mating cooldown is multiplied by `1 + stretch * somatic_maint`. |

### `reproduction` (`ReproductionRules`)

Drive, readiness, mating, pregnancy and birth (animals).

| Field | Default | Meaning |
| --- | --- | --- |
| `readiness_upkeep` | `0.03` |  |
| `readiness_reference_days` | `5.0` |  |
| `readiness_exponent` | `0.5` | Upkeep for staying ready to breed: `upkeep * (reference_days / cooldown_days) ** exponent`. |
| `drive_upkeep` | `0.05` |  |
| `drive_upkeep_exponent` | `2.0` | Upkeep of the urge to mate: `drive_upkeep * repro_drive ** exponent`. |
| `drive_threshold_base` | `0.85` |  |
| `drive_threshold_slope` | `0.5` |  |
| `drive_threshold_vitality` | `0.2` |  |
| `drive_threshold_range` | `(0.1, 0.95)` | Energy share needed to start looking for a mate: `clamp(base - slope * drive - vitality_term * (1 - vitality), *range)`. |
| `drive_boldness` | `0.3` | While a mate is in view, fear is multiplied by `1 - boldness * effective drive`. |
| `sex_drive_modifier` | `((2, 0.25), (3, -0.25))` | The sex digit's second job, as (digit, change) pairs: digit 2 raises the effective drive by 25%, digit 3 lowers it. The sex itself is the digit modulo 2: 0 impregnates, 1 bears. |
| `maturity_share` | `0.06` | An animal (or plant) can first breed at this share of its expected lifespan. |
| `mating_effort` | `0.03` | Share of its store each partner spends on a mating, whether or not it takes. |
| `conception_base` | `0.3` |  |
| `conception_slope` | `0.6` | A mating takes with chance `base + slope * mean fertility of the two`. |
| `litter_max` | `8` | Litter size is `1 + round(litter_capacity * (litter_max - 1))`. |
| `gestation_days_base` | `2.0` |  |
| `gestation_days_span` | `18.0` | Gestation is `base + span * fertility` days. |
| `fertility_upkeep` | `0.04` |  |
| `fertility_upkeep_exponent` | `2.0` |  |
| `gestation_upkeep` | `0.5` | A pregnant bearer burns an extra `gestation_upkeep * litter / litter_max` of her basal metabolism. |
| `gestation_slowing` | `0.3` | A pregnant bearer's top speed is multiplied by `1 - slowing * litter / litter_max`. |

### `recovery` (`RecoveryRules`)

Healing and rest (`TRAIT.7`).

| Field | Default | Meaning |
| --- | --- | --- |
| `heal_halflife_days` | `(20.0, 1.0)` | Half-life of lost health at recovery 0 and recovery 1 (log scale between). |
| `heal_energy_cost` | `0.5` | Energy spent per point of health healed. |
| `heal_min_energy_ratio` | `0.5` | Lost health only heals while the energy store is at least this full. |
| `rest_regain` | `(0.5, 2.0)` | Multiplier on `SleepRules.energy_regain` at recovery 0 and recovery 1. |
| `upkeep` | `0.1` |  |
| `upkeep_exponent` | `2.0` | Upkeep of recovery: `upkeep * recovery ** exponent`. |

### `plant` (`PlantTraitRules`)

A plant's body, growth and seeding (`REPRO.3`, `TRAIT.8`).

| Field | Default | Meaning |
| --- | --- | --- |
| `damage_capacity_share` | `0.8` | Health is this share of the full biomass. |
| `mass_share` | `0.5` | Mass is this share of the full biomass. |
| `upkeep_scale` | `0.02` |  |
| `upkeep_exponent` | `0.5` | Upkeep of the plant body: `scale * mass ** exponent`. |
| `toxin_cost` | `0.05` |  |
| `toxin_cost_exponent` | `1.5` | Upkeep of chemical defence: `cost * toxicity ** exponent`. |
| `start_biomass` | `0.15` | A seedling without a parent's gift starts with this share of its full size. |
| `start_health` | `0.5` | A seedling starts with this share of its health. |
| `repair_share` | `0.5` | Net growth also repairs the plant by this share of it. |
| `light_floor` | `0.05` | Sunlight and soil factors never fall below this. |
| `graze_damage` | `0.75` | Grazing hurts a plant by this much per unit eaten. |
| `dies_below_biomass` | `2.0` | A grazed plant with this little left dies. |
| `seed_budget_share` | `0.35` | Share of its biomass a plant can put into one burst of seeds, before the longevity trade-off. |
| `seed_ready_share` | `0.85` | A plant is ready to seed once it holds this share of its full size. |
| `seed_ready_vitality` | `0.4` | ...and its vitality is above this. |
| `longevity_growth` | `0.3` | Growth is multiplied by `1 - longevity_growth * longevity`. |
| `longevity_seeds` | `0.4` | The seed budget share is multiplied by `1 - longevity_seeds * longevity`. |

### `organs` (`OrganRules`)

What sense organs cost and how noisy they are (`SENSE.11`, `SENSE.16`). The ranges the genes stretch each organ over are the trait table's (`sense_genes.py`).

| Field | Default | Meaning |
| --- | --- | --- |
| `hearing_noise` | `(0.3, 0.15)` |  |
| `smell_noise` | `(0.5, 0.25)` | Standard deviation of the direction error, in input units, at gene 0 and at gene 1. Vision's depends on its working acuity instead. |
| `acuity_reach` | `(0.6, 1.4)` | Vision reach as a multiple of the base reach at working acuity 0 and 1. |
| `acuity_direction_noise` | `(0.02, 0.005)` | Vision direction error, and relative-size error, at working acuity 0 and 1. |
| `acuity_closeness_noise` | `(0.05, 0.01)` | Vision closeness error at working acuity 0 and 1. |
| `vision_cost_per_area` | `8e-06` |  |
| `hearing_cost_per_area` | `2.5e-06` |  |
| `smell_cost_per_area` | `2.5e-06` | Energy per tick per square unit covered; vision's is multiplied by `1 + working acuity`. Placeholders for `SENSE.13` to calibrate. |
| `touch_cost` | `0.08` |  |
| `taste_cost` | `0.08` | Energy per tick times the gene level squared. |

### `sensing` (`SensingRules`)

The constants of the sensing step: starting values from the design note, for calibration against a running world (`SENSE.13`) now part of the constants config (`TRAIT.3`): `TraitRules.sensing`.

| Field | Default | Meaning |
| --- | --- | --- |
| `light_floor` | `0.25` | Vision range at full darkness as a fraction of its daylight range: `light_floor + (1 - light_floor) * daylight`. |
| `sleep_vision` | `0.0` |  |
| `sleep_hearing` | `0.5` |  |
| `sleep_smell` | `0.5` |  |
| `sleep_touch` | `1.0` | The fraction of each organ's range that still works while asleep. |
| `weak_smell` | `0.5` | Fraction of the smell range at which prey and threats can be smelled (a presence, not a precise report). A placeholder: the design note gives no number. |
| `crowding_reference` | `8` | This many animals in reach gives a crowding input of 1. |
| `closeness_noise` | `0.03` | Standard deviation of the error on every closeness report (input units). |
