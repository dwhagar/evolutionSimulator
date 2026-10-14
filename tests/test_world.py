"""The world and its step loop: placing, moving, feeding, reproducing, repeating."""

import math

import pytest
from world_support import (
    animal_dna,
    breeding_pair,
    grown,
    hourly_world,
    lover_dna,
    plant_dna,
)

from evolution_simulator.world import Bounds, TimeScale, Vec, World, WorldConfig

HERE = Vec.of(500, 500)
STILL = {"speed": -2.0}  # logistic(-2) = 0.12 of top speed: nearly still
EATER = {"eat": 2.0}
LOVER = {"mate": 2.0}
BIG_PLANT = {"max_biomass": "3333", "toxicity": "0000", "growth_rate": "0000"}


def make(seed=0, **config):
    return World(WorldConfig(seed=seed, **config))


# --- repeatability ------------------------------------------------------------


def test_the_same_seed_gives_the_same_world():
    runs = []
    for _ in range(2):
        world = make(seed=11)
        world.populate(animals=15, plants=60)
        world.run(150)
        runs.append((world.state_digest(), world.tick, len(world.animals), len(world.plants)))
    assert runs[0] == runs[1]


def test_stepping_in_pieces_equals_stepping_at_once():
    a, b = make(seed=5), make(seed=5)
    for world in (a, b):
        world.populate(animals=10, plants=50)
    a.run(60)
    for _ in range(3):
        b.run(20)
    assert a.state_digest() == b.state_digest()


def test_a_different_seed_gives_a_different_world():
    a, b = make(seed=1), make(seed=2)
    for world in (a, b):
        world.populate(animals=5, plants=20)
        world.run(10)
    assert a.state_digest() != b.state_digest()


# --- placing organisms --------------------------------------------------------


def test_organisms_get_increasing_ids_and_random_places_inside_the_bounds():
    world = make(bounds=Bounds((100, 50)))
    world.populate(animals=5, plants=5)
    ids = [o.id for o in world.plants + world.animals]
    assert ids == sorted(ids) == list(range(1, 11))
    for organism in world.plants + world.animals:
        assert world.bounds.contains(organism.position)


def test_placing_outside_the_world_or_past_the_cap_is_refused():
    world = make(bounds=Bounds((100, 100)), max_animals=1, max_plants=0)
    with pytest.raises(ValueError):
        world.add_animal(animal_dna(), Vec.of(101, 50))
    world.add_animal(animal_dna(), Vec.of(10, 10))
    with pytest.raises(ValueError):
        world.add_animal(animal_dna(), Vec.of(20, 20))
    with pytest.raises(ValueError):
        world.add_plant(plant_dna(), Vec.of(20, 20))


def test_neighbour_queries_return_what_is_near():
    world = make()
    near = world.add_animal(animal_dna(), Vec.of(110, 100))
    world.add_animal(animal_dna(), Vec.of(400, 400))
    plant = world.add_plant(plant_dna(), Vec.of(100, 105))
    assert world.animals_near(Vec.of(100, 100), 20) == [near]
    assert world.plants_near(Vec.of(100, 100), 20) == [plant]


def test_the_within_queries_give_distances_in_id_order():
    world = make()
    first = world.add_animal(animal_dna(), Vec.of(103, 104))
    second = world.add_animal(animal_dna(), Vec.of(100, 101))
    world.add_animal(animal_dna(), Vec.of(400, 400))
    plant = world.add_plant(plant_dna(), Vec.of(106, 108))
    assert world.animals_within(Vec.of(100, 100), 20) == [(first, 5.0), (second, 1.0)]
    assert world.plants_within(Vec.of(100, 100), 20) == [(plant, 10.0)]


# --- time ---------------------------------------------------------------------


def test_a_tick_is_a_second_and_the_clock_follows():
    world = make()
    world.run(3725)
    assert world.tick == 3725
    assert world.simulated_seconds == 3725.0
    assert world.elapsed == "01:02:05"


def test_a_longer_tick_changes_the_clock_not_the_loop():
    world = make(time_scale=TimeScale(seconds_per_tick=60.0))
    world.run(60)
    assert world.simulated_seconds == 3600.0


def test_running_a_negative_number_of_ticks_is_refused():
    with pytest.raises(ValueError):
        make().run(-1)


# --- movement and walls -------------------------------------------------------


def test_animals_move_and_age():
    world = make()
    animal = world.add_animal(animal_dna(brain={"speed": 2.0}), HERE, heading=0.0)
    energy = animal.traits.current_energy
    world.step()
    assert animal.position.distance_to(HERE) > 0.5
    assert animal.traits.age_ticks == 1
    assert animal.traits.current_energy < energy


