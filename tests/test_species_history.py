"""Species in the history (SPECIES.2): the series the tracker adds to every sample, how they merge,
the run file's species table and its migration, and a round trip through a run."""

import json
import sqlite3
from pathlib import Path

import pytest
from persistence_support import rich_world

from evolution_simulator.history import (
    HistoryMirror,
    HistorySamples,
    Recorder,
    RecorderRules,
    Sample,
)
from evolution_simulator.runs import RunStore, RunStoreRules
from evolution_simulator.runs.database import SCHEMA_VERSION, RunFile
from evolution_simulator.session import FakeSimulation
from evolution_simulator.species import (
    SpeciesRow,
    SpeciesRules,
    SpeciesTracker,
    _Species,
    parse_series_name,
    series_name,
)


class Nothing:
    tick = 0
    simulated_seconds = 0.0
    animals = ()
    plants = ()


def ranked_tracker(**rules) -> SpeciesTracker:
    """A tracker holding eight living animal species whose rankings by size and divergence differ."""
    tracker = SpeciesTracker(Nothing(), SpeciesRules(**rules), attach=False)
    sizes = [50, 40, 30, 20, 10, 9, 8, 7]
    divergences = [0.01, 0.30, 0.02, 0.28, 0.03, 0.26, 0.24, 0.05]
    for i, (size, divergence) in enumerate(zip(sizes, divergences, strict=True), start=1):
        species = _Species(i, "animal", None if i == 1 else 1, 0.0, 7.0, "0123")
        species.size = size
        species.divergence = divergence
        tracker._species[i] = species
    gone = _Species(9, "animal", 1, 0.0, 3.0, "0123")
    gone.extinct_day = 3.0
    tracker._species[9] = gone
    tracker._founders["animal"] = "0123"
    tracker._taken = 1
    return tracker


# --- the names -----------------------------------------------------------------------------


def test_series_names_round_trip():
    assert series_name("animal", 12) == "species.animal.12"
    assert series_name("plant", 3, "divergence") == "species.plant.3.divergence"
    assert series_name("animal", field="total") == "species.animal.total"
    for args in (("animal", 12, None), ("plant", 3, "parent"), ("animal", None, "rest_by_size")):
        assert parse_series_name(series_name(*args)) == args
    for other in (
        "animals",
        "species.fungus.1",
        "species.animal",
        "species.animal.x.y",
        "species.",
    ):
        assert parse_series_name(other) is None or other == "species.animal"
    assert parse_series_name("species.animal") == ("animal", None, None)


# --- the top five and the rest -------------------------------------------------------------


def test_the_series_hold_the_top_five_by_divergence_and_by_size_and_the_rest_summed():
    values = ranked_tracker().series_values()
    total = 50 + 40 + 30 + 20 + 10 + 9 + 8 + 7
    assert values["species.animal.total"] == total and values["species.animal.count"] == 8
    by_size = {1, 2, 3, 4, 5}  # 50 40 30 20 10
    by_divergence = {2, 4, 6, 7, 8}  # 0.30 0.28 0.26 0.24 0.05
    named = {parse_series_name(n)[1] for n in values if parse_series_name(n)[1] is not None}
    assert named == by_size | by_divergence  # nothing for an extinct species, nor one outside both
    assert values["species.animal.rest_by_size"] == 9 + 8 + 7
    assert values["species.animal.rest_by_divergence"] == total - (40 + 20 + 9 + 8 + 7)
    assert values["species.animal.2"] == 40.0 and values["species.animal.2.divergence"] == 0.30
    assert values["species.animal.2.parent"] == 1.0 and values["species.animal.1.parent"] == -1.0
    # the top five of either ranking sum with its rest to the total
    for ids, rest in ((by_size, "rest_by_size"), (by_divergence, "rest_by_divergence")):
        assert (
            sum(values[f"species.animal.{i}"] for i in ids) + values[f"species.animal.{rest}"]
            == total
        )
    assert not any(n.startswith("species.plant") for n in values)  # no plants tracked


def test_top_count_is_a_setting_and_nothing_is_added_before_the_first_sample():
    values = ranked_tracker(top_count=2).series_values()
    named = {parse_series_name(n)[1] for n in values if parse_series_name(n)[1] is not None}
    assert named == {1, 2, 4}  # size 50 40, divergence 0.30 0.28
    assert values["species.animal.rest_by_size"] == 30 + 20 + 10 + 9 + 8 + 7
    empty = SpeciesTracker(Nothing(), attach=False)
    assert empty.series_values() == {}


