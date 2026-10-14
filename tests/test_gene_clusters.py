"""Gene clusters (DNA.15): weighted terms, modifier genes, cluster tags in the layout, crossover
linkage and the explained cost table."""

import random
from itertools import pairwise

import pytest

from evolution_simulator.diploid import DiploidDNA, DominanceModel
from evolution_simulator.dna import DNA, BlockSpec, GeneSpec, GenomeLayout
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.trait_defs import (
    ANIMAL_TRAITS,
    DEFAULT_MODIFIER_WEIGHT,
    MODIFIER_SWING,
    Combine,
    GeneTerm,
    Kind,
    Role,
    TraitDef,
    TraitSet,
)

BASE = DNA.from_string(ANIMAL_LAYOUT, "1" * ANIMAL_LAYOUT.length)

TRIO = GenomeLayout(
    "trio",
    1,
    [
        GeneSpec("main", length=3, cluster="c"),
        GeneSpec("up", length=3, cluster="c"),
        GeneSpec("down", length=3, cluster="c"),
        GeneSpec("loose", length=3),
    ],
)


def trio(main: float, up: float, down: float) -> DNA:
    dna = DNA.from_string(TRIO, "0" * TRIO.length)
    return dna.with_value("main", main).with_value("up", up).with_value("down", down)


def genome(**values: float) -> DNA:
    dna = BASE
    for gene_id, value in values.items():
        dna = dna.with_value(gene_id, value)
    return dna


def modified(weight_up: float | None = None, weight_down: float | None = -0.2) -> TraitDef:
    return TraitDef(
        "mix",
        (
            GeneTerm("main"),
            GeneTerm("up", Role.MODIFIER, weight_up),
            GeneTerm("down", Role.MODIFIER, weight_down),
        ),
        combine=Combine.MODIFIED,
    )


# --- reading a cluster -----------------------------------------------------------


def test_a_plain_gene_id_reads_as_before():
    plain = TraitDef("t", ("main", "up"), 10.0, 20.0)
    dna = trio(0.2, 0.8, 0.0)
    assert plain.express(dna) == pytest.approx(
        10.0 + 10.0 * (dna.value("main") + dna.value("up")) / 2
    )
    assert plain.genes == ("main", "up")
    assert [t.weight for t in plain.terms] == [1.0, 1.0]
    assert plain.combine is Combine.MEAN


def test_a_mean_uses_the_weights():
    weighted = TraitDef("t", (GeneTerm("main", weight=3.0), GeneTerm("up")))
    dna = trio(0.4, 0.8, 0.0)
    assert weighted.unit(dna) == pytest.approx((3 * dna.value("main") + dna.value("up")) / 4)


def test_modifiers_at_their_middle_value_leave_the_main_gene_alone():
    dna = trio(0.6, 0.5, 0.5)
    assert modified().unit(dna) == pytest.approx(dna.value("main"), abs=0.01)


def test_a_modifier_at_an_end_changes_the_effect_by_up_to_its_weight():
    trait = modified(weight_down=None)  # both modifiers at the default weight
    low = trio(0.5, 0.0, 0.0)
    high = trio(0.5, 1.0, 1.0)
    assert DEFAULT_MODIFIER_WEIGHT == 0.2 and MODIFIER_SWING == 2.0
    assert trait.unit(low) == pytest.approx(0.5 * 0.6, abs=0.02)
    assert trait.unit(high) == pytest.approx(0.5 * 1.4, abs=0.02)


def test_a_negative_weight_weakens_the_effect_as_the_modifier_rises():
    trait = modified()  # `down` has weight -0.2
    assert trait.unit(trio(0.5, 0.5, 1.0)) < trait.unit(trio(0.5, 0.5, 0.0))
    assert trait.unit(trio(0.5, 0.5, 1.0)) == pytest.approx(0.5 * 0.8, abs=0.01)


def test_a_modified_cluster_is_clamped_to_the_range():
    trait = modified(weight_down=None)
    assert trait.unit(trio(1.0, 1.0, 1.0)) == 1.0
    assert trait.unit(trio(0.0, 1.0, 1.0)) == 0.0


