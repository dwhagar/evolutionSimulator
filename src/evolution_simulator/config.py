"""The tuning constants of the organisms, in one place (``TRAIT.3``).

``TraitRules`` is a tree of frozen dataclasses, one section per area, holding every number that
``traits.py`` and ``sense_genes.py`` use to turn genes into a living animal or plant and to run its
upkeep: the sizes and speeds a body gets, what it costs to live, wear, heal, think, mate and bear
young, and what a plant grows and seeds. The defaults are the current starting values (the
prototype's where it had one, the design notes' proposals elsewhere), to be tuned as the world
arrives. ``DEFAULT_RULES`` is what everything uses unless it is given another.

* An ``AnimalTraits`` or ``PlantTraits`` takes ``rules=`` and keeps it, so two runs with different
  rules can sit side by side and a test can change one number: ``replace(rules.life, wear_base=0.05)``
  and ``replace(DEFAULT_RULES, life=...)`` give a new tree without touching the default.
* ``WorldConfig.traits`` holds the rules for a run, next to the other settings of the world
  (``sensing``, ``learning``, ``sleep``, ``day_cycle``, ``time_scale``).
* What is **not** here: the ranges of the traits (how far a gene stretches a trait, such as
  ``SIGHT_REACH`` or ``COOLDOWN_DAYS_RANGE``), which are the trait table's data (``trait_defs.py``);
  the fixed structure of a formula (half of a care fraction per parent, a half-life's one half); and
  the settings that already have their own rules object (``LearningRules``, ``SleepRules``,
  ``DayCycle``, ``TimeScale``). ``SensingRules`` (the sensing step's light, sleep, smell and noise
  numbers) lives here as ``TraitRules.sensing``; ``WorldConfig.sensing`` reads it from there.

Each field's meaning is next to it. Time is in **reference ticks** (an hour of simulated time) and
rates are per reference tick; the world multiplies them by its ``dt`` (``TimeRules``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TimeRules:
    """The reference tick every per-tick rate is written for."""

    reference_tick_seconds: float = 3600.0
    """Simulated seconds in one reference tick. The world's ``dt`` is its tick length over this."""
    ticks_per_day: float = 24.0
    """Reference ticks in a simulated day."""


@dataclass(frozen=True)
class BodyRules:
    """What a body is, costs to keep and does as it wears down (animals)."""

    damage_capacity: float = 100.0
    """Health at size 0; times ``1 + size``."""
    energy_capacity: float = 100.0
    """Energy store at size 0; times ``1 + energy_size_gain * size``."""
    energy_size_gain: float = 2.0
    start_energy: float = 0.75
    """A newborn without parental energy starts with this share of its store."""
    speed_base: float = 2.0
    speed_span: float = 6.0
    speed_size_drag: float = 0.8
    """Top speed is ``(speed_base + speed_span * speed) / (1 + speed_size_drag * size)``."""
    turn_base: float = 0.05
    turn_span: float = 0.25
    turn_size_drag: float = 0.5
    """Turn rate is ``(turn_base + turn_span * agility) / (1 + turn_size_drag * size)``."""
    body_radius_scale: float = 0.5
    body_radius_exponent: float = 0.33
    """Body radius is ``scale * mass ** exponent``."""
    basal_scale: float = 0.18
    basal_exponent: float = 0.75
    """Upkeep of the body itself is ``scale * mass ** exponent`` (Kleiber's law)."""
    gut_cost: float = 0.06
    """Upkeep of the gut: ``gut_cost * (herbivore_eff ** 2 + carnivore_eff ** 2)``."""
    kinetic_burn: float = 0.35
    """Energy per reference tick per unit of mass for an animal moving at ``speed_reference``; the
    burn goes with the square of the speed actually moved, so a fast animal pays more per hour and
    more than twice as much per unit of distance moved at twice the speed (``TRAIT.9``)."""
    speed_reference: float = 3.5
    """Distance per reference tick of an average animal (speed gene 0.5, size 0.5) at full speed."""
    agility_cost: float = 0.06
    """Upkeep of quick reflexes: ``agility_cost * agility ** 2`` per reference tick (``TRAIT.9``)."""
    temperament_cost: float = 0.04
    """Upkeep of a strong temperament: ``temperament_cost * (aggression ** 2 + fear ** 2)``. A
    placeholder until fighting and fleeing cost something of their own (``BRAIN.10``) (``TRAIT.9``)."""
    speed_floor: float = 0.3
    """Top speed at no vitality is this share of the base speed (the rest scales with vitality)."""
    sense_floor: float = 0.4
    """Sight and hearing at no vitality are this share of their ranges."""
    health_floor: float = 0.35
    """Physical condition at no health is this share of vitality (the rest scales with health)."""


