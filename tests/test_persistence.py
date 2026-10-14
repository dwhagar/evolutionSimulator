"""Saving and loading a world (UX.9): a restored world is the saved one, and runs on identically."""

import gzip
import json
from dataclasses import replace

import pytest
from persistence_support import (
    MORE_TICKS,
    SAVE_TICK,
    assert_same_world,
    differences,
    rich_world,
    what_the_scenario_covers,
)
from world_support import animal_dna, hourly_world, plant_dna

from evolution_simulator.diploid import DiploidDNA
from evolution_simulator.layouts import founder_animal_dna, founder_plant_dna
from evolution_simulator.world import Bounds, DayCycle, Vec, World, WorldConfig, WorldSenses
from evolution_simulator.world import persistence as saves
from evolution_simulator.world.persistence import (
    FORMAT_VERSION,
    SaveFormatError,
    load_world,
    save_world,
    world_from_dict,
    world_to_dict,
)

# Saving at these ticks catches the world asleep (37), with the day's decisions logged (52) and
# with learners, pregnancies and callers in the middle of things (20, 45).
SAVE_TICKS = [1, 20, 37, 45, 52]


def rich_world_at(tick: int, seed: int = 5) -> World:
    world = rich_world(seed)
    world.run(tick - world.tick)
    return world


# --- the test world really holds everything ---------------------------------------------------


def test_the_test_world_holds_every_kind_of_state():
    seen: dict[str, int] = {}
    for tick in SAVE_TICKS:
        for key, count in what_the_scenario_covers(rich_world_at(tick)).items():
            seen[key] = max(seen.get(key, 0), count)
    missing = [key for key, count in seen.items() if count == 0]
    assert missing == []
    assert what_the_scenario_covers(rich_world_at(37))["asleep"] > 0
    assert what_the_scenario_covers(rich_world_at(52))["logged_decisions"] > 0


# --- the restored world is the saved world ------------------------------------------------------


@pytest.mark.parametrize("tick", SAVE_TICKS)
def test_a_restored_world_matches_the_saved_one_in_every_attribute(tick):
    world = rich_world_at(tick)
    restored = world_from_dict(world_to_dict(world))
    assert differences(world, restored) == []
    assert restored.state_digest() == world.state_digest()


@pytest.mark.parametrize("tick", [20, 37, 52])
def test_a_resumed_run_matches_an_uninterrupted_one(tick):
    uninterrupted = rich_world_at(tick)
    uninterrupted_report = uninterrupted.run(MORE_TICKS)

    saved = rich_world_at(tick)
    resumed = world_from_dict(world_to_dict(saved))
    resumed_report = resumed.run(MORE_TICKS)

    assert resumed_report == uninterrupted_report
    assert_same_world(resumed, uninterrupted)
    # Saving did not disturb the world it was taken from.
    saved.run(MORE_TICKS)
    assert_same_world(saved, uninterrupted)


def test_the_litters_are_born_after_the_restore():
    world = rich_world_at(SAVE_TICK)
    before = len(world.animals)
    resumed = world_from_dict(world_to_dict(world))
    report = resumed.run(MORE_TICKS)
    assert report.animal_births > 0
    assert len(resumed.animals) > before - report.animal_deaths


def test_a_world_can_be_saved_and_restored_again_and_again():
    world = rich_world_at(10)
    for _ in range(4):
        world = world_from_dict(world_to_dict(world))
        world.run(15)
    expected = rich_world_at(10)
    expected.run(60)
    assert_same_world(world, expected)


def test_saving_twice_gives_the_same_document():
    world = rich_world_at(SAVE_TICK)
    assert world_to_dict(world) == world_to_dict(world)
    assert world_to_dict(world_from_dict(world_to_dict(world))) == world_to_dict(world)


def test_the_comparison_notices_a_field_that_a_save_forgets():
    world = rich_world_at(SAVE_TICK)
    world.animals[0].traits.invented_later = 1.5  # state a future change might add
    found = differences(world, world_from_dict(world_to_dict(world)))
    assert any("invented_later" in line for line in found)


