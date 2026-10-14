"""The long-run reproduction check (REPRO.8): a short run, and the pile-up rule."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "reproduction_check", ROOT / "scripts" / "reproduction_check.py"
)
check = importlib.util.module_from_spec(spec)
sys.modules["reproduction_check"] = check  # dataclasses look the module up by name
spec.loader.exec_module(check)


def row(**genes: float) -> dict[str, float]:
    base = {gene: 0.5 for gene in check.WATCHED}
    return {"tick": 0.0, "population": 50.0, **base, **genes}


def test_a_short_run_is_repeatable_and_records_the_genes():
    first = check.run(200, check.Ecology(founders=10, seed=3))
    second = check.run(200, check.Ecology(founders=10, seed=3))
    assert first.history == second.history
    assert first.history[0]["population"] == 10
    assert set(check.WATCHED) <= set(first.history[0])
    assert abs(first.history[0]["fertility"] - 0.75) < 0.03


def test_the_young_of_a_fed_population_are_born_in_the_check():
    eco = check.run(1500, check.Ecology(founders=40, seed=1, meeting_chance=0.2))
    assert max(row["population"] for row in eco.history) > 40


def test_a_gene_at_an_end_of_its_range_is_reported():
    history = [row(fertility=0.99), row(fertility=0.98), row(fertility=0.97)]
    assert check.piled_up(history) == ["fertility"]
    assert check.piled_up([row(), row(), row()]) == []
    assert check.piled_up([row(parenting=0.02), row(parenting=0.01)]) == ["parenting"]
    assert check.piled_up([row(fertility=0.99), row(), row(), row(), row()]) == []  # an early blip


def test_a_dead_population_has_no_genes_to_report():
    history = [row(), {**row(), "population": 0.0, "fertility": float("nan")}]
    assert check.piled_up(history) == []
