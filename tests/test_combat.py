"""Attacks and meat (BRAIN.10)."""

import pytest
from world_support import animal_dna, plant_dna

from evolution_simulator.world import AttackRules, Vec, World, WorldConfig

HERE = Vec.of(500, 500)
STILL = {"speed": -2.0}
BITER = {"speed": -2.0, "eat": 2.0}
SMALL, MEDIUM, LARGE = "0000", "1111", "3333"


def make(**config):
    config.setdefault("day_cycle", None)
    config.setdefault("calls_enabled", False)
    return World(WorldConfig(**config))


def hunter(world, at=HERE, **genes):
    genes = {"size": MEDIUM, "carnivore_eff": "3333", **genes}
    return world.add_animal(animal_dna(brain=BITER, **genes), at, heading=0.0)


def victim(world, at=HERE, brain=STILL, **genes):
    genes = {"size": SMALL, **genes}
    return world.add_animal(animal_dna(brain=brain, **genes), at, heading=0.0)


def test_the_rules_are_checked():
    with pytest.raises(ValueError):
        AttackRules(damage=-1.0)
    with pytest.raises(ValueError):
        AttackRules(meat_share=float("nan"))


def test_a_bite_grows_with_the_hunters_skill_and_size():
    rules = AttackRules()
    assert rules.bite(0.0, 10.0, 5.0) == 0.0
    assert rules.bite(1.0, 20.0, 5.0) > rules.bite(1.0, 10.0, 5.0) > rules.bite(0.5, 10.0, 5.0)
    assert rules.bite(1.0, 10.0, 10.0) == pytest.approx(rules.damage)


def test_a_hunter_in_contact_bites_its_prey():
    world = make()
    hunter(world)
    p = victim(world, Vec.of(501, 500))
    health = p.traits.current_health
    world.run(1)
    assert p.traits.current_health < health
    assert p.disturbed


def test_a_hunter_keeps_biting_until_the_prey_dies_and_then_eats_it():
    world = make()
    h, p = hunter(world), victim(world, Vec.of(501, 500))
    h.traits.current_energy = 0.3 * h.traits.max_energy
    before = h.traits.current_energy
    world.run(30)
    assert not p.is_alive
    assert p.id not in {a.id for a in world.animals}
    assert h.traits.current_energy > before
    assert h.traits.damage_taken == 0.0


def test_meat_is_worth_a_share_of_the_victims_energy_store():
    world = make(attack=AttackRules(damage=10_000.0, meat_share=0.5))
    h, p = hunter(world), victim(world, Vec.of(501, 500))
    h.traits.current_energy = 0.1 * h.traits.max_energy
    start = h.traits.current_energy
    prey_max = p.traits.max_energy
    world.run(1)
    gained = h.traits.current_energy - start
    assert not p.is_alive
    # The hunter also paid the tick's metabolism, so the gain is just under the meat's value.
    assert 0.2 * prey_max < gained <= 0.5 * prey_max


def test_the_hunters_meat_efficiency_decides_how_much_it_gains():
    def gain(carnivore_eff):
        world = make(attack=AttackRules(damage=10_000.0))
        h = hunter(world, carnivore_eff=carnivore_eff)
        victim(world, Vec.of(501, 500))
        h.traits.current_energy = 0.1 * h.traits.max_energy
        world.run(1)
        return h.traits.current_energy

    assert gain("3333") > gain("2222")


def test_no_bite_without_the_brain_asking():
    world = make()
    calm = world.add_animal(
        animal_dna(brain=STILL, size=MEDIUM, carnivore_eff="3333"), HERE, heading=0.0
    )
    p = victim(world, Vec.of(501, 500))
    health = p.traits.current_health
    world.run(3)
    assert p.traits.current_health == health
    assert calm.traits.damage_taken == 0.0


def test_only_prey_is_bitten():
    world = make()
    hunter(world)
    bigger = victim(world, Vec.of(501, 500), size=LARGE)
    same = victim(world, Vec.of(499, 500), size=MEDIUM)
    health = (bigger.traits.current_health, same.traits.current_health)
    world.run(3)
    assert (bigger.traits.current_health, same.traits.current_health) == health


def test_a_plant_eater_does_not_bite():
    world = make()
    hunter(world, carnivore_eff="0000")
    p = victim(world, Vec.of(501, 500))
    health = p.traits.current_health
    world.run(3)
    assert p.traits.current_health == health


def test_prey_out_of_contact_is_left_alone():
    world = make()
    hunter(world)
    p = victim(world, Vec.of(560, 500))
    health = p.traits.current_health
    world.run(3)
    assert p.traits.current_health == health


def test_the_nearest_prey_is_the_one_bitten():
    world = make()
    hunter(world)
    near = victim(world, Vec.of(501, 500))
    far = victim(world, Vec.of(502.5, 500))
    far_health = far.traits.current_health
    world.run(1)
    assert near.traits.current_health < near.traits.max_damage_capacity
    assert far.traits.current_health == far_health


def test_a_plant_underfoot_is_eaten_instead_of_biting():
    world = make()
    h = hunter(world, herbivore_eff="3333")
    world.add_plant(plant_dna(), HERE)
    p = victim(world, Vec.of(501, 500))
    health = p.traits.current_health
    h.traits.current_energy = 0.3 * h.traits.max_energy
    world.run(1)
    assert p.traits.current_health == health
    assert h.traits.current_energy != 0.3 * h.traits.max_energy


def test_a_sleeper_is_bitten_and_woken():
    world = make()
    hunter(world)
    p = victim(world, Vec.of(501, 500))
    p.asleep = True
    health = p.traits.current_health
    world.run(1)
    assert p.traits.current_health < health
    assert p.disturbed
