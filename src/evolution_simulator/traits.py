"""Traits: the living phenotype built from a genome (haploid `DNA` or `DiploidDNA`).

Each traits class reads its genes once to fix the organism's static phenotype (mass, speed, senses,
upkeep and so on), then tracks runtime state (energy, health, age, drive flags) as the simulation
ticks. All numeric constants below are the original prototype's tuning values; they are meant to
be adjusted as the world model arrives.

Anything random takes an injected ``random.Random`` so runs are repeatable.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from evolution_simulator.brain import DEFAULT_BLUEPRINT, Brain
from evolution_simulator.brain_adapter import (
    BrainDecision,
    Percepts,
    Temperament,
    Wanderer,
    build_inputs,
    decode_outputs,
)
from evolution_simulator.dna import Genome
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.learning import Learner, LearningRules, State
from evolution_simulator.sense_genes import (
    direction_noise,
    sense_cost,
    vision_closeness_noise,
    vision_direction_noise,
    vision_reach,
    working_acuity,
)
from evolution_simulator.trait_defs import ANIMAL_TRAITS, PLANT_TRAITS

# Energy cost of thinking per tick, added to basal metabolism. Placeholders for the first brain
# (BRAIN.5, issue #25): they put a typical random brain at a few percent of the basal budget and are
# meant to move into the shared config object (TRAIT.3).
BRAIN_NEURON_COST: float = 0.0005
"""Per hidden or output neuron."""
BRAIN_CONNECTION_COST: float = 0.0001
"""Per active connection, a weight whose absolute value is above ``BRAIN_DEAD_ZONE``."""
BRAIN_DEAD_ZONE: float = 0.5
"""The brain's dead zone (``BRAIN.21``, ``BRAIN.23``): a weight at or below this is off, both for cost
and in ``Brain.decide``, so a connection pays only if it does something. At 0.5 a quarter of random
weights are off (the levels at about +-0.13 and +-0.4)."""
DECISION_INTERVAL: int = 1
"""Ticks between brain decisions (``BRAIN.11``) for an animal built with an explicit interval; the
default comes from the animal's ``reaction_time`` gene. Between decisions the animal keeps its last
one. Thinking costs are charged per tick divided by this, so a slower thinker is cheaper. Meant to
move into the shared config object (TRAIT.3)."""
INTERRUPT_PAIN: float = 0.05
"""Pain at or above this (1% of maximum health lost since the last decision) cuts the decision
interval short, so a hurt animal reacts at once (``BRAIN.22``)."""
PAIN_FULL_FRACTION: float = 0.2
"""Losing this fraction of maximum health (or more) since the last decision reads as full pain."""

# Time. Every per-tick rate in this file is "per reference tick" (REPRO.8): an hour of simulated
# time. The world multiplies the rates by ``dt = seconds_per_tick / REFERENCE_TICK_SECONDS``, so a
# different tick length changes how many ticks things take, not how long they take. Durations are
# kept in reference ticks (hours) too. Meant to move into the shared config object (TRAIT.3).
REFERENCE_TICK_SECONDS: float = 3600.0
TICKS_PER_DAY: float = 24.0
"""Reference ticks in a simulated day."""

# Wear and repair. Lifespan is the damage an animal can take divided by its wear per reference tick.
WEAR_BASE: float = 0.0362
"""Damage accumulated per reference tick with no repair and no drive. A default animal (size 0.5,
repair 0.5, drive 0.5) lives 8,765 reference ticks, about a simulated year."""
REPAIR_WEAR_DAMPING: float = 3.5
"""Wear is divided by ``1 + REPAIR_WEAR_DAMPING * somatic_maint``."""
DRIVE_WEAR: float = 0.6
"""Wear is multiplied by ``1 + DRIVE_WEAR * repro_drive``: a strong urge to mate shortens life."""

# Longevity trades against reproduction (TRAIT.6, docs/design/reproduction-genes.md). These are
# starting values to be tuned and meant to move into the shared config object (TRAIT.3).
REPAIR_COST: float = 0.20
"""Upkeep per tick at full repair; it grows with the square of ``somatic_maint`` (convex)."""
REPAIR_COST_EXPONENT: float = 2.0
REPAIR_BIRTH_SURCHARGE: float = 2.0
"""A parent's cost of a birth is multiplied by ``1 + REPAIR_BIRTH_SURCHARGE * somatic_maint``."""
REPAIR_COOLDOWN_STRETCH: float = 1.0
"""The cooldown is multiplied by ``1 + REPAIR_COOLDOWN_STRETCH * somatic_maint``."""

# Plants (REPRO.3).
PLANT_LIFESPAN_TICKS: int = 25_000
"""How long a plant lives, in ticks: about five times an average animal's. A configured constant until
plants get a lifespan gene (TRAIT.8, owner question 10 on issue #36); meant to move into the shared
config object (TRAIT.3)."""
SEED_BUDGET_SHARE: float = 0.35
"""Share of its biomass a plant can put into one burst of seeds (the prototype's fixed number)."""
SEED_READY_SHARE: float = 0.85
"""A plant is ready to seed once it holds this share of its full size (the prototype's number)."""

