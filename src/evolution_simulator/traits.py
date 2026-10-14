"""Traits: the living phenotype built from a genome (haploid `DNA` or `DiploidDNA`).

Each traits class reads its genes once to fix the organism's static phenotype (mass, speed, senses,
upkeep and so on), then tracks runtime state (energy, health, age, drive flags) as the simulation
ticks. Every tuning number is in the rules tree of ``config.py`` (``TraitRules``, ``TRAIT.3``): an
organism takes ``rules=`` and reads them from there, so nothing here is a constant.

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
    BrainTrace,
    Percepts,
    Temperament,
    Wanderer,
    build_inputs,
    decode_outputs,
)
from evolution_simulator.config import DEFAULT_RULES, TraitRules
from evolution_simulator.deaths import DeathCause
from evolution_simulator.dna import Genome
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.learning import Learner, LearningRules, State
from evolution_simulator.lineage import family_key
from evolution_simulator.sense_genes import (
    direction_noise,
    sense_cost,
    vision_closeness_noise,
    vision_direction_noise,
    vision_reach,
    working_acuity,
)
from evolution_simulator.trait_defs import ANIMAL_TRAITS, CARE_FRACTION_RANGE, PLANT_TRAITS

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
        self.death_cause: DeathCause | None = None
        """Why it died, once it has (``DeathCause``); ``None`` while it lives."""

    def apply_damage(self, amount: float, cause: DeathCause = DeathCause.DAMAGE) -> float:
        """Applies physical/toxin damage. Kills entity if health hits 0, of ``cause``."""
        if not self.is_alive:
            return 0.0

        before = self.current_health
        self.current_health = max(0.0, self.current_health - amount)
        self.damage_since_decision += before - self.current_health
        self.damage_taken += before - self.current_health
        if self.current_health <= 0.0:
            self._die(cause)
        else:
            self._refresh_vitality_dependents()
            self._update_needs_and_drives()
        return self.current_health

    def _die(self, cause: DeathCause) -> None:
        """Internal teardown when life criteria fail."""
        self.is_alive = False
        self.death_cause = cause
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

    def __init__(
        self,
        dna: Genome,
        decision_interval: int | None = None,
        rules: TraitRules = DEFAULT_RULES,
        dt: float = 1.0,
    ) -> None:
        if dna.layout != ANIMAL_LAYOUT:
            raise TypeError("AnimalTraits requires DNA with the animal layout.")
        t = ANIMAL_TRAITS.express(dna)
        if dt <= 0.0:
            raise ValueError(f"dt must be above zero, got {dt}.")
        if decision_interval is None:
            # The gene is a time in reference ticks (hours); a shorter world tick means more ticks.
            decision_interval = max(
                1, round(t["decision_interval"] * rules.brain.interval_scale / dt)
            )
        if decision_interval < 1:
            raise ValueError(f"Decision interval must be at least 1 tick, got {decision_interval}.")
        super().__init__(dna, t)
        self.rules: TraitRules = rules
        """Every tuning constant this animal lives by (``config.py``)."""
        self.dt: float = dt
        """Reference ticks (hours) per world tick, which the decision interval and the learning
        window are counted in (``WORLD.16``)."""
        body = rules.body

        # ---------------------------------------------------------------------
        # 1. Epistatic Coupling & Allometric Scaling
        # ---------------------------------------------------------------------
        self.mass = float(t["mass"])
        self.max_damage_capacity = body.damage_capacity * (1.0 + t["size"])
        self.max_energy = body.energy_capacity * (1.0 + (body.energy_size_gain * t["size"]))

        self.base_max_speed: float = (body.speed_base + (body.speed_span * t["speed"])) / (
            1.0 + (body.speed_size_drag * t["size"])
        )
        self.base_turn_rate: float = (body.turn_base + (body.turn_span * t["agility"])) / (
            1.0 + (body.turn_size_drag * t["size"])
        )

        # Sensory geometry
        # The eye (SENSE.16): the field gene is the half-angle, and working acuity is capped by it.
        self.acuity: float = working_acuity(t["sight_fov"], t["sight_acuity"])
        self.effective_sight_range: float = vision_reach(
            t["sight_reach"], self.acuity, rules.organs
        )
        self.fov_half_degrees: float = t["fov_half_degrees"]
        self.fov_degrees: float = 2.0 * self.fov_half_degrees
        self.hearing_range: float = t["hearing_range"]
        self.smell_sensitivity: float = t["smell"]
        self.smell_range: float = t["smell_range"]

        self.body_radius: float = body.body_radius_scale * (self.mass**body.body_radius_exponent)
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
            rules.organs,
        )
        self.vision_noise: float = vision_direction_noise(self.acuity, rules.organs)
        self.vision_closeness_noise: float = vision_closeness_noise(self.acuity, rules.organs)
        self.hearing_noise: float = direction_noise("hearing", t["hearing"], rules.organs)
        self.smell_noise: float = direction_noise("smell", t["smell"], rules.organs)
        self.gut_maintenance: float = body.gut_cost * (
            (t["herbivore_eff"] ** 2) + (t["carnivore_eff"] ** 2)
        )
        # The brain is read from the genome once at birth, like the body.
        # Its size comes from the gates in the genome, its sharpness from the gain gene.
        self.innate_brain: Brain = DEFAULT_BLUEPRINT.build(
            dna.values("brain"), dead_zone=rules.brain.dead_zone, gain=t["brain_gain"]
        )
        # What it thinks with: the inherited brain plus what it has learned (BRAIN.24).
        self.brain: Brain = self.innate_brain
        self.curiosity: float = t["curiosity"]
        self.learning_rate: float = t["learning_rate"]
        self.learning_rules: LearningRules | None = self.rules.learning
        """The run's learning settings (``TraitRules.learning``); ``None`` turns learning off."""
        self.learner: Learner | None = None
        self.matings: int = 0
        self.wanderer: Wanderer = Wanderer()
        self.decision_interval: int = decision_interval
        self.trace_brain: bool = False
        self.family_key: tuple[float, float] = family_key(dna)
        """Two numbers that stay close for relatives (``lineage.family_key``), worked out once."""
        """Keep ``brain_trace`` up to date; the world turns it on for the selected animal only."""
        self.brain_trace: BrainTrace | None = None
        """The inputs, hidden values and outputs of the last brain run, while ``trace_brain``."""
        self._decision: BrainDecision | None = None
        self._last_threat: float = 0.0
        self._decided_threat: float = 0.0  # what the brain saw when it last ran (BRAIN.22)
        self._decided_touch: bool = False
        """The threat closeness the last time the brain looked, for the learning log."""
        self._ticks_since_decision: int = 0
        self.brain_upkeep: float = (
            rules.brain.neuron_cost * self.brain.neuron_count
            + rules.brain.connection_cost * self.brain.active_connections()
        ) / (self.decision_interval * dt)
        life, repro, recovery = rules.life, rules.reproduction, rules.recovery
        # The sex digit: its value modulo 2 is the sex (0 impregnates, 1 bears), and digits 2 and 3
        # raise or lower the effective drive (REPRO.8), which is what the drive costs in upkeep and
        # wear (TRAIT.9), so those digits pay for it. The behavioural offsets further down are the
        # prototype's and are kept as they were.
        self.sex_type: int = int(t["sex_strategy"])
        self.sex: int = self.sex_type % 2
        self.drive_modifier: float = dict(repro.sex_drive_modifier).get(self.sex_type, 0.0)
        self.effective_drive: float = min(
            1.0, max(0.0, t["repro_drive"] * (1.0 + self.drive_modifier))
        )
        self.repair_upkeep: float = life.repair_cost * (
            t["somatic_maint"] ** life.repair_cost_exponent
        )
        self.readiness_upkeep: float = repro.readiness_upkeep * (
            (repro.readiness_reference_days / t["cooldown_days"]) ** repro.readiness_exponent
        )
        self.drive_upkeep: float = repro.drive_upkeep * (
            self.effective_drive**repro.drive_upkeep_exponent
        )
        self.fertility_upkeep: float = repro.fertility_upkeep * (
            t["fertility"] ** repro.fertility_upkeep_exponent
        )
        self.recovery_upkeep: float = recovery.upkeep * (t["recovery"] ** recovery.upkeep_exponent)
        self.agility_upkeep: float = body.agility_cost * (t["agility"] ** 2)
        self.temperament_upkeep: float = body.temperament_cost * (
            t["aggression"] ** 2 + t["fear"] ** 2
        )
        self.learning_upkeep: float = rules.brain.learning_cost * t["learning_rate"]
        self.basal_metabolism = (
            (body.basal_scale * (self.mass**body.basal_exponent))
            + self.repair_upkeep
            + self.readiness_upkeep
            + self.drive_upkeep
            + self.fertility_upkeep
            + self.recovery_upkeep
            + self.agility_upkeep
            + self.temperament_upkeep
            + self.learning_upkeep
            + sensory_overhead
            + self.gut_maintenance
            + self.brain_upkeep
        )

        # Acoustic signaling
        self.call_radius: float = t["call_radius"]
        self.call_energy_cost: float = t["call_energy_cost"]

        behaviour = rules.behaviour
        self.base_fear_weight: float = t["fear"]
        self.base_aggression: float = t["aggression"]

        if self.sex_type == 0:  # Tournament Male
            self.base_aggression = min(
                1.0, self.base_aggression * behaviour.tournament_male_aggression
            )
            self.base_fear_weight *= behaviour.tournament_male_fear
        elif self.sex_type == 3:  # Brooding Female
            self.base_fear_weight = min(1.0, self.base_fear_weight * behaviour.brooding_female_fear)

        # ---------------------------------------------------------------------
        # 2. Dynamic Runtime States
        # ---------------------------------------------------------------------
        self.current_energy = self.max_energy * body.start_energy
        self.current_health = self.max_damage_capacity
        # A juvenile cannot mate until it has grown for a share of its expected lifespan. The
        # cooldown counts down in reference ticks, so it is a float.
        self.mating_cooldown: float = repro.maturity_share * self.lifespan_ticks
        self.pregnancy: Pregnancy | None = None
        self.tiredness: float = 0.0
        """Time awake as a share of a day, 0 to 1; the world sets it (``SENSE.14``)."""

        # Environmental stimulus inputs
        self.env_target_size_ratio: float = 1.0
        self.env_local_density: float = 0.0

        # Modulated outputs
        self.current_aggression: float = self.base_aggression
        self.current_max_speed: float = self.base_max_speed
        self.effective_herb_eff: float = t["herbivore_eff"]
        self.effective_carn_eff: float = t["carnivore_eff"]
        self.current_sight_range: float = self.effective_sight_range
        self.current_hearing_range: float = self.hearing_range

        self._refresh_vitality_dependents()
        self._update_needs_and_drives()  # so the drive flags are right at birth, not after tick one

    @property
    def wear_per_tick(self) -> float:
        """Damage added per reference tick: the base wear, quicker with a strong urge to mate, slowed
        by repair (``somatic_maint``)."""
        life = self.rules.life
        drive = 1.0 + (life.drive_wear * self.effective_drive)
        return (
            life.wear_base
            * drive
            / (1.0 + (life.repair_wear_damping * self.phenotype["somatic_maint"]))
        )

    @property
    def lifespan_ticks(self) -> float:
        """Reference ticks (hours) until accumulated wear reaches the damage this body can take."""
        return self.max_damage_capacity / self.wear_per_tick

    @property
    def lived_ticks(self) -> float:
        """Reference ticks (hours) lived so far (wear grows with time, whatever the tick)."""
        return self.accumulated_damage / self.wear_per_tick

    @property
    def parenting(self) -> float:
        """The ``parenting`` gene as 0 to 1 (the care fraction's place in its range)."""
        low, high = CARE_FRACTION_RANGE
        return (self.phenotype["care_fraction"] - low) / (high - low)

    @property
    def dependence_ticks(self) -> float:
        """How long, in reference ticks, this animal's young depend on it after birth."""
        return self.parenting * self.rules.reproduction.young_dependence * self.lifespan_ticks

    @property
    def cooldown_ticks(self) -> float:
        """Reference ticks before this animal can mate again: the ``repro_cooldown`` gene in days,
        stretched by repair (the energy that goes into repair is not there for breeding)."""
        stretch = 1.0 + (self.rules.life.repair_cooldown_stretch * self.phenotype["somatic_maint"])
        return self.phenotype["cooldown_days"] * self.rules.time.ticks_per_day * stretch

    @property
    def litter_size(self) -> int:
        """Young per birth if this animal bears: the ``litter_capacity`` cluster, which is the
        ``fertility`` gene scaled by body size and recovery (``DNA.15``)."""
        return 1 + round(
            self.phenotype["litter_capacity"] * (self.rules.reproduction.litter_max - 1)
        )

    @property
    def gestation_ticks(self) -> float:
        """Reference ticks a litter is carried if this animal bears."""
        repro = self.rules.reproduction
        days = repro.gestation_days_base + (repro.gestation_days_span * self.phenotype["fertility"])
        return days * self.rules.time.ticks_per_day

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
        low, high = self.rules.recovery.rest_regain
        return low + (high - low) * self.phenotype["recovery"]

    @property
    def heal_halflife_ticks(self) -> float:
        """Reference ticks for half of the lost health to heal (``recovery``, log scale)."""
        slow, fast = self.rules.recovery.heal_halflife_days
        return slow * (fast / slow) ** self.phenotype["recovery"] * self.rules.time.ticks_per_day

    def _refresh_vitality_dependents(self) -> None:
        v = self.vitality
        body, repro = self.rules.body, self.rules.reproduction
        health_ratio = max(0.0, self.current_health / self.max_damage_capacity)
        physical_factor = v * (body.health_floor + ((1.0 - body.health_floor) * health_ratio))

        self.current_max_speed = self.base_max_speed * (
            body.speed_floor + ((1.0 - body.speed_floor) * physical_factor)
        )
        if self.pregnancy is not None:
            load = self.pregnancy.litter / repro.litter_max
            self.current_max_speed *= 1.0 - (repro.gestation_slowing * load)
        self.effective_herb_eff = self.phenotype["herbivore_eff"] * v
        self.effective_carn_eff = self.phenotype["carnivore_eff"] * v
        sense_scale = body.sense_floor + ((1.0 - body.sense_floor) * v)
        self.current_sight_range = self.effective_sight_range * sense_scale
        self.current_hearing_range = self.hearing_range * sense_scale

    def update_metabolism_and_aging(
        self, movement_speed_ratio: float = 0.0, dt: float = 1.0
    ) -> None:
        """Advances one simulation tick of ``dt`` reference ticks (an hour each): wear, energy burn,
        healing, the mating cooldown and the pregnancy all run on that clock, and so does the
        energy spent on moving (the world moves an animal ``dt`` times its per-reference-tick
        distance)."""
        if not self.is_alive:
            return

        self.age_ticks += 1

        # Somatic repair dampens wear rate
        self.accumulated_damage += self.wear_per_tick * dt

        self.vitality = max(0.0, 1.0 - (self.accumulated_damage / self.max_damage_capacity))
        self._refresh_vitality_dependents()

        # Kinetic movement burn
        repro = self.rules.reproduction
        body = self.rules.body
        speed = movement_speed_ratio * self.current_max_speed
        kinetic_burn = ((speed / body.speed_reference) ** 2) * (body.kinetic_burn * self.mass) * dt
        upkeep = self.basal_metabolism
        if self.pregnancy is not None:
            upkeep *= 1.0 + (repro.gestation_upkeep * self.pregnancy.litter / repro.litter_max)
        self.current_energy -= (upkeep * dt) + kinetic_burn

        self._heal(dt)

        if self.mating_cooldown > 0.0:
            self.mating_cooldown = max(0.0, self.mating_cooldown - dt)
        if self.pregnancy is not None:
            self.pregnancy.remaining -= dt

        if self.current_energy <= 0.0 or self.vitality <= 0.0:
            self._die(DeathCause.OLD_AGE if self.vitality <= 0.0 else DeathCause.STARVATION)
            return

        self._update_needs_and_drives()

    def _heal(self, dt: float) -> None:
        """Lost health heals with a half-life set by ``recovery``, while there is energy to spare,
        at ``RecoveryRules.heal_energy_cost`` per point. Accumulated wear (ageing) does not heal."""
        lost = self.max_damage_capacity - self.current_health
        recovery = self.rules.recovery
        if lost <= 0.0 or self.current_energy < recovery.heal_min_energy_ratio * self.max_energy:
            return
        healed = lost * (1.0 - 0.5 ** (dt / self.heal_halflife_ticks))
        self.current_health += healed
        self.current_energy -= healed * recovery.heal_energy_cost

    def set_environmental_stimuli(
        self, target_size_ratio: float = 1.0, local_density: float = 0.0
    ) -> None:
        """Feeds sensory world events into dynamic drive modulation."""
        self.env_target_size_ratio = max(
            self.rules.behaviour.min_target_size_ratio, target_size_ratio
        )
        self.env_local_density = min(1.0, max(0.0, local_density))

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
        full = self.rules.brain.pain_full_fraction
        return min(1.0, self.damage_since_decision / (full * self.max_damage_capacity))

    def _effective_fear(self, mate_in_view: bool = False) -> float:
        """Fear as it currently acts: the gene (after sex adjustment), stronger when worn down.
        A driven animal is bolder while a possible mate is in view (``drive_boldness``)."""
        behaviour = self.rules.behaviour
        fear = self.base_fear_weight * (
            behaviour.fear_wear_base - (behaviour.fear_wear_slope * self.vitality)
        )
        if mate_in_view:
            fear *= 1.0 - (self.rules.reproduction.drive_boldness * self.effective_drive)
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
            percepts = replace(
                percepts, mate_closeness=0.0, mate_direction=0.0, mate_similarity=0.0
            )
        aggression, fear = (
            self.current_aggression,
            self._effective_fear(mate_in_view=percepts.mate_closeness > 0.0),
        )
        if percepts.young_closeness > 0.0 and percepts.threat_closeness > 0.0:
            # A threat near its dependent young: a caring parent fights instead of fleeing.
            repro = self.rules.reproduction
            aggression *= 1.0 + self.parenting * repro.young_protection
            fear *= 1.0 - self.parenting * repro.young_fearlessness
        inputs = build_inputs(
            percepts,
            energy_ratio=self.current_energy / self.max_energy,
            health_ratio=self.current_health / self.max_damage_capacity,
            vitality=self.vitality,
            ready_to_mate=self.can_mate,
            pain=self.pain,
            tiredness=self.tiredness,
            temperament=Temperament(
                aggression=min(1.0, aggression),
                fear=min(1.0, fear),
                repro_drive=self.effective_drive,
                parenting=self.parenting,
            ),
        )
        self.damage_since_decision = 0.0
        self._decided_threat = percepts.threat_closeness
        self._decided_touch = bool(percepts.touching)
        hidden, proposal = self.brain.decide_with_hidden(inputs)
        action = self._explore(proposal, rng)
        if self.trace_brain:
            self.brain_trace = BrainTrace(tuple(inputs), hidden, proposal, action)
        if learner is not None and state is not None:
            learner.record(state, hidden, proposal, action)
        decision = decode_outputs(action)
        if rng is not None:
            decision = self.wanderer.apply(decision, percepts, rng)
        self._decision = decision
        self._ticks_since_decision = 1
        factor = self.rules.brain.idle_interval_factor
        if factor > 1.0 and percepts.senses_nothing:
            # Nothing near: look again later. The count starts below 1 for the extra wait.
            self._ticks_since_decision = 1 - round((factor - 1.0) * self.decision_interval)
        return decision

    @property
    def brain_slots(self) -> tuple[int, ...]:
        """The genome slots of the hidden neurons that exist (their gates are on), in the order of
        the hidden layer."""
        return DEFAULT_BLUEPRINT.slots_on(self.dna.values("brain"))

    def _interrupted(self, percepts: Percepts) -> bool:
        """Whether something happened since the brain last ran that should not wait for the next
        scheduled decision (``BRAIN.22``): it is hurting, a threat has appeared, or it is newly in
        contact with something."""
        if self.pain >= self.rules.brain.interrupt_pain:
            return True
        if percepts.threat_closeness > 0.0 and self._decided_threat <= 0.0:
            return True
        return bool(percepts.touching) and not self._decided_touch

    @property
    def looks_every_tick(self) -> bool:
        """Whether the brain runs on every tick, so there is no interval for a touch to cut short
        (an idle wait, ``WORLD.17``, counts below zero)."""
        return self.decision_interval <= 1 and self._ticks_since_decision >= 0

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
        if self.pain >= self.rules.brain.interrupt_pain:
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
            self.learner = Learner(
                self.brain.shape.hidden, self.brain.shape.outputs, rules, self.dt
            )
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

    @property
    def mating_energy_threshold(self) -> float:
        """Share of the energy store an animal needs before it is willing to mate: the drive gene
        lowers it, and so does failing health (senescence desperation)."""
        repro = self.rules.reproduction
        low, high = repro.drive_threshold_range
        return min(
            high,
            max(
                low,
                repro.drive_threshold_base
                - (repro.drive_threshold_slope * self.effective_drive)
                - (repro.drive_threshold_vitality * (1.0 - self.vitality)),
            ),
        )

    @property
    def wants_mate(self) -> bool:
        """Whether the body is ready and rich enough to mate (the brain reads the same two facts
        as its ``ready_to_mate`` and ``energy_ratio`` inputs)."""
        return (
            self.can_mate and self.current_energy / self.max_energy >= self.mating_energy_threshold
        )

    def _update_needs_and_drives(self) -> None:
        behaviour = self.rules.behaviour
        energy_ratio = self.current_energy / self.max_energy
        starvation_factor = max(0.0, 1.0 - energy_ratio)

        # Dynamic Aggression (Nature + Nurture)
        hunger_aggression_boost = 1.0 + (behaviour.hunger_aggression_gain * (starvation_factor**2))
        crowd_aggression_boost = 1.0 + (behaviour.crowd_aggression_gain * self.env_local_density)
        low_confidence, high_confidence = behaviour.size_confidence_range
        size_confidence = min(high_confidence, max(low_confidence, self.env_target_size_ratio))

        modulated_aggression = (
            self.base_aggression
            * hunger_aggression_boost
            * crowd_aggression_boost
            * size_confidence
        )
        self.current_aggression = min(1.0, max(0.0, modulated_aggression))

    def inspect_food(self, toxicity: float, rng: random.Random) -> bool:
        """Uses taste to detect toxins before consumption."""
        behaviour = self.rules.behaviour
        detection_probability = min(
            1.0,
            toxicity
            * (
                behaviour.taste_detection_base
                + (behaviour.taste_detection_gain * self.phenotype["taste"])
            ),
        )
        return rng.random() < detection_probability

    def feed(self, biomass: float, is_meat: bool, toxicity: float = 0.0, dt: float = 1.0) -> float:
        """Processes food intake, applying toxic damage and extracting calories. A poisonous bite
        does its damage per reference tick, so a bite of a tick of ``dt`` reference ticks does ``dt``
        times as much."""
        if not self.is_alive:
            return 0.0

        behaviour = self.rules.behaviour
        if toxicity > 0.0:
            poison_damage = (
                toxicity
                * (1.0 - (behaviour.poison_taste_shield * self.phenotype["taste"]))
                * behaviour.poison_damage
                * dt
            )
            self.apply_damage(poison_damage, DeathCause.POISON)
            if not self.is_alive:
                return 0.0

        if is_meat:
            other = behaviour.diet_penalty * self.phenotype["herbivore_eff"]
            efficiency = self.effective_carn_eff * (1.0 - other)
        else:
            other = behaviour.diet_penalty * self.phenotype["carnivore_eff"]
            efficiency = self.effective_herb_eff * (1.0 - other)

        energy_gain = biomass * efficiency
        self.current_energy = min(self.max_energy, self.current_energy + energy_gain)

        self._refresh_vitality_dependents()
        self._update_needs_and_drives()
        return energy_gain

    @staticmethod
    def mate(impregnator: AnimalTraits, bearer: AnimalTraits, rng: random.Random) -> MatingResult:
        """One mating between a sex-0 animal (``impregnator``) and a sex-1 animal (``bearer``).

        Both must be able to mate and have more energy than the mating effort, or nothing happens
        (``REFUSED``). Otherwise each spends ``mating_effort`` of its store and starts its cooldown,
        and the mating takes with chance ``conception_base + conception_slope * mean fertility``. If it takes, the bearer
        is pregnant: the litter's genomes are fixed now, its size and the gestation time come from
        the bearer's ``fertility`` gene, and her cooldown starts at the birth instead.
        """
        if impregnator.sex != 0 or bearer.sex != 1:
            return MatingResult.REFUSED
        for animal in (impregnator, bearer):
            effort = animal.rules.reproduction.mating_effort
            if not animal.can_mate or animal.current_energy <= effort * animal.max_energy:
                return MatingResult.REFUSED
        for animal in (impregnator, bearer):
            animal.current_energy -= animal.rules.reproduction.mating_effort * animal.max_energy
            animal.mating_cooldown = animal.cooldown_ticks
            animal.matings += 1
        mean_fertility = 0.5 * (impregnator.phenotype["fertility"] + bearer.phenotype["fertility"])
        repro = impregnator.rules.reproduction
        chance = repro.conception_base + (repro.conception_slope * mean_fertility)
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
        surcharge = 1.0 + (self.rules.life.repair_birth_surcharge * self.phenotype["somatic_maint"])
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