def test_a_dead_father_is_not_kept_and_the_litter_still_comes():
    world = rich_world_at(SAVE_TICK)
    orphaned = [
        a.id
        for a in world.animals
        if a.traits.pregnancy
        and a.traits.pregnancy.father is not None
        and not a.traits.pregnancy.father.is_alive
    ]
    assert len(orphaned) == 1
    restored = world_from_dict(world_to_dict(world))
    (mother,) = (a for a in restored.animals if a.id == orphaned[0])
    assert mother.traits.pregnancy is not None
    assert mother.traits.pregnancy.father is None


def test_a_living_father_is_the_same_animal_after_a_restore():
    restored = world_from_dict(world_to_dict(rich_world_at(SAVE_TICK)))
    fathers = [
        a.traits.pregnancy.father
        for a in restored.animals
        if a.traits.pregnancy and a.traits.pregnancy.father
    ]
    assert fathers
    by_traits = {id(a.traits) for a in restored.animals}
    assert all(id(father) in by_traits for father in fathers)


# --- other kinds of world -----------------------------------------------------------------------


def test_an_empty_world_round_trips_with_its_random_stream():
    world = World(WorldConfig(seed=12))
    world.rng.random()
    world.run(3)
    restored = world_from_dict(world_to_dict(world))
    assert_same_world(world, restored)
    assert restored.rng.random() == world.rng.random()


def test_a_config_with_nothing_switched_on_round_trips():
    config = WorldConfig(
        seed=4,
        bounds=Bounds((80.0, 90.0)),
        day_cycle=None,
        learning=None,
        calls_enabled=False,
        max_animals=7,
    )
    world = World(config)
    world.populate(animals=5, plants=20)
    world.run(30)
    restored = world_from_dict(world_to_dict(world))
    assert restored.config == config
    assert_same_world(world, restored)
    world.run(30)
    restored.run(30)
    assert_same_world(world, restored)


def test_a_changed_config_and_its_rules_round_trip():
    base = WorldConfig()
    config = replace(
        base,
        seed=9,
        day_cycle=DayCycle(length_seconds=36000.0, night_below=0.4),
        graze_amount=7.5,
        traits=replace(base.traits, body=replace(base.traits.body, energy_capacity=150.0)),
        plants=replace(base.plants, capacity=0.02),
    )
    restored = world_from_dict(world_to_dict(World(config)))
    assert restored.config == config


def test_diploid_animals_and_plants_with_no_animals_round_trip():
    world = hourly_world(seed=3, day_cycle=None)
    for x in (100.0, 110.0):
        world.add_plant(plant_dna(), Vec.of(x, 100.0))
    animal = world.add_animal(animal_dna(brain={"speed": 0.5}), Vec.of(300.0, 300.0))
    animal.traits.dna = DiploidDNA.from_haploid(animal.traits.dna)
    world.run(10)
    restored = world_from_dict(world_to_dict(world))
    assert isinstance(restored.animals[0].traits.dna, DiploidDNA)
    assert restored.animals[0].traits.dna == animal.traits.dna
    assert restored.state_digest() == world.state_digest()


def test_a_noise_free_world_keeps_its_senses_settings():
    world = World(WorldConfig(seed=2, day_cycle=None), senses=WorldSenses(noisy=False))
    world.populate(animals=6, plants=30)
    world.run(10)
    restored = world_from_dict(world_to_dict(world))
    world.run(20)
    restored.run(20)
    assert_same_world(world, restored)


def test_other_senses_have_to_be_passed_again():
    class Blind:
        def perceive(self, world, animal):
            return WorldSenses(noisy=False).perceive(world, animal)

    world = World(WorldConfig(seed=2, day_cycle=None), senses=Blind())
    world.populate(animals=3, plants=10)
    data = world_to_dict(world)
    with pytest.raises(SaveFormatError, match="senses"):
        world_from_dict(data)
    senses = Blind()
    assert world_from_dict(data, senses=senses).senses is senses