# Reproduction genes (REPRO.5, REPRO.8).
READINESS_UPKEEP: float = 0.03
"""Upkeep per tick for staying ready to breed, at ``READINESS_REFERENCE_DAYS`` between matings."""
READINESS_REFERENCE_DAYS: float = 5.0
READINESS_EXPONENT: float = 0.5
"""Readiness upkeep is ``READINESS_UPKEEP * (REFERENCE_DAYS / cooldown_days) ** EXPONENT``."""
DRIVE_UPKEEP: float = 0.05
DRIVE_UPKEEP_EXPONENT: float = 2.0
"""Upkeep per tick for the urge to mate: ``DRIVE_UPKEEP * repro_drive ** EXPONENT``."""
DRIVE_THRESHOLD_BASE: float = 0.85
DRIVE_THRESHOLD_SLOPE: float = 0.5
DRIVE_THRESHOLD_VITALITY: float = 0.2
DRIVE_THRESHOLD_RANGE: tuple[float, float] = (0.10, 0.95)
"""Energy share needed to start looking for a mate:
``clamp(BASE - SLOPE * drive - VITALITY * (1 - vitality), *RANGE)``."""
DRIVE_BOLDNESS: float = 0.3
"""While a mate is in view, fear is multiplied by ``1 - DRIVE_BOLDNESS * repro_drive``."""
SEX_DRIVE_MODIFIER: Mapping[int, float] = {2: 0.25, 3: -0.25}
"""The sex digit's second job: digit 2 raises the effective drive by 25%, digit 3 lowers it by 25%.
The sex itself is the digit modulo 2: 0 impregnates, 1 bears."""
MATURITY_SHARE: float = 0.06
"""An animal can first mate at this share of its expected lifespan."""
MATING_EFFORT: float = 0.03
"""Share of its energy store each partner spends on a mating, whether or not it takes."""
FERTILITY_CONCEPTION_BASE: float = 0.30
FERTILITY_CONCEPTION_SLOPE: float = 0.60
"""A mating takes with chance ``BASE + SLOPE * mean fertility of the two``."""
LITTER_MAX: int = 8
"""Litter size is ``1 + round(litter_capacity * (LITTER_MAX - 1))``: the bearer's ``fertility`` gene
scaled by her size and recovery genes."""
GESTATION_DAYS_BASE: float = 2.0
GESTATION_DAYS_SPAN: float = 18.0
"""Gestation is ``BASE + SPAN * fertility`` days (the bearer's gene)."""
FERTILITY_UPKEEP: float = 0.04
FERTILITY_UPKEEP_EXPONENT: float = 2.0
GESTATION_UPKEEP: float = 0.5
"""A pregnant bearer burns an extra ``GESTATION_UPKEEP * litter / LITTER_MAX`` of her basal metabolism."""
GESTATION_SLOWING: float = 0.3
"""A pregnant bearer's top speed is multiplied by ``1 - GESTATION_SLOWING * litter / LITTER_MAX``."""

# Recovery (TRAIT.7).
HEAL_HALFLIFE_DAYS: tuple[float, float] = (20.0, 1.0)
"""Half-life of lost health at recovery 0 and recovery 1 (log scale between)."""
HEAL_ENERGY_COST: float = 0.5
"""Energy spent per point of health healed."""
HEAL_MIN_ENERGY_RATIO: float = 0.5
"""Lost health only heals while the energy store is at least this full."""
RECOVERY_REGAIN: tuple[float, float] = (0.5, 2.0)
"""Multiplier on ``SleepRules.energy_regain`` at recovery 0 and recovery 1."""
RECOVERY_UPKEEP: float = 0.10
RECOVERY_UPKEEP_EXPONENT: float = 2.0

# =============================================================================
# Base Traits: Shared Organism Physiology, Vitality & Mortality
# =============================================================================


class BaseTraits:
    """Abstract base class managing fundamental organism physiology:

    mass scaling, energy pools, damage accumulation, vitality degradation,
    and life-cycle mortality checks.
    """

    def __init__(self, dna: Genome, phenotype: Mapping[str, float | int]) -> None:
        self.dna: Genome = dna
        # Primary trait values from the trait table (see trait_defs.py), fixed at birth.
        self.phenotype: Mapping[str, float | int] = phenotype

        # Core physiological metrics (to be scaled by subclasses)
        self.mass: float = 1.0
        self.max_damage_capacity: float = 100.0
        self.max_energy: float = 100.0
        self.basal_metabolism: float = 0.1

        # Dynamic runtime states
        self.current_energy: float = 0.0
        self.current_health: float = 0.0
        self.accumulated_damage: float = 0.0
        self.damage_since_decision: float = 0.0  # health lost, for the brain's pain input
        self.damage_taken: float = 0.0  # health lost over the whole life, for learning's reward
        self.vitality: float = 1.0  # Scales from 1.0 (prime) down to 0.0 (dead)
        self.age_ticks: int = 0
        self.is_alive: bool = True

    def apply_damage(self, amount: float) -> float:
        """Applies physical/toxin damage. Kills entity if health hits 0."""
        if not self.is_alive:
            return 0.0

        before = self.current_health
        self.current_health = max(0.0, self.current_health - amount)
        self.damage_since_decision += before - self.current_health
        self.damage_taken += before - self.current_health
        if self.current_health <= 0.0:
            self._die()
        else:
            self._refresh_vitality_dependents()
            self._update_needs_and_drives()
        return self.current_health

    def _die(self) -> None:
        """Internal teardown when life criteria fail."""
        self.is_alive = False
        self.current_energy = 0.0
        self.current_health = 0.0
        self._clear_flags()

    def _refresh_vitality_dependents(self) -> None:
        """Hook for subclasses to degrade capabilities as vitality drops."""

    def _update_needs_and_drives(self) -> None:
        """Hook for subclasses to recalculate internal urgency flags."""

    def _clear_flags(self) -> None:
        """Hook for subclasses to reset intent flags on death."""


# =============================================================================
# Animal Traits: Kinematics, 5 Senses, Epistasis & Dynamic Drives
# =============================================================================


class MatingResult(Enum):
    """What came of two animals trying to mate (``AnimalTraits.mate``)."""

    REFUSED = "refused"
    """One of them could not mate (cooldown, pregnant, same sex, cannot pay the effort): nothing was
    charged."""
    MISSED = "missed"
    """The effort was spent and both are on cooldown, but the mating did not take."""
    CONCEIVED = "conceived"
    """The bearer is pregnant."""


@dataclass
class Pregnancy:
    """A litter on the way. The genomes are fixed at conception; the bearer carries them for the
    gestation time and the children are born when ``remaining`` (reference ticks) reaches zero and
    both parents can pay."""

    children: tuple[Genome, ...]
    remaining: float
    father: AnimalTraits | None = None
    """The impregnating parent, who pays his share at the birth if he is still alive."""

    @property
    def litter(self) -> int:
        return len(self.children)

    @property
    def due(self) -> bool:
        return self.remaining <= 0.0


