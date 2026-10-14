import random

import pytest

from evolution_simulator.dna import DNA, GeneSpec, GenomeLayout
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.traits import AnimalTraits, BaseTraits, PlantTraits


def animal_dna(sequence: str) -> DNA:
    return DNA(ANIMAL_LAYOUT, sequence)


def plant_dna(sequence: str) -> DNA:
    return DNA(PLANT_LAYOUT, sequence)


LOW_ANIMAL = animal_dna("0" * 65)
HIGH_ANIMAL = animal_dna("3" * 65)
LOW_PLANT = plant_dna("0" * 24)
HIGH_PLANT = plant_dna("3" * 24)


def animal_with(**genes: str) -> DNA:
    """All-zero animal DNA with the named genes set to the given digit strings."""
    digits = ["0"] * ANIMAL_LAYOUT.length
    for name, text in genes.items():
        gene = ANIMAL_LAYOUT.gene(name)
        digits[gene.start : gene.end] = text
    return animal_dna("".join(digits))


def plant_with(**genes: str) -> DNA:
    digits = ["0"] * 24
    for name, text in genes.items():
        gene = PLANT_LAYOUT.gene(name)
        digits[gene.start : gene.end] = text
    return plant_dna("".join(digits))


# --- construction -----------------------------------------------------------


def test_type_checks():
    with pytest.raises(TypeError):
        AnimalTraits(LOW_PLANT)
    with pytest.raises(TypeError):
        PlantTraits(LOW_ANIMAL)


def test_phenotype_is_exposed_by_trait_name():
    traits = AnimalTraits(HIGH_ANIMAL)
    assert traits.phenotype["mass"] == pytest.approx(4.0)
    assert traits.phenotype["size"] == 1.0
    assert traits.phenotype["sex_strategy"] == 3
    assert PlantTraits(HIGH_PLANT).phenotype["seed_count"] == 8


def test_animal_phenotype_ranges_at_extremes():
    low, high = AnimalTraits(LOW_ANIMAL), AnimalTraits(HIGH_ANIMAL)
    assert low.mass == pytest.approx(1.0)
    assert high.mass == pytest.approx(4.0)
    assert low.max_energy == pytest.approx(100.0)
    assert high.max_energy == pytest.approx(300.0)
    for traits in (low, high):
        assert traits.basal_metabolism > 0
        assert traits.base_max_speed > 0
        assert traits.base_turn_rate > 0
        assert 0 < traits.fov_degrees <= 360
        assert traits.current_energy == pytest.approx(traits.max_energy * 0.75)
        assert traits.current_health == traits.max_damage_capacity
        assert traits.is_alive


def test_bigger_animals_are_heavier_slower_and_costlier():
    small, big = AnimalTraits(animal_with(size="0000")), AnimalTraits(animal_with(size="3333"))
    assert big.mass > small.mass
    assert big.max_energy > small.max_energy
    assert big.base_max_speed < small.base_max_speed
    assert big.basal_metabolism > small.basal_metabolism


def test_senses_cost_upkeep():
    blind, sharp = AnimalTraits(animal_with()), AnimalTraits(animal_with(sight_range="3333"))
    assert sharp.basal_metabolism > blind.basal_metabolism
    assert sharp.effective_sight_range > blind.effective_sight_range


def test_wide_fov_shortens_effective_sight():
    narrow = AnimalTraits(animal_with(sight_range="3333", sight_fov="0000"))
    wide = AnimalTraits(animal_with(sight_range="3333", sight_fov="3333"))
    assert wide.fov_degrees > narrow.fov_degrees
    assert wide.effective_sight_range < narrow.effective_sight_range


def test_sex_strategy_shifts_temperament():
    def build(sex: str) -> AnimalTraits:
        return AnimalTraits(animal_with(aggression="2000", fear="2000", sex_strategy=sex))

    male, neutral, brood = build("0"), build("1"), build("3")
    assert male.sex_type == 0 and neutral.sex_type == 1 and brood.sex_type == 3
    assert male.base_aggression == pytest.approx(min(1.0, neutral.base_aggression * 1.35))
    assert male.base_fear_weight == pytest.approx(neutral.base_fear_weight * 0.65)
    assert brood.base_fear_weight == pytest.approx(min(1.0, neutral.base_fear_weight * 1.3))
    assert brood.base_aggression == pytest.approx(neutral.base_aggression)


