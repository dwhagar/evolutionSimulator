"""Sense genes (SENSE.11): ranges that can reach zero, noise from the gene, cost on covered area."""

import itertools
import math
import random
import statistics

import pytest

from evolution_simulator import sense_genes as sg
from evolution_simulator.config import DEFAULT_RULES
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, FOUNDER_SENSE_SPREAD, seed_sense_genes
from evolution_simulator.sensing import Neighbour, SenseOrgans, organs_from_traits, sense
from evolution_simulator.traits import AnimalTraits
from evolution_simulator.world import Vec, World, WorldConfig


def animal(**genes: str) -> AnimalTraits:
    """All-zero animal DNA with the named genes set to the given digit strings."""
    digits = ["0"] * ANIMAL_LAYOUT.length
    for name, text in genes.items():
        gene = ANIMAL_LAYOUT.gene(name)
        digits[gene.start : gene.end] = text
    return AnimalTraits(DNA(ANIMAL_LAYOUT, "".join(digits)))


# --- range floor -------------------------------------------------------------------


def test_vision_hearing_and_smell_can_be_lost():
    blind = animal()
    assert blind.effective_sight_range == 0.0
    assert blind.hearing_range == 0.0
    assert blind.smell_range == 0.0
    assert blind.current_sight_range == 0.0 and blind.current_hearing_range == 0.0


def test_the_ends_of_each_range():
    sharp = animal(sight_range="3333", sight_acuity="3333", hearing="3333", smell="3333")
    assert sharp.hearing_range == pytest.approx(85.0)
    assert sharp.smell_range == pytest.approx(100.0)
    assert sharp.fov_degrees == pytest.approx(30.0)  # the narrowest field, 15 degrees either side
    assert sharp.effective_sight_range == pytest.approx(84.0)  # narrow field allows acuity 1
    wide = animal(sight_range="3333", sight_fov="3333", sight_acuity="3333")
    assert wide.fov_degrees == pytest.approx(360.0)
    assert wide.acuity == 0.0  # the widest field leaves no acuity to use
    assert wide.effective_sight_range == pytest.approx(36.0)


def test_touch_is_always_on():
    numb = animal(touch="0000")
    assert numb.tactile_range == pytest.approx(numb.body_radius * 1.1)
    assert organs_from_traits(numb).touch_reach > 0.0
    assert (
        organs_from_traits(animal(touch="3333")).touch_reach > organs_from_traits(numb).touch_reach
    )


RULES = DEFAULT_RULES.organs
NOISE = {"hearing": RULES.hearing_noise, "smell": RULES.smell_noise}


# --- noise ---------------------------------------------------------------------------


def test_noise_falls_as_the_gene_rises():
    for organ, (worst, best) in NOISE.items():
        assert sg.direction_noise(organ, 0.0) == worst
        assert sg.direction_noise(organ, 1.0) == best
        assert sg.direction_noise(organ, 0.5) == pytest.approx((worst + best) / 2)
        assert worst > best
        assert sg.direction_noise(organ, 2.0) == best and sg.direction_noise(organ, -1.0) == worst
    assert sg.vision_direction_noise(0.5) < sg.direction_noise("hearing", 0.5)
    assert sg.direction_noise("hearing", 0.5) < sg.direction_noise("smell", 0.5)


def test_animals_carry_the_noise_their_genes_give():
    dull = animal()
    sharp = animal(sight_acuity="3333", hearing="3333", smell="3333")
    assert (dull.vision_noise, dull.hearing_noise, dull.smell_noise) == (0.02, 0.30, 0.50)
    assert (dull.vision_closeness_noise) == pytest.approx(0.05)
    assert sharp.vision_noise == pytest.approx(0.005)
    assert (sharp.hearing_noise, sharp.smell_noise) == (0.15, 0.25)
    assert sharp.vision_closeness_noise == pytest.approx(0.01)


# --- cost on covered area ------------------------------------------------------------