@dataclass(frozen=True)
class BehaviourRules:
    """Drives, temperament, feeding and calling (animals)."""

    hunger_aggression_gain: float = 1.6
    """Aggression is multiplied by ``1 + gain * starvation ** 2``."""
    crowd_aggression_gain: float = 0.4
    """Aggression is multiplied by ``1 + gain * local density``."""
    size_confidence_range: tuple[float, float] = (0.2, 2.0)
    """The target-to-own size ratio, clamped, scales aggression."""
    min_target_size_ratio: float = 0.1
    fear_wear_base: float = 1.2
    fear_wear_slope: float = 0.5
    """Fear acts as ``gene * (base - slope * vitality)``: stronger when worn down."""
    tournament_male_aggression: float = 1.35
    tournament_male_fear: float = 0.65
    brooding_female_fear: float = 1.3
    """The sex digit's behaviour offsets (digit 0 and digit 3); the prototype's."""
    taste_detection_base: float = 0.2
    taste_detection_gain: float = 0.8
    """Chance to notice toxin: ``toxicity * (base + gain * taste)``."""
    poison_damage: float = 25.0
    poison_taste_shield: float = 0.5
    """Eating toxin hurts ``toxicity * (1 - shield * taste) * poison_damage``."""
    diet_penalty: float = 0.4
    """Meat is digested ``1 - penalty * herbivore_eff`` as well, and plants ``1 - penalty *
    carnivore_eff`` (the generalist's cost)."""


@dataclass(frozen=True)
class BrainRules:
    """What thinking costs and how often it happens."""

    neuron_cost: float = 0.0005
    """Energy per tick per hidden or output neuron (a placeholder, ``BRAIN.5``)."""
    connection_cost: float = 0.0001
    """Per active connection, a weight whose absolute value is above ``dead_zone``."""
    dead_zone: float = 0.5
    """A weight at or below this is off, for cost and in ``Brain.decide`` (``BRAIN.21``): at 0.5 a
    quarter of random weights are off."""
    interrupt_pain: float = 0.05
    """Pain at or above this cuts the decision interval short (``BRAIN.22``)."""
    learning_cost: float = 0.004
    """Upkeep of plasticity: ``learning_cost * learning_rate`` per reference tick, paid by every
    animal whatever the world's learning switch says (``TRAIT.9``)."""
    pain_full_fraction: float = 0.2
    """Losing this fraction of maximum health since the last decision reads as full pain."""


@dataclass(frozen=True)
class LifeRules:
    """Wear and repair: how long an animal lives and what it gives up for a longer life."""

    wear_base: float = 0.0362
    """Damage per reference tick with no repair and no drive. A default animal (size 0.5, repair 0.5,
    drive 0.5) lives 8,765 reference ticks, about a simulated year."""
    repair_wear_damping: float = 3.5
    """Wear is divided by ``1 + damping * somatic_maint``."""
    drive_wear: float = 0.6
    """Wear is multiplied by ``1 + drive_wear * repro_drive``."""
    repair_cost: float = 0.20
    repair_cost_exponent: float = 2.0
    """Upkeep of repair: ``repair_cost * somatic_maint ** exponent`` (convex)."""
    repair_birth_surcharge: float = 2.0
    """A parent's cost of a birth is multiplied by ``1 + surcharge * somatic_maint``."""
    repair_cooldown_stretch: float = 1.0
    """The mating cooldown is multiplied by ``1 + stretch * somatic_maint``."""


