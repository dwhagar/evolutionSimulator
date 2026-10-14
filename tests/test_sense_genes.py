"""Sense genes (SENSE.11): ranges that can reach zero, noise from the gene, cost on covered area."""

import math
import random
import statistics

import pytest

from evolution_simulator import sense_genes as sg
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT
from evolution_simulator.sensing import SenseOrgans, organs_from_traits
from evolution_simulator.traits import AnimalTraits


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
    sharp = animal(sight_range="3333", hearing="3333", smell="3333")
    assert sharp.hearing_range == pytest.approx(85.0)
    assert sharp.smell_range == pytest.approx(100.0)
    assert sharp.effective_sight_range == pytest.approx(60.0)  # narrowest field: no penalty
    wide = animal(sight_range="3333", sight_fov="3333")
    assert wide.fov_degrees == pytest.approx(360.0)
    assert wide.effective_sight_range == pytest.approx(60.0 * (1 - sg.FOV_RANGE_PENALTY))


def test_touch_is_always_on():
    numb = animal(touch="0000")
    assert numb.tactile_range == pytest.approx(numb.body_radius * 1.1)
    assert organs_from_traits(numb).touch_reach > 0.0
    assert (
        organs_from_traits(animal(touch="3333")).touch_reach > organs_from_traits(numb).touch_reach
    )


# --- noise ---------------------------------------------------------------------------


def test_noise_falls_as_the_gene_rises():
    for sense, (worst, best) in sg.NOISE_AT_GENE.items():
        assert sg.direction_noise(sense, 0.0) == worst
        assert sg.direction_noise(sense, 1.0) == best
        assert sg.direction_noise(sense, 0.5) == pytest.approx((worst + best) / 2)
        assert worst > best
        assert sg.direction_noise(sense, 2.0) == best and sg.direction_noise(sense, -1.0) == worst
    assert sg.direction_noise("vision", 0.5) < sg.direction_noise("hearing", 0.5)
    assert sg.direction_noise("hearing", 0.5) < sg.direction_noise("smell", 0.5)


def test_animals_carry_the_noise_their_genes_give():
    dull, sharp = animal(), animal(sight_range="3333", hearing="3333", smell="3333")
    assert (dull.vision_noise, dull.hearing_noise, dull.smell_noise) == (0.02, 0.30, 0.50)
    assert (sharp.vision_noise, sharp.hearing_noise, sharp.smell_noise) == (0.01, 0.15, 0.25)


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
    assert sg.sense_cost(0, 360, 0, 0, 1.0, 0.0) == sg.TOUCH_COST
    assert sg.sense_cost(0, 360, 0, 0, 0.0, 0.5) == pytest.approx(sg.TASTE_COST * 0.25)


def test_vision_costs_the_most_per_area():
    assert sg.COST_PER_AREA["vision"] > max(sg.COST_PER_AREA["hearing"], sg.COST_PER_AREA["smell"])


def test_a_wide_eye_costs_more_than_a_narrow_one_at_the_same_gene():
    narrow = animal(sight_range="3333", sight_fov="0000")
    wide = animal(sight_range="3333", sight_fov="3333")
    assert wide.basal_metabolism > narrow.basal_metabolism  # 3,421 square units against 1,257


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


def test_a_blind_animal_gives_organs_that_sense_nothing_but_touch():
    organs = organs_from_traits(animal())
    assert (organs.vision_range, organs.hearing_range, organs.smell_range) == (0.0, 0.0, 0.0)
