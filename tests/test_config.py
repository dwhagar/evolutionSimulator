"""The tuning constants live in one rules tree (TRAIT.3)."""

import dataclasses
from dataclasses import replace

import pytest
from world_support import ANIMAL_BASE, PLANT_BASE, animal_dna, plant_dna, world_config

from evolution_simulator import sense_genes as sg
from evolution_simulator.config import DEFAULT_RULES, SensingRules, TraitRules
from evolution_simulator.traits import AnimalTraits, PlantTraits
from evolution_simulator.world import TimeScale, Vec, World, WorldConfig

# --- the default rules reproduce the numbers the formulas had inline -----------


def test_the_default_rules_give_a_known_reference_animal():
    animal = AnimalTraits(ANIMAL_BASE)
    assert animal.rules is DEFAULT_RULES
    assert animal.max_energy == pytest.approx(166.666667)
    assert animal.max_damage_capacity == pytest.approx(133.333333)
    assert animal.base_max_speed == pytest.approx(3.157894737)
    assert animal.basal_metabolism == pytest.approx(0.4409428867)
    assert animal.wear_per_tick == pytest.approx(0.0200492308)
    assert animal.brain_upkeep == pytest.approx(0.00345)
    assert animal.repair_upkeep == pytest.approx(0.0222222222)
    assert animal.gut_maintenance == pytest.approx(0.0133333333)
    assert animal.cooldown_ticks == pytest.approx(227.641171487)
    assert animal.gestation_ticks == pytest.approx(192.0)
    assert animal.litter_size == 3


def test_the_defaults_give_the_same_plant_as_before_the_move():
    plant = PlantTraits(PLANT_BASE)
    assert plant.rules is DEFAULT_RULES
    assert plant.basal_metabolism == pytest.approx(0.1361136109)
    assert plant.chemical_defense_tax == pytest.approx(0.0096225045)
    assert plant.max_damage_capacity == pytest.approx(64.0)
    assert plant.lifespan_ticks == pytest.approx(627.635581778)
    assert plant.seed_budget == pytest.approx(3.64)


def test_the_brief_s_brain_costs_are_in_the_brain_rules():
    brain = DEFAULT_RULES.brain
    assert (brain.neuron_cost, brain.connection_cost, brain.dead_zone) == (0.0005, 0.0001, 0.5)


def test_a_random_brain_costs_about_four_percent_of_basal_metabolism():
    import random

    from evolution_simulator.dna import DNA
    from evolution_simulator.layouts import ANIMAL_LAYOUT

    shares = []
    for seed in range(60):
        animal = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(seed)))
        shares.append(animal.brain_upkeep / animal.basal_metabolism)
    assert 0.02 < sum(shares) / len(shares) < 0.08


# --- the rules are values ---------------------------------------------------------


def test_the_rules_are_frozen_hashable_and_compare_by_value():
    assert TraitRules() == DEFAULT_RULES
    assert hash(TraitRules()) == hash(DEFAULT_RULES)
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_RULES.body.damage_capacity = 1.0  # type: ignore[misc]
    changed = replace(DEFAULT_RULES, life=replace(DEFAULT_RULES.life, wear_base=0.05))
    assert changed != DEFAULT_RULES
    assert DEFAULT_RULES.life.wear_base == 0.0362  # the default is untouched


def test_every_organism_rule_is_read_by_the_formulas():
    # A rule nobody reads is a constant left behind: each field of the organism sections is read
    # by the trait code, the learning step or the world (the sensing and day-cycle sections have their own tests).
    import pathlib

    source = ""
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "evolution_simulator"
    for name in (
        "traits.py",
        "sense_genes.py",
        "learning.py",
        "world/senses.py",
        "world/world.py",
        "world/daycycle.py",
    ):
        source += (root / name).read_text()
    unused = []
    for section in dataclasses.fields(TraitRules):
        for item in dataclasses.fields(getattr(DEFAULT_RULES, section.name)):
            if item.name not in source and section.name not in ("time", "sensing", "day_cycle"):
                unused.append(f"{section.name}.{item.name}")
    assert unused == []


# --- changing one rule changes the behaviour that reads it --------------------------


def with_rules(**sections) -> TraitRules:
    return replace(DEFAULT_RULES, **sections)