def test_a_cluster_row_can_be_a_string_role():
    term = GeneTerm("up", "modifier", 0.3)
    assert term.role is Role.MODIFIER
    assert TraitDef("t", ("main", term), combine="modified").combine is Combine.MODIFIED


@pytest.mark.parametrize(
    "build",
    [
        lambda: TraitDef("t", (GeneTerm("a"), GeneTerm("b")), combine=Combine.MODIFIED),
        lambda: TraitDef("t", (GeneTerm("a"),), combine=Combine.MODIFIED),
        lambda: TraitDef(
            "t",
            (GeneTerm("a", Role.MODIFIER), GeneTerm("b", Role.MODIFIER)),
            combine=Combine.MODIFIED,
        ),
        lambda: TraitDef(
            "t", (GeneTerm("a"), GeneTerm("b", Role.MODIFIER, 0.0)), combine=Combine.MODIFIED
        ),
        lambda: TraitDef(
            "t", (GeneTerm("a"), GeneTerm("a", Role.MODIFIER)), combine=Combine.MODIFIED
        ),
        lambda: TraitDef("t", (GeneTerm("a", weight=0.0), GeneTerm("b"))),
        lambda: TraitDef("t", (GeneTerm("a", weight=-1.0), GeneTerm("b"))),
        lambda: GeneTerm("a", weight=float("nan")),
        lambda: GeneTerm(""),
        lambda: TraitDef("t", (GeneTerm("a"), GeneTerm("b")), kind=Kind.CATEGORY),
    ],
)
def test_a_badly_formed_cluster_is_rejected(build):
    with pytest.raises(ValueError):
        build()


# --- dominance first, then the cluster ---------------------------------------------


def test_dominance_acts_inside_each_gene_before_the_cluster_combines():
    # The reproduction design's litter-capacity example (DNA.14): fertility partly dominant high.
    strands = (
        genome(fertility=0.9, size=0.2, recovery=0.9),
        genome(fertility=0.5, size=0.8, recovery=0.9),
    )
    dominance = DominanceModel(per_gene={"fertility": 0.5})
    diploid = DiploidDNA(*strands, dominance)
    trait = ANIMAL_TRAITS["litter_capacity"]

    fertility, size, recovery = (diploid.value(g) for g in ("fertility", "size", "recovery"))
    assert fertility == pytest.approx(0.80, abs=0.02)
    assert size == pytest.approx(0.50, abs=0.01)
    expected = fertility * (1 + 2 * (0.2 * (size - 0.5) + 0.2 * (recovery - 0.5)))
    assert trait.unit(diploid) == pytest.approx(expected)

    # Combining the cluster inside each strand and then blending would give another answer.
    per_strand = [trait.unit(strand) for strand in strands]
    assert sum(per_strand) / 2 != pytest.approx(trait.unit(diploid), abs=0.005)


# --- the litter capacity row -----------------------------------------------------


@pytest.mark.parametrize(
    ("fertility", "size", "recovery", "litter"),
    [
        (0.75, 0.5, 0.5, 6),  # neutral modifiers
        (0.75, 1.0, 1.0, 8),  # a big, quick healer: the unit value is clamped from 1.05 to 1.0
        (0.75, 0.0, 0.0, 4),  # a small, slow healer
    ],
)
def test_the_same_fertility_gene_gives_different_litters(fertility, size, recovery, litter):
    from evolution_simulator.config import DEFAULT_RULES
    from evolution_simulator.traits import AnimalTraits

    LITTER_MAX = DEFAULT_RULES.reproduction.litter_max

    traits = AnimalTraits(genome(fertility=fertility, size=size, recovery=recovery))
    assert (
        traits.litter_size
        == litter
        == 1 + round(traits.phenotype["litter_capacity"] * (LITTER_MAX - 1))
    )


# --- mutation steps ----------------------------------------------------------------