def test_an_animal_that_senses_nothing_wanders_instead_of_standing_still():
    world = make(seed=9)
    animal = world.add_animal(animal_dna(brain=STILL), HERE, heading=0.0)
    world.run(20)
    assert animal.last_decision is not None and animal.last_decision.wandering
    assert animal.position.distance_to(HERE) > 1.0


def test_walls_stop_animals_at_the_edge():
    world = make(bounds=Bounds((100, 100)))
    runner = world.add_animal(animal_dna(brain={"speed": 2.0}), Vec.of(99, 50), heading=0.0)
    world.run(5)
    assert runner.position.x == 100.0
    assert world.bounds.contains(runner.position)


def test_animals_stay_inside_a_small_busy_world():
    world = make(seed=4, bounds=Bounds((60, 60)))
    world.populate(animals=20, plants=20)
    for _ in range(100):
        world.step()
        assert all(world.bounds.contains(a.position) for a in world.animals)
        assert all(-math.pi <= a.heading <= math.pi for a in world.animals)


def test_animals_that_run_out_of_energy_die_and_leave_the_world():
    world = make()
    animal = world.add_animal(animal_dna(), HERE, heading=0.0)
    animal.traits.current_energy = 0.001
    report = world.step()
    assert report.animal_deaths == 1
    assert world.animals == []
    assert world.animals_near(HERE, 50) == []


# --- feeding ------------------------------------------------------------------


def test_an_animal_that_decides_to_eat_grazes_a_plant_in_reach():
    world = make()
    plant = world.add_plant(plant_dna(**BIG_PLANT), HERE)
    plant.traits.current_biomass = 100.0
    animal = world.add_animal(animal_dna(brain={**STILL, **EATER}), HERE, heading=0.0)
    animal.traits.current_energy = 10.0
    world.step()
    assert plant.traits.current_biomass < 100.0
    assert animal.traits.current_energy > 10.0


# A seedling starts at half vitality (TRAIT.5), so an ungrazed plant drifts down by about 0.1 in a
# tick; grazing takes about 5.
NOT_GRAZED = 99.0


def test_an_animal_does_not_graze_a_plant_out_of_reach_or_when_it_does_not_eat():
    world = make()
    far = world.add_plant(plant_dna(**BIG_PLANT), Vec.of(520, 500))
    far.traits.current_biomass = 100.0
    hungry = world.add_animal(animal_dna(brain={**STILL, **EATER}), HERE, heading=0.0)
    world.step()
    assert far.traits.current_biomass >= NOT_GRAZED
    assert hungry.is_alive

    world = make()
    close = world.add_plant(plant_dna(**BIG_PLANT), HERE)
    close.traits.current_biomass = 100.0
    world.add_animal(animal_dna(brain={**STILL, "eat": -2.0}), HERE, heading=0.0)
    world.step()
    assert close.traits.current_biomass >= NOT_GRAZED


def test_a_plant_that_is_eaten_down_dies_and_is_removed():
    world = make(graze_amount=50.0)
    plant = world.add_plant(plant_dna(**BIG_PLANT), HERE)
    plant.traits.current_biomass = 3.0
    world.add_animal(animal_dna(brain={**STILL, **EATER}), HERE, heading=0.0)
    report = world.step()
    assert report.plant_deaths == 1
    assert world.plants == []
    assert world.plants_near(HERE, 50) == []


# --- reproduction -------------------------------------------------------------


def conceived(world, **genes):
    """A grown father and mother side by side, mated by one step; returns (father, mother)."""
    father, mother = breeding_pair(world, **genes)
    report = world.step()
    assert report.animal_births == 0  # a litter takes its gestation to arrive
    assert mother.traits.is_pregnant and mother.partner == father.id
    return father, mother


def due(world, mother):
    """Bring the birth forward and make sure the parents can afford it."""
    mother.traits.pregnancy.remaining = 0.0
    for animal in world.animals:
        animal.traits.current_energy = animal.traits.max_energy


def test_a_willing_pair_conceives_and_the_litter_arrives_after_the_gestation(sure_conception):
    world = hourly_world()
    father, mother = conceived(world)
    litter = mother.traits.pregnancy.litter
    assert len(world.animals) == 2
    assert father.traits.mating_cooldown > 0  # the mother's cooldown starts at the birth
    due(world, mother)
    report = world.step()
    assert report.animal_births == litter == len(world.animals) - 2
    for child in world.animals[2:]:
        assert child.parents == (father.id, mother.id)
        assert child.traits.dna.layout == mother.traits.dna.layout
        assert world.bounds.contains(child.position)
        assert child.position.distance_to(mother.position) <= world.config.birth_scatter + 1e-9
    assert not mother.traits.is_pregnant and mother.partner is None
    assert mother.traits.mating_cooldown > 0  # her cooldown starts at the birth


