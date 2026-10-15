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
* ``WorldConfig.traits`` holds the rules for a run. The settings of the world that used to sit
  beside it have moved into the tree (``TRAIT.10``, ``TRAIT.11``): ``learning``, ``sleep``, ``day_cycle``,
  the tick length and speed (``time``), the plants' soil and shade limits (``plant_limits``), bites
  (``attack``), corpses (``corpses``) and the grazing, mating reach, birth scatter and call switch
  (``world``). ``WorldConfig`` reads them from the tree, so a run has one source of tuning constants.
* What is **not** here: the ranges of the traits (how far a gene stretches a trait, such as
  ``SIGHT_REACH`` or ``COOLDOWN_DAYS_RANGE``), which are the trait table's data (``trait_defs.py``);
  the fixed structure of a formula (half of a care fraction per parent, a half-life's one half); and
  the settings that still have their own rules object (``DayCycle``, ``TimeScale``).
  ``SensingRules`` (the sensing step's light, sleep, smell and noise numbers) lives here as
  ``TraitRules.sensing`` and ``LearningRules`` as ``TraitRules.learning``, ``SleepRules`` as ``TraitRules.sleep``; ``WorldConfig.sensing``, ``.learning``
  and ``.sleep`` read them from there.

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
    seconds_per_tick: float = 3600.0
    """Simulated seconds in one tick of this run (``TRAIT.10``; was ``TimeScale``). A tick of the
    reference length gives the world a ``dt`` of 1."""
    speed: float = 1.0
    """Simulated seconds that pass for each real second; how fast a viewer asks the run to go."""

    def __post_init__(self) -> None:
        for name in ("reference_tick_seconds", "ticks_per_day", "seconds_per_tick", "speed"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be a positive finite number, got {value}.")


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
    burn_scale: float = 0.1
    """Share of its upkeep bill (``basal_metabolism``: the body, gut, organ, brain and temperament
    terms together) an animal burns per reference tick; sleeping saves against the same burn. The
    tables give the bill at full size, and at 1 a seeded first generation eats a tenth of what it
    burns and is dead within about 1,000 ticks (``WORLD.15``, issue 242 question 1)."""
    kinetic_burn: float = 0.035
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
    camouflage_cost: float = 0.03
    """Upkeep of camouflage: ``camouflage_cost * camouflage ** 2`` per reference tick, about 7% of a
    basal 0.43 at the top (``SENSE.21``)."""
    camouflage_slowing: float = 0.25
    """Top speed is multiplied by ``1 - camouflage_slowing * camouflage``: a creature that keeps
    itself hidden moves with care (``SENSE.21``)."""
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
    interval_scale: float = 1.0
    """Speed option (``WORLD.17``): every animal's decision interval, as its genes give it, is
    multiplied by this when it is made (rounded to whole ticks, at least 1), so the brain runs less
    often and the run costs less. 1 is the genes' own interval. The brain upkeep follows the
    interval, as it does between animals: a slower thinker is cheaper."""
    idle_interval_factor: float = 1.0
    """Speed option (``WORLD.17``): an animal whose last look sensed nothing at all (no creature,
    plant, contact, call, crowd or wall) waits this many times its decision interval before it looks
    again. Contact or pain still make it look at once. 1 is off: the interval is the same whatever
    it sensed."""

    def __post_init__(self) -> None:
        for name in ("interval_scale", "idle_interval_factor"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 1.0):
                raise ValueError(f"{name} must be 1 or more, got {value}.")


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
    founder_toxicity: float = 0.3
    """A first generation's plants have this share of the toxicity their genes give (``WORLD.15``,
    issue 242 question 3): a random plant is poisonous enough to kill an animal that eats it often."""
    founder_size: float = 0.7
    """A first generation's plants start at this share of their full size, not as seedlings."""
    founder_age_spread: float = 0.5
    """...and at a random age up to this share of their lifespan, so they do not die in one wave."""
    founder_upkeep_share: float = 0.3
    """A first generation's plants must be able to pay their way: ``World.populate`` redraws a
    random plant whose full-size upkeep is more than this share of its growth (``WORLD.11``).
    Measured: of random plants, those above 0.4 all died as seedlings and those below 0.3 mostly
    lived (about 40% of random plants were above 0.4)."""


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
    visibility_reference_radius: float = 0.7
    """The body radius that is seen exactly as far as the viewer's vision reaches: the radius of an
    average animal (``SENSE.21``)."""
    plant_visibility_reference_radius: float = 5.0
    """The same for a plant's canopy radius, which runs from 2 to 12 where an animal's body is
    0.5 to 0.8: a plant of average canopy is seen as far as the reach, a wide one farther."""
    visibility_size_exponent: float = 0.5
    visibility_size_range: tuple[float, float] = (0.7, 1.5)
    """Seen from ``(radius / reference) ** exponent`` times as far, kept within this range, so a
    plant's wide canopy and a small animal are seen from 1.5 and 0.7 times the reach at most."""
    still_visibility: float = 0.7
    moving_visibility: float = 1.3
    """An animal's visibility factor for movement, from a still or sleeping one to one at full speed.
    Plants do not move, so only their size counts."""
    camouflage_strength: float = 0.5
    """At camouflage 1 an animal is seen from ``1 - strength`` of the distance it would be otherwise."""

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
        for name in ("visibility_reference_radius", "plant_visibility_reference_radius"):
            if not (math.isfinite(getattr(self, name)) and getattr(self, name) > 0.0):
                raise ValueError(f"{name} must be above zero.")
        low, high = self.visibility_size_range
        if not (0.0 < low <= high and math.isfinite(high)):
            raise ValueError(f"visibility_size_range must run from above 0 up, got {low}, {high}.")
        for name in ("visibility_size_exponent", "still_visibility", "moving_visibility"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0.0):
                raise ValueError(f"{name} cannot be negative, got {value}.")
        if not 0.0 <= self.camouflage_strength < 1.0:
            raise ValueError("camouflage_strength must be at least 0 and below 1.")
        if not (math.isfinite(self.closeness_noise) and self.closeness_noise >= 0.0):
            raise ValueError("closeness_noise cannot be negative.")

    def visibility(
        self, radius: float, speed_ratio: float | None = None, camouflage: float = 0.0
    ) -> float:
        """How far a creature of this body ``radius`` is seen, as a multiple of the viewer's vision
        reach (``SENSE.21``): its size, how fast it is moving (``speed_ratio`` 0 to 1 of its top
        speed; ``None`` for a plant, which only has its size, judged against the plant reference) and its camouflage gene."""
        low, high = self.visibility_size_range
        reference = (
            self.plant_visibility_reference_radius
            if speed_ratio is None
            else self.visibility_reference_radius
        )
        size = min(high, max(low, (radius / reference) ** self.visibility_size_exponent))
        if speed_ratio is None:
            motion = 1.0
        else:
            motion = (
                self.still_visibility
                + (self.moving_visibility - self.still_visibility) * speed_ratio
            )
        return size * motion * (1.0 - self.camouflage_strength * camouflage)

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
class LearningRules:
    """Learning during life (``BRAIN.24``): the log, the reward and the size of a night's change.

    ``TraitRules.learning`` holds them for a run; ``None`` there turns learning off.
    """

    log_size: int = 64
    """Decisions kept in the day log; the oldest are dropped when it is full."""
    reward_window: float = 10.0
    """Reference ticks (hours) after a decision over which its outcome is counted; the learner
    turns it into ticks with the world's ``dt`` (at least one), so the length of a tick does not
    change what an animal learns from (``WORLD.16``)."""
    energy_weight: float = 1.0
    """Reward per unit of energy-store fraction gained (a fall counts against)."""
    health_weight: float = 2.0
    """Penalty per unit of damage-capacity fraction lost."""
    mating_weight: float = 1.0
    """Reward for each mating achieved."""
    safety_weight: float = 0.5
    """Reward per unit that the threat input falls after a threat was sensed."""
    night_cap: float = 0.5
    """The most any one number may change in one night (an eighth of a weight's range)."""
    fade: float = 0.0
    """Share of the learned offsets lost each night (forgetting); off by default."""
    max_offset: float = 2.0
    """The most a number's total learned change may reach, so repeated nights cannot run away."""

    def __post_init__(self) -> None:
        if self.log_size < 1:
            raise ValueError("log_size must be at least 1.")
        if not (math.isfinite(self.reward_window) and self.reward_window > 0.0):
            raise ValueError(f"reward_window must be above zero, got {self.reward_window}.")
        for name in ("energy_weight", "health_weight", "mating_weight", "safety_weight"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be a finite number.")
        for name in ("night_cap", "max_offset"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0.0):
                raise ValueError(f"{name} must be zero or more, got {value}.")
        if not 0.0 <= self.fade <= 1.0:
            raise ValueError(f"fade must be between 0 and 1, got {self.fade}.")


@dataclass(frozen=True)
class SleepRules:
    """Sleep (``WORLD.5``): who stays awake, what a sleeper burns and regains, what wakes it.

    ``TraitRules.sleep`` holds them for a run (``TRAIT.10``).
    """

    starving_below: float = 0.15
    """An animal with less than this fraction of its energy store stays awake to find food."""
    metabolism_factor: float = 0.4
    """Fraction of its basal metabolism an animal burns while asleep."""
    energy_regain: float = 0.0002
    """Fraction of its energy store an animal regains each reference tick (hour) of sleep, at
    average ``recovery``, on top of burning less."""
    alarm_wakes_above: float = 0.2
    """An alarm call heard at least this strongly (1 at the caller, 0 at the edge of its radius)
    wakes a sleeper, and it stays awake until the next day (SENSE.7)."""

    def __post_init__(self) -> None:
        for name in ("starving_below", "metabolism_factor", "energy_regain", "alarm_wakes_above"):
            value = getattr(self, name)
            if not (math.isfinite(value) and 0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be between 0 and 1, got {value}.")


@dataclass(frozen=True)
class DayCycle:
    """One day of light and dark (``WORLD.5``, ``TraitRules.day_cycle``); the module docstring of
    ``world/daycycle.py`` describes the curve."""

    length_seconds: float = 24.0 * 3600.0
    start_phase: float = 0.5
    night_below: float = 0.3

    def __post_init__(self) -> None:
        if not (math.isfinite(self.length_seconds) and self.length_seconds > 0.0):
            raise ValueError(f"length_seconds must be positive, got {self.length_seconds}.")
        if not (math.isfinite(self.start_phase) and 0.0 <= self.start_phase < 1.0):
            raise ValueError(f"start_phase must be from 0 up to 1, got {self.start_phase}.")
        if not 0.0 <= self.night_below <= 1.0:
            raise ValueError(f"night_below must be between 0 and 1, got {self.night_below}.")

    def phase(self, simulated_seconds: float) -> float:
        """Fraction of the day gone, from 0 up to 1 (0 is midnight, 0.5 noon)."""
        return (self.start_phase + simulated_seconds / self.length_seconds) % 1.0

    def daylight(self, simulated_seconds: float) -> float:
        """Light from 0 (midnight) to 1 (noon)."""
        return 0.5 - 0.5 * math.cos(math.tau * self.phase(simulated_seconds))

    def is_night(self, simulated_seconds: float) -> bool:
        return self.daylight(simulated_seconds) < self.night_below

    def day_number(self, simulated_seconds: float) -> int:
        """Whole midnights passed since the start, counting from 0."""
        return math.floor(self.start_phase + simulated_seconds / self.length_seconds)

    @property
    def night_fraction(self) -> float:
        """The share of each day that counts as night."""
        return math.acos(1.0 - 2.0 * self.night_below) / math.pi


@dataclass(frozen=True)
class PlantRules:
    """How neighbouring plants limit each other's growth (WORLD.8, ``TraitRules.plant_limits``).

    **Soil.** Within ``neighbourhood`` units of a plant, its neighbours (not the plant itself) hold
    some biomass per unit of ground. Once that reaches ``capacity`` the soil can feed no more: the
    plant keeps ``1 - density / capacity`` of its soil access (nothing, and so in practice
    starvation, at or above capacity). This is a logistic limit, and what keeps a population from
    running to the cap however fast the plants grow. It is the same for every plant on purpose: if
    root reach set the neighbourhood, evolution would shrink roots to dodge it. A plant's own
    biomass is left out so a lone plant of any size can grow to full size and seed (``WORLD.11``):
    counted in, a default plant (80 biomass) stalled at about 22 and no big plant ever seeded.

    **Light.** Each heavier neighbour whose canopy covers the plant adds ``1 - distance / canopy
    radius`` to its shade load, and the plant keeps ``1 / (1 + shade_strength * load)`` of the
    light, so tall plants shade seedlings.

    The effects are refreshed for one in every ``refresh_interval`` plants each tick, because
    plants do not move and the loads change slowly.
    """

    neighbourhood: float = 25.0
    capacity: float = 0.015
    """Biomass per unit of ground that the soil can feed."""
    shade_strength: float = 1.0
    refresh_interval: int = 10

    def __post_init__(self) -> None:
        if not (math.isfinite(self.neighbourhood) and self.neighbourhood > 0.0):
            raise ValueError(f"neighbourhood must be positive, got {self.neighbourhood}.")
        if not (math.isfinite(self.capacity) and self.capacity > 0.0):
            raise ValueError(f"capacity must be positive, got {self.capacity}.")
        if not (math.isfinite(self.shade_strength) and self.shade_strength >= 0.0):
            raise ValueError(f"shade_strength must be zero or more, got {self.shade_strength}.")
        if self.refresh_interval < 1:
            raise ValueError("refresh_interval must be at least 1.")


@dataclass(frozen=True)
class AttackRules:
    """Bites (``BRAIN.10``); ``TraitRules.attack`` holds them for a run (``TRAIT.11``)."""

    damage: float = 30.0
    """Damage of one bite at carnivore efficiency 1 against prey of the attacker's own mass; a
    full-health animal of average size has 200, so a good hunter needs several bites."""

    def __post_init__(self) -> None:
        if not math.isfinite(self.damage) or self.damage < 0.0:
            raise ValueError(f"damage must be zero or more, got {self.damage}.")

    def bite(self, carnivore_eff: float, attacker_mass: float, prey_mass: float) -> float:
        """The damage of one bite."""
        return self.damage * carnivore_eff * math.sqrt(attacker_mass / prey_mass)


@dataclass(frozen=True)
class CorpseRules:
    """What the dead leave (``WORLD.12``): meat that rots and that meat eaters smell and eat;
    ``TraitRules.corpses`` holds them for a run (``TRAIT.11``)."""

    meat_share: float = 0.5
    """Share of a dead animal's maximum energy that is left as meat."""
    bite: float = 25.0
    """Meat one animal can take from a corpse in one reference tick (an hour)."""
    rot_halflife: float = 72.0
    """Reference ticks (hours) for half the meat to rot away."""
    scent_meat: float = 100.0
    """A corpse with this much meat or more can be smelled as far as a meat eater's smell reaches;
    one with less is smelled from proportionally closer, like a plant's biomass."""
    gone_below: float = 1.0
    """A corpse with less meat than this is removed."""

    def __post_init__(self) -> None:
        for name in ("meat_share", "bite", "rot_halflife", "scent_meat", "gone_below"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be zero or more, got {value}.")
        if self.rot_halflife == 0.0 or self.scent_meat == 0.0:
            raise ValueError("rot_halflife and scent_meat must be above zero.")

    def meat(self, max_energy: float) -> float:
        """The meat a dead animal with this energy store leaves."""
        return self.meat_share * max_energy


@dataclass(frozen=True)
class ScentRules:
    """Smell trails (``SENSE.20``): animals and corpses leave scent on a coarse grid that fades, and
    animals smell it like any other source, classed by who left it. Off by default."""

    enabled: bool = False
    cell_size: float = 20.0
    """Side of a grid cell in world units: a trail is smelled as coming from the cell's centre."""
    deposit: float = 0.25
    """Scent an animal adds to its cell each reference tick (an hour), up to 1."""
    carrion_deposit: float = 0.5
    """Scent a corpse adds to its cell each reference tick; it lingers after the corpse has rotted."""
    half_life_hours: float = 24.0
    """Reference ticks (hours) for a trail to fade to half."""
    min_strength: float = 0.05
    """A trail weaker than this is forgotten."""
    deposit_interval: int = 4
    """An animal adds its scent every this many ticks (staggered by id) and four times as much, so a
    trail costs a quarter as much to lay; it has to be short against how long a cell takes to cross."""
    purge_interval: int = 24
    """Ticks between sweeps that drop forgotten trails (they have no effect before, only memory)."""

    def __post_init__(self) -> None:
        for name in ("cell_size", "half_life_hours"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value > 0.0):
                raise ValueError(f"{name} must be above zero, got {value}.")
        for name in ("deposit", "carrion_deposit"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0.0):
                raise ValueError(f"{name} must be zero or more, got {value}.")
        if not 0.0 <= self.min_strength < 1.0:
            raise ValueError(f"min_strength must be from 0 up to 1, got {self.min_strength}.")
        for name in ("deposit_interval", "purge_interval"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1.")


@dataclass(frozen=True)
class WorldRules:
    """The small settings of how the world applies its rules to organisms (``TRAIT.11``);
    ``TraitRules.world`` holds them for a run."""

    graze_amount: float = 20.0
    """Biomass an animal can take from a plant in one reference tick (an hour); a shorter or longer
    tick takes proportionally less or more."""
    mating_reach: float = 3.0
    """Two animals mate only if their centres are this close or closer."""
    birth_scatter: float = 1.0
    """A litter appears within this distance of its mother."""
    calls_enabled: bool = True
    """Whether animals can call (their brains' call outputs, paid for with ``call_energy_cost``).
    A call is made only by an animal with a call radius (the encoder gene) that can afford it,
    so a brain that calls on every tick starves itself; seeded founders do not call at all and
    calling has to be evolved. Turn it off to study a silent world."""
    scent: ScentRules = field(default_factory=ScentRules)
    """Smell trails that fade (``SENSE.20``)."""

    def __post_init__(self) -> None:
        for name in ("graze_amount", "mating_reach", "birth_scatter"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be zero or more, got {value}.")


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
    day_cycle: DayCycle | None = field(default_factory=DayCycle)
    """Light and night over simulated time; ``None`` means permanent full daylight and no sleep."""
    plant_limits: PlantRules = field(default_factory=PlantRules)
    """How crowded soil and shade limit plant growth (``WORLD.8``)."""
    sleep: SleepRules = field(default_factory=SleepRules)
    """Who sleeps at night and what sleep does (``WORLD.5``, ``TRAIT.10``)."""
    learning: LearningRules | None = field(default_factory=LearningRules)
    """Learning during life (``BRAIN.24``, ``TRAIT.10``); ``None`` turns it off."""
    attack: AttackRules = field(default_factory=AttackRules)
    """Bites (``BRAIN.10``, ``TRAIT.11``)."""
    corpses: CorpseRules = field(default_factory=CorpseRules)
    """What the dead leave (``WORLD.12``, ``TRAIT.11``)."""
    world: WorldRules = field(default_factory=WorldRules)
    """Grazing, mating reach, birth scatter and whether animals call (``TRAIT.11``)."""


DEFAULT_RULES = TraitRules()
"""The starting values everything uses unless it is given other rules."""
