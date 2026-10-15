"""How easy a creature is to see: size, movement and camouflage (SENSE.21)."""

import random
import statistics

import pytest
from world_support import animal_dna, plant_dna, world_config

from evolution_simulator.config import DEFAULT_RULES, SensingRules
from evolution_simulator.sensing import (
    Neighbour,
    SenseOrgans,
    SensingConditions,
    effective_reach,
    organs_from_traits,
    sense,
)
from evolution_simulator.traits import AnimalTraits, PlantTraits
from evolution_simulator.world import Vec, World, WorldSenses

ORIGIN = Vec.of(0.0, 0.0)
HERE = Vec.of(500, 500)
RULES = SensingRules()
SIGHT = SenseOrgans(vision_range=20.0, vision_fov_degrees=120.0, vision_noise=0.1)


def look(*neighbours, organs=SIGHT, rng=None):
    return sense(ORIGIN, 0.0, 0.0, organs, neighbours, rng=rng)


def thing(distance, role="prey", **kwargs):
    return Neighbour(1, role, Vec.of(distance, 0.0), **kwargs)


# --- the rule ---------------------------------------------------------------------------


def test_an_average_animal_moving_at_half_speed_is_seen_at_the_reach():
    assert RULES.visibility(0.7, 0.5) == pytest.approx(1.0)


def test_bigger_is_seen_from_farther_within_limits():
    small, middle, big, huge = (RULES.visibility(r, 0.5) for r in (0.05, 0.7, 1.4, 50.0))
    assert small == RULES.visibility_size_range[0] < middle < big < huge
    assert huge == RULES.visibility_size_range[1]


def test_moving_is_easier_to_see_than_still_and_a_plant_has_only_its_size():
    assert RULES.visibility(0.7, 1.0) > RULES.visibility(0.7, 0.5) > RULES.visibility(0.7, 0.0)
    assert RULES.visibility(0.7, 0.0) == pytest.approx(RULES.still_visibility)
    assert RULES.visibility(5.0) == pytest.approx(
        1.0
    )  # speed_ratio None: a plant, by its own scale


def test_camouflage_cuts_the_distance_it_is_seen_from():
    plain, hidden = RULES.visibility(0.7, 0.5), RULES.visibility(0.7, 0.5, 1.0)
    assert hidden == pytest.approx(plain * (1 - RULES.camouflage_strength))
    assert RULES.visibility(0.7, 0.5, 0.5) == pytest.approx(
        plain * (1 - RULES.camouflage_strength / 2)
    )


def test_the_visibility_rules_reject_bad_values():
    for bad in (
        {"visibility_reference_radius": 0.0},
        {"plant_visibility_reference_radius": -1.0},
        {"visibility_size_range": (0.0, 1.0)},
        {"visibility_size_range": (1.5, 1.0)},
        {"still_visibility": -0.1},
        {"camouflage_strength": 1.0},
    ):
        with pytest.raises(ValueError):
            SensingRules(**bad)


# --- the sensing step ---------------------------------------------------------------------


def test_vision_reaches_a_neighbour_in_proportion_to_its_visibility():
    assert look(thing(25.0, visibility=1.0)).prey_closeness == 0.0  # beyond 20
    assert look(thing(25.0, visibility=1.5)).prey_closeness > 0.0
    assert look(thing(15.0, visibility=0.5)).prey_closeness == 0.0
    assert look(thing(15.0, visibility=1.0)).prey_closeness > 0.0


def test_touch_and_overlap_are_always_seen_and_hearing_and_smell_ignore_visibility():
    assert look(thing(0.0, visibility=0.1)).prey_closeness > 0.0
    ears = SenseOrgans(hearing_range=20.0, smell_range=20.0)
    assert look(thing(10.0, visibility=0.1), organs=ears).prey_closeness > 0.0


def test_a_faint_neighbour_is_reported_with_more_direction_error():
    def spread(visibility):
        rng = random.Random(4)
        return statistics.pstdev(
            look(thing(10.0, visibility=visibility), rng=rng).prey_direction for _ in range(300)
        )

    assert spread(0.5) > spread(1.0) > spread(2.0)


