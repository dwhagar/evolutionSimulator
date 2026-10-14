import random

import pytest

from evolution_simulator import traits as traits_module
from evolution_simulator.dna import DNA, GeneSpec, GenomeLayout
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.traits import AnimalTraits, BaseTraits, PlantTraits


def animal_dna(sequence: str) -> DNA:
    return DNA(ANIMAL_LAYOUT, sequence)


def plant_dna(sequence: str) -> DNA:
    return DNA(PLANT_LAYOUT, sequence)


LOW_ANIMAL = animal_dna("0" * ANIMAL_LAYOUT.length)
HIGH_ANIMAL = animal_dna("3" * ANIMAL_LAYOUT.length)
LOW_PLANT = plant_dna("0" * PLANT_LAYOUT.length)
HIGH_PLANT = plant_dna("3" * PLANT_LAYOUT.length)


def animal_with(**genes: str) -> DNA:
    """All-zero animal DNA with the named genes set to the given digit strings."""
    digits = ["0"] * ANIMAL_LAYOUT.length
    for name, text in genes.items():
        gene = ANIMAL_LAYOUT.gene(name)
        digits[gene.start : gene.end] = text
    return animal_dna("".join(digits))


def plant_with(**genes: str) -> DNA:
    digits = ["0"] * PLANT_LAYOUT.length
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


def newborn_of(*_parents) -> AnimalTraits:
    """A child to be born: any animal will do, the birth step only reads its energy store."""
    return AnimalTraits(animal_with(size="3333"))  # max_energy 300


def grown(traits: AnimalTraits) -> AnimalTraits:
    traits.mating_cooldown = 0
    traits._update_needs_and_drives()
    return traits


def test_birth_costs_each_parent_half_the_newborns_energy_at_its_own_care():
    a = grown(AnimalTraits(animal_with(caregiving="333", somatic_maint="0000")))  # care 0.8
    b = grown(AnimalTraits(animal_with(caregiving="000", somatic_maint="0000")))  # care 0.1
    child = newborn_of()
    a.current_energy = b.current_energy = 200.0
    assert AnimalTraits.give_birth(a, b, child)
    assert child.max_energy == pytest.approx(300.0)
    assert child.current_energy == pytest.approx(0.45 * 300.0)  # the mean of 0.8 and 0.1
    assert a.current_energy == pytest.approx(200.0 - 0.4 * 300.0)
    assert b.current_energy == pytest.approx(200.0 - 0.05 * 300.0)


def test_repair_makes_a_birth_dearer_full_repair_doubles_it():
    base = AnimalTraits(animal_with(caregiving="222", somatic_maint="0000"))
    full = AnimalTraits(animal_with(caregiving="222", somatic_maint="3333"))
    assert full.birth_cost(300.0) == pytest.approx(2.0 * base.birth_cost(300.0))
    half = AnimalTraits(animal_with(caregiving="222", somatic_maint="1333"))
    assert half.birth_cost(300.0) == pytest.approx(
        base.birth_cost(300.0) * (1.0 + half.phenotype["somatic_maint"])
    )
    # The newborn still gets the unsurcharged amount.
    a, b = (
        grown(AnimalTraits(animal_with(caregiving="222", somatic_maint="3333"))),
        grown(AnimalTraits(animal_with(caregiving="222", somatic_maint="3333"))),
    )
    a.current_energy = b.current_energy = 250.0
    child = newborn_of()
    assert AnimalTraits.give_birth(a, b, child)
    assert child.current_energy == pytest.approx(a.phenotype["care_fraction"] * 300.0)
    assert 250.0 - a.current_energy == pytest.approx(a.phenotype["care_fraction"] * 300.0)


def test_nobody_is_charged_unless_both_parents_can_pay():
    rich = grown(AnimalTraits(animal_with(caregiving="333")))
    poor = grown(AnimalTraits(animal_with(caregiving="333")))
    rich.current_energy = rich.max_energy
    poor.current_energy = 1.0
    child = newborn_of()
    assert not AnimalTraits.give_birth(rich, poor, child)
    assert rich.current_energy == rich.max_energy and poor.current_energy == 1.0
    assert rich.mating_cooldown == 0 and poor.mating_cooldown == 0
    assert child.current_energy == pytest.approx(child.max_energy * 0.75)  # untouched