def test_plant_phenotype_ranges_at_extremes():
    low, high = PlantTraits(LOW_PLANT), PlantTraits(HIGH_PLANT)
    assert low.max_biomass == pytest.approx(20.0)
    assert high.max_biomass == pytest.approx(200.0)
    assert high.seed_count == 8
    assert low.seed_count == 1
    assert high.chemical_defense_tax > low.chemical_defense_tax
    for traits in (low, high):
        assert traits.current_biomass == pytest.approx(traits.max_biomass * 0.15)
        assert traits.is_alive


# --- animal life cycle ------------------------------------------------------


def test_animal_dies_of_starvation_without_food():
    traits = AnimalTraits(HIGH_ANIMAL)
    for _ in range(100_000):
        traits.update_metabolism_and_aging()
        if not traits.is_alive:
            break
    assert not traits.is_alive
    assert traits.current_energy == 0.0
    assert not traits.flag_wants_mate and not traits.flag_wants_to_attack


def test_animal_ages_out_when_fed():
    traits = AnimalTraits(animal_with(somatic_maint="0000"))
    for _ in range(100_000):
        traits.feed(1000.0, is_meat=False)  # no herbivore efficiency gene: nothing gained
        traits.current_energy = traits.max_energy
        traits.update_metabolism_and_aging()
        if not traits.is_alive:
            break
    assert not traits.is_alive
    assert traits.vitality <= 0.0


def test_somatic_maintenance_extends_life():
    def lifespan(maintenance: str) -> int:
        traits = AnimalTraits(animal_with(somatic_maint=maintenance))
        while traits.is_alive:
            traits.current_energy = traits.max_energy
            traits.update_metabolism_and_aging()
        return traits.age_ticks

    assert lifespan("3333") > lifespan("0000")


def test_dead_animal_ignores_further_events():
    traits = AnimalTraits(LOW_ANIMAL)
    traits.apply_damage(1e9)
    assert not traits.is_alive
    age = traits.age_ticks
    traits.update_metabolism_and_aging()
    assert traits.age_ticks == age
    assert traits.apply_damage(5) == 0.0
    assert traits.feed(50, is_meat=False) == 0.0


def test_damage_lowers_health_and_speed():
    traits = AnimalTraits(HIGH_ANIMAL)
    top_speed = traits.current_max_speed
    remaining = traits.apply_damage(traits.max_damage_capacity / 2)
    assert remaining == pytest.approx(traits.max_damage_capacity / 2)
    assert traits.is_alive
    assert traits.current_max_speed < top_speed


def test_movement_costs_energy():
    still, running = AnimalTraits(HIGH_ANIMAL), AnimalTraits(HIGH_ANIMAL)
    still.update_metabolism_and_aging(0.0)
    running.update_metabolism_and_aging(1.0)
    assert running.current_energy < still.current_energy


def test_herbivore_and_carnivore_feeding():
    herb = AnimalTraits(animal_with(herbivore_eff="3333"))
    herb.current_energy = 10.0
    plant_gain = herb.feed(20.0, is_meat=False)
    assert plant_gain == pytest.approx(20.0 * herb.effective_herb_eff)
    herb.current_energy = 10.0
    assert herb.feed(20.0, is_meat=True) == 0.0  # no carnivore efficiency

    carn = AnimalTraits(animal_with(carnivore_eff="3333"))
    carn.current_energy = 10.0
    assert carn.feed(20.0, is_meat=True) > 0.0


def test_feeding_never_exceeds_max_energy():
    traits = AnimalTraits(animal_with(herbivore_eff="3333"))
    traits.feed(1e6, is_meat=False)
    assert traits.current_energy <= traits.max_energy