def test_visibility_must_be_above_zero():
    with pytest.raises(ValueError):
        thing(5.0, visibility=0.0)


# --- the body ---------------------------------------------------------------------------------


def test_camouflage_costs_upkeep_with_its_square_and_slows_the_animal():
    plain = AnimalTraits(animal_dna(camouflage="0000"))
    half = AnimalTraits(animal_dna(camouflage="1333"))
    top = AnimalTraits(animal_dna(camouflage="3333"))
    body = DEFAULT_RULES.body
    assert plain.camouflage_upkeep == 0.0 and plain.camouflage == 0.0
    assert top.camouflage_upkeep == pytest.approx(body.camouflage_cost)
    assert half.camouflage_upkeep == pytest.approx(top.camouflage_upkeep / 4, rel=0.01)
    assert top.basal_metabolism == pytest.approx(plain.basal_metabolism + body.camouflage_cost)
    assert top.base_max_speed == pytest.approx(plain.base_max_speed * (1 - body.camouflage_slowing))


def test_camouflage_is_paid_for_so_no_gene_is_left_unpaid():
    from evolution_simulator.trait_defs import ANIMAL_TRAITS

    assert "camouflage" not in ANIMAL_TRAITS.unpaid_genes()
    assert "camouflage upkeep and slowing" in ANIMAL_TRAITS.explain("camouflage").costs


def test_a_first_generation_starts_without_camouflage():
    from evolution_simulator.layouts import founder_animal_dna

    assert all(founder_animal_dna(random.Random(s)).value("camouflage") == 0.0 for s in range(5))


# --- the world ----------------------------------------------------------------------------------

LOOKOUT = {
    "sight_range": "3333",
    "sight_fov": "3333",
    "touch": "0000",
    "hearing": "0000",
    "smell": "0000",
}


def perceived(world, animal):
    return WorldSenses(RULES, noisy=False).perceive(world, animal)


def vision_reach(animal):
    return effective_reach(organs_from_traits(animal.traits), SensingConditions(), RULES)["vision"]


def test_a_camouflaged_animal_is_found_later_than_a_plain_one():
    prey_genes = {"size": "0000"}
    radius = AnimalTraits(animal_dna(**prey_genes)).body_radius
    plain = RULES.visibility(radius, 0.0, 0.0)
    hidden = RULES.visibility(radius, 0.0, AnimalTraits(animal_dna(camouflage="3333")).camouflage)
    assert hidden < plain

    def prey_seen(camouflage, surface_gap):
        world = World(world_config(day_cycle=None))
        me = world.add_animal(animal_dna(size="1111", **LOOKOUT), HERE, heading=0.0)
        centre = me.radius + radius + surface_gap
        world.add_animal(animal_dna(camouflage=camouflage, **prey_genes), HERE + Vec.of(centre, 0))
        return perceived(world, me).prey_closeness > 0.0, vision_reach(me)

    _, reach = prey_seen("0000", 1.0)
    between = reach * (plain + hidden) / 2
    assert prey_seen("0000", between)[0] and not prey_seen("3333", between)[0]


def test_a_wide_plant_is_seen_from_farther_than_a_narrow_one():
    small = PlantTraits(plant_dna(max_biomass="0000")).canopy_radius
    large = PlantTraits(plant_dna(max_biomass="3333")).canopy_radius
    assert RULES.visibility(small) < 1.0 < RULES.visibility(large)

    def plant_seen(max_biomass, canopy, surface_gap):
        world = World(world_config(day_cycle=None))
        me = world.add_animal(animal_dna(**LOOKOUT), HERE, heading=0.0)
        world.add_plant(
            plant_dna(max_biomass=max_biomass), HERE + Vec.of(me.radius + canopy + surface_gap, 0)
        )
        return perceived(world, me).plant_closeness > 0.0, vision_reach(me)

    _, reach = plant_seen("0000", small, 1.0)
    between = reach * (RULES.visibility(small) + RULES.visibility(large)) / 2
    assert plant_seen("3333", large, between)[0] and not plant_seen("0000", small, between)[0]
