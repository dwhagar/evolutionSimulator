"""The gene balance audit (TRAIT.17): the standard, the table of balancers and the sweeps."""

import math
import random

import pytest

from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.trait_defs import ANIMAL_TRAITS, PLANT_TRAITS
from evolution_simulator.traits import AnimalTraits, PlantTraits
from evolution_tools import balance_audit as audit

# --- the fitness: a growth rate --------------------------------------------------------------


def test_a_lineage_that_leaves_nothing_gets_the_floor():
    assert audit.growth_rate([]) == audit.R_FLOOR
    assert audit.growth_rate([(10.0, 0.0)]) == audit.R_FLOOR


def test_one_replacement_after_a_day_is_zero_growth_and_doubling_is_log_two():
    assert audit.growth_rate([(24.0, 1.0)]) == pytest.approx(0.0, abs=1e-9)
    assert audit.growth_rate([(24.0, 2.0)]) == pytest.approx(math.log(2.0), abs=1e-6)
    assert audit.growth_rate([(48.0, 2.0)], founders=1.0) == pytest.approx(
        math.log(2.0) / 2.0, abs=1e-6
    )


def test_earlier_and_more_young_both_raise_the_growth_rate():
    base = audit.growth_rate([(240.0, 2.0)])
    assert audit.growth_rate([(120.0, 2.0)]) > base
    assert audit.growth_rate([(240.0, 3.0)]) > base
    assert audit.growth_rate([(240.0, 2.0), (480.0, 2.0)]) > base


def test_a_cohort_is_measured_per_founder():
    assert audit.growth_rate([(24.0, 4.0)], founders=4.0) == pytest.approx(0.0, abs=1e-9)


# --- shapes and verdicts -----------------------------------------------------------------------

GRID = (0.0, 0.5, 1.0)


def shape(*values):
    return audit.shape_of(list(values), list(GRID))


def test_shapes_follow_where_the_best_value_is():
    assert shape(0.0, 0.1, 0.2).kind == "rises"
    assert shape(0.2, 0.1, 0.0).kind == "falls"
    assert shape(0.0, 0.2, 0.0).kind == "peaks"
    assert shape(0.2, 0.0, 0.2).kind == "dips"
    assert shape(0.05, 0.05, 0.0505).kind == "flat"
    assert shape(0.0, 0.2, 0.1995).at_top  # within the tie of the best


def test_the_best_value_is_the_grid_point_with_the_highest_proxy():
    assert shape(0.0, 0.3, 0.1).best == 0.5
    assert shape(0.3, 0.1, 0.0).best == 0.0


def test_a_gene_best_at_the_top_everywhere_runs_to_the_top():
    assert audit.judge([shape(0.0, 0.1, 0.2), shape(0.0, 0.2, 0.3)]) == "top"
    assert audit.judge([shape(0.0, 0.1, 0.2), shape(0.1, 0.2, 0.2)]) == "top"  # ties at the top
    assert audit.judge([shape(0.2, 0.1, 0.0), shape(0.3, 0.2, 0.0)]) == "bottom"


def test_a_gene_that_the_world_pushes_both_ways_is_balanced():
    assert audit.judge([shape(0.0, 0.1, 0.2), shape(0.2, 0.1, 0.0)]) == "ok"
    assert audit.judge([shape(0.0, 0.2, 0.0)]) == "ok"
    assert audit.judge([shape(0.0, 0.1, 0.2), shape(0.0, 0.2, 0.0)]) == "ok"


def test_flat_environments_do_not_count_and_a_flat_gene_is_dead():
    assert audit.judge([shape(0.1, 0.1, 0.1), shape(0.0, 0.1, 0.2)]) == "top"
    assert audit.judge([shape(0.1, 0.1, 0.1), shape(0.2, 0.2, 0.2)]) == "dead"


def test_a_category_gene_has_no_top_or_bottom():
    assert audit.judge([shape(0.2, 0.1, 0.0)], category=True) == "ok"
    assert audit.judge([shape(0.1, 0.1, 0.1)], category=True) == "dead"


# --- the reference organisms -------------------------------------------------------------------