class AnimalTraits(BaseTraits):
    """Manages mobile entity phenotypes, 5-modality sensory systems,

    metabolic trade-offs, senescence degradation, and environmental drive flags.
    """

    def __init__(self, dna: Genome, decision_interval: int | None = None) -> None:
        if dna.layout != ANIMAL_LAYOUT:
            raise TypeError("AnimalTraits requires DNA with the animal layout.")
        t = ANIMAL_TRAITS.express(dna)
        if decision_interval is None:
            decision_interval = int(t["decision_interval"])
        if decision_interval < 1:
            raise ValueError(f"Decision interval must be at least 1 tick, got {decision_interval}.")
        super().__init__(dna, t)

        # ---------------------------------------------------------------------
        # 1. Epistatic Coupling & Allometric Scaling
        # ---------------------------------------------------------------------
        self.mass = float(t["mass"])
        self.max_damage_capacity = 100.0 * (1.0 + t["size"])
        self.max_energy = 100.0 * (1.0 + (2.0 * t["size"]))

        self.base_max_speed: float = (2.0 + (6.0 * t["speed"])) / (1.0 + (0.8 * t["size"]))
        self.base_turn_rate: float = (0.05 + (0.25 * t["agility"])) / (1.0 + (0.5 * t["size"]))

        # Sensory geometry
        # The eye (SENSE.16): the field gene is the half-angle, and working acuity is capped by it.
        self.acuity: float = working_acuity(t["sight_fov"], t["sight_acuity"])
        self.effective_sight_range: float = vision_reach(t["sight_reach"], self.acuity)
        self.fov_half_degrees: float = t["fov_half_degrees"]
        self.fov_degrees: float = 2.0 * self.fov_half_degrees
        self.hearing_range: float = t["hearing_range"]
        self.smell_sensitivity: float = t["smell"]
        self.smell_range: float = t["smell_range"]

        self.body_radius: float = 0.5 * (self.mass**0.33)
        self.tactile_range: float = self.body_radius * t["tactile_factor"]

        # Neural & Digestive Upkeep ("The Brain and Gut Tax")
        # Organs cost in proportion to the area they cover (SENSE.11).
        sensory_overhead = sense_cost(
            self.effective_sight_range,
            self.fov_degrees,
            self.hearing_range,
            self.smell_range,
            t["touch"],
            t["taste"],
            self.acuity,
        )
        self.vision_noise: float = vision_direction_noise(self.acuity)
        self.vision_closeness_noise: float = vision_closeness_noise(self.acuity)
        self.hearing_noise: float = direction_noise("hearing", t["hearing"])
        self.smell_noise: float = direction_noise("smell", t["smell"])
        self.gut_maintenance: float = 0.06 * ((t["herbivore_eff"] ** 2) + (t["carnivore_eff"] ** 2))
        # The brain is read from the genome once at birth, like the body.
        # Its size comes from the gates in the genome, its sharpness from the gain gene.
        self.innate_brain: Brain = DEFAULT_BLUEPRINT.build(
            dna.values("brain"), dead_zone=BRAIN_DEAD_ZONE, gain=t["brain_gain"]
        )
        # What it thinks with: the inherited brain plus what it has learned (BRAIN.24).
        self.brain: Brain = self.innate_brain
        self.curiosity: float = t["curiosity"]
        self.learning_rate: float = t["learning_rate"]
        self.learning_rules: LearningRules | None = LearningRules()
        """The world's learning settings; ``None`` turns learning off."""
        self.learner: Learner | None = None
        self.matings: int = 0
        self.wanderer: Wanderer = Wanderer()
        self.decision_interval: int = decision_interval
        self._decision: BrainDecision | None = None
        self._last_threat: float = 0.0
        self._decided_threat: float = 0.0  # what the brain saw when it last ran (BRAIN.22)
        self._decided_touch: bool = False
        """The threat closeness the last time the brain looked, for the learning log."""
        self._ticks_since_decision: int = 0
        self.brain_upkeep: float = (
            BRAIN_NEURON_COST * self.brain.neuron_count
            + BRAIN_CONNECTION_COST * self.brain.active_connections()
        ) / self.decision_interval
        self.repair_upkeep: float = REPAIR_COST * (t["somatic_maint"] ** REPAIR_COST_EXPONENT)
        self.readiness_upkeep: float = READINESS_UPKEEP * (
            (READINESS_REFERENCE_DAYS / t["cooldown_days"]) ** READINESS_EXPONENT
        )
        self.drive_upkeep: float = DRIVE_UPKEEP * (t["repro_drive"] ** DRIVE_UPKEEP_EXPONENT)
        self.fertility_upkeep: float = FERTILITY_UPKEEP * (
            t["fertility"] ** FERTILITY_UPKEEP_EXPONENT
        )
        self.recovery_upkeep: float = RECOVERY_UPKEEP * (t["recovery"] ** RECOVERY_UPKEEP_EXPONENT)
        self.basal_metabolism = (
            (0.18 * (self.mass**0.75))
            + self.repair_upkeep
            + self.readiness_upkeep
            + self.drive_upkeep
            + self.fertility_upkeep
            + self.recovery_upkeep
            + sensory_overhead
            + self.gut_maintenance
            + self.brain_upkeep
        )

        # Acoustic signaling
        self.call_radius: float = t["call_radius"]
        self.call_energy_cost: float = t["call_energy_cost"]

        # The sex digit: its value modulo 2 is the sex (0 impregnates, 1 bears), and digits 2 and 3
        # raise or lower the effective drive (REPRO.8). The behavioural offsets below are the
        # prototype's and are kept as they were.
        self.sex_type: int = int(t["sex_strategy"])
        self.sex: int = self.sex_type % 2
        self.drive_modifier: float = SEX_DRIVE_MODIFIER.get(self.sex_type, 0.0)
        self.effective_drive: float = min(
            1.0, max(0.0, t["repro_drive"] * (1.0 + self.drive_modifier))
        )
        self.base_fear_weight: float = t["fear"]
        self.base_aggression: float = t["aggression"]

        if self.sex_type == 0:  # Tournament Male
            self.base_aggression = min(1.0, self.base_aggression * 1.35)
            self.base_fear_weight *= 0.65
        elif self.sex_type == 3:  # Brooding Female
            self.base_fear_weight = min(1.0, self.base_fear_weight * 1.3)

        # ---------------------------------------------------------------------
        # 2. Dynamic Runtime States
        # ---------------------------------------------------------------------
        self.current_energy = self.max_energy * 0.75
        self.current_health = self.max_damage_capacity
        # A juvenile cannot mate until it has grown for a share of its expected lifespan. The
        # cooldown counts down in reference ticks, so it is a float.
        self.mating_cooldown: float = MATURITY_SHARE * self.lifespan_ticks
        self.pregnancy: Pregnancy | None = None

        # Environmental stimulus inputs
        self.env_threat_detected: bool = False
        self.env_target_size_ratio: float = 1.0
        self.env_local_density: float = 0.0
        self.env_tactile_collision: bool = False

        # Modulated outputs
        self.current_aggression: float = self.base_aggression
        self.current_max_speed: float = self.base_max_speed
        self.effective_herb_eff: float = t["herbivore_eff"]
        self.effective_carn_eff: float = t["carnivore_eff"]
        self.current_sight_range: float = self.effective_sight_range
        self.current_hearing_range: float = self.hearing_range

        # Behavioral flags
        self.flag_wants_food: bool = False
        self.flag_target_is_plant: bool = False
        self.flag_target_is_prey: bool = False
        self.flag_wants_mate: bool = False
        self.flag_in_fear: bool = False
        self.flag_wants_to_attack: bool = False
        self.flag_tactile_evade: bool = False
        self.flag_ready_to_signal: bool = False
        self.signal_to_emit: int | None = None

        self._refresh_vitality_dependents()
        self._update_needs_and_drives()  # so the drive flags are right at birth, not after tick one

    @property
    def wear_per_tick(self) -> float:
        """Damage added per reference tick: the base wear, quicker with a strong urge to mate, slowed
        by repair (``somatic_maint``)."""
        drive = 1.0 + (DRIVE_WEAR * self.phenotype["repro_drive"])
        return WEAR_BASE * drive / (1.0 + (REPAIR_WEAR_DAMPING * self.phenotype["somatic_maint"]))

    @property
    def lifespan_ticks(self) -> float:
        """Reference ticks (hours) until accumulated wear reaches the damage this body can take."""
        return self.max_damage_capacity / self.wear_per_tick

    @property
    def cooldown_ticks(self) -> float:
        """Reference ticks before this animal can mate again: the ``repro_cooldown`` gene in days,
        stretched by repair (the energy that goes into repair is not there for breeding)."""
        stretch = 1.0 + (REPAIR_COOLDOWN_STRETCH * self.phenotype["somatic_maint"])
        return self.phenotype["cooldown_days"] * TICKS_PER_DAY * stretch

    @property
    def litter_size(self) -> int:
        """Young per birth if this animal bears: the ``litter_capacity`` cluster, which is the
        ``fertility`` gene scaled by body size and recovery (``DNA.15``)."""
        return 1 + round(self.phenotype["litter_capacity"] * (LITTER_MAX - 1))

    @property
    def gestation_ticks(self) -> float:
        """Reference ticks a litter is carried if this animal bears."""
        days = GESTATION_DAYS_BASE + (GESTATION_DAYS_SPAN * self.phenotype["fertility"])
        return days * TICKS_PER_DAY

    @property
    def is_pregnant(self) -> bool:
        return self.pregnancy is not None

    @property
    def can_mate(self) -> bool:
        """Alive, grown, off cooldown and not pregnant."""
        return self.is_alive and self.mating_cooldown <= 0.0 and self.pregnancy is None

    @property
    def rest_regain_factor(self) -> float:
        """Multiplier on the energy regained at rest (``recovery``)."""
        low, high = RECOVERY_REGAIN
        return low + (high - low) * self.phenotype["recovery"]

    @property
    def heal_halflife_ticks(self) -> float:
        """Reference ticks for half of the lost health to heal (``recovery``, log scale)."""
        slow, fast = HEAL_HALFLIFE_DAYS
        return slow * (fast / slow) ** self.phenotype["recovery"] * TICKS_PER_DAY

    def _refresh_vitality_dependents(self) -> None:
        v = self.vitality
        health_ratio = max(0.0, self.current_health / self.max_damage_capacity)
        physical_factor = v * (0.35 + (0.65 * health_ratio))

        self.current_max_speed = self.base_max_speed * (0.3 + (0.7 * physical_factor))
        if self.pregnancy is not None:
            load = self.pregnancy.litter / LITTER_MAX
            self.current_max_speed *= 1.0 - (GESTATION_SLOWING * load)
        self.effective_herb_eff = self.phenotype["herbivore_eff"] * v
        self.effective_carn_eff = self.phenotype["carnivore_eff"] * v
        self.current_sight_range = self.effective_sight_range * (0.4 + (0.6 * v))
        self.current_hearing_range = self.hearing_range * (0.4 + (0.6 * v))

    def update_metabolism_and_aging(
        self, movement_speed_ratio: float = 0.0, dt: float = 1.0
    ) -> None:
        """Advances one simulation tick of ``dt`` reference ticks (an hour each): wear, energy burn,
        healing, the mating cooldown and the pregnancy all run on that clock. Movement is charged
        per tick, not per ``dt``: it follows the distance moved."""
        if not self.is_alive:
            return

        self.age_ticks += 1

        # Somatic repair dampens wear rate
        self.accumulated_damage += self.wear_per_tick * dt

        self.vitality = max(0.0, 1.0 - (self.accumulated_damage / self.max_damage_capacity))
        self._refresh_vitality_dependents()

        # Kinetic movement burn
        kinetic_burn = (movement_speed_ratio**2) * (0.35 * self.mass)
        upkeep = self.basal_metabolism
        if self.pregnancy is not None:
            upkeep *= 1.0 + (GESTATION_UPKEEP * self.pregnancy.litter / LITTER_MAX)
        self.current_energy -= (upkeep * dt) + kinetic_burn

        self._heal(dt)

        if self.mating_cooldown > 0.0:
            self.mating_cooldown = max(0.0, self.mating_cooldown - dt)
        if self.pregnancy is not None:
            self.pregnancy.remaining -= dt

        if self.current_energy <= 0.0 or self.vitality <= 0.0:
            self._die()
            return

        self._update_needs_and_drives()

    def _heal(self, dt: float) -> None:
        """Lost health heals with a half-life set by ``recovery``, while there is energy to spare,
        at ``HEAL_ENERGY_COST`` per point. Accumulated wear (ageing) does not heal."""
        lost = self.max_damage_capacity - self.current_health
        if lost <= 0.0 or self.current_energy < HEAL_MIN_ENERGY_RATIO * self.max_energy:
            return
        healed = lost * (1.0 - 0.5 ** (dt / self.heal_halflife_ticks))
        self.current_health += healed
        self.current_energy -= healed * HEAL_ENERGY_COST

    def set_environmental_stimuli(
        self,
        threat_detected: bool,
        target_size_ratio: float = 1.0,
        local_density: float = 0.0,
        tactile_contact: bool = False,
    ) -> None:
        """Feeds sensory world events into dynamic drive modulation."""
        self.env_threat_detected = threat_detected
        self.env_target_size_ratio = max(0.1, target_size_ratio)
        self.env_local_density = min(1.0, max(0.0, local_density))
        self.env_tactile_collision = tactile_contact

        if self.is_alive:
            self._update_needs_and_drives()

    def reset_behaviour(self) -> None:
        """Forget the cached brain decision and the wander turn, so the next ``think`` decides
        afresh. The world calls it when an animal falls asleep (``WORLD.5``)."""
        self._decision = None
        self._ticks_since_decision = 0
        self.wanderer.reset()

    @property
    def pain(self) -> float:
        """Health lost since the last decision as a share of the pain ceiling (0 to 1)."""
        return min(
            1.0, self.damage_since_decision / (PAIN_FULL_FRACTION * self.max_damage_capacity)
        )

    def _effective_fear(self, mate_in_view: bool = False) -> float:
        """Fear as it currently acts: the gene (after sex adjustment), stronger when worn down.
        A driven animal is bolder while a possible mate is in view (``DRIVE_BOLDNESS``)."""
        fear = self.base_fear_weight * (1.2 - (0.5 * self.vitality))
        if mate_in_view:
            fear *= 1.0 - (DRIVE_BOLDNESS * self.effective_drive)
        return fear

    def think(self, percepts: Percepts, rng: random.Random | None = None) -> BrainDecision:
        """Ask the brain what to do given what the world reports.

        Adds this animal's own state (energy, health, vitality, readiness to mate) to the world's
        ``percepts`` and returns the brain's decision. Its behaviour genes bend what the brain sees:
        aggression (as it currently acts, after hunger, crowding and size) scales how close prey
        looks and fear scales how close a threat looks (``BRAIN.14``). Pass ``rng`` to turn on the wander fallback
        (``BRAIN.16``): when the animal senses nothing or its brain outputs are all quiet, the
        decision comes back with a random turn and ``wandering`` set. Without ``rng`` the brain's
        decision is returned as is. Call it once per tick: the brain only runs every
        ``decision_interval`` calls (``BRAIN.11``) and the calls in between return the last decision
        (including its wander turn) without looking at the new percepts. It only reads state, apart
        from that and the wander turn it remembers: acting on the decision (and replacing the
        fixed-rule flags with it) belongs to the world loop.
        """
        learner = self._active_learner(rng)
        self._last_threat = percepts.threat_closeness
        state = self._learning_state(percepts.threat_closeness) if learner is not None else None
        if learner is not None and state is not None:
            learner.observe(state)
        if (
            self._decision is not None
            and self._ticks_since_decision < self.decision_interval
            and not self._interrupted(percepts)
        ):
            self._ticks_since_decision += 1
            return self._decision
        if not self.can_mate and (percepts.mate_closeness or percepts.mate_direction):
            # Not ready to breed: a possible mate does not pull on it (REPRO.5).
            percepts = replace(percepts, mate_closeness=0.0, mate_direction=0.0)
        inputs = build_inputs(
            percepts,
            energy_ratio=self.current_energy / self.max_energy,
            health_ratio=self.current_health / self.max_damage_capacity,
            vitality=self.vitality,
            ready_to_mate=self.can_mate,
            pain=self.pain,
            temperament=Temperament(
                aggression=self.current_aggression,
                fear=min(1.0, self._effective_fear(mate_in_view=percepts.mate_closeness > 0.0)),
                repro_drive=self.effective_drive,
            ),
        )
        self.damage_since_decision = 0.0
        self._decided_threat = percepts.threat_closeness
        self._decided_touch = bool(percepts.touching)
        hidden, proposal = self.brain.decide_with_hidden(inputs)
        action = self._explore(proposal, rng)
        if learner is not None and state is not None:
            learner.record(state, hidden, proposal, action)
        decision = decode_outputs(action)
        if rng is not None:
            decision = self.wanderer.apply(decision, percepts, rng)
        self._decision = decision
        self._ticks_since_decision = 1
        return decision

    def _interrupted(self, percepts: Percepts) -> bool:
        """Whether something happened since the brain last ran that should not wait for the next
        scheduled decision (``BRAIN.22``): it is hurting, a threat has appeared, or it is newly in
        contact with something."""
        if self.pain >= INTERRUPT_PAIN:
            return True
        if percepts.threat_closeness > 0.0 and self._decided_threat <= 0.0:
            return True
        return bool(percepts.touching) and not self._decided_touch

    @property
    def decided_touch(self) -> bool:
        """Whether the animal was in contact with something when its brain last ran; the world uses
        it to tell a new contact (which interrupts the decision interval) from a continuing one."""
        return self._decided_touch

    def interrupt(self) -> None:
        """Make the next ``cached_decision`` return ``None``, so the brain looks at the world
        again now instead of at the end of the interval."""
        self._ticks_since_decision = self.decision_interval

    def cached_decision(self, rng: random.Random | None = None) -> BrainDecision | None:
        """The decision to repeat this tick, or ``None`` if the brain must look at the world.

        Between brain runs (``decision_interval``) ``think`` returns the last decision and ignores
        the percepts, so the world can skip sensing for those ticks. An animal that is logging its
        day (``BRAIN.24``) logs the threat level it saw when the brain last ran. Counts the tick
        exactly as ``think`` does.
        """
        if self._decision is None or self._ticks_since_decision >= self.decision_interval:
            return None
        if self.pain >= INTERRUPT_PAIN:
            return None
        learner = self._active_learner(rng)
        if learner is not None:
            learner.observe(self._learning_state(self._last_threat))
        self._ticks_since_decision += 1
        return self._decision

    def _explore(self, proposal: tuple[float, ...], rng: random.Random | None) -> tuple[float, ...]:
        """The brain's proposal plus curiosity noise (``BRAIN.24``): each output moves by up to
        ``curiosity`` either way and stays in its range. Without ``rng`` there is no noise."""
        if rng is None or self.curiosity <= 0.0:
            return proposal
        signed = self.brain.shape.signed_outputs
        c = self.curiosity
        return tuple(
            max(-1.0 if signed[k] else 0.0, min(1.0, o + rng.uniform(-c, c)))
            for k, o in enumerate(proposal)
        )

    def _active_learner(self, rng: random.Random | None) -> Learner | None:
        """The learner, made on first use, if this animal logs its day: learning is on in the
        world, it has a learning rate, and noise is possible (nothing can be learned without it)."""
        rules = self.learning_rules
        if rules is None or rng is None or self.learning_rate <= 0.0 or self.curiosity <= 0.0:
            return None
        if self.learner is None:
            self.learner = Learner(self.brain.shape.hidden, self.brain.shape.outputs, rules)
        return self.learner

    def _learning_state(self, threat: float) -> State:
        return State(
            energy=self.current_energy / self.max_energy,
            damage=self.damage_taken / self.max_damage_capacity,
            matings=self.matings,
            threat=threat,
        )

    def learn_night(self) -> bool:
        """The nightly learning step (``BRAIN.24``), run when the animal falls asleep: learn from
        the day's log, switch to the inherited brain plus what is now learned, empty the log.
        Returns whether the brain changed. The genome is never touched."""
        learner = self.learner
        if learner is None or not self.is_alive:
            return False
        state = State(
            energy=self.current_energy / self.max_energy,
            damage=self.damage_taken / self.max_damage_capacity,
            matings=self.matings,
            threat=0.0,
        )
        if not learner.sleep(state, self.learning_rate):
            return False
        weights, biases = learner.offsets
        self.brain = self.innate_brain.with_output_offsets(weights, biases)
        return True

    def _update_needs_and_drives(self) -> None:
        energy_ratio = self.current_energy / self.max_energy
        starvation_factor = max(0.0, 1.0 - energy_ratio)

        # Dynamic Aggression (Nature + Nurture)
        hunger_aggression_boost = 1.0 + (1.6 * (starvation_factor**2))
        crowd_aggression_boost = 1.0 + (0.4 * self.env_local_density)
        size_confidence = min(2.0, max(0.2, self.env_target_size_ratio))

        modulated_aggression = (
            self.base_aggression
            * hunger_aggression_boost
            * crowd_aggression_boost
            * size_confidence
        )
        self.current_aggression = min(1.0, max(0.0, modulated_aggression))

        # Tactile Reflex
        self.flag_tactile_evade = self.env_tactile_collision and (self.phenotype["touch"] > 0.1)

        # Fear vs Aggression Fight-or-Flight
        if self.env_threat_detected:
            effective_fear = self._effective_fear()
            if effective_fear > (self.current_aggression * size_confidence):
                self.flag_in_fear = True
                self.flag_wants_to_attack = False
            else:
                self.flag_in_fear = False
                self.flag_wants_to_attack = True
        else:
            self.flag_in_fear = False
            self.flag_wants_to_attack = (
                self.current_aggression > 0.4
                and starvation_factor > 0.3
                and self.effective_carn_eff > 0.1
            )

        # Hunger
        if energy_ratio < 0.5:
            self.flag_wants_food = True
            self.flag_target_is_plant = self.effective_herb_eff > 0.1
            self.flag_target_is_prey = (
                self.effective_carn_eff > 0.1 and self.current_aggression > 0.2
            )
        else:
            self.flag_wants_food = False
            self.flag_target_is_plant = False
            self.flag_target_is_prey = False

        # Mating urgency: the drive gene lowers the energy needed to start looking, and so does
        # failing health (senescence desperation).
        low, high = DRIVE_THRESHOLD_RANGE
        mating_threshold = min(
            high,
            max(
                low,
                DRIVE_THRESHOLD_BASE
                - (DRIVE_THRESHOLD_SLOPE * self.effective_drive)
                - (DRIVE_THRESHOLD_VITALITY * (1.0 - self.vitality)),
            ),
        )
        self.flag_wants_mate = (
            energy_ratio >= mating_threshold and self.can_mate and not self.flag_in_fear
        )

        # Communication
        self.flag_ready_to_signal = False
        self.signal_to_emit = None

        if (
            self.phenotype["encoder_fidelity"] > 0.05
            and self.current_energy > self.call_energy_cost
        ):
            if self.flag_in_fear:
                self.flag_ready_to_signal = True
                self.signal_to_emit = 2  # Alarm / Flee
            elif self.flag_wants_mate and (1.0 - self.vitality) > 0.3:
                self.flag_ready_to_signal = True
                self.signal_to_emit = 0  # Mating Call

    def _clear_flags(self) -> None:
        self.flag_wants_food = False
        self.flag_target_is_plant = False
        self.flag_target_is_prey = False
        self.flag_wants_mate = False
        self.flag_in_fear = False
        self.flag_wants_to_attack = False
        self.flag_tactile_evade = False
        self.flag_ready_to_signal = False
        self.signal_to_emit = None

    def inspect_food(self, toxicity: float, rng: random.Random) -> bool:
        """Uses taste to detect toxins before consumption."""
        detection_probability = min(1.0, toxicity * (0.2 + (0.8 * self.phenotype["taste"])))
        return rng.random() < detection_probability

    def feed(self, biomass: float, is_meat: bool, toxicity: float = 0.0) -> float:
        """Processes food intake, applying toxic damage and extracting calories."""
        if not self.is_alive:
            return 0.0

        if toxicity > 0.0:
            poison_damage = toxicity * (1.0 - (0.5 * self.phenotype["taste"])) * 25.0
            self.apply_damage(poison_damage)
            if not self.is_alive:
                return 0.0

        if is_meat:
            efficiency = self.effective_carn_eff * (1.0 - (0.4 * self.phenotype["herbivore_eff"]))
        else:
            efficiency = self.effective_herb_eff * (1.0 - (0.4 * self.phenotype["carnivore_eff"]))

        energy_gain = biomass * efficiency
        self.current_energy = min(self.max_energy, self.current_energy + energy_gain)

        self._refresh_vitality_dependents()
        self._update_needs_and_drives()
        return energy_gain

    @staticmethod
    def mate(impregnator: AnimalTraits, bearer: AnimalTraits, rng: random.Random) -> MatingResult:
        """One mating between a sex-0 animal (``impregnator``) and a sex-1 animal (``bearer``).

        Both must be able to mate and have more energy than the mating effort, or nothing happens
        (``REFUSED``). Otherwise each spends ``MATING_EFFORT`` of its store and starts its cooldown,
        and the mating takes with chance ``0.30 + 0.60 * mean fertility``. If it takes, the bearer
        is pregnant: the litter's genomes are fixed now, its size and the gestation time come from
        the bearer's ``fertility`` gene, and her cooldown starts at the birth instead.
        """
        if impregnator.sex != 0 or bearer.sex != 1:
            return MatingResult.REFUSED
        for animal in (impregnator, bearer):
            if not animal.can_mate or animal.current_energy <= MATING_EFFORT * animal.max_energy:
                return MatingResult.REFUSED
        for animal in (impregnator, bearer):
            animal.current_energy -= MATING_EFFORT * animal.max_energy
            animal.mating_cooldown = animal.cooldown_ticks
            animal.matings += 1
        mean_fertility = 0.5 * (impregnator.phenotype["fertility"] + bearer.phenotype["fertility"])
        chance = FERTILITY_CONCEPTION_BASE + (FERTILITY_CONCEPTION_SLOPE * mean_fertility)
        taken = rng.random() < chance
        if taken:
            children = tuple(
                bearer.dna.reproduce(impregnator.dna, rng) for _ in range(bearer.litter_size)
            )
            bearer.mating_cooldown = 0.0
            bearer.pregnancy = Pregnancy(children, bearer.gestation_ticks, impregnator)
            bearer._refresh_vitality_dependents()
        for animal in (impregnator, bearer):
            animal._update_needs_and_drives()
        return MatingResult.CONCEIVED if taken else MatingResult.MISSED

    def birth_cost(self, newborn_max_energies: Iterable[float]) -> float:
        """What this parent pays for a litter: its own ``care_fraction`` over two of each newborn's
        energy store, times a surcharge for repair (the disposable-soma trade-off: energy put into
        repair is not there for the young). The newborns get the unsurcharged amount."""
        surcharge = 1.0 + (REPAIR_BIRTH_SURCHARGE * self.phenotype["somatic_maint"])
        return 0.5 * self.phenotype["care_fraction"] * sum(newborn_max_energies) * surcharge

    @staticmethod
    def give_birth(bearer: AnimalTraits, newborns: Sequence[AnimalTraits]) -> bool:
        """Deliver a pregnancy that is due. Each parent pays ``birth_cost`` for the litter; the
        father pays only if he is still alive. If any payer cannot afford it (strictly more energy
        than the cost) nobody is charged, the pregnancy goes on and this returns False. Otherwise
        each newborn starts with half of each paying parent's ``care_fraction`` times its own energy
        store (the mean of the two when both pay), and the bearer's cooldown starts."""
        pregnancy = bearer.pregnancy
        if pregnancy is None or not bearer.is_alive or not pregnancy.due:
            return False
        father = pregnancy.father
        payers = [bearer]
        if father is not None and father.is_alive:
            payers.append(father)
        energies = [newborn.max_energy for newborn in newborns]
        for parent in payers:
            if parent.current_energy <= parent.birth_cost(energies):
                return False
        share = 0.0
        for parent in payers:
            parent.current_energy -= parent.birth_cost(energies)
            share += 0.5 * parent.phenotype["care_fraction"]
        for newborn in newborns:
            newborn.current_energy = share * newborn.max_energy
            newborn._update_needs_and_drives()
        bearer.pregnancy = None
        bearer.mating_cooldown = bearer.cooldown_ticks
        bearer._refresh_vitality_dependents()
        for parent in payers:
            parent._update_needs_and_drives()
        return True

    def trigger_signal_emission(self) -> int | None:
        if self.flag_ready_to_signal and self.signal_to_emit is not None:
            self.current_energy -= self.call_energy_cost
            signal = self.signal_to_emit
            self.flag_ready_to_signal = False
            self.signal_to_emit = None
            return signal
        return None


