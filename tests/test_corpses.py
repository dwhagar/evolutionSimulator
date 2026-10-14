"""Corpses: meat that rots, is smelled and is eaten (WORLD.12)."""

import pytest
from world_support import animal_dna

from evolution_simulator.world import CorpseRules, Vec, World, WorldConfig

HERE = Vec.of(500, 500)
STILL = {"speed": -2.0}
EATER = {"speed": -2.0, "eat": 2.0}
SMALL, MEDIUM = "0000", "1111"


def make(**config):
    config.setdefault("day_cycle", None)
    config.setdefault("calls_enabled", False)
    return World(WorldConfig(**config))


def kill(world, animal):
    animal.traits.apply_damage(animal.traits.max_damage_capacity * 10)
    world.step()


def test_the_rules_are_checked():
    with pytest.raises(ValueError):
        CorpseRules(bite=-1.0)
    with pytest.raises(ValueError):
        CorpseRules(rot_halflife=0.0)
    with pytest.raises(ValueError):
        CorpseRules(scent_meat=float("nan"))


def test_a_dead_animal_leaves_a_corpse_with_meat():
    world = make()
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), HERE, heading=0.0)
    store = prey.traits.max_energy
    kill(world, prey)
    (corpse,) = world.corpses
    assert corpse.position == HERE
    assert corpse.meat == pytest.approx(0.5 * store)
    assert corpse.radius == pytest.approx(prey.radius)


def test_the_living_leave_no_corpse():
    world = make()
    world.add_animal(animal_dna(brain=STILL), HERE, heading=0.0)
    world.run(3)
    assert world.corpses == []


def test_corpses_rot_away():
    world = make(corpses=CorpseRules(rot_halflife=10.0, gone_below=1.0))
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), HERE, heading=0.0)
    kill(world, prey)
    start = world.corpses[0].meat
    world.run(10)
    assert world.corpses[0].meat == pytest.approx(start * 0.5, rel=1e-6)
    world.run(200)
    assert world.corpses == []


def test_a_meat_eater_eats_a_corpse_it_touches():
    world = make()
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), HERE, heading=0.0)
    eater = world.add_animal(
        animal_dna(brain=EATER, size=MEDIUM, carnivore_eff="3333"), Vec.of(501, 500), heading=0.0
    )
    kill(world, prey)
    eater.position = HERE  # it wandered a little while the prey died
    eater.traits.current_energy = 0.2 * eater.traits.max_energy
    before = eater.traits.current_energy
    meat = world.corpses[0].meat
    world.step()
    assert eater.traits.current_energy > before
    assert world.corpses[0].meat < meat
    assert eater.traits.damage_taken == 0.0


def test_a_corpse_is_eaten_up():
    world = make(corpses=CorpseRules(bite=1000.0))
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), HERE, heading=0.0)
    eater = world.add_animal(
        animal_dna(brain=EATER, size=MEDIUM, carnivore_eff="3333"), Vec.of(501, 500), heading=0.0
    )
    kill(world, prey)
    eater.position = HERE
    eater.traits.current_energy = 0.2 * eater.traits.max_energy
    world.run(2)
    assert world.corpses == []


def test_a_plant_eater_ignores_corpses():
    world = make()
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), HERE, heading=0.0)
    grazer = world.add_animal(
        animal_dna(brain=EATER, size=MEDIUM, carnivore_eff="0000"), Vec.of(501, 500), heading=0.0
    )
    kill(world, prey)
    grazer.position = HERE
    meat = world.corpses[0].meat
    world.step()
    grazer.position = HERE
    world.step()
    assert world.corpses[0].meat < meat  # only rot
    assert grazer.traits.damage_taken == 0.0


def test_a_hunters_kill_leaves_a_corpse():
    world = make()
    world.add_animal(animal_dna(brain=EATER, size=MEDIUM, carnivore_eff="3333"), HERE, heading=0.0)
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), Vec.of(501, 500), heading=0.0)
    for _ in range(40):
        world.step()
        if not prey.is_alive:
            break
    assert not prey.is_alive
    assert len(world.corpses) == 1


def test_corpses_are_in_the_state_digest():
    a, b = make(), make()
    for world in (a, b):
        prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), HERE, heading=0.0)
        kill(world, prey)
    assert a.state_digest() == b.state_digest()
    b.corpses[0].meat -= 1.0
    assert a.state_digest() != b.state_digest()


# --- the senses ----------------------------------------------------------------------------

SMELLER = {"sight_range": "0000", "hearing": "0000", "smell": "3333", "touch": "0000"}


def test_a_meat_eater_smells_a_corpse_as_prey_and_a_grazer_does_not():
    world = make()
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), HERE, heading=0.0)
    eater = world.add_animal(
        animal_dna(brain=STILL, size=MEDIUM, carnivore_eff="3333", **SMELLER),
        Vec.of(520, 500),
        heading=0.0,
    )
    grazer = world.add_animal(
        animal_dna(brain=STILL, size=MEDIUM, carnivore_eff="0000", **SMELLER),
        Vec.of(480, 500),
        heading=0.0,
    )
    kill(world, prey)
    seen = world.senses.perceive(world, eater)
    other = world.senses.perceive(world, grazer)
    assert seen.prey_closeness > 0.0
    assert other.prey_closeness == 0.0


def test_a_corpse_is_not_crowding():
    world = make()
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), HERE, heading=0.0)
    eater = world.add_animal(
        animal_dna(brain=STILL, size=MEDIUM, carnivore_eff="3333", **SMELLER),
        Vec.of(520, 500),
        heading=0.0,
    )
    kill(world, prey)
    assert world.senses.perceive(world, eater).crowding == 0.0