def test_areas():
    assert sg.circle_area(10.0) == pytest.approx(math.pi * 100.0)
    assert sg.cone_area(10.0, 360.0) == pytest.approx(sg.circle_area(10.0))
    assert sg.cone_area(10.0, 90.0) == pytest.approx(sg.circle_area(10.0) / 4)
    assert sg.cone_area(0.0, 120.0) == 0.0


def test_a_lost_sense_costs_nothing_and_cost_grows_with_the_area_covered():
    assert sg.sense_cost(0.0, 360.0, 0.0, 0.0, 0.0, 0.0) == 0.0
    small = sg.sense_cost(0.0, 360.0, 20.0, 0.0, 0.0, 0.0)
    big = sg.sense_cost(0.0, 360.0, 40.0, 0.0, 0.0, 0.0)
    assert big == pytest.approx(4 * small)  # twice the range, four times the area
    assert sg.sense_cost(30.0, 90.0, 0, 0, 0, 0) == pytest.approx(
        sg.sense_cost(30.0, 360.0, 0, 0, 0, 0) / 4
    )  # a quarter of the field costs a quarter
    assert sg.sense_cost(0, 360, 0, 0, 1.0, 0.0) == RULES.touch_cost
    assert sg.sense_cost(0, 360, 0, 0, 0.0, 0.5) == pytest.approx(RULES.taste_cost * 0.25)


def test_vision_costs_the_most_per_area():
    assert RULES.vision_cost_per_area > max(RULES.hearing_cost_per_area, RULES.smell_cost_per_area)


def test_a_wide_eye_costs_more_than_a_narrow_one_at_the_same_gene():
    narrow = animal(sight_range="3333", sight_fov="0000", sight_acuity="1111")
    wide = animal(sight_range="3333", sight_fov="3333", sight_acuity="1111")
    assert wide.basal_metabolism > narrow.basal_metabolism  # same reach and acuity, more area


def test_a_blind_animal_pays_nothing_for_range_senses():
    blind = animal()
    reproduction = blind.repair_upkeep + blind.readiness_upkeep + blind.drive_upkeep
    expected = blind.basal_metabolism - blind.brain_upkeep - blind.gut_maintenance - reproduction
    assert expected == pytest.approx(0.18 * blind.mass**0.75)


def test_the_sense_bill_is_a_sensible_share_of_basal_metabolism():
    rng = random.Random(1)
    shares = []
    for _ in range(300):
        t = AnimalTraits(DNA.random(ANIMAL_LAYOUT, rng))
        p = t.phenotype
        cost = sg.sense_cost(
            t.effective_sight_range,
            t.fov_degrees,
            t.hearing_range,
            t.smell_range,
            p["touch"],
            p["taste"],
            t.acuity,
        )
        shares.append(cost / t.basal_metabolism)
    assert 0.12 < statistics.mean(shares) < 0.26  # about 19% measured; the old rule gave 22%
    assert max(shares) < 0.6


# --- the seam to the sensing step ------------------------------------------------------


def test_organs_from_traits():
    t = animal(sight_range="3333", sight_fov="1111", hearing="2222", smell="3333", touch="3333")
    organs = organs_from_traits(t)
    assert isinstance(organs, SenseOrgans)
    assert organs.vision_range == t.current_sight_range
    assert organs.vision_fov_degrees == t.fov_degrees
    assert organs.hearing_range == t.current_hearing_range
    assert organs.smell_range == t.smell_range
    assert organs.touch_reach == pytest.approx(t.tactile_range - t.body_radius)
    assert (organs.vision_noise, organs.hearing_noise, organs.smell_noise) == (
        t.vision_noise,
        t.hearing_noise,
        t.smell_noise,
    )
    assert organs.closeness_noise == t.vision_closeness_noise


def test_a_blind_animal_gives_organs_that_sense_nothing_but_touch():
    organs = organs_from_traits(animal())
    assert (organs.vision_range, organs.hearing_range, organs.smell_range) == (0.0, 0.0, 0.0)


