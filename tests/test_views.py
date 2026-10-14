"""Read-only views of the world and the brain trace (UX.6)."""

import pickle

from world_support import animal_dna, plant_dna

from evolution_simulator.brain_adapter import INPUT_NAMES, OUTPUT_NAMES
from evolution_simulator.world import (
    ANIMAL_FIELDS,
    CORPSE_FIELDS,
    PLANT_FIELDS,
    AnimalView,
    CorpseView,
    PlantView,
    Vec,
    World,
    WorldConfig,
)

HERE = Vec.of(500, 500)


def busy_world(seed=3, animals=20, plants=60, ticks=30):
    world = World(WorldConfig(seed=seed))
    world.populate(animals=animals, plants=plants)
    world.run(ticks)
    return world


def test_the_field_lists_name_the_columns_in_order():
    assert ANIMAL_FIELDS[:3] == ("id", "x", "y")
    assert PLANT_FIELDS == PlantView._fields
    assert CORPSE_FIELDS == CorpseView._fields
    assert len(ANIMAL_FIELDS) == len(AnimalView._fields)


def test_there_is_one_view_per_organism_in_id_order():
    world = busy_world()
    animals, plants = world.animal_views(), world.plant_views()
    assert [v.id for v in animals] == [a.id for a in world.animals]
    assert [v.id for v in plants] == [p.id for p in world.plants]
    assert len(animals) > 0 and len(plants) == world.plant_count


def test_an_animal_view_reads_the_animal():
    world = World(WorldConfig(seed=1, day_cycle=None))
    animal = world.add_animal(animal_dna(carnivore_eff="3333", herbivore_eff="0000"), HERE, 1.5)
    view = world.animal_views()[0]
    assert (view.id, view.x, view.y, view.heading) == (animal.id, 500.0, 500.0, 1.5)
    assert view.radius == animal.radius
    assert view.diet == 1.0
    assert 0.0 <= view.energy_ratio <= 1.0 and view.health_ratio == 1.0
    assert view.age_ratio == 0.0
    assert view.sex == animal.traits.sex
    assert not view.asleep and not view.pregnant


def test_a_plant_view_reads_the_plant():
    world = World(WorldConfig(seed=1))
    plant = world.add_plant(plant_dna(max_biomass="3333"), HERE)
    plant.traits.current_biomass = plant.traits.max_biomass / 2
    view = world.plant_views()[0]
    assert (view.id, view.x, view.y, view.radius) == (plant.id, 500.0, 500.0, plant.radius)
    assert abs(view.biomass_ratio - 0.5) < 1e-9


def test_a_dead_animal_leaves_a_corpse_view():
    world = World(WorldConfig(seed=1, day_cycle=None))
    animal = world.add_animal(animal_dna(), HERE, 0.0)
    animal.traits.current_energy = 0.001
    world.step()
    (corpse,) = world.corpse_views()
    assert (corpse.x, corpse.y) == (500.0, 500.0)
    assert corpse.meat > 0.0


def test_views_are_immutable_values_that_pickle():
    world = busy_world()
    view = world.animal_views()[0]
    assert pickle.loads(pickle.dumps(view)) == view
    assert pickle.loads(pickle.dumps(world.plant_views()[0])) == world.plant_views()[0]


def test_views_change_nothing_in_the_world():
    a = busy_world(seed=9)
    b = busy_world(seed=9)
    for _ in range(3):
        a.animal_views(), a.plant_views(), a.corpse_views()
        a.animal_detail(a.animals[0].id)
    assert a.state_digest() == b.state_digest()


# --- the detail ---------------------------------------------------------------------


def test_the_detail_of_an_animal_and_of_nobody():
    world = busy_world()
    animal = world.animals[0]
    detail = world.animal_detail(animal.id)
    assert detail is not None
    assert detail.id == animal.id and detail.alive and detail.tick == world.tick
    assert detail.genome == str(animal.traits.dna)
    assert detail.traits["mass"] == animal.traits.mass
    assert detail.max_energy == animal.traits.max_energy
    assert detail.decision is animal.last_decision
    assert world.animal_detail(10**9) is None
    assert pickle.loads(pickle.dumps(detail)) == detail


# --- the brain trace ------------------------------------------------------------------


def test_the_brain_trace_is_empty_until_the_animal_is_traced():
    world = busy_world()
    animal = world.animals[0]
    assert world.animal_detail(animal.id).brain is None
    assert not animal.traits.trace_brain


def test_a_traced_animal_keeps_the_last_inputs_hidden_values_and_outputs():
    world = busy_world(ticks=5)
    animal = world.animals[0]
    assert world.trace_brain(animal.id)
    for _ in range(40):
        world.step()
        if not animal.is_alive:
            break
    detail = world.animal_detail(animal.id)
    if detail is None:
        return  # died before its brain ran again; covered by the session tests
    trace = detail.brain
    assert trace is not None
    assert len(trace.inputs) == len(INPUT_NAMES)
    assert len(trace.proposal) == len(trace.action) == len(OUTPUT_NAMES)
    assert len(trace.hidden) == animal.traits.brain.shape.hidden


def test_tracing_moves_to_the_new_animal_and_can_stop():
    world = busy_world()
    first, second = world.animals[:2]
    assert world.trace_brain(first.id)
    assert world.trace_brain(second.id)
    assert not first.traits.trace_brain and second.traits.trace_brain
    assert world.trace_brain(None)
    assert not second.traits.trace_brain
    assert not world.trace_brain(10**9)


def test_tracing_does_not_change_the_run():
    digests = []
    for traced in (False, True):
        world = busy_world(seed=4, ticks=0)
        if traced:
            world.trace_brain(world.animals[0].id)
        world.run(150)
        digests.append(world.state_digest())
    assert digests[0] == digests[1]