def test_a_parent_cannot_pay_its_last_energy_or_birth_during_cooldown():
    a, b = grown(AnimalTraits(LOW_ANIMAL)), grown(AnimalTraits(LOW_ANIMAL))
    child = newborn_of()
    a.current_energy = b.current_energy = a.birth_cost(child.max_energy)  # exactly the cost
    assert not AnimalTraits.give_birth(a, b, child)
    a.current_energy = b.current_energy = a.max_energy
    b.mating_cooldown = 3
    assert not AnimalTraits.give_birth(a, b, child)
    assert a.current_energy == a.max_energy


def test_the_dead_cannot_have_children():
    a, b = grown(AnimalTraits(LOW_ANIMAL)), grown(AnimalTraits(LOW_ANIMAL))
    b.apply_damage(b.max_damage_capacity * 10)
    assert not b.is_alive
    assert not AnimalTraits.give_birth(a, b, newborn_of())


def test_birth_starts_each_parents_own_cooldown():
    quick = grown(AnimalTraits(animal_with(repro_interval="000")))
    slow = grown(AnimalTraits(animal_with(repro_interval="333")))
    quick.current_energy = slow.current_energy = quick.max_energy
    assert AnimalTraits.give_birth(quick, slow, newborn_of())
    assert (
        quick.mating_cooldown == quick.interval_ticks < slow.mating_cooldown == slow.interval_ticks
    )
    assert not quick.flag_wants_mate and not slow.flag_wants_mate


def test_interval_is_a_share_of_the_animals_own_lifespan():
    small = AnimalTraits(animal_with(size="0000", repro_interval="222"))
    large = AnimalTraits(animal_with(size="3333", repro_interval="222"))
    assert large.lifespan_ticks > small.lifespan_ticks
    for traits in (small, large):
        stretch = 1.0 + 0.5 * traits.phenotype["somatic_maint"]
        expected = traits.phenotype["interval_fraction"] * traits.lifespan_ticks * stretch
        assert traits.interval_ticks == round(expected)
    assert large.interval_ticks > small.interval_ticks


def test_repair_stretches_the_interval_and_the_lifespan():
    plain = AnimalTraits(animal_with(repro_interval="222", somatic_maint="0000"))
    repaired = AnimalTraits(animal_with(repro_interval="222", somatic_maint="3333"))
    assert repaired.lifespan_ticks == pytest.approx(plain.lifespan_ticks * 4.5)
    assert repaired.interval_ticks == pytest.approx(plain.interval_ticks * 4.5 * 1.5, abs=1)


def test_interval_gene_spans_one_to_twenty_five_percent_of_a_lifespan():
    low = AnimalTraits(animal_with(repro_interval="000", somatic_maint="0000"))
    high = AnimalTraits(animal_with(repro_interval="333", somatic_maint="0000"))
    assert low.phenotype["interval_fraction"] == pytest.approx(0.01)
    assert high.phenotype["interval_fraction"] == pytest.approx(0.25)
    assert low.interval_ticks == round(0.01 * low.lifespan_ticks)
    assert high.interval_ticks == round(0.25 * high.lifespan_ticks)


def test_a_newborn_is_a_juvenile_for_one_birth_interval():
    traits = AnimalTraits(animal_with(repro_interval="111", repro_drive="333"))
    assert traits.mating_cooldown == traits.interval_ticks > 1
    assert not traits.flag_wants_mate
    for _ in range(traits.interval_ticks):
        traits.current_energy = traits.max_energy
        traits.update_metabolism_and_aging()
    assert traits.mating_cooldown == 0
    assert traits.flag_wants_mate


def test_caregiving_spans_ten_to_eighty_percent():
    assert AnimalTraits(animal_with(caregiving="000")).phenotype["care_fraction"] == 0.1
    assert AnimalTraits(animal_with(caregiving="333")).phenotype["care_fraction"] == pytest.approx(
        0.8
    )