@dataclass(frozen=True)
class ReproductionRules:
    """Drive, readiness, mating, pregnancy and birth (animals)."""

    readiness_upkeep: float = 0.03
    readiness_reference_days: float = 5.0
    readiness_exponent: float = 0.5
    """Upkeep for staying ready to breed: ``upkeep * (reference_days / cooldown_days) ** exponent``."""
    drive_upkeep: float = 0.05
    drive_upkeep_exponent: float = 2.0
    """Upkeep of the urge to mate: ``drive_upkeep * repro_drive ** exponent``."""
    drive_threshold_base: float = 0.85
    drive_threshold_slope: float = 0.5
    drive_threshold_vitality: float = 0.2
    drive_threshold_range: tuple[float, float] = (0.10, 0.95)
    """Energy share needed to start looking for a mate:
    ``clamp(base - slope * drive - vitality_term * (1 - vitality), *range)``."""
    drive_boldness: float = 0.3
    """While a mate is in view, fear is multiplied by ``1 - boldness * effective drive``."""
    sex_drive_modifier: tuple[tuple[int, float], ...] = ((2, 0.25), (3, -0.25))
    """The sex digit's second job, as (digit, change) pairs: digit 2 raises the effective drive by
    25%, digit 3 lowers it. The sex itself is the digit modulo 2: 0 impregnates, 1 bears."""
    maturity_share: float = 0.06
    """An animal (or plant) can first breed at this share of its expected lifespan."""
    young_dependence: float = 0.06
    """Young depend on a parent for ``parenting * young_dependence`` of the parent's expected
    lifespan after birth; a parent senses them as "own young" while they do (``SENSE.14``)."""
    young_protection: float = 0.5
    young_fearlessness: float = 0.4
    """A parent that sees its dependent young and a threat fights harder and flees less: aggression
    rises by ``parenting * young_protection`` and fear falls by ``parenting * young_fearlessness``
    (as fractions of their values)."""
    similarity_unrelated: float = 0.75
    """The share of digits that differ between two unrelated random genomes; a possible mate whose
    genome differs by this much or more has similarity 0 (``SENSE.14``)."""
    mating_effort: float = 0.03
    """Share of its store each partner spends on a mating, whether or not it takes."""
    conception_base: float = 0.30
    conception_slope: float = 0.60
    """A mating takes with chance ``base + slope * mean fertility of the two``."""
    litter_max: int = 8
    """Litter size is ``1 + round(litter_capacity * (litter_max - 1))``."""
    gestation_days_base: float = 2.0
    gestation_days_span: float = 18.0
    """Gestation is ``base + span * fertility`` days."""
    fertility_upkeep: float = 0.04
    fertility_upkeep_exponent: float = 2.0
    gestation_upkeep: float = 0.5
    """A pregnant bearer burns an extra ``gestation_upkeep * litter / litter_max`` of her basal
    metabolism."""
    gestation_slowing: float = 0.3
    """A pregnant bearer's top speed is multiplied by ``1 - slowing * litter / litter_max``."""


@dataclass(frozen=True)
class RecoveryRules:
    """Healing and rest (``TRAIT.7``)."""

    heal_halflife_days: tuple[float, float] = (20.0, 1.0)
    """Half-life of lost health at recovery 0 and recovery 1 (log scale between)."""
    heal_energy_cost: float = 0.5
    """Energy spent per point of health healed."""
    heal_min_energy_ratio: float = 0.5
    """Lost health only heals while the energy store is at least this full."""
    rest_regain: tuple[float, float] = (0.5, 2.0)
    """Multiplier on ``SleepRules.energy_regain`` at recovery 0 and recovery 1."""
    upkeep: float = 0.10
    upkeep_exponent: float = 2.0
    """Upkeep of recovery: ``upkeep * recovery ** exponent``."""


@dataclass(frozen=True)
class PlantTraitRules:
    """A plant's body, growth and seeding (``REPRO.3``, ``TRAIT.8``)."""

    damage_capacity_share: float = 0.8
    """Health is this share of the full biomass."""
    mass_share: float = 0.5
    """Mass is this share of the full biomass."""
    upkeep_scale: float = 0.02
    upkeep_exponent: float = 0.5
    """Upkeep of the plant body: ``scale * mass ** exponent``."""
    toxin_cost: float = 0.05
    toxin_cost_exponent: float = 1.5
    """Upkeep of chemical defence: ``cost * toxicity ** exponent``."""
    start_biomass: float = 0.15
    """A seedling without a parent's gift starts with this share of its full size."""
    start_health: float = 0.5
    """A seedling starts with this share of its health."""
    repair_share: float = 0.5
    """Net growth also repairs the plant by this share of it."""
    light_floor: float = 0.05
    """Sunlight and soil factors never fall below this."""
    graze_damage: float = 0.75
    """Grazing hurts a plant by this much per unit eaten."""
    dies_below_biomass: float = 2.0
    """A grazed plant with this little left dies."""
    seed_budget_share: float = 0.35
    """Share of its biomass a plant can put into one burst of seeds, before the longevity trade-off."""
    seed_ready_share: float = 0.85
    """A plant is ready to seed once it holds this share of its full size."""
    seed_ready_vitality: float = 0.4
    """...and its vitality is above this."""
    longevity_growth: float = 0.3
    """Growth is multiplied by ``1 - longevity_growth * longevity``."""
    longevity_seeds: float = 0.4
    """The seed budget share is multiplied by ``1 - longevity_seeds * longevity``."""