# --- merging samples ----------------------------------------------------------------------


def test_a_species_missing_from_a_sample_counts_as_nothing_when_samples_merge():
    a = Sample(1, 1, 24, {"species.animal.3": 10.0, "species.animal.3.divergence": 0.2})
    b = Sample(2, 1, 48, {"animals": 5.0})
    merged = a.merge(b)
    assert merged.values["species.animal.3"] == 5.0  # half the time it was not there
    assert merged.values["species.animal.3.divergence"] == 0.2  # no value, so no averaging in
    both = a.merge(Sample(2, 3, 96, {"species.animal.3": 2.0, "species.animal.3.divergence": 0.4}))
    assert both.values["species.animal.3"] == pytest.approx((10.0 + 3 * 2.0) / 4)
    assert both.values["species.animal.3.divergence"] == pytest.approx((0.2 + 3 * 0.4) / 4)


# --- the recorder ---------------------------------------------------------------------------


def test_a_recorder_adds_the_species_series_and_carries_them_between_tracker_samples():
    world = rich_world()
    recorder = Recorder(world)
    assert recorder.species is not None
    world.run(24 * 16)
    days = recorder.history().tiers[0].samples
    assert len(days) >= 15
    first = days[0].values
    assert first["species.animal.total"] > 0 and first["species.plant.total"] > 0
    # the tracker samples weekly: a week's days all carry the last snapshot
    week = [s.values["species.animal.total"] for s in days[:6]]
    assert len(set(week)) == 1
    taken = recorder.species.samples_taken
    assert 2 <= taken <= 4
    newest = recorder.species.series_values()
    assert days[-1].values["species.animal.total"] == newest["species.animal.total"]
    ids = {parse_series_name(n)[1] for n in days[-1].values if parse_series_name(n)}
    assert 1 in ids


def test_the_recorder_can_leave_the_species_out_and_a_stand_in_world_has_none():
    world = rich_world()
    recorder = Recorder(world, RecorderRules(track_species=False))
    world.run(24 * 3)
    assert recorder.species is None
    assert not any(n.startswith("species.") for n in recorder.history().names())
    fake = FakeSimulation(20, 30, seed=1)
    stand_in = Recorder(fake)
    for _ in range(24 * 3):
        fake.step()
        stand_in.observe()
    assert not any(n.startswith("species.") for n in stand_in.history().names())


def test_a_recorder_with_species_leaves_the_world_as_it_was():
    plain, watched = rich_world(), rich_world()
    Recorder(watched)
    plain.run(24 * 9)
    watched.run(24 * 9)
    assert watched.state_digest() == plain.state_digest()
    assert watched.rng.getstate() == plain.rng.getstate()


def test_a_saved_recorder_carries_its_species_and_goes_on_the_same():
    straight_world, split_world = rich_world(), rich_world()
    straight = Recorder(straight_world)
    split = Recorder(split_world)
    straight_world.run(24 * 20)
    split_world.run(24 * 9)
    saved = json.loads(json.dumps(split.to_dict()))
    assert saved["format"] == 3 and saved["species"]["kind"] == "species"
    split.close()
    split.species.close()
    again = Recorder.restore(split_world, saved)
    split_world.run(24 * 11)
    assert again.species.to_dict() == straight.species.to_dict()
    assert again.history() == straight.history()


def test_an_older_recorder_state_restores_and_starts_a_new_tracker():
    world = rich_world()
    recorder = Recorder(world, RecorderRules(track_species=False))
    world.run(24 * 3)
    old = json.loads(json.dumps(recorder.to_dict()))
    old["format"] = 2
    old.pop("species")
    old["rules"].pop("track_species")
    restored = Recorder.restore(world, old)
    assert restored.species is not None and restored.species.samples_taken == 0
    world.run(24 * 2)
    assert "species.animal.total" in restored.history().samples()[-1].values