def test_repair_upkeep_is_convex():
    def upkeep(digits: str) -> float:
        return AnimalTraits(animal_with(somatic_maint=digits)).repair_upkeep

    assert upkeep("0000") == 0.0
    assert upkeep("3333") == pytest.approx(0.20)
    assert upkeep("1333") < 0.5 * upkeep(
        "3333"
    )  # a quarter-ish of repair costs far less than a quarter
    quarter = AnimalTraits(animal_with(somatic_maint="1000")).phenotype["somatic_maint"]
    assert upkeep("1000") == pytest.approx(0.20 * quarter**2)


def test_repair_cost_is_in_basal_metabolism():
    plain = AnimalTraits(animal_with(somatic_maint="0000"))
    repaired = AnimalTraits(animal_with(somatic_maint="3333"))
    assert repaired.basal_metabolism - plain.basal_metabolism == pytest.approx(0.20)


def test_staying_ready_to_breed_costs_energy_more_when_the_interval_is_short():
    quick = AnimalTraits(animal_with(repro_interval="000"))
    slow = AnimalTraits(animal_with(repro_interval="333"))
    assert quick.readiness_upkeep > slow.readiness_upkeep
    assert quick.readiness_upkeep == pytest.approx(0.03 * (0.05 / 0.01) ** 0.5)
    assert slow.readiness_upkeep == pytest.approx(0.03 * (0.05 / 0.25) ** 0.5)


def test_the_drive_costs_upkeep_with_its_square():
    assert AnimalTraits(animal_with(repro_drive="000")).drive_upkeep == 0.0
    assert AnimalTraits(animal_with(repro_drive="333")).drive_upkeep == pytest.approx(0.05)
    half = AnimalTraits(animal_with(repro_drive="133"))
    assert half.drive_upkeep == pytest.approx(0.05 * half.phenotype["repro_drive"] ** 2)


def test_the_drive_lowers_the_energy_needed_to_look_for_a_mate():
    def wants(drive: str, energy_ratio: float) -> bool:
        traits = grown(AnimalTraits(animal_with(repro_drive=drive)))
        traits.current_energy = energy_ratio * traits.max_energy
        traits._update_needs_and_drives()
        return traits.flag_wants_mate

    assert not wants("000", 0.80) and wants("000", 0.86)  # threshold 0.85 with no drive
    assert not wants("333", 0.30) and wants("333", 0.36)  # threshold 0.35 at full drive
    assert wants("333", 0.60) and not wants("000", 0.60)


def test_failing_health_also_lowers_the_threshold():
    traits = grown(AnimalTraits(animal_with(repro_drive="000")))
    traits.current_energy = 0.7 * traits.max_energy
    traits._update_needs_and_drives()
    assert not traits.flag_wants_mate
    traits.vitality = 0.2  # threshold 0.85 - 0.2 * 0.8 = 0.69
    traits._update_needs_and_drives()
    assert traits.flag_wants_mate


def test_a_driven_animal_is_bolder_while_a_mate_is_in_view():
    driven = AnimalTraits(animal_with(repro_drive="333", fear="3333"))
    unmoved = AnimalTraits(animal_with(repro_drive="000", fear="3333"))
    assert driven._effective_fear(mate_in_view=True) == pytest.approx(
        0.7 * driven._effective_fear()
    )
    assert unmoved._effective_fear(mate_in_view=True) == unmoved._effective_fear()


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


def test_the_seed_budget_is_35_percent_of_biomass():
    traits = PlantTraits(HIGH_PLANT)
    traits.current_biomass = traits.max_biomass
    assert traits.seed_budget == pytest.approx(traits.max_biomass * 0.35)


