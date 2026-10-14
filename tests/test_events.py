"""World events and death causes (UX.6): births, deaths and matings, told to listeners."""

import pytest
from world_support import animal_dna, breeding_pair, hourly_world, plant_dna, world_config

from evolution_simulator.deaths import DeathCause
from evolution_simulator.traits import AnimalTraits, PlantTraits
from evolution_simulator.world import Ate, Born, Died, Mated, Vec, World, WorldConfig

HERE = Vec.of(500, 500)
STILL = {"speed": -2.0}
BITER = {"speed": -2.0, "eat": 2.0}


def make(**config):
    config.setdefault("day_cycle", None)
    config.setdefault("calls_enabled", False)
    return World(world_config(**config))


def listen(world):
    events = []
    world.add_event_listener(events.append)
    return events


# --- death causes on the body -----------------------------------------------------


def test_a_living_body_has_no_death_cause():
    assert AnimalTraits(animal_dna()).death_cause is None


def test_an_animal_out_of_energy_dies_of_starvation():
    animal = make().add_animal(animal_dna(), HERE, heading=0.0)
    animal.traits.current_energy = 0.001
    make_dead = animal.traits
    make_dead.update_metabolism_and_aging(0.0, 1.0)
    assert make_dead.death_cause is DeathCause.STARVATION


def test_an_animal_worn_out_dies_of_old_age():
    traits = AnimalTraits(animal_dna())
    traits.accumulated_damage = traits.max_damage_capacity
    traits.update_metabolism_and_aging(0.0, 1.0)
    assert traits.death_cause is DeathCause.OLD_AGE


def test_damage_kills_with_the_cause_it_is_given_and_a_default():
    plain = AnimalTraits(animal_dna())
    plain.apply_damage(1e9)
    assert plain.death_cause is DeathCause.DAMAGE
    bitten = AnimalTraits(animal_dna())
    bitten.apply_damage(1e9, DeathCause.PREDATION)
    assert bitten.death_cause is DeathCause.PREDATION


def test_a_toxic_meal_kills_by_poison():
    traits = AnimalTraits(animal_dna(herbivore_eff="3333"))
    traits.current_health = 1.0
    traits.feed(10.0, is_meat=False, toxicity=1.0)
    assert traits.death_cause is DeathCause.POISON


def test_a_plant_dies_of_old_age_hunger_or_being_eaten():
    old = PlantTraits(plant_dna())
    old.lived_ticks = old.lifespan_ticks
    old.update_growth_and_metabolism(1.0)
    assert old.death_cause is DeathCause.OLD_AGE

    eaten = PlantTraits(plant_dna(max_biomass="3333"))
    eaten.current_biomass = 1.0
    eaten.graze(1e6)
    assert eaten.death_cause is DeathCause.EATEN

    hungry = PlantTraits(plant_dna(growth_rate="0000"))
    hungry.current_biomass = 1e-9
    hungry.update_growth_and_metabolism(1.0)
    assert hungry.death_cause is DeathCause.STARVATION


# --- events -----------------------------------------------------------------------


def test_adding_organisms_is_announced_with_place_and_parents():
    world = make()
    events = listen(world)
    animal = world.add_animal(animal_dna(), Vec.of(10, 20), heading=0.0, parents=(3, 4))
    plant = world.add_plant(plant_dna(), Vec.of(30, 40))
    assert events == [
        Born(0, "animal", animal.id, 10.0, 20.0, (3, 4)),
        Born(0, "plant", plant.id, 30.0, 40.0, ()),
    ]


def test_a_death_event_names_the_cause_and_the_tick_the_step_finished():
    world = make()
    events = listen(world)
    animal = world.add_animal(animal_dna(), HERE, heading=0.0)
    animal.traits.current_energy = 0.001
    world.step()
    deaths = [e for e in events if isinstance(e, Died)]
    assert deaths == [
        Died(1, "animal", animal.id, 500.0, 500.0, DeathCause.STARVATION, None, age_ticks=1)
    ]
    assert world.tick == 1


def test_a_kill_names_the_predator():
    world = make()
    events = listen(world)
    hunter = world.add_animal(
        animal_dna(brain=BITER, size="1111", carnivore_eff="3333"), HERE, heading=0.0
    )
    prey = world.add_animal(animal_dna(brain=STILL, size="0000"), Vec.of(501, 500), heading=0.0)
    hunter.traits.current_energy = 0.3 * hunter.traits.max_energy
    world.run(30)
    kills = [e for e in events if isinstance(e, Died) and e.id == prey.id]
    assert len(kills) == 1
    assert kills[0].cause is DeathCause.PREDATION
    assert kills[0].killer == hunter.id