def test_a_format_one_history_still_loads_without_species():
    world = rich_world()
    recorder = Recorder(world, RecorderRules(track_species=False))
    world.run(24 * 3)
    data = json.loads(json.dumps(recorder.history().to_dict()))
    data["format"] = 1
    for tier in data["tiers"]:
        for sample in tier["samples"]:
            sample["stats"] = {k: v[:5] for k, v in sample["stats"].items()}
    loaded = HistorySamples.from_dict(data)
    assert len(loaded) == len(recorder.history())
    assert not any(n.startswith("species.") for n in loaded.names())
    newer = HistorySamples.from_dict(
        json.loads(json.dumps(Recorder(rich_world()).history().to_dict()))
    )
    assert newer.format == 3


def test_a_mirror_fed_the_new_samples_equals_the_recorder_with_species_in_them():
    world = rich_world()
    recorder = Recorder(world, RecorderRules())
    mirror = HistoryMirror()
    mirror.reset(recorder.rules, recorder.history())
    recorder.add_sample_listener(lambda sample: mirror.push([sample]))
    world.run(24 * 40)
    assert any(n.startswith("species.") for n in recorder.history().names())
    assert mirror.history() == recorder.history()


# --- the run file ---------------------------------------------------------------------------


def store_in(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs", RunStoreRules(min_wall_seconds=0.0))


def test_a_run_keeps_the_species_series_and_the_species_rows(tmp_path):
    store = store_in(tmp_path)
    world = rich_world()
    recorder = Recorder(world)
    run = store.create(world, recorder=recorder)
    saver = run.autosave(world, recorder)
    world.run(24 * 16)
    saver.finish()
    history = store.open(run.id).history()
    assert history == recorder.history()  # the series came back from the tables unchanged
    assert any(n.startswith("species.animal.") for n in history.names())
    rows = store.open(run.id, readonly=True).species()
    assert rows == sorted(recorder.species.rows(), key=lambda r: (r.kind, r.id)) and rows
    first = rows[0]
    assert isinstance(first, SpeciesRow) and first.parent is None and first.extinct_day is None
    assert {r.kind for r in rows} == {"animal", "plant"}


def test_a_resumed_run_carries_on_with_its_species(tmp_path):
    store = store_in(tmp_path)
    reference = rich_world()
    ref_recorder = Recorder(reference)
    reference.run(24 * 20)

    world = rich_world()
    recorder = Recorder(world)
    run = store.create(world, recorder=recorder)
    world.run(24 * 9)
    run.checkpoint(world, recorder)
    resumed = store.open(run.id).resume()
    assert resumed.recorder is not None and resumed.recorder.species is not None
    assert resumed.recorder.species.samples_taken == recorder.species.samples_taken
    resumed.world.run(24 * 11)
    assert resumed.recorder.species.to_dict() == ref_recorder.species.to_dict()
    assert resumed.recorder.history() == ref_recorder.history()


def test_a_run_with_no_species_has_no_rows(tmp_path):
    store = store_in(tmp_path)
    world = rich_world()
    recorder = Recorder(world, RecorderRules(track_species=False))
    run = store.create(world, recorder=recorder)
    world.run(24 * 3)
    run.checkpoint(world, recorder)
    assert run.species() == []


def test_a_schema_1_run_file_gets_the_species_table_when_opened(tmp_path):
    store = store_in(tmp_path)
    world = rich_world()
    run = store.create(world, recorder=Recorder(world))
    path = run.file_path
    run.close()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE species")
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()
    assert SCHEMA_VERSION == 2
    with_table = RunFile.open(path, readonly=True)
    assert with_table.species_read() == []  # a read-only look at an old file: no table, no rows
    with_table.close()
    migrated = RunFile.open(path)
    try:
        migrated.species_replace([SpeciesRow("animal", 1, None, 0.0, 7.0, None, None, 30, 0.0)])
        assert [r.id for r in migrated.species_read()] == [1]
        migrated.species_upsert([SpeciesRow("animal", 1, None, 0.0, 14.0, 14.0, None, 31, 0.0)])
        row = migrated.species_read()[0]
        assert (row.last_day, row.extinct_day, row.peak) == (14.0, 14.0, 31)
    finally:
        migrated.close()
    with sqlite3.connect(path) as check:
        assert check.execute("PRAGMA user_version").fetchone()[0] == 2


def test_a_newer_run_file_is_still_refused(tmp_path):
    store = store_in(tmp_path)
    run = store.create(rich_world())
    path = run.file_path
    run.close()
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(Exception, match="newer"):
        RunFile.open(path)