def test_seed_capacity_is_the_clutch_the_budget_can_pay_for():
    small = PlantTraits(plant_with(max_biomass="3333", seed_clutch="3333", seed_provision="000"))
    small.current_biomass = small.max_biomass
    assert small.seed_count == 8 and small.seed_capacity() == 7  # 0.35 / 0.05

    dear = PlantTraits(plant_with(max_biomass="3333", seed_clutch="3333", seed_provision="333"))
    dear.current_biomass = dear.max_biomass
    assert dear.seed_provision == pytest.approx(0.50)
    assert dear.seed_capacity() == 0  # one seed costs more than the budget
    empty = PlantTraits(plant_with(seed_clutch="3333"))
    empty.current_biomass = 0.0
    assert empty.seed_capacity() == 0


def test_launch_seeds_pays_provision_per_seed_and_restarts_the_cooldown():
    parent = PlantTraits(
        plant_with(max_biomass="3333", seed_provision="000", seeding_interval="333")
    )
    parent.current_biomass = parent.max_biomass
    parent.flag_ready_to_seed = True
    seeds = [PlantTraits(parent.dna) for _ in range(3)]
    spent = parent.launch_seeds(seeds)
    each = parent.seed_provision * parent.max_biomass
    assert spent == pytest.approx(3 * each)
    assert parent.current_biomass == pytest.approx(parent.max_biomass - 3 * each)
    assert all(seed.current_biomass == pytest.approx(each) for seed in seeds)
    assert parent.seed_cooldown == parent.seeding_interval_ticks > 0
    assert not parent.flag_ready_to_seed


def test_launch_seeds_scales_down_together_when_over_budget():
    parent = PlantTraits(plant_with(max_biomass="3333", seed_provision="333"))
    parent.current_biomass = parent.max_biomass
    seeds = [PlantTraits(parent.dna) for _ in range(4)]
    spent = parent.launch_seeds(seeds)
    assert spent == pytest.approx(parent.max_biomass * 0.35)
    shares = {round(seed.current_biomass, 9) for seed in seeds}
    assert len(shares) == 1


def test_a_young_plant_waits_a_seeding_interval_before_it_seeds():
    traits = PlantTraits(plant_with(max_biomass="3333", growth_rate="3333", seeding_interval="333"))
    assert traits.seed_cooldown == traits.seeding_interval_ticks
    for _ in range(traits.seeding_interval_ticks - 1):
        traits.update_growth_and_metabolism()
    assert not traits.flag_ready_to_seed
    for _ in range(5):
        traits.update_growth_and_metabolism()
    assert traits.flag_ready_to_seed


def test_the_seeding_interval_gene_sets_the_wait():
    short = PlantTraits(plant_with(seeding_interval="000"))
    long = PlantTraits(plant_with(seeding_interval="333"))
    assert short.seeding_interval_ticks < long.seeding_interval_ticks
    assert long.seeding_interval_ticks <= traits_module.PLANT_LIFESPAN_TICKS


def test_a_plant_dies_of_old_age():
    traits = PlantTraits(plant_with(max_biomass="3333"))
    traits.age_ticks = traits.lifespan_ticks - 1
    traits.update_growth_and_metabolism()
    assert not traits.is_alive


# --- base class -------------------------------------------------------------


def test_base_traits_hooks_are_noops_and_damage_kills():
    tiny = GenomeLayout("tiny", 1, [GeneSpec("a", 2), GeneSpec("b", 1)])
    traits = BaseTraits(DNA(tiny, "012"), {})
    traits.current_health = 10.0
    assert traits.apply_damage(4.0) == 6.0
    assert traits.is_alive
    assert traits.apply_damage(100.0) == 0.0
    assert not traits.is_alive


# --- construction state and pinned numbers (TRAIT.5) -------------------------

# A fixed genome, so these numbers only change when a formula or the layout does. The body digits are
# the prototype's test genome with the three reproduction genes (caregiving, repro_interval and
# repro_drive) set in the place its `fertility` gene held; the brain is all zeros.
_BODY = "3302332321121021200230232133200030321201111300230220212303212"
_AT = ANIMAL_LAYOUT.gene("caregiving").start
PINNED_ANIMAL = animal_dna(_BODY[:_AT] + "211" + "123" + "220" + _BODY[_AT:] + "0" * 396)
PINNED_PLANT = plant_dna("330233232112102120023023" + "211" + "122")