def test_the_gestation_runs_on_the_reference_clock_not_the_tick_count(sure_conception):
    hourly = hourly_world()
    _, slow = conceived(hourly)
    daily = hourly_world(time_scale=TimeScale(seconds_per_tick=24 * 3600.0))
    _, quick = conceived(daily)
    assert hourly.dt == 1.0 and daily.dt == 24.0
    assert quick.traits.pregnancy.remaining == slow.traits.pregnancy.remaining  # same litter
    start = slow.traits.pregnancy.remaining
    hourly.step()
    daily.step()
    assert start - slow.traits.pregnancy.remaining == pytest.approx(1.0)
    assert start - quick.traits.pregnancy.remaining == pytest.approx(24.0)


def test_newborns_start_with_the_energy_their_parents_gave_them(sure_conception):
    world = hourly_world()
    father, mother = conceived(world)
    due(world, mother)
    before = father.traits.current_energy + mother.traits.current_energy
    world.step()
    children = world.animals[2:]
    care = 0.5 * (
        father.traits.phenotype["care_fraction"] + mother.traits.phenotype["care_fraction"]
    )
    gave = sum(c.traits.current_energy for c in children)
    for child in children:
        assert child.traits.current_energy == pytest.approx(care * child.traits.max_energy)
    paid = before - (father.traits.current_energy + mother.traits.current_energy)
    assert paid > gave  # the repair surcharge is lost


def test_nobody_mates_again_during_a_cooldown_or_a_pregnancy(sure_conception):
    world = hourly_world()
    _, mother = conceived(world)
    pregnancy = mother.traits.pregnancy
    assert world.step().animal_births == 0
    assert mother.traits.pregnancy is pregnancy


def test_juveniles_far_apart_or_unable_to_pay_the_effort_do_not_mate(sure_conception):
    world = hourly_world()
    young = [
        world.add_animal(lover_dna(sex), Vec.of(500 + sex, 500), heading=0.0) for sex in (0, 1)
    ]
    world.step()
    assert not any(a.traits.is_pregnant for a in young)  # both are still juveniles
    assert all(a.traits.mating_cooldown > 0 for a in young)

    world = hourly_world()
    father, mother = breeding_pair(world, gap=20.0)
    world.step()
    assert not mother.traits.is_pregnant  # out of reach

    world = hourly_world()
    father, mother = breeding_pair(world)
    father.traits.current_energy = 1.0
    world.step()
    assert not mother.traits.is_pregnant
    assert mother.traits.mating_cooldown == 0  # nobody was charged for a mating that did not happen


def test_two_animals_of_the_same_sex_do_not_mate(sure_conception):
    world = hourly_world()
    pair = [world.add_animal(lover_dna(0), Vec.of(x, 500), heading=0.0) for x in (500, 501)]
    grown(*pair)
    world.step()
    assert not any(a.traits.is_pregnant for a in pair)
    assert all(a.traits.mating_cooldown == 0 for a in pair)


def test_an_animal_that_does_not_seek_a_mate_is_left_alone(sure_conception):
    world = hourly_world()
    cold = world.add_animal(
        animal_dna(brain={**STILL, "mate": -2.0}, sex_strategy="0"), HERE, heading=0.0
    )
    keen = world.add_animal(lover_dna(1), Vec.of(501, 500), heading=0.0)
    grown(cold, keen)
    world.step()
    assert not keen.traits.is_pregnant


def test_the_animal_cap_limits_the_litter_and_it_pays_only_for_those_born(sure_conception):
    world = hourly_world(max_animals=3)
    _, mother = conceived(world, fertility="333")  # a litter of 8
    assert mother.traits.pregnancy.litter == 8
    due(world, mother)
    assert world.step().animal_births == 1
    assert len(world.animals) == 3
    assert not mother.traits.is_pregnant


def test_a_birth_waits_until_both_parents_can_pay(sure_conception):
    world = hourly_world()
    father, mother = conceived(world, parenting="000")
    due(world, mother)
    father.traits.current_energy = 1.0
    assert world.step().animal_births == 0
    assert mother.traits.is_pregnant  # she keeps carrying the litter
    father.traits.current_energy = father.traits.max_energy
    assert world.step().animal_births > 0


def test_a_father_who_has_died_pays_nothing(sure_conception):
    world = hourly_world()
    father, mother = conceived(world, parenting="000")
    due(world, mother)
    father.traits.apply_damage(1e9)
    report = world.step()
    assert report.animal_deaths == 1
    assert report.animal_births > 0
    child = world.animals[-1]
    assert child.parents == (father.id, mother.id)
    assert child.traits.current_energy == pytest.approx(
        0.5 * 0.1 * child.traits.max_energy
    )  # her half


