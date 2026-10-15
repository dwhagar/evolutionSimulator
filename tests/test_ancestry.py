"""The ancestry book and the family view of an animal (UX.39)."""

import json

import pytest
from world_support import animal_dna, breeding_pair, hourly_world

from evolution_simulator.deaths import DeathCause
from evolution_simulator.world import (
    Died,
    Vec,
    World,
    WorldConfig,
    load_world,
    persistence,
    save_world,
)
from evolution_simulator.world.ancestry import AncestryBook

FAMILY = (0.1, 0.2)


def book_of(*rows, max_dead=100):
    """A book from ``(id, parents)`` pairs, all born at tick 0."""
    book = AncestryBook(max_dead)
    for animal_id, parents in rows:
        book.born(animal_id, parents, animal_id % 2, 0, FAMILY)
    return book


def ids(view):
    return [kin.id for kin in view.kin]


# --- the book ----------------------------------------------------------------------


def test_a_new_animal_is_remembered_with_its_parents_and_listed_as_its_parents_child():
    book = AncestryBook()
    book.born(1, (), 0, 0, FAMILY)
    book.born(2, (), 1, 0, FAMILY)
    book.born(3, (1, 2), 1, 7, (0.3, 0.4))
    kin = book.get(3)
    assert (kin.parents, kin.sex, kin.born, kin.family) == ((1, 2), 1, 7, (0.3, 0.4))
    assert kin.died is None and kin.cause is None
    assert book.children_of(1) == book.children_of(2) == (3,)
    assert book.children_of(3) == () and 3 in book and len(book) == 3


def test_a_death_is_recorded_once():
    book = book_of((1, ()))
    book.died(1, 9, DeathCause.STARVATION)
    book.died(1, 12, DeathCause.OLD_AGE)
    book.died(99, 12, DeathCause.OLD_AGE)  # not a known animal: ignored
    kin = book.get(1)
    assert (kin.died, kin.cause) == (9, DeathCause.STARVATION) and book.dead_count == 1


def test_a_family_goes_up_and_down_the_asked_number_of_generations():
    #   1  2
    #    \\/
    #     3   4
    #      \\/
    #       5
    #       |
    #       6
    book = book_of((1, ()), (2, ()), (3, (1, 2)), (4, ()), (5, (3, 4)), (6, (5,)))
    view = book.family_of(5, up=1, down=1)
    assert ids(view) == [5, 3, 4, 6]
    assert (view.center, view.up, view.down, view.truncated) == (5, 1, 1, False)
    assert ids(book.family_of(5, up=2, down=0)) == [5, 3, 4, 1, 2]
    assert ids(book.family_of(5, up=0, down=3)) == [5, 6]
    assert ids(book.family_of(1, up=4, down=4)) == [1, 3, 5, 6]
    assert book.family_of(404) is None


def test_the_view_carries_what_the_tree_needs_for_each_animal():
    book = book_of((1, ()), (2, ()), (3, (1, 2)))
    book.died(1, 5, DeathCause.OLD_AGE)
    view = book.family_of(3)
    first = next(k for k in view.kin if k.id == 1)
    assert (first.died, first.cause, first.sex) == (5, DeathCause.OLD_AGE, 1)
    assert (first.family_a, first.family_b) == FAMILY
    assert next(k for k in view.kin if k.id == 3).parents == (1, 2)


def test_an_animal_two_paths_lead_to_is_listed_once():
    book = book_of((1, ()), (2, (1,)), (3, (1,)), (4, (2, 3)))  # siblings 2 and 3 mated
    assert sorted(ids(book.family_of(4))) == [1, 2, 3, 4]
    assert sorted(ids(book.family_of(1))) == [1, 2, 3, 4]


def test_a_big_family_is_cut_at_the_limit_with_the_descendants_going_first():
    rows = [(1, ()), (2, ()), (3, (1, 2))] + [(10 + n, (3,)) for n in range(50)]
    view = AncestryBook.from_data(book_of(*rows).to_data()).family_of(3, limit=10)
    assert len(view.kin) == 10 and view.truncated
    assert {1, 2} <= set(ids(view))  # the parents are kept
    assert not book_of((1, ())).family_of(1).truncated


def test_the_oldest_dead_are_forgotten_past_the_bound_and_the_living_never_are():
    book = book_of((1, ()), (2, (1,)), (3, (2,)), (4, (3,)), max_dead=2)
    for animal_id, tick in ((1, 10), (2, 11), (3, 12)):
        book.died(animal_id, tick, DeathCause.OLD_AGE)
    assert 1 not in book and 2 in book and 3 in book and 4 in book
    assert book.dead_count == 2
    assert book.children_of(1) == ()  # forgotten with its record
    assert book.get(2).parents == (1,)  # the child still names it
    assert ids(book.family_of(4, up=4)) == [4, 3, 2]  # the tree stops where the record does


def test_forgetting_a_dead_animal_takes_it_off_its_parents_lists():
    book = book_of((1, ()), (2, (1,)), (3, (1,)), max_dead=0)
    book.died(2, 5, DeathCause.POISON)
    assert 2 not in book and book.children_of(1) == (3,)


def test_nothing_is_remembered_with_a_bound_of_zero_but_the_living():
    book = book_of((1, ()), max_dead=0)
    book.died(1, 1, DeathCause.OLD_AGE)
    assert len(book) == 0
    with pytest.raises(ValueError):
        AncestryBook(-1)


