"""Traits: the living phenotype built from a genome (haploid `DNA` or `DiploidDNA`).

Each traits class reads its genes once to fix the organism's static phenotype (mass, speed, senses,
upkeep and so on), then tracks runtime state (energy, health, age, drive flags) as the simulation
ticks. All numeric constants below are the original prototype's tuning values; they are meant to
be adjusted as the world model arrives.

Anything random takes an injected ``random.Random`` so runs are repeatable.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from evolution_simulator.brain import DEFAULT_SHAPE, Brain
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
from evolution_simulator.sense_genes import direction_noise, sense_cost
from evolution_simulator.trait_defs import ANIMAL_TRAITS, PLANT_TRAITS

# Energy cost of thinking per tick, added to basal metabolism. Placeholders for the first brain
# (BRAIN.5, issue #25): they put a typical random brain at a few percent of the basal budget and are
# meant to move into the shared config object (TRAIT.3).
BRAIN_NEURON_COST: float = 0.0005
"""Per hidden or output neuron."""
BRAIN_CONNECTION_COST: float = 0.0001
"""Per active connection, a weight whose absolute value is above ``BRAIN_ACTIVE_THRESHOLD``."""
BRAIN_ACTIVE_THRESHOLD: float = 0.25
DECISION_INTERVAL: int = 1
"""Ticks between brain decisions (``BRAIN.11``); between them the animal keeps its last decision.
Thinking costs are charged per tick divided by this, so a slower thinker is cheaper. Meant to move
into the shared config object (TRAIT.3), and later perhaps to become a gene (reaction time)."""

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
        self.vitality: float = 1.0  # Scales from 1.0 (prime) down to 0.0 (dead)
        self.age_ticks: int = 0
        self.is_alive: bool = True

    def apply_damage(self, amount: float) -> float:
        """Applies physical/toxin damage. Kills entity if health hits 0."""
        if not self.is_alive:
            return 0.0

        self.current_health = max(0.0, self.current_health - amount)
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


class AnimalTraits(BaseTraits):
    """Manages mobile entity phenotypes, 5-modality sensory systems,

    metabolic trade-offs, senescence degradation, and environmental drive flags.
    """

    def __init__(self, dna: Genome, decision_interval: int = DECISION_INTERVAL) -> None:
        if dna.layout != ANIMAL_LAYOUT:
            raise TypeError("AnimalTraits requires DNA with the animal layout.")
        if decision_interval < 1:
            raise ValueError(f"Decision interval must be at least 1 tick, got {decision_interval}.")
        t = ANIMAL_TRAITS.express(dna)
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
        self.effective_sight_range: float = t["sight_reach"] * (1.0 - (0.45 * t["sight_fov"]))
        self.fov_degrees: float = t["fov_degrees"]
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
        )
        self.vision_noise: float = direction_noise("vision", t["sight_range"])
        self.hearing_noise: float = direction_noise("hearing", t["hearing"])
        self.smell_noise: float = direction_noise("smell", t["smell"])
        self.gut_maintenance: float = 0.06 * ((t["herbivore_eff"] ** 2) + (t["carnivore_eff"] ** 2))
        # The brain is read from the genome once at birth, like the body.
        self.brain: Brain = Brain.from_values(DEFAULT_SHAPE, dna.values("brain"))
        self.wanderer: Wanderer = Wanderer()
        self.decision_interval: int = decision_interval
        self._decision: BrainDecision | None = None
        self._ticks_since_decision: int = 0
        self.brain_upkeep: float = (
            BRAIN_NEURON_COST * self.brain.neuron_count
            + BRAIN_CONNECTION_COST * self.brain.active_connections(BRAIN_ACTIVE_THRESHOLD)
        ) / self.decision_interval
        self.basal_metabolism = (
            (0.18 * (self.mass**0.75))
            + (0.12 * t["somatic_maint"])
            + sensory_overhead
            + self.gut_maintenance
            + self.brain_upkeep
        )

        # Acoustic signaling
        self.call_radius: float = t["call_radius"]
        self.call_energy_cost: float = t["call_energy_cost"]

        # Sex strategy behavioral offsets (Option 2)
        self.sex_type: int = int(t["sex_strategy"])
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
        self.mating_cooldown: int = 0

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

    def _refresh_vitality_dependents(self) -> None:
        v = self.vitality
        health_ratio = max(0.0, self.current_health / self.max_damage_capacity)
        physical_factor = v * (0.35 + (0.65 * health_ratio))

        self.current_max_speed = self.base_max_speed * (0.3 + (0.7 * physical_factor))
        self.effective_herb_eff = self.phenotype["herbivore_eff"] * v
        self.effective_carn_eff = self.phenotype["carnivore_eff"] * v
        self.current_sight_range = self.effective_sight_range * (0.4 + (0.6 * v))
        self.current_hearing_range = self.hearing_range * (0.4 + (0.6 * v))

    def update_metabolism_and_aging(self, movement_speed_ratio: float = 0.0) -> None:
        """Advances one simulation tick, draining energy and accumulating wear-and-tear."""
        if not self.is_alive:
            return

        self.age_ticks += 1

        # Somatic repair dampens wear rate
        wear_per_tick = 0.075 / (1.0 + (3.5 * self.phenotype["somatic_maint"]))
        self.accumulated_damage += wear_per_tick

        self.vitality = max(0.0, 1.0 - (self.accumulated_damage / self.max_damage_capacity))
        self._refresh_vitality_dependents()

        # Kinetic movement burn
        kinetic_burn = (movement_speed_ratio**2) * (0.35 * self.mass)
        total_drain = self.basal_metabolism + kinetic_burn
        self.current_energy -= total_drain

        if self.mating_cooldown > 0:
            self.mating_cooldown -= 1

        if self.current_energy <= 0.0 or self.vitality <= 0.0:
            self._die()
            return

        self._update_needs_and_drives()

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

    def _effective_fear(self) -> float:
        """Fear as it currently acts: the gene (after sex adjustment), stronger when worn down."""
        return self.base_fear_weight * (1.2 - (0.5 * self.vitality))

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
        if self._decision is not None and self._ticks_since_decision < self.decision_interval:
            self._ticks_since_decision += 1
            return self._decision
        inputs = build_inputs(
            percepts,
            energy_ratio=self.current_energy / self.max_energy,
            health_ratio=self.current_health / self.max_damage_capacity,
            vitality=self.vitality,
            ready_to_mate=self.mating_cooldown == 0,
            temperament=Temperament(
                aggression=self.current_aggression, fear=min(1.0, self._effective_fear())
            ),
        )
        decision = decode_outputs(self.brain.decide(inputs))
        if rng is not None:
            decision = self.wanderer.apply(decision, percepts, rng)
        self._decision = decision
        self._ticks_since_decision = 1
        return decision

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

        # Mating urgency (senescence desperation lowers threshold)
        mating_threshold = 0.35 + (0.35 * self.vitality)
        self.flag_wants_mate = (
            energy_ratio >= mating_threshold and self.mating_cooldown == 0 and not self.flag_in_fear
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

        # Passive recovery when well-fed
        if (
            self.current_energy > (self.max_energy * 0.8)
            and self.current_health < self.max_damage_capacity
        ):
            repair = min(4.0, self.max_damage_capacity - self.current_health)
            self.current_health += repair
            self.current_energy -= repair * 0.5

        self._refresh_vitality_dependents()
        self._update_needs_and_drives()
        return energy_gain

    def consume_mating_cost(self) -> None:
        cost_multiplier = 0.25 if self.sex_type in (0, 1) else 0.45
        self.current_energy = max(0.0, self.current_energy - self.max_energy * cost_multiplier)
        self.mating_cooldown = 100 if self.sex_type in (2, 3) else 40
        self._update_needs_and_drives()

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

        # Behavioral/Lifecycle flag
        self.flag_ready_to_seed: bool = False

        # A seedling's vitality follows its starting health, not the default of 1.0.
        self._refresh_vitality_dependents()
        self._update_needs_and_drives()

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
        # A plant is ready to drop seeds when it reaches 85% biomass capacity
        self.flag_ready_to_seed = (
            self.current_biomass >= (self.max_biomass * 0.85) and self.vitality > 0.4
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

    def consume_reproduction_cost(self) -> float:
        """Expends biomass to package into outgoing seeds.

        Returns the total energy budget to be divided among seed offspring.
        """
        seed_investment = self.current_biomass * 0.35
        self.current_biomass -= seed_investment
        self.current_energy = self.current_biomass
        self.flag_ready_to_seed = False
        return seed_investment
