"""Diploid genomes and dominance (DNA.13)."""

import random

import pytest

from evolution_simulator.diploid import CODOMINANT, DiploidDNA, DominanceModel
from evolution_simulator.dna import DNA, BlockSpec, GeneSpec, GenomeLayout
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT, dna_from_dict
from evolution_simulator.trait_defs import ANIMAL_TRAITS, PLANT_TRAITS
from evolution_simulator.traits import AnimalTraits, PlantTraits

LAYOUT = GenomeLayout(
    "d",
    1,
    [
        GeneSpec("a"),
        GeneSpec("b"),
        GeneSpec("flag", 1),
        BlockSpec("w", 3, digits_per_value=1, low=-1.0, high=2.0, segment="brain"),
    ],
)
LOW = DNA(LAYOUT, "000000000000")
HIGH = DNA(LAYOUT, "333333333333")


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


# --- reading genes ----------------------------------------------------------


def test_codominant_is_the_average():
    genome = DiploidDNA(LOW, HIGH)
    assert genome.value("a") == pytest.approx(0.5)
    assert genome.values("w") == pytest.approx((0.5, 0.5, 0.5))  # midway between -1 and 2
    assert genome.ploidy == 2 and LOW.ploidy == 1


def test_homozygous_reads_like_the_haploid_genome():
    dna = DNA.random(ANIMAL_LAYOUT, rng(1))
    genome = DiploidDNA.from_haploid(dna)
    for dominance in (-1.0, 0.0, 1.0):
        same = DiploidDNA.from_haploid(dna, DominanceModel(dominance))
        assert same.value("size") == pytest.approx(dna.value("size"))
        assert same.digit("sex_strategy") == dna.digit("sex_strategy")
        assert same.values("brain") == pytest.approx(dna.values("brain"))
    assert genome.is_homozygous("size")


def test_dominance_coefficient_picks_between_the_strands():
    low_value, high_value = 0.0, 1.0
    for coefficient, expected in ((1.0, high_value), (-1.0, low_value), (0.5, 0.75), (0.0, 0.5)):
        genome = DiploidDNA(LOW, HIGH, DominanceModel(coefficient))
        assert genome.value("a") == pytest.approx(expected)


def test_strand_order_does_not_change_expression():
    genome = DiploidDNA(LOW, HIGH, DominanceModel(0.3))
    swapped = DiploidDNA(HIGH, LOW, DominanceModel(0.3))
    assert genome.value("a") == swapped.value("a")
    assert genome == swapped and hash(genome) == hash(swapped)


def test_dominance_can_differ_per_gene():
    model = DominanceModel(0.0, {"a": 1.0, "b": -1.0})
    genome = DiploidDNA(LOW, HIGH, model)
    assert (genome.value("a"), genome.value("b")) == (1.0, 0.0)
    assert model.coefficient("flag") == 0.0


def test_category_genes_blend_digits_and_round_half_up():
    one, three = DNA(LAYOUT, "0" * 8 + "1" + "000"), DNA(LAYOUT, "0" * 8 + "3" + "000")
    assert DiploidDNA(one, three).digit("flag") == 2
    assert DiploidDNA(one, DNA(LAYOUT, "0" * 8 + "2" + "000")).digit("flag") == 2  # 1.5 rounds up
    assert DiploidDNA(one, three, DominanceModel(1.0)).digit("flag") == 3
    assert DiploidDNA(one, three, DominanceModel(-1.0)).digit("flag") == 1


def test_expressed_values_stay_between_the_strands():
    for seed in range(50):
        genome = DiploidDNA.random(ANIMAL_LAYOUT, rng(seed), DominanceModel(0.7))
        first, second = genome.strands
        for gene in ANIMAL_LAYOUT.genes:
            if gene.block is None and gene.length > 1:
                low, high = sorted((first.value(gene.id), second.value(gene.id)))
                assert low <= genome.value(gene.id) <= high


def test_wrong_kinds_of_gene_raise_like_dna():
    genome = DiploidDNA(LOW, HIGH)
    with pytest.raises(ValueError):
        genome.digit("a")
    with pytest.raises(ValueError):
        genome.values("a")
    with pytest.raises(KeyError):
        genome.value("nope")


# --- the dominance model ----------------------------------------------------


@pytest.mark.parametrize("bad", [1.1, -1.5])
def test_dominance_out_of_range_rejected(bad):
    with pytest.raises(ValueError):
        DominanceModel(bad)
    with pytest.raises(ValueError):
        DominanceModel(0.0, {"a": bad})


def test_dominance_naming_unknown_genes_rejected():
    with pytest.raises(ValueError):
        DiploidDNA(LOW, HIGH, DominanceModel(0.0, {"nope": 1.0}))