# --- the eye: field against acuity (SENSE.16) ------------------------------------------

LEVELS = [i / 20 for i in range(21)]


def test_the_acuity_gene_sits_after_the_field_gene_in_the_sight_cluster():
    assert ANIMAL_LAYOUT.version == 9
    assert ANIMAL_LAYOUT.clusters["sight"] == ("sight_range", "sight_fov", "sight_acuity")
    assert ANIMAL_LAYOUT.gene("sight_acuity").start == ANIMAL_LAYOUT.gene("sight_fov").end


def test_working_acuity_never_exceeds_what_the_field_allows():
    for f in LEVELS:
        for a in LEVELS:
            working = sg.working_acuity(f, a)
            assert working <= 1.0 - f + 1e-12
            assert working <= a
            if a <= 1.0 - f:
                assert working == a  # below the ceiling it is the gene itself
            else:
                assert working == pytest.approx(1.0 - f)  # above it, the ceiling
    assert sg.working_acuity(0.0, 1.0) == 1.0 and sg.working_acuity(1.0, 1.0) == 0.0


def test_the_field_gene_is_a_half_angle_on_a_log_scale():
    assert sg.half_angle(0.0) == pytest.approx(15.0)
    assert sg.half_angle(0.5) == pytest.approx(15.0 * math.sqrt(12.0))  # 52 degrees
    assert sg.half_angle(1.0) == pytest.approx(180.0)
    assert sg.half_angle(-1.0) == pytest.approx(15.0) and sg.half_angle(2.0) == pytest.approx(180.0)
    steps = [sg.half_angle(i / 10) for i in range(11)]
    ratios = [b / a for a, b in itertools.pairwise(steps)]
    assert ratios == pytest.approx([ratios[0]] * 10)  # equal steps multiply by the same factor
    assert animal().fov_degrees == pytest.approx(30.0)
    assert animal(sight_fov="3333").fov_degrees == pytest.approx(360.0)


# Level 0.5 of the range gene, on the frontier (acuity = 1 - field): the design note's table.
FRONTIER = [  # field gene, half-angle, reach, eye cost per tick
    (0.00, 15.0, 42.0, 0.0074),
    (0.20, 25.0, 37.2, 0.0086),
    (0.35, 36.0, 33.6, 0.0093),
    (0.50, 52.0, 30.0, 0.0098),
    (0.65, 75.0, 26.4, 0.0099),
    (0.80, 110.0, 22.8, 0.0095),
    (1.00, 180.0, 18.0, 0.0081),
]


def eye(field: float, level: float = 0.5):
    acuity = sg.working_acuity(field, 1.0 - field)
    reach = sg.vision_reach(60.0 * level, acuity)
    cost = sg.sense_cost(reach, 2.0 * sg.half_angle(field), 0, 0, 0, 0, acuity)
    return reach, cost


@pytest.mark.parametrize(("field", "half", "reach", "cost"), FRONTIER)
def test_reach_and_cost_follow_the_design_table(field, half, reach, cost):
    assert sg.half_angle(field) == pytest.approx(half, abs=0.6)
    got_reach, got_cost = eye(field)
    assert got_reach == pytest.approx(reach, abs=0.05)
    assert got_cost == pytest.approx(cost, abs=0.00005)


def test_the_whole_frontier_costs_about_the_same():
    costs = [eye(f / 20)[1] for f in range(21)]
    assert 0.007 < min(costs) and max(costs) < 0.0102
    assert max(costs) / min(costs) < 1.4  # you choose what to see, not how much to pay
    reaches = [eye(f / 20)[0] for f in range(21)]
    assert reaches == sorted(reaches, reverse=True)  # a wider field means a shorter reach