def test_equal_weights_scale_the_mutation_step_by_the_number_of_genes():
    layout = GenomeLayout("pair", 1, [GeneSpec("a"), GeneSpec("b"), GeneSpec("c")])
    mean = TraitSet("t", layout, [TraitDef("m", ("a", "b"), mutation_step=0.05)])
    single = TraitSet("t", layout, [TraitDef("m", ("a",), mutation_step=0.10)])
    assert mean["m"].step_multiplier("a") == 2.0
    assert mean.position_biases()["a"] == single.position_biases()["a"]


def test_weights_set_each_genes_share_of_the_step():
    trait = TraitDef("t", (GeneTerm("a", weight=3.0), GeneTerm("b")))
    assert trait.step_multiplier("a") == pytest.approx(4 / 3)
    assert trait.step_multiplier("b") == pytest.approx(4.0)


def test_a_modifier_is_a_second_order_change():
    trait = modified(weight_up=0.2)
    assert trait.step_multiplier("main") == 1.0
    assert trait.step_multiplier("up") == pytest.approx(
        1 / 0.4
    )  # moves the trait 0.4 of its change
    heavy = modified(weight_up=0.9)
    assert (
        heavy.step_multiplier("up") == 1.0
    )  # capped: a modifier cannot move it more than the main


# --- the layout ----------------------------------------------------------------------


def test_the_animal_clusters_are_tagged_and_consecutive():
    clusters = ANIMAL_LAYOUT.clusters
    assert clusters["frame"] == ("size", "speed", "agility")
    assert clusters["repair"] == ("somatic_maint", "recovery")
    assert clusters["reproduction"] == (
        "repro_drive",
        "repro_cooldown",
        "fertility",
        "parenting",
        "sex_strategy",
    )
    assert "touch" not in {g for members in clusters.values() for g in members}
    for members in clusters.values():
        genes = [ANIMAL_LAYOUT.gene(g) for g in members]
        assert all(a.end == b.start for a, b in pairwise(genes))
    assert PLANT_LAYOUT.clusters == {}


def test_a_cluster_must_be_consecutive():
    with pytest.raises(ValueError, match="consecutive"):
        GenomeLayout(
            "split",
            1,
            [GeneSpec("a", cluster="x"), GeneSpec("b"), GeneSpec("c", cluster="x")],
        )


def test_a_cluster_must_sit_inside_one_segment():
    with pytest.raises(ValueError, match="one segment"):
        GenomeLayout(
            "split",
            1,
            [GeneSpec("a", cluster="x"), GeneSpec("b", segment="other", cluster="x")],
        )


def test_a_cluster_needs_a_name_and_a_block_has_none():
    with pytest.raises(ValueError):
        GeneSpec("a", cluster="")
    block = BlockSpec("w", count=2, digits_per_value=1)
    assert GenomeLayout("b", 1, [GeneSpec("a", cluster="x"), block]).gene("w").cluster is None


def test_clusters_are_part_of_the_layouts_identity_but_the_unit_flag_is_not():
    plain = GenomeLayout("l", 1, [GeneSpec("a"), GeneSpec("b")])
    tagged = GenomeLayout("l", 1, [GeneSpec("a", cluster="x"), GeneSpec("b", cluster="x")])
    joined = GenomeLayout(
        "l", 1, [GeneSpec("a", cluster="x"), GeneSpec("b", cluster="x")], cluster_units=True
    )
    assert plain != tagged
    assert tagged == joined and hash(tagged) == hash(joined)


def test_a_trait_can_be_held_to_a_layout_cluster():
    trait = TraitDef("stat", ("size", "speed"), cluster="frame")
    assert TraitSet("ok", ANIMAL_LAYOUT, [trait])
    with pytest.raises(ValueError, match="outside cluster"):
        TraitSet("bad", ANIMAL_LAYOUT, [TraitDef("stat", ("size", "fear"), cluster="frame")])
    with pytest.raises(ValueError, match="does not have"):
        TraitSet("bad", ANIMAL_LAYOUT, [TraitDef("stat", ("size",), cluster="nope")])


# --- crossover keeps neighbours together ---------------------------------------------