# =============================================================================
# Plant Traits: Photosynthesis, Canopy, Toxicity Upkeep & Seed Clutches
# =============================================================================


class PlantTraits(BaseTraits):
    """Manages sessile plant phenotypes: photosynthetic biomass accumulation,

    canopy light shading, chemical defense expenditure, and seed burst triggers.
    """

    def __init__(self, dna: Genome, rules: TraitRules = DEFAULT_RULES) -> None:
        if dna.layout != PLANT_LAYOUT:
            raise TypeError("PlantTraits requires DNA with the plant layout.")
        t = PLANT_TRAITS.express(dna)
        super().__init__(dna, t)
        self.rules: TraitRules = rules
        plant = rules.plant

        # ---------------------------------------------------------------------
        # 1. Structural Scaling & Phenotypes
        # ---------------------------------------------------------------------
        self.max_biomass: float = float(t["max_biomass"])
        self.max_energy = self.max_biomass
        self.max_damage_capacity = self.max_biomass * plant.damage_capacity_share
        self.mass = self.max_biomass * plant.mass_share

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
        self.chemical_defense_tax: float = plant.toxin_cost * (
            self.toxicity**plant.toxin_cost_exponent
        )

        # Baseline photosynthetic intake per tick; a long life slows growth (TRAIT.8)
        self.longevity: float = t["longevity"]
        self.base_growth_rate: float = t["base_growth_rate"] * (
            1.0 - (plant.longevity_growth * self.longevity)
        )
        self.basal_metabolism = (
            plant.upkeep_scale * (self.mass**plant.upkeep_exponent)
        ) + self.chemical_defense_tax

        # ---------------------------------------------------------------------
        # 2. Dynamic Runtime States
        # ---------------------------------------------------------------------
        # Plants sprout as fragile seedlings with a small starter reserve
        self.current_biomass: float = self.max_biomass * plant.start_biomass
        self.current_energy = self.current_biomass
        self.current_health = self.max_damage_capacity * plant.start_health
        self.growth_cooldown: int = 0
        self._lifespan_ticks: float = self.phenotype["lifespan_days"] * rules.time.ticks_per_day
        """Fixed for life (genes and rules do not change), and read every tick."""
        self.lived_ticks: float = 0.0
        """Reference ticks (hours) lived so far; the plant dies of old age at ``lifespan_ticks``."""

        # Environmental factors: Sunlight availability (0.0 to 1.0) and soil competition
        self.sunlight_factor: float = 1.0
        self.soil_competition_factor: float = 1.0

        # Behavioral/Lifecycle flag. A seedling is a juvenile for a share of its lifespan, like an
        # animal (REPRO.5 and TRAIT.8): it can first seed at 6% of its lifespan.
        self.flag_ready_to_seed: bool = False
        self.seed_cooldown: float = rules.reproduction.maturity_share * self.lifespan_ticks

        # A seedling's vitality follows its starting health, not the default of 1.0.
        self._refresh_vitality_dependents()
        self._update_needs_and_drives()

    @property
    def upkeep_share(self) -> float:
        """Full-size upkeep as a share of the base growth: above about 0.4 a plant cannot pay its
        way as a seedling (``WORLD.11``); a first generation is drawn below
        ``founder_upkeep_share``."""
        return self.basal_metabolism / self.base_growth_rate

    @property
    def lifespan_ticks(self) -> float:
        """Reference ticks (hours) a plant lives if nothing kills it: the ``longevity`` gene in days."""
        return self._lifespan_ticks

    @property
    def seeding_interval_ticks(self) -> float:
        """Reference ticks between seed bursts at the shortest (the ``seeding_interval`` gene in days)."""
        return self.phenotype["seeding_days"] * self.rules.time.ticks_per_day

    @property
    def seed_budget(self) -> float:
        """Biomass this plant can put into a burst of seeds right now: a share of its biomass that
        shrinks as the plant lives longer."""
        plant = self.rules.plant
        share = plant.seed_budget_share * (1.0 - (plant.longevity_seeds * self.longevity))
        return share * self.current_biomass

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
        floor = self.rules.plant.light_floor
        self.sunlight_factor = min(1.0, max(floor, sunlight))
        self.soil_competition_factor = min(1.0, max(floor, soil_competition))

    def update_growth_and_metabolism(self, dt: float = 1.0) -> None:
        """Advances one tick of photosynthesis, chemical defense upkeep, and maturation. ``dt`` is the
        tick in reference ticks (hours): ageing, the seeding cooldown, growth and upkeep all run on
        that clock."""
        if not self.is_alive:
            return

        self.age_ticks += 1
        self.lived_ticks += dt
        if self.lived_ticks >= self.lifespan_ticks:
            self._die(DeathCause.OLD_AGE)
            return
        if self.seed_cooldown > 0.0:
            self.seed_cooldown = max(0.0, self.seed_cooldown - dt)

        # Photosynthetic intake scaled by growth gene, light, and soil access
        photosynthetic_gain = (
            self.base_growth_rate
            * self.sunlight_factor
            * self.soil_competition_factor
            * self.vitality
        )

        net_growth = (photosynthetic_gain - self.basal_metabolism) * dt

        # Apply net energy to biomass
        if net_growth > 0:
            self.current_biomass = min(self.max_biomass, self.current_biomass + net_growth)
            self.current_energy = self.current_biomass
            # Passive tissue repair when growing
            if self.current_health < self.max_damage_capacity:
                self.current_health = min(
                    self.max_damage_capacity,
                    self.current_health + (net_growth * self.rules.plant.repair_share),
                )
        else:
            # Deficit burns stored biomass to sustain metabolic tax
            self.current_biomass += net_growth
            self.current_energy = max(0.0, self.current_biomass)
            if self.current_biomass <= 0.0:
                self._die(DeathCause.STARVATION)
                return

        self._refresh_vitality_dependents()
        self._update_needs_and_drives()

    def _update_needs_and_drives(self) -> None:
        # A plant is ready to drop seeds when it is grown, healthy, past its seeding cooldown and
        # can pay for at least one seed
        plant = self.rules.plant
        self.flag_ready_to_seed = (
            self.current_biomass >= (self.max_biomass * plant.seed_ready_share)
            and self.vitality > plant.seed_ready_vitality
            and self.seed_cooldown <= 0.0
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
        self.apply_damage(actual_consumed * self.rules.plant.graze_damage, DeathCause.EATEN)

        if self.is_alive and self.current_biomass <= self.rules.plant.dies_below_biomass:
            self._die(DeathCause.EATEN)

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