def test_extra_sleep_listeners_are_attached_after_the_default_one():
    class Counter:
        woke_count = 0

        def fell_asleep(self, world, animal):
            return None

        def woke(self, world, animal):
            self.woke_count += 1

    listener = Counter()
    restored = world_from_dict(world_to_dict(rich_world_at(30)), sleep_listeners=[listener])
    restored.run(40)
    assert listener.woke_count > 0


# --- files ----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["world.json", "world.json.gz"])
def test_a_world_saved_to_a_file_comes_back(tmp_path, name):
    world = rich_world_at(SAVE_TICK)
    path = save_world(world, tmp_path / name)
    assert path == tmp_path / name
    assert [p.name for p in tmp_path.iterdir()] == [name]  # no half-written file left behind
    restored = load_world(path)
    assert_same_world(world, restored)
    restored.run(MORE_TICKS)
    expected = rich_world_at(SAVE_TICK)
    expected.run(MORE_TICKS)
    assert_same_world(restored, expected)


def test_the_same_world_always_gives_the_same_file(tmp_path):
    first = save_world(rich_world_at(20), tmp_path / "a.json.gz").read_bytes()
    second = save_world(rich_world_at(20), tmp_path / "b.json.gz").read_bytes()
    assert first == second
    plain = save_world(rich_world_at(20), tmp_path / "c.json")
    assert len(first) < plain.stat().st_size


def test_saving_over_a_file_replaces_it(tmp_path):
    path = tmp_path / "world.json"
    save_world(rich_world_at(10), path)
    save_world(rich_world_at(20), path)
    assert load_world(path).tick == 20


def test_the_document_says_what_it_is(tmp_path):
    path = save_world(rich_world_at(5), tmp_path / "world.json")
    document = json.loads(path.read_text())
    assert document["format"] == saves.FORMAT
    assert document["format_version"] == FORMAT_VERSION
    assert document["layouts"] == {"animal": 7, "plant": 3}
    assert document["state_digest"] == rich_world_at(5).state_digest()
    assert document["world"]["tick"] == 5


# --- bad saves ------------------------------------------------------------------------------


def test_a_file_that_is_not_a_save_is_refused(tmp_path):
    (tmp_path / "a.json").write_text("not json at all")
    (tmp_path / "b.json").write_text("[1, 2, 3]")
    (tmp_path / "c.json").write_text('{"format": "something else"}')
    (tmp_path / "d.json.gz").write_bytes(b"not gzip")
    for name in ("a.json", "b.json", "c.json", "d.json.gz"):
        with pytest.raises(SaveFormatError):
            load_world(tmp_path / name)


def test_a_save_from_a_newer_format_is_refused():
    data = world_to_dict(rich_world_at(3))
    data["format_version"] = FORMAT_VERSION + 1
    with pytest.raises(SaveFormatError, match="newer"):
        world_from_dict(data)


def test_a_save_with_other_gene_layouts_is_refused_up_front():
    data = world_to_dict(rich_world_at(3))
    data["layouts"] = {"animal": 6, "plant": 3}
    with pytest.raises(SaveFormatError, match="layouts"):
        world_from_dict(data)


def test_a_damaged_save_is_refused_not_half_loaded():
    data = world_to_dict(rich_world_at(3))
    del data["world"]["animals"][0]["traits"]["state"]
    with pytest.raises(SaveFormatError, match="damaged"):
        world_from_dict(data)
    data = world_to_dict(rich_world_at(3))
    data["world"]["plants"][0]["traits"]["dna"]["sequence"] = "123"
    with pytest.raises(SaveFormatError):
        world_from_dict(data)