def split_rate(layout: GenomeLayout, first: str, second: str, trials: int = 4000) -> float:
    """How often a child's two genes do not both come whole from one parent."""
    zeros = DNA.from_string(layout, "0" * layout.length)
    ones = DNA.from_string(layout, "1" * layout.length)
    rng = random.Random(5)
    a, b = layout.gene(first), layout.gene(second)
    split = 0
    for _ in range(trials):
        child = zeros.crossover_linked(ones, rng).sequence
        split += len(set(child[a.start : a.end] + child[b.start : b.end])) > 1
    return split / trials


def test_neighbouring_cluster_genes_are_rarely_split_by_crossover():
    assert split_rate(ANIMAL_LAYOUT, "size", "speed") < 0.06
    assert split_rate(ANIMAL_LAYOUT, "repro_drive", "repro_cooldown") < 0.06
    # Ten genes apart, about ten cut points in forty-one lie between them: far more than for neighbours.
    assert split_rate(ANIMAL_LAYOUT, "size", "taste") > 0.15


def test_whole_cluster_units_merge_each_cluster_into_one_crossover_unit():
    joined = GenomeLayout(
        ANIMAL_LAYOUT.name,
        ANIMAL_LAYOUT.version,
        ANIMAL_LAYOUT.specs,
        cluster_units=True,
    )
    assert not ANIMAL_LAYOUT.cluster_units and joined.cluster_units
    assert len(ANIMAL_LAYOUT.units) == 26 + 17
    assert len(joined.units) == 13 + 17  # eight clusters hold thirteen genes fewer as units
    assert (0, 12) in joined.units  # the frame cluster
    assert (67, 80) in joined.units  # the reproduction cluster
    assert joined.units[-17][0] >= 96  # the brain's groups follow, unchanged

    zeros = DNA.from_string(joined, "0" * joined.length)
    ones = DNA.from_string(joined, "1" * joined.length)
    rng = random.Random(9)
    for _ in range(300):
        child = zeros.crossover_linked(ones, rng, mean_cuts=3.0, gene_fidelity=1.0)
        for start, end in joined.units:
            assert len(set(child.sequence[start:end])) == 1


# --- the cost table -----------------------------------------------------------------


def test_explain_lists_the_genes_clusters_neighbours_and_costs():
    litter = ANIMAL_TRAITS.explain("litter_capacity")
    assert litter.combine is Combine.MODIFIED
    assert [(t.gene, t.role, t.weight) for t in litter.terms] == [
        ("fertility", Role.MAIN, 1.0),
        ("size", Role.MODIFIER, 0.2),
        ("recovery", Role.MODIFIER, 0.2),
    ]
    assert litter.clusters == ("reproduction", "frame", "repair")
    assert litter.shared["size"] == ("size", "mass")  # pleiotropy: other traits read the gene too
    assert "gestation" in litter.costs
    mass = ANIMAL_TRAITS.explain("mass")
    assert mass.costs == ("body upkeep", "movement burn")
    assert mass.clusters == ("frame",)


def test_the_cost_table_names_real_traits():
    assert set(ANIMAL_TRAITS.costs) >= {"repair upkeep", "fertility upkeep", "birth cost"}
    with pytest.raises(ValueError, match="unknown traits"):
        TraitSet("bad", PLANT_LAYOUT, [TraitDef("t", ("toxicity",))], costs={"c": ("nope",)})


def test_the_genes_the_cost_table_leaves_free_are_a_known_short_list():
    # What pays for these is not in traits.py yet (TRAIT.9 will decide). A new
    # gene that lands here without a cost should be a deliberate choice.
    assert ANIMAL_TRAITS.unpaid_genes() == (
        "speed",
        "agility",
        "aggression",
        "fear",
        "sex_strategy",
        "brain_gain",
        "curiosity",
        "learning_rate",
    )


def test_every_reproduction_gene_is_paid_for():
    paid = set(ANIMAL_LAYOUT.clusters["reproduction"]) - set(ANIMAL_TRAITS.unpaid_genes())
    assert paid == {"repro_drive", "repro_cooldown", "fertility", "parenting"}