def test_dominance_is_a_value():
    assert DominanceModel(0.0, {"a": 1.0}) == DominanceModel(0.0, (("a", 1.0),))
    assert hash(DominanceModel(0.2)) == hash(DominanceModel(0.2))
    assert CODOMINANT == DominanceModel()


# --- construction and value semantics ---------------------------------------


def test_strands_must_share_a_layout_and_be_dna():
    with pytest.raises(TypeError):
        DiploidDNA(LOW, DNA(PLANT_LAYOUT, "0" * PLANT_LAYOUT.length))
    with pytest.raises(TypeError):
        DiploidDNA(LOW, "0000")  # type: ignore[arg-type]


def test_immutable():
    genome = DiploidDNA(LOW, HIGH)
    with pytest.raises(AttributeError):
        genome.strands = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        del genome.strands


def test_random_is_seeded():
    assert DiploidDNA.random(LAYOUT, rng(3)) == DiploidDNA.random(LAYOUT, rng(3))
    assert DiploidDNA.random(LAYOUT, rng(3)) != DiploidDNA.random(LAYOUT, rng(4))


def test_distance_ignores_strand_order_and_is_a_fraction():
    genome = DiploidDNA(LOW, HIGH)
    assert genome.distance(DiploidDNA(HIGH, LOW)) == 0.0
    assert genome.distance(genome) == 0.0
    assert DiploidDNA(LOW, LOW).distance(DiploidDNA(HIGH, HIGH)) == 1.0
    assert DiploidDNA(LOW, LOW).distance(DiploidDNA(LOW, HIGH)) == pytest.approx(0.5)
    with pytest.raises(TypeError):
        genome.distance(LOW)  # type: ignore[arg-type]


# --- reproduction -----------------------------------------------------------


def test_gamete_is_a_haploid_mix_of_the_two_strands():
    genome = DiploidDNA(LOW, HIGH)
    seen_mixed = False
    for seed in range(40):
        gamete = genome.gamete(rng(seed))
        assert isinstance(gamete, DNA) and gamete.layout == LAYOUT
        seen_mixed |= gamete not in (LOW, HIGH)
    assert seen_mixed


def test_gamete_accepts_any_crossover_strategy():
    genome = DiploidDNA(LOW, HIGH)
    assert genome.gamete(rng(2), DNA.crossover) == LOW.crossover(HIGH, rng(2))


def test_homozygous_parent_always_gives_its_strand():
    genome = DiploidDNA.from_haploid(HIGH)
    assert genome.gamete(rng()) == HIGH


def test_child_gets_one_gamete_from_each_parent():
    mother, father = DiploidDNA(LOW, LOW), DiploidDNA(HIGH, HIGH)
    child = mother.reproduce(father, rng(), mutation_rate=0.0)
    assert set(child.strands) == {LOW, HIGH}
    assert child.value("a") == pytest.approx(0.5)


def test_reproduction_is_seeded_and_leaves_parents_alone():
    a, b = DiploidDNA.random(LAYOUT, rng(1)), DiploidDNA.random(LAYOUT, rng(2))
    before = (repr(a), repr(b))
    assert a.reproduce(b, rng(5)) == a.reproduce(b, rng(5))
    assert (repr(a), repr(b)) == before


def test_asexual_child_copies_both_strands():
    parent = DiploidDNA(LOW, HIGH)
    child = parent.reproduce(None, rng(), mutation_rate=0.0)
    assert child == parent
    mutated = parent.reproduce(None, rng(), mutation_rate=1.0)
    assert all(a != b for a, b in zip(mutated.strands[0].sequence, LOW.sequence))


def test_child_keeps_the_dominance_model():
    model = DominanceModel(0.4)
    a, b = DiploidDNA.random(LAYOUT, rng(1), model), DiploidDNA.random(LAYOUT, rng(2), model)
    assert a.reproduce(b, rng()).dominance == model


def test_expected_changes_per_child_match_the_layout_not_per_strand():
    base = DiploidDNA.random(ANIMAL_LAYOUT, rng(1))
    r, trials, changed = rng(2), 400, 0
    expected = sum(ANIMAL_LAYOUT.default_mutations.values())
    for _ in range(trials):
        child = base.reproduce(None, r)
        for old, new in zip(base.strands, child.strands):
            changed += sum(a != b for a, b in zip(old.sequence, new.sequence))
    assert changed / trials == pytest.approx(expected, rel=0.1)


def test_per_digit_rate_applies_to_every_digit_of_both_strands():
    base = DiploidDNA.random(LAYOUT, rng(1))
    r, trials, changed = rng(2), 600, 0
    for _ in range(trials):
        child = base.reproduce(None, r, mutation_rate=0.1)
        for old, new in zip(base.strands, child.strands):
            changed += sum(a != b for a, b in zip(old.sequence, new.sequence))
    assert changed / trials == pytest.approx(0.1 * 2 * LAYOUT.length, rel=0.12)