def test_toxic_food_does_damage_and_taste_softens_it():
    dull = AnimalTraits(animal_with(herbivore_eff="3333", taste="0000"))
    keen = AnimalTraits(animal_with(herbivore_eff="3333", taste="3333"))
    dull.feed(10.0, is_meat=False, toxicity=0.5)
    keen.feed(10.0, is_meat=False, toxicity=0.5)
    assert dull.current_health < dull.max_damage_capacity
    assert keen.current_health > dull.current_health


def test_lethal_toxin_kills_and_yields_nothing():
    traits = AnimalTraits(animal_with(herbivore_eff="3333"))
    traits.current_health = 1.0
    assert traits.feed(10.0, is_meat=False, toxicity=1.0) == 0.0
    assert not traits.is_alive


def test_inspect_food_uses_injected_rng():
    keen = AnimalTraits(animal_with(taste="3333"))
    dull = AnimalTraits(animal_with(taste="0000"))
    always = sum(keen.inspect_food(1.0, random.Random(s)) for s in range(50))
    assert always == 50
    assert not any(dull.inspect_food(0.0, random.Random(s)) for s in range(50))
    assert keen.inspect_food(0.5, random.Random(7)) == keen.inspect_food(0.5, random.Random(7))
    sometimes = sum(dull.inspect_food(0.5, random.Random(s)) for s in range(500))
    assert 0 < sometimes < 500


def test_hunger_sets_food_flags():
    traits = AnimalTraits(animal_with(herbivore_eff="3333"))
    traits.current_energy = traits.max_energy * 0.2
    traits.set_environmental_stimuli(threat_detected=False)
    assert traits.flag_wants_food
    assert traits.flag_target_is_plant
    assert not traits.flag_target_is_prey
    traits.current_energy = traits.max_energy
    traits.set_environmental_stimuli(threat_detected=False)
    assert not traits.flag_wants_food


def test_fear_beats_aggression_for_a_timid_animal():
    timid = AnimalTraits(animal_with(fear="3333", aggression="0000"))
    timid.set_environmental_stimuli(threat_detected=True)
    assert timid.flag_in_fear
    assert not timid.flag_wants_to_attack
    assert not timid.flag_wants_mate


def test_bold_animal_stands_and_fights():
    bold = AnimalTraits(animal_with(fear="0000", aggression="3333"))
    bold.set_environmental_stimuli(threat_detected=True)
    assert not bold.flag_in_fear
    assert bold.flag_wants_to_attack


def test_alarm_and_mating_signals():
    caller = AnimalTraits(animal_with(fear="3333", encoder_fidelity="3333"))
    caller.set_environmental_stimuli(threat_detected=True)
    energy = caller.current_energy
    assert caller.trigger_signal_emission() == 2
    assert caller.current_energy == pytest.approx(energy - caller.call_energy_cost)
    assert caller.trigger_signal_emission() is None  # flag consumed

    mute = AnimalTraits(animal_with(fear="3333", encoder_fidelity="0000"))
    mute.set_environmental_stimuli(threat_detected=True)
    assert mute.trigger_signal_emission() is None


def test_tactile_reflex_needs_touch():
    numb = AnimalTraits(animal_with(touch="0000"))
    feeling = AnimalTraits(animal_with(touch="3333"))
    numb.set_environmental_stimuli(False, tactile_contact=True)
    feeling.set_environmental_stimuli(False, tactile_contact=True)
    assert not numb.flag_tactile_evade
    assert feeling.flag_tactile_evade


def test_mating_cost_and_cooldown():
    traits = AnimalTraits(animal_with(sex_strategy="0"))
    before = traits.current_energy
    traits.consume_mating_cost()
    assert traits.current_energy == pytest.approx(before - traits.max_energy * 0.25)
    assert traits.mating_cooldown == 40
    assert not traits.flag_wants_mate
    for _ in range(40):
        traits.current_energy = traits.max_energy
        traits.update_metabolism_and_aging()
    assert traits.mating_cooldown == 0
    assert traits.flag_wants_mate

    female = AnimalTraits(animal_with(sex_strategy="3"))
    female.consume_mating_cost()
    assert female.mating_cooldown == 100