@dataclass(frozen=True)
class OrganRules:
    """What sense organs cost and how noisy they are (``SENSE.11``, ``SENSE.16``). The ranges the
    genes stretch each organ over are the trait table's (``sense_genes.py``)."""

    hearing_noise: tuple[float, float] = (0.30, 0.15)
    smell_noise: tuple[float, float] = (0.50, 0.25)
    """Standard deviation of the direction error, in input units, at gene 0 and at gene 1. Vision's
    depends on its working acuity instead."""
    acuity_reach: tuple[float, float] = (0.6, 1.4)
    """Vision reach as a multiple of the base reach at working acuity 0 and 1."""
    acuity_direction_noise: tuple[float, float] = (0.02, 0.005)
    """Vision direction error, and relative-size error, at working acuity 0 and 1."""
    acuity_closeness_noise: tuple[float, float] = (0.05, 0.01)
    """Vision closeness error at working acuity 0 and 1."""
    vision_cost_per_area: float = 8e-6
    hearing_cost_per_area: float = 2.5e-6
    smell_cost_per_area: float = 2.5e-6
    """Energy per tick per square unit covered; vision's is multiplied by ``1 + working acuity``.
    Placeholders for ``SENSE.13`` to calibrate."""
    touch_cost: float = 0.08
    taste_cost: float = 0.08
    """Energy per tick times the gene level squared."""


@dataclass(frozen=True)
class SensingRules:
    """The constants of the sensing step: starting values from the design note, for calibration
    against a running world (``SENSE.13``) now part of the constants config (``TRAIT.3``): ``TraitRules.sensing``."""

    light_floor: float = 0.25
    """Vision range at full darkness as a fraction of its daylight range:
    ``light_floor + (1 - light_floor) * daylight``."""
    sleep_vision: float = 0.0
    sleep_hearing: float = 0.5
    sleep_smell: float = 0.5
    sleep_touch: float = 1.0
    """The fraction of each organ's range that still works while asleep."""
    weak_smell: float = 0.5
    """Fraction of the smell range at which prey and threats can be smelled (a presence, not a
    precise report). A placeholder: the design note gives no number."""
    crowding_reference: int = 8
    """This many animals in reach gives a crowding input of 1."""
    closeness_noise: float = 0.03
    """Standard deviation of the error on every closeness report (input units)."""

    def __post_init__(self) -> None:
        for name in (
            "light_floor",
            "sleep_vision",
            "sleep_hearing",
            "sleep_smell",
            "sleep_touch",
            "weak_smell",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1, got {getattr(self, name)}.")
        if self.crowding_reference < 1:
            raise ValueError("crowding_reference must be at least 1.")
        if not (math.isfinite(self.closeness_noise) and self.closeness_noise >= 0.0):
            raise ValueError("closeness_noise cannot be negative.")

    def light_factor(self, daylight: float) -> float:
        return self.light_floor + (1.0 - self.light_floor) * daylight

    def sleep_factor(self, sense: str) -> float:
        return {
            "vision": self.sleep_vision,
            "hearing": self.sleep_hearing,
            "smell": self.sleep_smell,
            "touch": self.sleep_touch,
        }[sense]


@dataclass(frozen=True)
class TraitRules:
    """All the organism constants of a run."""

    time: TimeRules = field(default_factory=TimeRules)
    body: BodyRules = field(default_factory=BodyRules)
    behaviour: BehaviourRules = field(default_factory=BehaviourRules)
    brain: BrainRules = field(default_factory=BrainRules)
    life: LifeRules = field(default_factory=LifeRules)
    reproduction: ReproductionRules = field(default_factory=ReproductionRules)
    recovery: RecoveryRules = field(default_factory=RecoveryRules)
    plant: PlantTraitRules = field(default_factory=PlantTraitRules)
    organs: OrganRules = field(default_factory=OrganRules)
    sensing: SensingRules = field(default_factory=SensingRules)


DEFAULT_RULES = TraitRules()
"""The starting values everything uses unless it is given other rules."""
