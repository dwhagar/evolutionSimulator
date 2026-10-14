import random

import pytest

from evolution_simulator.dna import DNA, GeneSpec, GenomeLayout
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.trait_defs import (
    ANIMAL_TRAITS,
    PLANT_TRAITS,
    Kind,
    Scale,
    TraitDef,
    TraitSet,
)

LAYOUT = GenomeLayout("t", 1, [GeneSpec("a"), GeneSpec("b"), GeneSpec("c", 2), GeneSpec("flag", 1)])


def genome(a="0000", b="0000", c="00", flag="0") -> DNA:
    return DNA(LAYOUT, a + b + c + flag)


# --- one trait --------------------------------------------------------------


def test_linear_mapping_hits_both_ends_and_middle():
    trait = TraitDef("x", ("a",), 10.0, 20.0)
    assert trait.express(genome(a="0000")) == 10.0
    assert trait.express(genome(a="3333")) == 20.0
    assert trait.express(genome(a="1333")) == pytest.approx(10.0 + 10.0 * 127 / 255)


def test_log_mapping_is_geometric():
    trait = TraitDef("size", ("a",), 0.1, 10.0, scale=Scale.LOG)
    assert trait.express(genome(a="0000")) == pytest.approx(0.1)
    assert trait.express(genome(a="3333")) == pytest.approx(10.0)
    assert trait.from_unit(0.5) == pytest.approx(1.0)  # geometric midpoint of 0.1 and 10


def test_integer_trait():
    trait = TraitDef("n", ("a",), 1, 8, kind=Kind.INTEGER)
    assert trait.express(genome(a="0000")) == 1
    assert trait.express(genome(a="3333")) == 8
    assert isinstance(trait.express(genome(a="1111")), int)


def test_category_trait_reads_the_raw_digit():
    trait = TraitDef("sex", ("flag",), kind=Kind.CATEGORY)
    assert trait.express(genome(flag="2")) == 2


def test_polygenic_trait_is_the_mean_of_its_genes():
    trait = TraitDef("poly", ("a", "b"), 0.0, 1.0)
    assert trait.express(genome(a="3333", b="0000")) == pytest.approx(0.5)
    assert trait.express(genome(a="3333", b="3333")) == 1.0
    assert trait.express(genome(a="0000", b="0000")) == 0.0


def test_from_unit_clamps():
    trait = TraitDef("x", ("a",), 0.0, 10.0)
    assert trait.from_unit(-1) == 0.0
    assert trait.from_unit(2) == 10.0


@pytest.mark.parametrize(
    "make",
    [
        lambda: TraitDef(name="", genes=("a",)),
        lambda: TraitDef(name="x", genes=()),
        lambda: TraitDef(name="x", genes=("a",), lo=1.0, hi=1.0),
        lambda: TraitDef(name="x", genes=("a",), lo=2.0, hi=1.0),
        lambda: TraitDef(name="x", genes=("a",), lo=0.0, hi=1.0, scale=Scale.LOG),
        lambda: TraitDef(name="x", genes=("a",), mutation_step=0.0),
        lambda: TraitDef(name="x", genes=("a",), mutation_step=1.5),
        lambda: TraitDef(name="x", genes=("a",), lo=0.5, hi=3, kind=Kind.INTEGER),
        lambda: TraitDef(name="x", genes=("a", "b"), kind=Kind.CATEGORY),
    ],
)
def test_invalid_definitions_rejected(make):
    with pytest.raises(ValueError):
        make()


def test_mutation_step_defaults_to_five_percent_of_range():
    assert TraitDef("x", ("a",)).mutation_step == 0.05


# --- a trait set ------------------------------------------------------------


def test_trait_set_expresses_every_trait_by_name():
    traits = TraitSet(
        "t",
        LAYOUT,
        [TraitDef("low", ("a",), 0.0, 4.0), TraitDef("high", ("a",), 0.0, 8.0)],
    )
    values = traits.express(genome(a="3333"))
    assert values == {"low": 4.0, "high": 8.0}  # one gene, two traits (pleiotropy)
    assert len(traits) == 2 and "low" in traits and traits["high"].hi == 8.0
    assert [t.name for t in traits] == ["low", "high"]


def test_trait_set_rejects_unknown_genes_and_duplicates():
    with pytest.raises(ValueError):
        TraitSet("t", LAYOUT, [TraitDef("x", ("nope",))])
    with pytest.raises(ValueError):
        TraitSet("t", LAYOUT, [TraitDef("x", ("a",)), TraitDef("x", ("b",))])
    with pytest.raises(ValueError):  # category trait on a four-digit gene
        TraitSet("t", LAYOUT, [TraitDef("x", ("a",), kind=Kind.CATEGORY)])


def test_trait_set_rejects_the_wrong_species():
    with pytest.raises(TypeError):
        ANIMAL_TRAITS.express(DNA(PLANT_LAYOUT, "0" * PLANT_LAYOUT.length))