def test_a_grazed_plant_dies_eaten():
    world = make(graze_amount=50.0)
    events = listen(world)
    plant = world.add_plant(plant_dna(max_biomass="3333", toxicity="0000"), HERE)
    plant.traits.current_biomass = 3.0
    world.add_animal(animal_dna(brain={**STILL, "eat": 2.0}), HERE, heading=0.0)
    world.step()
    deaths = [e for e in events if isinstance(e, Died) and e.kind == "plant"]
    assert [(d.id, d.cause) for d in deaths] == [(plant.id, DeathCause.EATEN)]


def test_a_meal_from_a_plant_is_announced_with_the_amount_taken():
    world = make(graze_amount=2.0)
    events = listen(world)
    plant = world.add_plant(plant_dna(max_biomass="3333", toxicity="0000"), HERE)
    plant.traits.current_biomass = 50.0
    animal = world.add_animal(animal_dna(brain={**STILL, "eat": 2.0}), HERE, heading=0.0)
    world.step()
    meals = [e for e in events if isinstance(e, Ate)]
    assert meals == [Ate(1, animal.id, "plant", plant.id, pytest.approx(2.0))]


def test_a_meal_from_a_corpse_is_announced_and_a_refused_one_is_not():
    world = make()
    events = listen(world)
    hunter = world.add_animal(
        animal_dna(brain=BITER, size="1111", carnivore_eff="3333"), HERE, heading=0.0
    )
    prey = world.add_animal(animal_dna(brain=STILL, size="0000"), Vec.of(501, 500), heading=0.0)
    hunter.traits.current_energy = 0.3 * hunter.traits.max_energy
    world.run(40)
    corpse_meals = [e for e in events if isinstance(e, Ate) and e.food == "corpse"]
    assert corpse_meals and all(e.eater == hunter.id and e.amount > 0 for e in corpse_meals)
    kill_tick = next(e.tick for e in events if isinstance(e, Died) and e.id == prey.id)
    assert corpse_meals[0].tick >= kill_tick


def test_a_mating_a_pregnancy_and_a_birth_are_announced(sure_conception):
    world = hourly_world()
    father, mother = breeding_pair(world)
    events = listen(world)
    world.step()
    assert Mated(1, father.id, mother.id, True) in events
    mother.traits.pregnancy.remaining = 0.0
    for animal in world.animals:
        animal.traits.current_energy = animal.traits.max_energy
    events.clear()
    world.step()
    births = [e for e in events if isinstance(e, Born)]
    assert births
    assert all(b.kind == "animal" and b.parents == (father.id, mother.id) for b in births)
    assert all(b.tick == world.tick for b in births)


def test_removing_a_listener_stops_the_events():
    world = make()
    events = []
    world.add_event_listener(events.append)
    world.remove_event_listener(events.append)
    world.add_animal(animal_dna(), HERE, heading=0.0)
    assert events == []


def test_listening_changes_nothing_about_the_run():
    digests = []
    for listening in (False, True):
        world = World(WorldConfig(seed=5))
        if listening:
            world.add_event_listener(lambda event: None)
        world.populate(animals=20, plants=80)
        world.run(200)
        digests.append(world.state_digest())
    assert digests[0] == digests[1]


def test_a_busy_world_reports_as_many_deaths_as_the_step_reports_say():
    world = World(WorldConfig(seed=2))
    world.populate(animals=30, plants=120)
    events = listen(world)
    report = world.run(300)
    deaths = [e for e in events if isinstance(e, Died)]
    assert len([d for d in deaths if d.kind == "animal"]) == report.animal_deaths
    assert len([d for d in deaths if d.kind == "plant"]) == report.plant_deaths
    births = [e for e in events if isinstance(e, Born)]
    assert len([b for b in births if b.kind == "plant"]) == report.plant_births
    assert all(isinstance(d.cause, DeathCause) for d in deaths)
    assert all(d.tick <= world.tick for d in deaths)


def test_events_are_plain_values():
    import pickle

    event = Died(3, "plant", 7, 1.0, 2.0, DeathCause.OLD_AGE)
    assert pickle.loads(pickle.dumps(event)) == event
    with pytest.raises(AttributeError):
        event.tick = 4  # type: ignore[misc]