def test_acuity_sharpens_every_report_and_lengthens_the_reach():
    assert sg.vision_reach(30.0, 0.0) == pytest.approx(18.0)
    assert sg.vision_reach(30.0, 0.5) == pytest.approx(30.0)
    assert sg.vision_reach(30.0, 1.0) == pytest.approx(42.0)
    assert [sg.vision_direction_noise(a) for a in (0.0, 0.5, 1.0)] == pytest.approx(
        [0.02, 0.0125, 0.005]
    )
    assert [sg.vision_closeness_noise(a) for a in (0.0, 0.5, 1.0)] == pytest.approx(
        [0.05, 0.03, 0.01]
    )  # the middle matches the old fixed 0.03


def test_an_unused_acuity_gene_does_nothing_and_costs_nothing():
    capped = animal(sight_range="2222", sight_fov="2222", sight_acuity="3333")
    matching = animal(sight_range="2222", sight_fov="2222", sight_acuity="1111")
    assert capped.acuity == pytest.approx(1.0 - capped.phenotype["sight_fov"])
    assert capped.acuity < 0.5 < animal(sight_acuity="3333").acuity + 0.5
    same_cap = animal(sight_range="2222", sight_fov="2222", sight_acuity="2222")
    assert capped.effective_sight_range == same_cap.effective_sight_range
    assert capped.basal_metabolism == same_cap.basal_metabolism
    assert matching.acuity < capped.acuity  # a lower gene below the ceiling is used as it is


# --- the first generation's eyes ---------------------------------------------------------


def founders(diet: dict[str, str], count: int = 120, seed: int = 4):
    rng = random.Random(seed)
    made = []
    for _ in range(count):
        dna = DNA.random(ANIMAL_LAYOUT, rng)
        for gene_id, digits in diet.items():
            dna = dna.replaced(gene_id, digits)
        made.append(seed_sense_genes(dna, rng))
    return made


def levels(genomes, gene_id):
    return [g.value(gene_id) for g in genomes]


PREDATOR = {"carnivore_eff": "3333", "herbivore_eff": "0000"}
GRAZER = {"carnivore_eff": "0000", "herbivore_eff": "3333"}
GENERALIST = {"carnivore_eff": "2222", "herbivore_eff": "2222"}


def test_founders_start_in_the_middle_with_a_little_spread():
    made = founders(GENERALIST)
    for gene_id in ("sight_range", "hearing", "smell", "touch", "taste"):
        found = levels(made, gene_id)
        assert statistics.mean(found) == pytest.approx(0.5, abs=0.02)
        assert max(found) <= 0.5 + FOUNDER_SENSE_SPREAD + 0.01
        assert min(found) >= 0.5 - FOUNDER_SENSE_SPREAD - 0.01
        assert max(found) - min(found) > 0.05  # not clones
    assert statistics.mean(levels(made, "sight_fov")) == pytest.approx(0.5, abs=0.02)


def test_founder_predators_see_narrow_and_sharp_and_plant_eaters_wide_and_soft():
    predators, grazers = founders(PREDATOR), founders(GRAZER)
    narrow = statistics.mean(levels(predators, "sight_fov"))
    wide = statistics.mean(levels(grazers, "sight_fov"))
    assert narrow == pytest.approx(0.2, abs=0.02) and wide == pytest.approx(0.8, abs=0.02)
    assert statistics.mean(levels(predators, "sight_acuity")) == pytest.approx(0.8, abs=0.02)
    assert statistics.mean(levels(grazers, "sight_acuity")) == pytest.approx(0.2, abs=0.02)
    # About 49 degrees across and a reach of 37 for a pure predator; 219 and 23 for a pure grazer.
    hunter = AnimalTraits(predators[0].replaced("sight_range", "2222"))
    grazing = AnimalTraits(grazers[0].replaced("sight_range", "2222"))
    assert hunter.fov_degrees < 80.0
    assert grazing.fov_degrees > 150.0
    assert hunter.effective_sight_range > grazing.effective_sight_range