def test_a_mother_who_dies_loses_the_litter(sure_conception):
    world = hourly_world()
    _, mother = conceived(world)
    due(world, mother)
    mother.traits.apply_damage(1e9)
    assert world.step().animal_births == 0
    assert len(world.animals) == 1


def test_a_first_generation_starts_with_large_litters_and_no_parenting():
    world = make(seed=4)
    world.populate(animals=12)
    for animal in world.animals:
        traits = animal.traits
        assert traits.phenotype["fertility"] == pytest.approx(0.75, abs=0.02)
        assert traits.phenotype["care_fraction"] == pytest.approx(0.10)
        assert traits.litter_size == 6
        assert traits.phenotype["repro_drive"] == pytest.approx(0.5, abs=0.02)
        assert traits.phenotype["recovery"] == pytest.approx(0.5, abs=0.02)


def ready_plant(world, position, **genes):
    """A grown plant that is ready to seed: cheap seeds, no cooldown, near full size."""
    genes = {"seed_provision": "000", **genes}
    plant = world.add_plant(plant_dna(**genes), position)
    plant.traits.current_biomass = plant.traits.max_biomass * 0.95
    plant.traits.seed_cooldown = 0
    return plant


def test_a_ready_plant_drops_seeds_nearby():
    world = make(bounds=Bounds((200, 200)))
    plant = ready_plant(world, Vec.of(150, 150), seed_clutch="3333", dispersal_radius="1111")
    assert plant.traits.seed_count == 8
    capacity = plant.traits.seed_capacity()
    assert 1 <= capacity <= 8
    report = world.step()
    assert report.plant_births == capacity
    seeds = [p for p in world.plants if p is not plant]
    assert len(seeds) == capacity
    for seed in seeds:
        assert seed.parents == (plant.id,)
        assert seed.position.distance_to(plant.position) <= plant.traits.dispersal_radius + 1e-9
        assert world.bounds.contains(seed.position)
    assert plant.traits.current_biomass < plant.traits.max_biomass * 0.95
    assert plant.traits.seed_cooldown > 0


def test_seeds_start_with_the_biomass_their_parent_spent():
    world = make(bounds=Bounds((200, 200)))
    plant = ready_plant(world, Vec.of(150, 150), seed_clutch="3333", dispersal_radius="1111")
    before = plant.traits.current_biomass
    world.step()
    seeds = [p for p in world.plants if p is not plant]
    provision = plant.traits.seed_provision
    for seed in seeds:
        assert seed.traits.current_biomass == pytest.approx(provision * seed.traits.max_biomass)
        assert seed.traits.current_energy == seed.traits.current_biomass
    spent = sum(seed.traits.current_biomass for seed in seeds)
    assert before - plant.traits.current_biomass >= spent * 0.99  # the plant also grew a little


def test_a_plant_with_no_room_for_seeds_keeps_its_biomass():
    world = make(max_plants=1)
    plant = ready_plant(world, HERE, seed_clutch="3333")
    report = world.step()
    assert report.plant_births == 0
    assert plant.traits.current_biomass >= plant.traits.max_biomass * 0.94
    assert plant.traits.seed_cooldown == 0


def test_the_plant_cap_stops_seeding():
    world = make(max_plants=3)
    ready_plant(world, HERE, seed_clutch="3333")
    report = world.step()
    assert report.plant_births == 2
    assert len(world.plants) == 3


def test_a_plant_in_its_cooldown_does_not_seed():
    world = make()
    plant = ready_plant(world, HERE, seed_clutch="3333")
    plant.traits.seed_cooldown = 50
    assert world.step().plant_births == 0


def test_seeds_are_clones_of_the_parent_with_a_few_mutations():
    world = make(bounds=Bounds((200, 200)), seed=3)
    plant = ready_plant(world, Vec.of(150, 150), seed_clutch="3333", dispersal_radius="1111")
    world.step()
    seeds = [p for p in world.plants if p is not plant]
    assert all(seed.traits.dna.layout is plant.traits.dna.layout for seed in seeds)
    mean_distance = sum(seed.traits.dna.distance(plant.traits.dna) for seed in seeds) / len(seeds)
    assert mean_distance < 0.05  # about 0.15 digits changed in 30


# --- reports ------------------------------------------------------------------


def test_run_sums_the_reports():
    world = make(seed=2)
    world.populate(animals=20, plants=50)
    total = world.run(40)
    assert total.tick == 40
    assert len(world.plants) == 50 + total.plant_births - total.plant_deaths
    assert len(world.animals) == 20 + total.animal_births - total.animal_deaths
