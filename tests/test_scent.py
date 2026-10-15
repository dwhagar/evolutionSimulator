"""Smell trails (SENSE.20): a scent field that animals and corpses add to, that fades, and that a
smelling animal reads like any other scent source."""

from dataclasses import replace

import pytest
from persistence_support import assert_same_world
from world_support import TEST_RULES, animal_dna, hourly_world

from evolution_simulator.config import ScentRules
from evolution_simulator.world import Bounds, CorpseRules, Vec, persistence
from evolution_simulator.world.scent import ANIMAL, CARRION, ScentField

SMALL, MEDIUM, LARGE = "0000", "1111", "3333"
STILL = {"speed": -2.0}


def rules_with(scent: ScentRules, corpses: CorpseRules | None = None):
    world_rules = replace(TEST_RULES.world, scent=scent)
    return replace(
        TEST_RULES,
        world=world_rules,
        corpses=corpses if corpses is not None else TEST_RULES.corpses,
    )


def scented_world(**scent):
    scent.setdefault("enabled", True)
    return hourly_world(traits=rules_with(ScentRules(**scent)), bounds=Bounds((1000.0, 1000.0)))


def hunter(world, at=(500, 500), **genes):
    genes = {"size": MEDIUM, "carnivore_eff": "3333", "smell": "3333", **genes}
    return world.add_animal(animal_dna(brain=STILL, **genes), Vec.of(*at), heading=0.0)


def percepts(world, animal):
    return world.senses.perceive(world, animal)


# --- the rules and the field -------------------------------------------------------------------


def test_trails_are_off_by_default() -> None:
    assert ScentRules().enabled is False
    assert hourly_world().scent is None


@pytest.mark.parametrize(
    "bad",
    [
        {"cell_size": 0.0},
        {"half_life_hours": -1.0},
        {"deposit": -0.1},
        {"carrion_deposit": float("nan")},
        {"min_strength": 1.0},
        {"purge_interval": 0},
        {"deposit_interval": 0},
    ],
)
def test_the_rules_are_checked(bad) -> None:
    with pytest.raises(ValueError):
        ScentRules(**bad)


def test_scent_fades_by_half_each_half_life() -> None:
    field = ScentField(ScentRules(half_life_hours=24.0), dt=1.0)
    field.deposit(ANIMAL, Vec.of(5, 5), 0.8, 0, 1.0, False, 1)
    record = field._cells[(0, 0)][ANIMAL]
    assert field.strength(record, 0) == 0.8
    assert field.strength(record, 24) == pytest.approx(0.4)
    assert field.strength(record, 48) == pytest.approx(0.2)


def test_a_longer_tick_fades_faster_per_tick() -> None:
    field = ScentField(ScentRules(half_life_hours=24.0), dt=24.0)
    field.deposit(ANIMAL, Vec.of(5, 5), 0.8, 0, 1.0, False, 1)
    assert field.strength(field._cells[(0, 0)][ANIMAL], 1) == pytest.approx(0.4)


def test_deposits_add_up_to_one_and_the_latest_depositor_is_remembered() -> None:
    field = ScentField(ScentRules(), dt=1.0)
    field.deposit(ANIMAL, Vec.of(5, 5), 0.7, 0, 3.0, False, 1)
    field.deposit(ANIMAL, Vec.of(6, 6), 0.7, 0, 9.0, True, 2)
    (record,) = field.records()
    assert record == [ANIMAL, 0, 0, 1.0, 0, 9.0, True, 2]


def test_weak_trails_are_forgotten() -> None:
    field = ScentField(ScentRules(min_strength=0.1, half_life_hours=1.0), dt=1.0)
    field.deposit(ANIMAL, Vec.of(5, 5), 0.5, 0, 1.0, False, 1)
    field.purge(1)
    assert len(field) == 1
    field.purge(4)  # 0.5 / 16 is below 0.1
    assert len(field) == 0


def test_smelled_reports_only_what_is_in_reach_and_not_ones_own() -> None:
    field = ScentField(ScentRules(cell_size=10.0), dt=1.0)
    field.deposit(ANIMAL, Vec.of(25, 5), 1.0, 0, 1.0, False, 7)
    field.deposit(ANIMAL, Vec.of(95, 5), 1.0, 0, 1.0, False, 8)
    near = field.smelled(Vec.of(5, 5), 30.0, 0)
    assert [(c, cy) for _, c, cy, *_ in near] == [(2, 0)]
    assert field.smelled(Vec.of(5, 5), 30.0, 0, exclude=7) == []
    # A weak trail carries less far: strength 0.5 halves the reach.
    field.deposit(ANIMAL, Vec.of(45, 5), 0.5, 0, 1.0, False, 9)
    assert [c for _, c, *_ in field.smelled(Vec.of(5, 5), 30.0, 0)] == [2]
    assert sorted(c for _, c, *_ in field.smelled(Vec.of(5, 5), 90.0, 0)) == [2, 4, 9]