def test_founders_start_on_the_frontier_so_no_acuity_goes_unused():
    for diet in (PREDATOR, GRAZER, GENERALIST):
        for dna in founders(diet, count=60):
            field, acuity = dna.value("sight_fov"), dna.value("sight_acuity")
            assert acuity == pytest.approx(1.0 - field, abs=1.5 / 255)
            traits = AnimalTraits(dna)
            assert traits.acuity == pytest.approx(acuity, abs=1.5 / 255)


def test_seeding_changes_only_the_sense_genes_and_follows_the_seed():
    rng = random.Random(9)
    base = DNA.random(ANIMAL_LAYOUT, rng)
    seeded = seed_sense_genes(base, random.Random(1))
    assert seeded == seed_sense_genes(base, random.Random(1))
    assert seeded != seed_sense_genes(base, random.Random(2))
    sense_genes = {"sight_range", "sight_fov", "sight_acuity", "hearing", "smell", "touch", "taste"}
    for gene in ANIMAL_LAYOUT.genes:
        if gene.id not in sense_genes:
            assert seeded.slice_of(gene.id) == base.slice_of(gene.id)


def test_populate_makes_first_generations_with_seeded_senses():
    world = World(WorldConfig(seed=2))
    world.populate(animals=40)
    fields = [a.traits.phenotype["sight_fov"] for a in world.animals]
    assert all(0.0 <= f <= 1.0 for f in fields)
    assert all(a.traits.effective_sight_range > 0.0 for a in world.animals)  # none is born blind
    assert all(
        a.traits.acuity == pytest.approx(1.0 - a.traits.phenotype["sight_fov"], abs=0.01)
        for a in world.animals
    )


# --- what the eye does in the sensing step -----------------------------------------------


def prey_at(degrees: float, distance: float = 12.0) -> Neighbour:
    angle = math.radians(degrees)
    return Neighbour(
        ident=1,
        role="prey",
        position=Vec.of(distance * math.cos(angle), distance * math.sin(angle)),
        radius=0.0,
        loudness=0.0,
        scent=0.0,
    )


def look(organs, target, rng=None):
    return sense(Vec.of(0, 0), 0.0, 0.5, organs, [target], rng=rng)


def test_a_narrow_field_misses_what_a_wide_one_sees_to_the_side():
    sharp = organs_from_traits(animal(sight_range="3333", sight_fov="0000", sight_acuity="3333"))
    wide = organs_from_traits(animal(sight_range="3333", sight_fov="3333", sight_acuity="3333"))
    assert sharp.vision_fov_degrees == pytest.approx(30.0)
    assert wide.vision_fov_degrees == pytest.approx(360.0)
    ahead, aside = prey_at(10.0), prey_at(80.0)
    assert look(sharp, ahead).prey_closeness > 0.0
    assert look(sharp, aside).prey_closeness == 0.0  # outside 15 degrees either side
    assert look(wide, aside).prey_closeness > 0.0
    assert look(wide, aside).prey_direction == pytest.approx(-80.0 / 180.0, abs=0.1)


def test_sharper_eyes_report_closer_to_the_truth_and_equal_seeds_give_equal_reports():
    dull = organs_from_traits(animal(sight_range="3333", sight_acuity="0000"))
    sharp = organs_from_traits(animal(sight_range="3333", sight_fov="0000", sight_acuity="3333"))
    target = prey_at(0.0, 10.0)
    truth = look(sharp, target)
    assert look(sharp, target, rng=random.Random(3)) == look(sharp, target, rng=random.Random(3))
    errors = {}
    for name, organs in (("dull", dull), ("sharp", sharp)):
        errors[name] = statistics.mean(
            abs(look(organs, target, rng=random.Random(i)).prey_closeness - truth.prey_closeness)
            for i in range(300)
        )
    assert errors["sharp"] < errors["dull"]
    assert organs_from_traits(animal()).closeness_noise == pytest.approx(0.05)
    assert sharp.closeness_noise == pytest.approx(0.01)