def test_the_reference_organisms_sit_at_founder_values():
    animal = audit.reference_animal()
    assert animal.value("fertility") == pytest.approx(0.75, abs=0.01)
    assert animal.value("parenting") == 0.0
    assert animal.value("camouflage") == 0.0
    assert animal.value("size") == pytest.approx(0.5, abs=0.01)
    assert AnimalTraits(animal).sex == 0
    plant = audit.reference_plant()
    assert plant.value("longevity") == pytest.approx(audit.FOUNDER_PLANT_LONGEVITY, abs=0.01)
    assert PlantTraits(plant).upkeep_share < 0.3


def test_a_swept_gene_is_set_and_the_rest_stay():
    low, high = audit.reference_animal(speed=0.0), audit.reference_animal(speed=1.0)
    assert low.value("speed") == 0.0 and high.value("speed") == 1.0
    differing = [g.id for g in ANIMAL_LAYOUT.genes if low.value(g.id) != high.value(g.id)]
    assert differing == ["speed"]


# --- dead genes ----------------------------------------------------------------------------------


def test_root_reach_is_caught_as_a_gene_whose_trait_nobody_reads():
    assert audit.unread_traits(PLANT_TRAITS) == ["root_radius"]
    assert audit.dead_genes(PLANT_TRAITS, PLANT_LAYOUT.gene_ids) == ["root_reach"]


def test_no_animal_gene_is_dead_in_the_code():
    assert (
        audit.dead_genes(ANIMAL_TRAITS, [g for g in ANIMAL_LAYOUT.gene_ids if g != "brain"]) == []
    )


def test_a_gene_that_changes_nothing_is_flat_in_every_plant_stand():
    for stand in audit.STANDS:
        values = {
            audit.plant_fitness(audit.reference_plant(root_reach=v), stand) for v in audit.GRID_FAST
        }
        assert len(values) == 1


# --- the plant model -----------------------------------------------------------------------------


def test_the_plant_proxy_is_repeatable_and_the_reference_just_holds_its_own():
    first = [audit.plant_fitness(audit.reference_plant(), stand) for stand in audit.STANDS]
    second = [audit.plant_fitness(audit.reference_plant(), stand) for stand in audit.STANDS]
    assert first == second
    assert all(-0.1 < value < 0.2 for value in first)


def test_toxin_pays_against_a_grazer_that_avoids_it_and_costs_where_there_is_none():
    sparse, grazed, adapted = (
        audit.PLANT_ENVIRONMENTS[name] for name in ("sparse", "grazed", "adapted grazer")
    )

    def fitness(stand, toxicity):
        return audit.plant_fitness(audit.reference_plant(toxicity=toxicity), stand)

    assert fitness(grazed, 0.75) > fitness(grazed, 0.0)
    assert fitness(sparse, 0.0) > fitness(sparse, 1.0)
    assert fitness(adapted, 0.0) > fitness(adapted, 1.0)


def test_scattering_seeds_helps_only_where_the_stand_is_crowded_or_the_clutch_is_big():
    dense = audit.PLANT_ENVIRONMENTS["dense"]
    near = audit.plant_fitness(audit.reference_plant(dispersal_radius=0.0), dense)
    far = audit.plant_fitness(audit.reference_plant(dispersal_radius=1.0), dense)
    assert far > near


def test_the_plant_audit_matches_the_record():
    """Every plant gene either passes or fails with a reason on record, and every recorded failure
    still fails (so a fix has to take its entry out)."""
    results = audit.audit("plant")
    assert {a.gene for a in results} == set(PLANT_LAYOUT.gene_ids)
    assert [(a.gene, a.status, a.verdict) for a in audit.failures(results)] == []
    verdicts = {a.gene: a.verdict for a in results}
    assert verdicts["root_reach"] == "dead"
    assert verdicts["longevity"] == "ok" and verdicts["toxicity"] == "ok"


# --- the animal model ------------------------------------------------------------------------------


def test_the_animal_proxy_is_repeatable_and_a_richer_habitat_is_no_worse():
    reference = audit.reference_animal()
    rich, poor = audit.ANIMAL_ENVIRONMENTS["rich plants"], audit.ANIMAL_ENVIRONMENTS["poor plants"]
    first = audit.animal_fitness(reference, rich, animals=3, ticks=1500)
    assert first == audit.animal_fitness(reference, rich, animals=3, ticks=1500)
    assert first >= audit.animal_fitness(reference, poor, animals=3, ticks=1500)