def test_a_book_survives_being_written_and_read_in_the_same_order():
    book = book_of((1, ()), (2, ()), (3, (1, 2)), (4, (3,)), max_dead=3)
    book.died(2, 4, DeathCause.PREDATION)
    book.died(1, 6, DeathCause.OLD_AGE)
    rows = json.loads(json.dumps(book.to_data()))
    again = AncestryBook.from_data(rows, max_dead=3)
    assert again.to_data() == book.to_data()
    assert again.family_of(4) == book.family_of(4)
    again.died(3, 8, DeathCause.OLD_AGE)
    again.died(4, 9, DeathCause.OLD_AGE)  # the third and fourth dead: 2, the first, goes
    assert 2 not in again and 1 in again


# --- in the world ------------------------------------------------------------------


def test_every_animal_of_a_running_world_is_in_the_book_with_its_parents():
    world = World(WorldConfig(seed=2))
    world.populate(animals=20, plants=80)
    world.run(300)
    for animal in world.animals:
        kin = world.ancestry.get(animal.id)
        assert kin is not None and kin.died is None
        assert kin.parents == animal.parents and kin.sex == animal.traits.sex
        assert kin.family == animal.traits.family_key


def test_deaths_are_recorded_with_the_tick_and_cause_the_event_carries():
    world = World(WorldConfig(seed=2))
    deaths = []
    world.add_event_listener(
        lambda e: deaths.append(e) if isinstance(e, Died) and e.kind == "animal" else None
    )
    world.populate(animals=20, plants=80)
    world.run(300)
    assert deaths
    for event in deaths:
        kin = world.ancestry.get(event.id)
        assert (kin.died, kin.cause) == (event.tick, event.cause)


def test_a_birth_is_recorded_under_both_parents(sure_conception):
    world = hourly_world()
    father, mother = breeding_pair(world)
    world.step()
    mother.traits.pregnancy.remaining = 0.0
    for animal in world.animals:
        animal.traits.current_energy = animal.traits.max_energy
    world.step()
    children = [a for a in world.animals if a.parents == (father.id, mother.id)]
    assert children
    assert world.ancestry.children_of(father.id) == world.ancestry.children_of(mother.id)
    assert {c.id for c in children} <= set(world.ancestry.children_of(mother.id))
    assert world.ancestry.get(children[0].id).born == world.tick


def test_the_detail_of_an_animal_carries_its_family(sure_conception):
    world = hourly_world()
    father, mother = breeding_pair(world)
    world.step()
    mother.traits.pregnancy.remaining = 0.0
    for animal in world.animals:
        animal.traits.current_energy = animal.traits.max_energy
    world.step()
    child = next(a for a in world.animals if a.parents == (father.id, mother.id))
    family = world.animal_detail(child.id).family
    assert family.center == child.id and ids(family)[0] == child.id
    assert {father.id, mother.id} <= set(ids(family))
    assert world.animal_detail(father.id).family.kin[0].id == father.id
    assert child.id in ids(world.animal_detail(father.id).family)


def test_a_detail_with_its_family_crosses_a_pipe_whole():
    import pickle

    world = World(WorldConfig(seed=2))
    world.populate(animals=6, plants=10)
    world.run(50)
    detail = world.animal_detail(world.animals[0].id)
    assert detail.family is not None
    assert pickle.loads(pickle.dumps(detail)) == detail


def test_keeping_the_book_changes_nothing_about_the_run():
    digests = []
    for bound in (20_000, 0):
        world = World(WorldConfig(seed=5))
        world.ancestry = AncestryBook(bound)
        world.populate(animals=20, plants=80)
        world.run(200)
        digests.append(world.state_digest())
    assert digests[0] == digests[1]


# --- saving ------------------------------------------------------------------------


def test_a_saved_world_keeps_its_ancestry(tmp_path):
    world = World(WorldConfig(seed=2))
    world.populate(animals=20, plants=80)
    world.run(300)
    assert world.ancestry.dead_count > 0
    path = save_world(world, tmp_path / "w.json.gz")
    loaded = load_world(path)
    assert loaded.ancestry.to_data() == world.ancestry.to_data()
    some = world.animals[0].id
    assert loaded.family_of(some) == world.family_of(some)
    loaded.run(20)
    world.run(20)
    assert loaded.state_digest() == world.state_digest()


def test_a_save_from_before_the_book_starts_one_from_the_living(tmp_path):
    world = World(WorldConfig(seed=2))
    world.populate(animals=12, plants=40)
    world.run(100)
    document = persistence.world_to_dict(world)
    del document["world"]["ancestry"]
    document["format_version"] = 5
    old = persistence.world_from_dict(json.loads(json.dumps(document)))
    assert len(old.ancestry) == len(old.animals) and old.ancestry.dead_count == 0
    for animal in old.animals:
        kin = old.ancestry.get(animal.id)
        assert kin.parents == animal.parents and kin.born >= 0
        assert kin.born == max(0, old.tick - animal.traits.age_ticks)
    assert old.state_digest() == world.state_digest()


def test_the_world_holds_a_book_even_without_listeners():
    world = World(WorldConfig(seed=1))
    world.add_animal(animal_dna(), Vec.of(10, 10), heading=0.0)
    assert len(world.ancestry) == 1
