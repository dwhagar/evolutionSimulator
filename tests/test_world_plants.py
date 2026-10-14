"""Plants limit each other's soil and light (WORLD.8)."""

import math

import pytest
from world_support import plant_dna, world_config

from evolution_simulator.world import Bounds, PlantRules, Vec, World

BIG = {"max_biomass": "3333"}  # canopy radius 12, biomass up to 200
HERE = Vec.of(500, 500)


def make(rules=None, seed=0, **config):
    config.setdefault("day_cycle", None)
    return World(world_config(seed=seed, plants=rules or PlantRules(refresh_interval=1), **config))


def test_a_lone_plant_is_not_limited():
    world = make()
    plant = world.add_plant(plant_dna(), HERE)
    own = plant.traits.current_biomass  # only its own biomass is on the ground
    world.step()
    assert plant.shade == 1.0
    assert plant.soil == pytest.approx(1.0 - own / (math.pi * 25.0**2 * PlantRules().capacity))


def test_soil_runs_out_when_the_biomass_around_a_plant_reaches_capacity():
    world = make(PlantRules(refresh_interval=1, capacity=0.001))
    plants = [world.add_plant(plant_dna(**BIG), Vec.of(500 + i, 500)) for i in range(5)]
    for plant in plants:
        plant.traits.current_biomass = 100.0
    world.step()
    assert all(plant.soil == 0.0 for plant in plants)


def test_soil_is_shared_with_neighbours_but_not_with_distant_plants():
    rules = PlantRules(refresh_interval=1, capacity=0.05, neighbourhood=20.0)
    world = make(rules)
    near_a = world.add_plant(plant_dna(), HERE)
    near_b = world.add_plant(plant_dna(), Vec.of(510, 500))
    far = world.add_plant(plant_dna(), Vec.of(800, 800))
    for plant in (near_a, near_b, far):
        plant.traits.current_biomass = 20.0
    world.step()
    assert near_a.soil < far.soil
    assert near_a.soil == pytest.approx(near_b.soil)
    assert far.soil == pytest.approx(1.0 - 20.0 / (math.pi * 400 * 0.05), abs=1e-3)


def test_a_taller_plant_shades_a_smaller_one_under_its_canopy_and_not_the_reverse():
    world = make()
    tall = world.add_plant(plant_dna(**BIG), HERE)
    small = world.add_plant(plant_dna(**BIG), Vec.of(503, 500))
    tall.traits.current_biomass = 100.0
    small.traits.current_biomass = 10.0
    world.step()
    assert small.shade < 1.0
    assert tall.shade == 1.0


def test_shade_needs_the_canopy_to_reach_and_stronger_shade_takes_more_light():
    world = make()
    tall = world.add_plant(plant_dna(**BIG), HERE)
    clear = world.add_plant(plant_dna(**BIG), Vec.of(560, 500))  # past the 12 unit canopy
    tall.traits.current_biomass = 100.0
    clear.traits.current_biomass = 10.0
    world.step()
    assert clear.shade == 1.0
    shades = []
    for strength in (1.0, 3.0):
        world = make(PlantRules(refresh_interval=1, shade_strength=strength))
        tall = world.add_plant(plant_dna(**BIG), HERE)
        small = world.add_plant(plant_dna(**BIG), Vec.of(503, 500))
        tall.traits.current_biomass, small.traits.current_biomass = 100.0, 10.0
        world.step()
        shades.append(small.shade)
    assert shades[1] < shades[0] < 1.0


def test_only_a_share_of_the_plants_is_refreshed_each_tick():
    world = make(PlantRules(refresh_interval=10, capacity=0.0001))
    plants = [world.add_plant(plant_dna(), Vec.of(500 + i, 500)) for i in range(10)]
    for plant in plants:
        plant.traits.current_biomass = 50.0
    world.step()  # tick 0: only the plant with id 10 (10 % 10 == 0) is refreshed
    assert [p.soil for p in plants].count(1.0) == 9
    world.run(9)
    assert all(p.soil < 1.0 for p in plants)


def test_crowded_plants_grow_slower_than_a_lone_plant():
    crowd = make(PlantRules(refresh_interval=1, capacity=0.02))
    lone = make(PlantRules(refresh_interval=1, capacity=0.02))
    target = crowd.add_plant(plant_dna(**BIG), HERE)
    for i in range(1, 8):
        crowd.add_plant(plant_dna(**BIG), Vec.of(500 + 3 * i, 500)).traits.current_biomass = 60.0
    alone = lone.add_plant(plant_dna(**BIG), HERE)
    crowd.run(40)
    lone.run(40)
    assert target.traits.current_biomass < alone.traits.current_biomass


def test_a_small_world_settles_instead_of_running_to_the_cap():
    # Small, fast-growing plants that live about a month: the random founders of an hourly world
    # starve before they seed (WORLD.11), which would end the run before it settles.
    world = make(PlantRules(), seed=3, bounds=Bounds((200, 200)))
    seed_plant = plant_dna(growth_rate="3333", toxicity="0000", longevity="112", max_biomass="0000")
    for _ in range(20):
        world.add_plant(seed_plant, Vec.of(world.rng.uniform(0, 200), world.rng.uniform(0, 200)))
    counts = []
    for _ in range(14):
        world.run(100)
        counts.append(len(world.plants))
    assert max(counts) < world.config.max_plants / 4
    assert counts[-1] < 1.5 * counts[-3] and counts[-1] > counts[-3] / 1.5


def test_plant_rules_reject_bad_values():
    for bad in (
        {"capacity": 0},
        {"neighbourhood": -1},
        {"shade_strength": -1},
        {"refresh_interval": 0},
    ):
        with pytest.raises(ValueError):
            PlantRules(**bad)