def test_per_segment_settings_pass_through_and_split_across_strands():
    base = DiploidDNA.random(LAYOUT, rng(1))
    r, trials, changed = rng(2), 800, 0
    for _ in range(trials):
        child = base.reproduce(None, r, mutations_per_segment={"body": 1.0, "brain": 0.0})
        for old, new in zip(base.strands, child.strands):
            diff = [i for i, (a, b) in enumerate(zip(old.sequence, new.sequence)) if a != b]
            assert all(i < 9 for i in diff)  # nothing in the brain segment
            changed += len(diff)
    assert changed / trials == pytest.approx(1.0, rel=0.1)


def test_mutation_settings_are_validated():
    a = DiploidDNA.random(LAYOUT, rng(1))
    with pytest.raises(ValueError):
        a.reproduce(None, rng(), mutation_rate=0.1, mutations_per_segment={"body": 1.0})
    with pytest.raises(ValueError):
        a.reproduce(None, rng(), mutations_per_segment={"nope": 1.0})
    with pytest.raises(ValueError):
        a.reproduce(None, rng(), position_bias=0.0)


def test_locality_and_bias_reach_the_strands():
    base = DiploidDNA(DNA(LAYOUT, "1" * LAYOUT.length), DNA(LAYOUT, "1" * LAYOUT.length))
    child = base.reproduce(None, rng(), mutation_rate=0.5, locality=1.0)
    for old, new in zip(base.strands, child.strands):
        assert {b - a for a, b in zip(old.sequence, new.sequence)} <= {-1, 0, 1}


def test_cannot_reproduce_with_other_species_or_haploid_dna():
    animal = DiploidDNA.random(ANIMAL_LAYOUT, rng(1))
    plant = DiploidDNA.random(PLANT_LAYOUT, rng(1))
    with pytest.raises(TypeError):
        animal.reproduce(plant, rng())
    with pytest.raises(TypeError):
        animal.reproduce(DNA.random(ANIMAL_LAYOUT, rng(2)), rng())  # type: ignore[arg-type]


# --- saving -----------------------------------------------------------------


def test_round_trip_through_a_dict():
    model = DominanceModel(0.25, {"size": -1.0})
    genome = DiploidDNA.random(ANIMAL_LAYOUT, rng(4), model)
    restored = DiploidDNA.from_dict(genome.to_dict(), (ANIMAL_LAYOUT, PLANT_LAYOUT))
    assert restored == genome and restored.dominance == model


def test_loading_checks_the_layout_version_and_the_shape():
    genome = DiploidDNA.random(PLANT_LAYOUT, rng(4))
    data = genome.to_dict()
    data["strands"][1]["layout_version"] = 99
    with pytest.raises(ValueError):
        DiploidDNA.from_dict(data, (PLANT_LAYOUT,))
    with pytest.raises(ValueError):
        DiploidDNA.from_dict(DNA.random(PLANT_LAYOUT, rng()).to_dict(), (PLANT_LAYOUT,))
    # a haploid genome still loads through its own function
    assert dna_from_dict(DNA.random(PLANT_LAYOUT, rng()).to_dict()).ploidy == 1


# --- organisms use either kind ----------------------------------------------


def test_traits_express_a_diploid_genome():
    genome = DiploidDNA(DNA(PLANT_LAYOUT, "0" * 24), DNA(PLANT_LAYOUT, "3" * 24))
    values = PLANT_TRAITS.express(genome)
    assert values["max_biomass"] == pytest.approx(110.0)  # midway between 20 and 200


def test_organisms_are_built_from_a_diploid_genome_like_a_haploid_one():
    dna = DNA.random(ANIMAL_LAYOUT, rng(8))
    haploid, diploid = AnimalTraits(dna), AnimalTraits(DiploidDNA.from_haploid(dna))
    assert dict(haploid.phenotype) == pytest.approx(dict(diploid.phenotype))
    assert haploid.max_energy == pytest.approx(diploid.max_energy)
    assert diploid.brain.to_values() == pytest.approx(haploid.brain.to_values())
    plant = PlantTraits(DiploidDNA.random(PLANT_LAYOUT, rng(9)))
    assert plant.phenotype["max_biomass"] > 0


def test_a_whole_life_cycle_runs_on_diploid_genomes():
    r = rng(5)
    parents = [DiploidDNA.random(ANIMAL_LAYOUT, r) for _ in range(2)]
    child = parents[0].reproduce(parents[1], r)
    assert isinstance(child, DiploidDNA)
    animal = AnimalTraits(child)
    assert animal.max_energy > 0
    assert set(ANIMAL_TRAITS.express(child)) == {t.name for t in ANIMAL_TRAITS}


def test_other_layouts_are_refused_by_organisms():
    with pytest.raises(TypeError):
        AnimalTraits(DiploidDNA.random(PLANT_LAYOUT, rng()))