def test_records_restore_exactly() -> None:
    field = ScentField(ScentRules(), dt=1.0)
    field.deposit(ANIMAL, Vec.of(5, 5), 0.3, 4, 2.0, True, 5)
    field.deposit(CARRION, Vec.of(55, 75), 0.9, 6, 4.0, False, 6)
    other = ScentField(ScentRules(), dt=1.0)
    other.restore(field.records())
    assert other.records() == field.records()


# --- the world lays scent ----------------------------------------------------------------------


def test_animals_lay_scent_where_they_stand_and_it_builds_up() -> None:
    world = scented_world(deposit_interval=1)
    animal = hunter(world)
    world.run(2)
    cell = world.scent.cell_of(animal.position)
    ((_, cx, cy, strength, *_),) = world.scent.records()
    assert (cx, cy) == cell
    assert strength == pytest.approx(0.5, abs=0.05)
    world.run(10)
    assert max(r[3] for r in world.scent.records()) <= 1.0


def test_a_sparser_deposit_interval_lays_the_same_scent_less_often() -> None:
    laid = []
    for interval in (1, 4):
        world = scented_world(deposit_interval=interval, deposit=0.05, half_life_hours=1e9)
        hunter(world)
        world.run(4)
        ((_, _, _, strength, *_),) = world.scent.records()
        laid.append(strength)
    assert laid[0] == pytest.approx(laid[1], abs=0.01)
    assert laid[0] == pytest.approx(0.2, abs=0.02)


def test_a_corpses_scent_outlasts_the_corpse() -> None:
    world = scented_world(carrion_deposit=0.5)
    rotting = CorpseRules(rot_halflife=5.0, gone_below=1.0)
    world = hourly_world(traits=rules_with(ScentRules(enabled=True), rotting))
    prey = world.add_animal(animal_dna(brain=STILL, size=SMALL), Vec.of(500, 500), heading=0.0)
    prey.traits.apply_damage(prey.traits.max_damage_capacity * 10)
    world.run(2)
    assert world.corpses
    world.run(60)
    assert world.corpses == []
    kinds = {r[0] for r in world.scent.records()}
    assert CARRION in kinds


def test_nothing_is_laid_when_trails_are_off() -> None:
    world = hourly_world()
    hunter(world)
    world.run(3)
    assert world.scent is None


# --- smelling a trail --------------------------------------------------------------------------


def small_mass(world) -> float:
    return world.add_animal(animal_dna(brain=STILL, size=SMALL), Vec.of(10, 10)).traits.mass


def test_a_meat_eater_smells_the_trail_of_prey_that_is_no_longer_there() -> None:
    world = scented_world()
    seeker = hunter(world)
    mass = small_mass(world)
    world.scent.deposit(ANIMAL, Vec.of(515, 505), 1.0, world.tick, mass, False, 999)
    seen = percepts(world, seeker)
    assert seen.prey_closeness > 0.0
    assert seen.senses_nothing is False
    assert seen.crowding == 0.0 and seen.touching is False


def test_the_same_trail_means_nothing_to_a_grazer() -> None:
    world = scented_world()
    grazer = hunter(world, carnivore_eff="0000")
    mass = small_mass(world)
    world.scent.deposit(ANIMAL, Vec.of(515, 505), 1.0, world.tick, mass, False, 999)
    assert percepts(world, grazer).prey_closeness == 0.0


def test_the_trail_of_a_bigger_meat_eater_is_a_threat_to_anyone() -> None:
    world = scented_world()
    small = hunter(world, size=SMALL, carnivore_eff="0000")
    big = world.add_animal(
        animal_dna(brain=STILL, size=LARGE, carnivore_eff="3333"), Vec.of(10, 10), heading=0.0
    )
    world.scent.deposit(ANIMAL, Vec.of(515, 505), 1.0, world.tick, big.traits.mass, True, 999)
    seen = percepts(world, small)
    assert seen.threat_closeness > 0.0
    # A bigger plant eater is not a threat.
    world2 = scented_world()
    small2 = hunter(world2, size=SMALL, carnivore_eff="0000")
    world2.scent.deposit(ANIMAL, Vec.of(515, 505), 1.0, world2.tick, big.traits.mass, False, 999)
    assert percepts(world2, small2).threat_closeness == 0.0