def test_animal_drive_flags_are_set_at_birth():
    traits = AnimalTraits(PINNED_ANIMAL)
    assert (
        not traits.flag_wants_mate
    )  # well fed, but a juvenile until its birth interval has passed
    assert not traits.flag_wants_food
    assert traits.vitality == 1.0
    assert grown(traits).flag_wants_mate


def test_hungry_newborn_wants_food_without_waiting_for_a_tick():
    traits = AnimalTraits(PINNED_ANIMAL)
    traits.current_energy = 0.1 * traits.max_energy
    traits._update_needs_and_drives()
    assert traits.flag_wants_food and not traits.flag_wants_mate


def test_plant_vitality_matches_health_at_birth():
    traits = PlantTraits(PINNED_PLANT)
    assert traits.vitality == pytest.approx(0.5)  # a seedling starts at half its health


def test_pinned_reproduction_numbers():
    t = AnimalTraits(PINNED_ANIMAL)
    assert t.phenotype["care_fraction"] == pytest.approx(0.511111111)
    assert t.phenotype["interval_fraction"] == pytest.approx(0.039729870)
    assert t.phenotype["repro_drive"] == pytest.approx(0.634920635)
    assert t.wear_per_tick == pytest.approx(0.037463271)
    assert t.lifespan_ticks == pytest.approx(4239.446366782)
    assert t.interval_ticks == 193
    assert t.mating_cooldown == 193
    assert t.repair_upkeep == pytest.approx(0.016390619)
    assert t.readiness_upkeep == pytest.approx(0.033654852)
    assert t.drive_upkeep == pytest.approx(0.020156211)
    assert t.birth_cost(t.max_energy) == pytest.approx(71.543765219)


def test_pinned_animal_phenotype():
    t = AnimalTraits(PINNED_ANIMAL)
    assert t.mass == pytest.approx(2.764705882)
    assert t.max_energy == pytest.approx(217.647058824)
    assert t.max_damage_capacity == pytest.approx(158.823529412)
    assert t.base_max_speed == pytest.approx(5.232)
    assert t.base_turn_rate == pytest.approx(0.228787879)
    assert t.effective_sight_range == pytest.approx(19.630449827)
    assert t.fov_degrees == pytest.approx(294.745098039)
    assert t.hearing_range == pytest.approx(53.0)
    assert t.smell_range == pytest.approx(50.196078431)
    assert t.body_radius == pytest.approx(0.699381521)
    assert t.tactile_range == pytest.approx(1.616805516)
    # repair, readiness and drive upkeep and the zero-weight brain; the sense bill is on area (SENSE.11)
    assert t.basal_metabolism == pytest.approx(0.606158009)
    assert t.call_radius == pytest.approx(13.411764706)
    assert t.call_energy_cost == pytest.approx(2.841176471)
    assert t.sex_type == 2
    assert t.base_aggression == pytest.approx(0.156862745)
    assert t.base_fear_weight == pytest.approx(0.607843137)


def test_pinned_plant_phenotype():
    t = PlantTraits(PINNED_PLANT)
    assert t.max_biomass == pytest.approx(190.823529412)
    assert t.canopy_radius == pytest.approx(11.490196078)
    assert t.root_radius == pytest.approx(12.552941176)
    assert t.dispersal_radius == pytest.approx(27.176470588)
    assert t.seed_count == 4
    assert t.chemical_defense_tax == pytest.approx(0.022557794)
    assert t.base_growth_rate == pytest.approx(0.987450980)
    assert t.basal_metabolism == pytest.approx(0.217915686)


def test_a_seed_can_be_given_the_biomass_its_parent_spent():
    seed = PlantTraits(PINNED_PLANT)
    seed.set_starting_biomass(7.5)
    assert seed.current_biomass == 7.5 and seed.current_energy == 7.5
    seed.set_starting_biomass(10_000.0)
    assert seed.current_biomass == seed.max_biomass  # no bigger than the seed's own full size
    seed.set_starting_biomass(-1.0)
    assert seed.current_biomass == 0.0