# =============================================================================
# Plant Traits: Photosynthesis, Canopy, Toxicity Upkeep & Seed Clutches
# =============================================================================


class PlantTraits(BaseTraits):
    """Manages sessile plant phenotypes: photosynthetic biomass accumulation,

    canopy light shading, chemical defense expenditure, and seed burst triggers.
    """

    def __init__(self, dna: Genome) -> None:
        if dna.layout != PLANT_LAYOUT:
            raise TypeError("PlantTraits requires DNA with the plant layout.")
        t = PLANT_TRAITS.express(dna)
        super().__init__(dna, t)

        # ---------------------------------------------------------------------
        # 1. Structural Scaling & Phenotypes
        # ---------------------------------------------------------------------
        self.max_biomass: float = float(t["max_biomass"])
        self.max_energy = self.max_biomass
        self.max_damage_capacity = self.max_biomass * 0.8
        self.mass = self.max_biomass * 0.5

        # Canopy radius and root competition footprint
        self.canopy_radius: float = t["canopy_radius"]
        self.root_radius: float = t["root_radius"]

        # Reproduction: Dispersal distance and seed quantity
        self.dispersal_radius: float = t["dispersal_radius"]
        self.seed_count: int = int(t["seed_count"])
        """The most seeds one burst can hold (the clutch gene); the budget may pay for fewer."""
        self.seed_provision: float = t["seed_provision"]

        # Toxicity intensity (0.0 to 1.0) and ongoing chemical defense cost
        self.toxicity: float = t["toxicity"]
        self.chemical_defense_tax: float = 0.05 * (self.toxicity**1.5)

        # Baseline photosynthetic intake per tick
        self.base_growth_rate: float = t["base_growth_rate"]
        self.basal_metabolism = (0.02 * (self.mass**0.5)) + self.chemical_defense_tax

        # ---------------------------------------------------------------------
        # 2. Dynamic Runtime States
        # ---------------------------------------------------------------------
        # Plants sprout as fragile seedlings with a small starter reserve
        self.current_biomass: float = self.max_biomass * 0.15
        self.current_energy = self.current_biomass
        self.current_health = self.max_damage_capacity * 0.5
        self.growth_cooldown: int = 0

        # Environmental factors: Sunlight availability (0.0 to 1.0) and soil competition
        self.sunlight_factor: float = 1.0
        self.soil_competition_factor: float = 1.0

        # Behavioral/Lifecycle flag. A seedling is a juvenile for one seeding interval, like an
        # animal (REPRO.5): the gene that sets the gap between bursts sets the age of the first.
        self.flag_ready_to_seed: bool = False
        self.seed_cooldown: int = self.seeding_interval_ticks

        # A seedling's vitality follows its starting health, not the default of 1.0.
        self._refresh_vitality_dependents()
        self._update_needs_and_drives()

    @property
    def lifespan_ticks(self) -> int:
        """Ticks a plant lives (a configured constant for now: no lifespan gene yet)."""
        return PLANT_LIFESPAN_TICKS

    @property
    def seeding_interval_ticks(self) -> int:
        """Shortest gap between seed bursts, and the age of the first, as a share of the lifespan
        (the ``seeding_interval`` gene)."""
        return max(1, round(self.phenotype["seeding_fraction"] * self.lifespan_ticks))

    @property
    def seed_budget(self) -> float:
        """Biomass this plant can put into a burst of seeds right now."""
        return SEED_BUDGET_SHARE * self.current_biomass

    def seed_capacity(self) -> int:
        """How many seeds the budget pays for if each starts with ``seed_provision`` of this
        plant's own full size, up to the clutch the genes allow."""
        per_seed = self.seed_provision * self.max_biomass
        return max(0, min(self.seed_count, int(self.seed_budget / per_seed)))

    def _refresh_vitality_dependents(self) -> None:
        health_ratio = max(0.0, self.current_health / self.max_damage_capacity)
        self.vitality = health_ratio

    def set_environmental_conditions(
        self, sunlight: float = 1.0, soil_competition: float = 1.0
    ) -> None:
        """Sets external factors from the simulation tick:

        - sunlight: reduced by overhead canopies of taller neighboring plants.
        - soil_competition: reduced if neighboring root radii overlap.
        """
        self.sunlight_factor = min(1.0, max(0.05, sunlight))
        self.soil_competition_factor = min(1.0, max(0.05, soil_competition))

    def update_growth_and_metabolism(self) -> None:
        """Advances one tick of photosynthesis, chemical defense upkeep, and maturation."""
        if not self.is_alive:
            return

        self.age_ticks += 1
        if self.age_ticks >= self.lifespan_ticks:
            self._die()  # old age
            return
        if self.seed_cooldown > 0:
            self.seed_cooldown -= 1

        # Photosynthetic intake scaled by growth gene, light, and soil access
        photosynthetic_gain = (
            self.base_growth_rate
            * self.sunlight_factor
            * self.soil_competition_factor
            * self.vitality
        )

        net_growth = photosynthetic_gain - self.basal_metabolism

        # Apply net energy to biomass
        if net_growth > 0:
            self.current_biomass = min(self.max_biomass, self.current_biomass + net_growth)
            self.current_energy = self.current_biomass
            # Passive tissue repair when growing
            if self.current_health < self.max_damage_capacity:
                self.current_health = min(
                    self.max_damage_capacity, self.current_health + (net_growth * 0.5)
                )
        else:
            # Deficit burns stored biomass to sustain metabolic tax
            self.current_biomass += net_growth
            self.current_energy = max(0.0, self.current_biomass)
            if self.current_biomass <= 0.0:
                self._die()
                return

        self._refresh_vitality_dependents()
        self._update_needs_and_drives()

    def _update_needs_and_drives(self) -> None:
        # A plant is ready to drop seeds when it is grown, healthy, past its seeding cooldown and
        # can pay for at least one seed
        self.flag_ready_to_seed = (
            self.current_biomass >= (self.max_biomass * SEED_READY_SHARE)
            and self.vitality > 0.4
            and self.seed_cooldown == 0
            and self.seed_capacity() >= 1
        )

    def _clear_flags(self) -> None:
        self.flag_ready_to_seed = False

    def graze(self, amount: float) -> tuple[float, float]:
        """Herbivore grazing event.

        Returns (biomass_consumed, toxicity_level).
        """
        if not self.is_alive:
            return (0.0, 0.0)

        actual_consumed = min(self.current_biomass, amount)
        self.current_biomass -= actual_consumed
        self.current_energy = self.current_biomass

        # Grazing inflicts direct physical damage to plant structure
        self.apply_damage(actual_consumed * 0.75)

        if self.current_biomass <= 2.0:
            self._die()

        return (actual_consumed, self.toxicity)

    def set_starting_biomass(self, biomass: float) -> None:
        """Give a new plant the biomass its parent put into the seed, up to its own full size."""
        self.current_biomass = min(self.max_biomass, max(0.0, biomass))
        self.current_energy = self.current_biomass
        self._update_needs_and_drives()

    def launch_seeds(self, seeds: Sequence[PlantTraits]) -> float:
        """Pay for a burst of seeds and start the seeding cooldown. Each seed starts with this
        plant's ``seed_provision`` of its own full size, scaled down together if their total would
        be more than the budget (a seed that mutated bigger costs more). Returns the biomass spent."""
        wanted = [self.seed_provision * seed.max_biomass for seed in seeds]
        total = sum(wanted)
        scale = min(1.0, self.seed_budget / total) if total > 0.0 else 0.0
        for seed, amount in zip(seeds, wanted):
            seed.set_starting_biomass(amount * scale)
        spent = total * scale
        self.current_biomass -= spent
        self.current_energy = self.current_biomass
        self.seed_cooldown = self.seeding_interval_ticks
        self.flag_ready_to_seed = False
        return spent