def test_an_animal_does_not_smell_its_own_trail() -> None:
    world = scented_world()
    seeker = hunter(world)
    mass = small_mass(world)
    world.scent.deposit(ANIMAL, Vec.of(515, 505), 1.0, world.tick, mass, False, seeker.id)
    assert percepts(world, seeker).prey_closeness == 0.0


def test_a_faded_trail_is_smelled_less_far_and_then_not_at_all() -> None:
    world = scented_world(half_life_hours=10.0)
    seeker = hunter(world)
    mass = small_mass(world)
    world.scent.deposit(ANIMAL, Vec.of(525, 505), 1.0, world.tick, mass, False, 999)
    fresh = percepts(world, seeker).prey_closeness
    world.tick += 10  # half the strength: it now carries only half as far
    half = percepts(world, seeker).prey_closeness
    world.scent.deposit(ANIMAL, Vec.of(505, 505), 1.0, world.tick, mass, False, 998)
    still = percepts(world, seeker).prey_closeness
    world.tick += 200
    gone = percepts(world, seeker).prey_closeness
    assert fresh > 0.0
    assert half == 0.0  # at 31 units a half-strength trail is out of reach (limit 25)
    assert still > 0.0  # a fresh trail close by is smelled
    assert gone == 0.0


def test_a_trail_is_only_ever_smelled() -> None:
    from evolution_simulator.sensing import Neighbour, SenseOrgans, sense

    trail = Neighbour(
        ident=-1, role="prey", position=Vec.of(0.0, 0.0), loudness=0.0, scent=1.0, trail=True
    )
    real = Neighbour(ident=1, role="prey", position=Vec.of(0.0, 0.0), loudness=1.0, scent=1.0)

    def prey_closeness(neighbour, **organs):
        organs = SenseOrgans(**organs)
        found = sense(Vec.of(0.0, 0.0), 0.0, 1.0, organs, [neighbour])
        return found.prey_closeness, found.touching, found.crowding

    eyes_ears_touch = {"vision_range": 50.0, "hearing_range": 50.0, "touch_reach": 5.0}
    assert prey_closeness(real, **eyes_ears_touch)[0] > 0.0
    assert prey_closeness(trail, **eyes_ears_touch) == (0.0, False, 0.0)
    nose = prey_closeness(trail, smell_range=50.0)
    assert nose[0] > 0.0 and nose[1:] == (False, 0.0)


def test_carrion_trails_lead_a_meat_eater_to_the_place() -> None:
    world = scented_world()
    seeker = hunter(world)
    world.scent.deposit(CARRION, Vec.of(515, 505), 1.0, world.tick, 5.0, False, 999)
    assert percepts(world, seeker).prey_closeness > 0.0
    grazer = hunter(world, at=(700, 700), carnivore_eff="0000")
    world.scent.deposit(CARRION, Vec.of(715, 705), 1.0, world.tick, 5.0, False, 998)
    assert percepts(world, grazer).prey_closeness == 0.0


# --- digest and saves --------------------------------------------------------------------------


def test_the_field_is_part_of_the_digest() -> None:
    world = scented_world()
    hunter(world)
    before = world.state_digest()
    world.scent.deposit(ANIMAL, Vec.of(100, 100), 0.5, world.tick, 1.0, False, 3)
    assert world.state_digest() != before


def test_defaults_leave_the_digest_alone() -> None:
    plain, off = hourly_world(seed=3), hourly_world(seed=3, traits=rules_with(ScentRules()))
    for world in (plain, off):
        world.populate(animals=8, plants=40)
        world.run(30)
    assert plain.state_digest() == off.state_digest()


def test_a_saved_world_with_trails_goes_on_the_same(tmp_path) -> None:
    def build():
        world = scented_world()
        world.populate(animals=14, plants=60)
        world.run(40)
        return world

    world = build()
    assert len(world.scent) > 0
    path = persistence.save_world(world, tmp_path / "scent.json.gz")
    loaded = persistence.load_world(path)
    assert_same_world(loaded, world)
    world.run(40)
    loaded.run(40)
    assert loaded.state_digest() == world.state_digest()


def test_a_trail_changes_what_a_hunter_does() -> None:
    """With trails on, a hunter that has been left a trail behind prey it cannot otherwise sense
    turns the brain's prey input on; with trails off the same world gives nothing."""
    results = []
    for enabled in (False, True):
        world = scented_world(enabled=enabled)
        seeker = hunter(world)
        mass = small_mass(world)
        if enabled:
            world.scent.deposit(ANIMAL, Vec.of(520, 500), 1.0, world.tick, mass, False, 999)
        results.append(percepts(world, seeker).prey_closeness)
    assert results[0] == 0.0 < results[1]