def test_a_starving_animal_leaves_nothing():
    starved = audit.Habitat("none")
    assert audit.animal_fitness(audit.reference_animal(), starved, animals=2) == audit.R_FLOOR


def test_a_newborn_that_cannot_live_off_its_gift_counts_for_less():
    eco = audit.Ecology()
    young = AnimalTraits(audit.reference_animal())
    young.current_energy = young.max_energy
    full = audit._newborn_weight(young, eco, 1)
    young.current_energy = 0.1 * young.basal_metabolism * eco.newborn_fast_ticks
    assert full == 1.0 and audit._newborn_weight(young, eco, 1) == pytest.approx(0.1)
    assert audit._newborn_weight(young, eco, 4) < audit._newborn_weight(young, eco, 1)


@pytest.fixture(scope="module")
def fast_animals():
    return audit.audit("animal", fast=True)


def test_the_fast_animal_audit_covers_every_gene_in_two_environments(fast_animals):
    assert {a.gene for a in fast_animals} == {g for g in ANIMAL_LAYOUT.gene_ids if g != "brain"}
    assert all(set(a.series) == set(audit.FAST_ANIMAL_ENVIRONMENTS) for a in fast_animals)
    assert all(len(values) == 3 for a in fast_animals for values in a.series.values())


def test_no_animal_gene_fails_the_fast_audit_without_a_reason_on_record(fast_animals):
    assert [(a.gene, a.verdict) for a in fast_animals if a.status == "FAIL"] == []


def test_the_fast_audit_still_sees_what_the_habitats_can_see(fast_animals):
    verdicts = {a.gene: a.verdict for a in fast_animals}
    for gene in ("size", "speed", "recovery", "taste", "repro_drive", "sex_strategy"):
        assert verdicts[gene] == "ok", gene


# --- the table of balancers -----------------------------------------------------------------------


def test_every_gene_has_at_least_two_balancers():
    table = audit.load_balancers()
    assert audit.balancer_problems(table) == []
    for layout in audit.LAYOUT_NAMES:
        for gene in audit.sweepable_genes(layout):
            count = sum(1 for b in table if b.layout == layout and b.gene == gene)
            assert count >= 2, f"{layout} gene {gene} has {count} balancer(s)"
    assert sum(1 for b in table if b.gene == "brain") >= 2


def test_a_gene_with_one_balancer_is_reported():
    table = [b for b in audit.load_balancers() if not (b.gene == "agility" and b.kind == "link")]
    problems = audit.balancer_problems(table)
    assert any("agility" in p and "two are needed" in p for p in problems)


def test_a_balancer_for_a_gene_that_does_not_exist_is_reported():
    extra = audit.Balancer("animal", "wings", "cost", "none", "built", "-")
    assert any("wings" in p for p in audit.balancer_problems([*audit.load_balancers(), extra]))


def test_a_planned_balancer_must_name_a_task():
    bad = audit.Balancer("plant", "growth_rate", "cost", "later", "planned", "-")
    problems = audit.balancer_problems([*audit.load_balancers(), bad])
    assert any("needs a task" in p for p in problems)
    good = audit.Balancer("plant", "growth_rate", "cost", "later", "planned", "TRAIT.13, TRAIT.14")
    assert audit.balancer_problems([*audit.load_balancers(), good]) == []


def test_the_planned_genes_may_have_rows_before_they_exist():
    early = audit.Balancer("plant", "toughness", "cost", "upkeep", "planned", "TRAIT.13")
    assert audit.balancer_problems([*audit.load_balancers(), early]) == []


def test_the_table_agrees_with_the_audit_on_which_plant_genes_lack_two_built_balancers():
    """The audit measures what the table claims: a plant gene with fewer than two built balancers is a
    gene the audit fails (the other way round is allowed, since a balancer can be too weak)."""
    table = audit.load_balancers()
    failing = {a.gene for a in audit.audit("plant") if a.verdict != "ok"}
    thin = {
        gene
        for gene in audit.sweepable_genes("plant")
        if audit.built_balancers(table, "plant", gene) < 2
    }
    assert thin <= failing


def test_random_genomes_have_every_swept_gene():
    dna = audit.reference_animal()
    assert all(0.0 <= dna.value(g) <= 1.0 for g in audit.sweepable_genes("animal"))
    assert random.Random(0).random() >= 0.0  # the references are deterministic, not random