def test_a_save_that_was_edited_fails_the_digest_check():
    data = world_to_dict(rich_world_at(3))
    data["world"]["animals"][0]["traits"]["state"]["current_energy"] += 1.0
    with pytest.raises(SaveFormatError, match="digest"):
        world_from_dict(data)


def test_a_setting_the_rules_no_longer_have_is_refused():
    data = world_to_dict(rich_world_at(3))
    data["world"]["config"]["graze_amounts"] = 1.0
    with pytest.raises(SaveFormatError, match="graze_amounts"):
        world_from_dict(data)


def test_a_setting_the_save_lacks_takes_its_default():
    world = rich_world_at(3)
    data = world_to_dict(world)
    del data["world"]["config"]["birth_scatter"]
    del data["world"]["config"]["traits"]["body"]["energy_capacity"]
    restored = world_from_dict(data)
    assert restored.config.birth_scatter == WorldConfig().birth_scatter
    assert restored.config.traits.body.energy_capacity == WorldConfig().traits.body.energy_capacity


# --- migrations ---------------------------------------------------------------------------------


def test_an_older_format_is_upgraded_by_the_migration_chain(monkeypatch):
    world = rich_world_at(10)
    old = world_to_dict(world)
    old["world"]["ticks"] = old["world"].pop("tick")  # how format 1 spelt it, in this story

    def one_to_two(data):
        data["world"]["tick"] = data["world"].pop("ticks")
        return data

    monkeypatch.setattr(saves, "FORMAT_VERSION", FORMAT_VERSION + 1)
    monkeypatch.setattr(saves, "_MIGRATIONS", {FORMAT_VERSION: one_to_two})
    restored = world_from_dict(old)
    assert_same_world(restored, world)


def test_an_older_format_with_no_migration_is_refused(monkeypatch):
    data = world_to_dict(rich_world_at(3))
    monkeypatch.setattr(saves, "FORMAT_VERSION", FORMAT_VERSION + 1)
    monkeypatch.setattr(saves, "_MIGRATIONS", {})
    with pytest.raises(SaveFormatError, match="upgraded"):
        world_from_dict(data)


# --- founders from the real populate ------------------------------------------------------------


def test_a_populated_default_world_round_trips_after_a_run():
    world = World(WorldConfig(seed=21))
    world.populate(animals=20, plants=60)
    world.run(120)
    restored = world_from_dict(world_to_dict(world))
    assert_same_world(world, restored)
    world.run(60)
    restored.run(60)
    assert_same_world(world, restored)


def test_founder_genomes_survive_the_trip():
    import random

    rng = random.Random(1)
    world = World(WorldConfig(seed=1))
    for _ in range(5):
        world.add_animal(founder_animal_dna(rng))
        world.add_plant(founder_plant_dna(rng))
    restored = world_from_dict(world_to_dict(world))
    assert [a.traits.dna for a in restored.animals] == [a.traits.dna for a in world.animals]
    assert [p.traits.dna for p in restored.plants] == [p.traits.dna for p in world.plants]


def test_gzip_files_are_plain_gzip_json(tmp_path):
    path = save_world(rich_world_at(5), tmp_path / "w.json.gz")
    assert json.loads(gzip.decompress(path.read_bytes()))["world"]["tick"] == 5


# --- the digest sees what a save has to keep ----------------------------------------------------


def test_the_digest_sees_pregnancies_sleep_and_what_has_been_learned():
    world = rich_world_at(SAVE_TICK)
    base = world.state_digest()
    mother = next(a for a in world.animals if a.traits.pregnancy)
    mother.traits.pregnancy.remaining -= 1.0
    changed = world.state_digest()
    assert changed != base
    learner = next(a.traits.learner for a in world.animals if a.traits.learner)
    weights, biases = learner.offsets
    learner.offsets = (weights, (biases[0] + 0.25, *biases[1:]))
    assert world.state_digest() != changed
    asleep = world.state_digest()
    world.animals[0].asleep = not world.animals[0].asleep
    assert world.state_digest() != asleep