def test_which_traits_depend_on_a_gene():
    traits = TraitSet(
        "t", LAYOUT, [TraitDef("x", ("a",)), TraitDef("y", ("a", "b")), TraitDef("z", ("b",))]
    )
    assert [t.name for t in traits.traits_reading("a")] == ["x", "y"]
    assert [t.name for t in traits.traits_reading("c")] == []
    assert traits.unread_genes() == ("c", "flag")


# --- the real tables --------------------------------------------------------


def test_tables_only_read_genes_that_exist():
    # TraitSet validates this on construction; the point here is that the module imported.
    assert len(ANIMAL_TRAITS) > 0 and len(PLANT_TRAITS) > 0


def test_every_animal_gene_is_read():
    assert ANIMAL_TRAITS.unread_genes() == ()
    assert PLANT_TRAITS.unread_genes() == ()


def test_size_is_pleiotropic_in_the_animal_table():
    readers = {t.name for t in ANIMAL_TRAITS.traits_reading("size")}
    assert readers == {"size", "mass", "litter_capacity"}


def test_encoder_fidelity_feeds_both_call_traits():
    readers = {t.name for t in ANIMAL_TRAITS.traits_reading("encoder_fidelity")}
    assert {"call_radius", "call_energy_cost"} <= readers


def test_expressed_values_stay_inside_their_ranges():
    for seed in range(100):
        for layout, traits in ((ANIMAL_LAYOUT, ANIMAL_TRAITS), (PLANT_LAYOUT, PLANT_TRAITS)):
            values = traits.express(DNA.random(layout, random.Random(seed)))
            for trait in traits:
                if trait.kind is Kind.CATEGORY:
                    assert values[trait.name] in (0, 1, 2, 3)
                else:
                    assert trait.lo <= values[trait.name] <= trait.hi


def test_traits_are_monotonic_in_their_gene():
    for traits, layout in ((ANIMAL_TRAITS, ANIMAL_LAYOUT), (PLANT_TRAITS, PLANT_LAYOUT)):
        for trait in traits:
            if trait.kind is Kind.CATEGORY:
                continue
            gene = layout.gene(trait.genes[0])
            previous = None
            for raw in range(0, 4**gene.length, max(1, 4**gene.length // 16)):
                digits = [0] * layout.length
                for offset in range(gene.length):
                    digits[gene.end - 1 - offset] = (raw // 4**offset) % 4
                value = trait.express(DNA(layout, digits))
                if previous is not None:
                    assert value >= previous
                previous = value


def test_range_edges_match_the_prototype_formulas():
    low = ANIMAL_TRAITS.express(DNA(ANIMAL_LAYOUT, "0" * ANIMAL_LAYOUT.length))
    high = ANIMAL_TRAITS.express(DNA(ANIMAL_LAYOUT, "3" * ANIMAL_LAYOUT.length))
    assert (low["mass"], high["mass"]) == (1.0, 4.0)
    assert (low["fov_degrees"], high["fov_degrees"]) == (40.0, 360.0)
    assert (low["call_energy_cost"], high["call_energy_cost"]) == (1.5, pytest.approx(7.5))
    plant_low = PLANT_TRAITS.express(DNA(PLANT_LAYOUT, "0" * PLANT_LAYOUT.length))
    plant_high = PLANT_TRAITS.express(DNA(PLANT_LAYOUT, "3" * PLANT_LAYOUT.length))
    assert (plant_low["max_biomass"], plant_high["max_biomass"]) == (20.0, 200.0)
    assert (plant_low["seed_count"], plant_high["seed_count"]) == (1, 8)


def test_reproduction_traits_cover_their_ranges():
    low = ANIMAL_TRAITS.express(DNA(ANIMAL_LAYOUT, "0" * ANIMAL_LAYOUT.length))
    high = ANIMAL_TRAITS.express(DNA(ANIMAL_LAYOUT, "3" * ANIMAL_LAYOUT.length))
    assert (low["care_fraction"], high["care_fraction"]) == (0.10, pytest.approx(0.80))
    assert (low["cooldown_days"], high["cooldown_days"]) == (
        pytest.approx(2.0),
        pytest.approx(90.0),
    )
    assert (low["repro_drive"], high["repro_drive"]) == (0.0, 1.0)
    assert (low["fertility"], high["fertility"]) == (0.0, 1.0)
    assert (low["recovery"], high["recovery"]) == (0.0, 1.0)
    # The cooldown is geometric: the middle of the gene is the geometric mean of the ends.
    assert ANIMAL_TRAITS["cooldown_days"].from_unit(0.5) == pytest.approx((2.0 * 90.0) ** 0.5)


def test_each_reproduction_gene_feeds_its_own_trait():
    for gene_id, trait in (
        ("parenting", "care_fraction"),
        ("repro_cooldown", "cooldown_days"),
        ("repro_drive", "repro_drive"),
        ("fertility", "fertility"),
        ("recovery", "recovery"),
    ):
        assert trait in [t.name for t in ANIMAL_TRAITS.traits_reading(gene_id)]