def test_an_animal_reads_the_rules_it_is_given():
    base = AnimalTraits(ANIMAL_BASE)
    heavy = AnimalTraits(
        ANIMAL_BASE,
        rules=with_rules(body=replace(DEFAULT_RULES.body, basal_scale=0.36)),
    )
    assert heavy.basal_metabolism > base.basal_metabolism * 1.5
    assert heavy.rules.body.basal_scale == 0.36 and base.rules.body.basal_scale == 0.18


def test_brain_costs_come_from_the_brain_rules():
    free = AnimalTraits(
        ANIMAL_BASE,
        rules=with_rules(brain=replace(DEFAULT_RULES.brain, neuron_cost=0.0, connection_cost=0.0)),
    )
    assert free.brain_upkeep == 0.0


def test_sense_costs_come_from_the_organ_rules():
    dear = replace(DEFAULT_RULES.organs, vision_cost_per_area=1.0)
    default_cost = sg.sense_cost(10.0, 360.0, 0.0, 0.0, 0.0, 0.0)
    assert sg.sense_cost(10.0, 360.0, 0.0, 0.0, 0.0, 0.0, 0.0, dear) > default_cost * 100000


def test_wear_and_healing_come_from_the_life_and_recovery_rules():
    quick = AnimalTraits(
        ANIMAL_BASE,
        rules=with_rules(life=replace(DEFAULT_RULES.life, wear_base=0.2)),
    )
    assert quick.wear_per_tick == pytest.approx(
        AnimalTraits(ANIMAL_BASE).wear_per_tick * 0.2 / 0.0362
    )
    no_heal_cost = AnimalTraits(
        ANIMAL_BASE,
        rules=with_rules(recovery=replace(DEFAULT_RULES.recovery, heal_energy_cost=0.0)),
    )
    no_heal_cost.apply_damage(50.0)
    before = no_heal_cost.current_energy
    no_heal_cost._heal(1.0)
    assert no_heal_cost.current_energy == before


def test_litter_and_gestation_come_from_the_reproduction_rules():
    rules = with_rules(
        reproduction=replace(DEFAULT_RULES.reproduction, litter_max=2, gestation_days_base=1.0)
    )
    animal = AnimalTraits(ANIMAL_BASE, rules=rules)
    assert animal.litter_size <= 2
    assert animal.gestation_ticks == pytest.approx(
        24 * (1.0 + DEFAULT_RULES.reproduction.gestation_days_span * animal.phenotype["fertility"])
    )


def test_the_day_length_comes_from_the_time_rules():
    long_days = with_rules(time=replace(DEFAULT_RULES.time, ticks_per_day=48.0))
    default = AnimalTraits(ANIMAL_BASE)
    assert AnimalTraits(ANIMAL_BASE, rules=long_days).cooldown_ticks == pytest.approx(
        default.cooldown_ticks * 2
    )
    assert PlantTraits(PLANT_BASE, long_days).lifespan_ticks == pytest.approx(
        PlantTraits(PLANT_BASE).lifespan_ticks * 2
    )


def test_a_plant_reads_the_plant_rules():
    rules = with_rules(plant=replace(DEFAULT_RULES.plant, upkeep_scale=0.0, toxin_cost=0.0))
    plant = PlantTraits(PLANT_BASE, rules)
    assert plant.basal_metabolism == 0.0 and plant.chemical_defense_tax == 0.0


# --- the world carries the rules ----------------------------------------------------


def test_the_world_hands_its_rules_to_every_organism_it_makes():
    rules = with_rules(body=replace(DEFAULT_RULES.body, basal_scale=0.3))
    world = World(WorldConfig(traits=rules))
    animal = world.add_animal(animal_dna(), Vec.of(500, 500))
    plant = world.add_plant(plant_dna(), Vec.of(520, 500))
    assert animal.traits.rules is rules and plant.traits.rules is rules


def test_the_world_clock_comes_from_the_time_rules():
    slow = with_rules(time=replace(DEFAULT_RULES.time, reference_tick_seconds=7200.0))
    world = World(world_config(time_scale=TimeScale(seconds_per_tick=3600.0), traits=slow))
    assert world.dt == 0.5
    assert World(world_config(time_scale=TimeScale(seconds_per_tick=3600.0))).dt == 1.0


def test_the_sensing_rules_are_part_of_the_trait_rules():
    rules = with_rules(sensing=SensingRules(weak_smell=0.25))
    config = WorldConfig(traits=rules)
    assert config.sensing.weak_smell == 0.25
    assert WorldConfig().sensing == DEFAULT_RULES.sensing == SensingRules()