def test_stimuli_are_clamped():
    traits = AnimalTraits(LOW_ANIMAL)
    traits.set_environmental_stimuli(False, target_size_ratio=-5, local_density=7)
    assert traits.env_target_size_ratio == 0.1
    assert traits.env_local_density == 1.0
    assert 0.0 <= traits.current_aggression <= 1.0


def test_animal_simulation_is_deterministic():
    def run() -> tuple[float, int, bool]:
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(5)))
        for i in range(200):
            traits.set_environmental_stimuli(i % 5 == 0, local_density=(i % 10) / 10)
            traits.feed(15.0, is_meat=bool(i % 2))
            traits.update_metabolism_and_aging((i % 4) / 3)
        return traits.current_energy, traits.age_ticks, traits.is_alive

    assert run() == run()


def test_random_animals_always_have_valid_state():
    for seed in range(100):
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(seed)))
        for i in range(50):
            traits.set_environmental_stimuli(i % 3 == 0, 1.0 + (i % 3), (i % 10) / 10)
            traits.update_metabolism_and_aging((i % 4) / 3)
            assert 0.0 <= traits.vitality <= 1.0
            assert 0.0 <= traits.current_aggression <= 1.0
            assert traits.current_energy <= traits.max_energy
            assert traits.basal_metabolism > 0


# --- plant life cycle -------------------------------------------------------


def test_plant_grows_toward_max_and_signals_seeding():
    traits = PlantTraits(plant_with(max_biomass="1000", growth_rate="3333"))
    assert not traits.flag_ready_to_seed
    for _ in range(10_000):
        traits.update_growth_and_metabolism()
        if traits.flag_ready_to_seed:
            break
    assert traits.flag_ready_to_seed
    assert traits.current_biomass <= traits.max_biomass
    assert traits.current_energy == traits.current_biomass


def test_plant_in_shade_loses_biomass_and_dies():
    traits = PlantTraits(plant_with(growth_rate="0000", toxicity="3333"))
    traits.set_environmental_conditions(sunlight=0.0, soil_competition=0.0)
    assert traits.sunlight_factor == 0.05 and traits.soil_competition_factor == 0.05
    for _ in range(100_000):
        traits.update_growth_and_metabolism()
        if not traits.is_alive:
            break
    assert not traits.is_alive
    assert traits.current_energy == 0.0


def test_grazing_removes_biomass_reports_toxicity_and_hurts():
    traits = PlantTraits(plant_with(max_biomass="3333", toxicity="3333"))
    start_biomass, start_health = traits.current_biomass, traits.current_health
    eaten, toxicity = traits.graze(5.0)
    assert eaten == pytest.approx(5.0)
    assert toxicity == traits.toxicity == 1.0
    assert traits.current_biomass == pytest.approx(start_biomass - 5.0)
    assert traits.current_health < start_health


def test_grazing_cannot_exceed_standing_biomass_and_can_kill():
    traits = PlantTraits(LOW_PLANT)
    eaten, _ = traits.graze(1e6)
    assert eaten == pytest.approx(20.0 * 0.15)
    assert not traits.is_alive
    assert traits.graze(5.0) == (0.0, 0.0)


def test_seed_cost_takes_35_percent_of_biomass():
    traits = PlantTraits(HIGH_PLANT)
    traits.current_biomass = traits.max_biomass
    traits.flag_ready_to_seed = True
    budget = traits.consume_reproduction_cost()
    assert budget == pytest.approx(traits.max_biomass * 0.35)
    assert traits.current_biomass == pytest.approx(traits.max_biomass * 0.65)
    assert not traits.flag_ready_to_seed


# --- base class -------------------------------------------------------------


def test_base_traits_hooks_are_noops_and_damage_kills():
    tiny = GenomeLayout("tiny", 1, [GeneSpec("a", 2), GeneSpec("b", 1)])
    traits = BaseTraits(DNA(tiny, "012"), {})
    traits.current_health = 10.0
    assert traits.apply_damage(4.0) == 6.0
    assert traits.is_alive
    assert traits.apply_damage(100.0) == 0.0
    assert not traits.is_alive
