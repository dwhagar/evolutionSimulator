"""The names, units and meanings of genes and traits (UX.29)."""

import pytest

from evolution_simulator.catalogue import GENES, TRAITS, describe_gene, describe_trait
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.trait_defs import ANIMAL_TRAITS, PLANT_TRAITS


def all_gene_ids() -> set[str]:
    return {gene.id for layout in (ANIMAL_LAYOUT, PLANT_LAYOUT) for gene in layout.genes}


def all_trait_names() -> set[str]:
    return {t.name for table in (ANIMAL_TRAITS, PLANT_TRAITS) for t in table.defs}


def test_every_gene_of_every_layout_is_described_and_nothing_else():
    assert set(GENES) == all_gene_ids()


def test_every_trait_of_both_tables_is_described_and_nothing_else():
    assert set(TRAITS) == all_trait_names()


def test_the_two_tables_share_no_trait_name_with_a_different_meaning():
    animal = {t.name for t in ANIMAL_TRAITS.defs}
    plant = {t.name for t in PLANT_TRAITS.defs}
    assert animal.isdisjoint(plant)  # one catalogue entry per name is enough


@pytest.mark.parametrize("table", [GENES, TRAITS])
def test_each_entry_has_a_name_a_unit_and_a_one_line_meaning(table):
    for key, entry in table.items():
        assert entry.name.strip() and entry.unit.strip(), key
        assert entry.meaning.strip() and "\n" not in entry.meaning, key
        assert len(entry.meaning) <= 120, f"{key}: keep the meaning to one short line"
        assert entry.meaning.endswith("."), key


def test_lookups_and_unknown_ids():
    assert describe_gene("fear").name == "Fear"
    assert describe_trait("cooldown_days").unit == "days"
    with pytest.raises(KeyError):
        describe_gene("nope")
    with pytest.raises(KeyError):
        describe_trait("nope")
