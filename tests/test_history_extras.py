"""History extras (UX.32): percentiles in a statistic, lineage counts, and the format that carries
them (format 2) with format-1 history and saved recorders still loading."""

import json

import pytest
from test_history import Scripted, animal_view, feed
from world_support import hourly_world

from evolution_simulator.deaths import DeathCause
from evolution_simulator.history import (
    HISTORY_FORMAT,
    READABLE_FORMATS,
    HistorySamples,
    Recorder,
    RecorderRules,
    Stat,
    load_history_data,
    save_history,
)
from evolution_simulator.history.samples import percentile
from evolution_simulator.world.events import Born, Died
from evolution_simulator.world.views import PlantView

SMALL = RecorderRules()


def plant_view(i: int) -> PlantView:
    return PlantView(i, 0.0, 0.0, 1.0, 0.5, False)


def born(kind: str, ident: int, *parents: int) -> Born:
    return Born(1, kind, ident, 0.0, 0.0, tuple(parents))


def died(kind: str, ident: int) -> Died:
    return Died(1, kind, ident, 0.0, 0.0, DeathCause.OLD_AGE, None, 24)


# --- percentiles ----------------------------------------------------------------------------


def test_percentiles_interpolate_between_the_nearest_ranks():
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.1) == pytest.approx(1.4)
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.9) == pytest.approx(4.6)
    assert percentile([7.0], 0.9) == 7.0


def test_a_stat_has_the_tenth_and_ninetieth_percentile():
    stat = Stat.of([5.0, 1.0, 3.0, 2.0, 4.0])  # in any order
    assert (stat.p10, stat.p90) == (pytest.approx(1.4), pytest.approx(4.6))
    assert (stat.lo, stat.hi) == (1.0, 5.0)
    lone = Stat.of([2.5])
    assert lone.p10 == lone.p90 == 2.5


def test_merged_percentiles_are_weighted_by_count_and_absent_if_either_is():
    a = Stat(1, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0)
    b = Stat(3, 5.0, 0.0, 5.0, 5.0, 5.0, 5.0)
    merged = a.merge(b)
    assert (merged.p10, merged.p90) == (4.0, 4.0)
    old = Stat(2, 3.0, 0.0, 3.0, 3.0)
    assert (a.merge(old).p10, old.merge(a).p90) == (None, None)
    assert old.merge(old).p10 is None


def test_a_stat_saves_five_numbers_or_seven():
    full = Stat(4, 1.0, 0.5, 0.0, 2.0, 0.2, 1.8)
    assert Stat.from_list(full.to_list()) == full and len(full.to_list()) == 7
    old = Stat(4, 1.0, 0.5, 0.0, 2.0)
    assert Stat.from_list(old.to_list()) == old and len(old.to_list()) == 5
    with pytest.raises(ValueError):
        Stat.from_list([1, 2, 3, 4, 5, 6])


# --- lineages -------------------------------------------------------------------------------


def test_lineages_count_the_founders_that_still_have_descendants():
    source = Scripted()
    recorder = Recorder(source, SMALL)
    source.animals = [animal_view(1), animal_view(2), animal_view(3)]
    source.advance(24)
    first = recorder.history().samples()[-1]
    assert first.values["lineages.animal"] == 3  # three founders

    source.emit(born("animal", 4, 99, 1))  # father unknown to us, mother 1
    source.emit(born("animal", 5, 2, 4))  # mother 4, who comes from 1
    source.animals = [animal_view(i) for i in (1, 2, 3, 4, 5)]
    source.advance(24)
    assert recorder.history().samples()[-1].values["lineages.animal"] == 3  # 1, 2 and 3

    source.emit(died("animal", 1))
    source.emit(died("animal", 3))
    source.animals = [animal_view(i) for i in (2, 4, 5)]
    source.advance(24)
    # 4 and 5 are of line 1 (its founder is dead but the line is alive), 2 is its own
    assert recorder.history().samples()[-1].values["lineages.animal"] == 2


def test_plants_have_lineages_through_the_seeding_plant():
    source = Scripted()
    recorder = Recorder(source, SMALL)
    source.emit(born("plant", 11, 10))
    source.emit(born("plant", 12, 11))
    source.plants = [plant_view(10), plant_view(11), plant_view(12), plant_view(13)]
    source.advance(24)
    assert recorder.history().samples()[-1].values["lineages.plant"] == 2  # 10's line and 13


def test_a_mother_born_before_recording_is_the_root_of_her_line():
    source = Scripted()
    recorder = Recorder(source, SMALL)
    source.emit(born("animal", 7, 3))  # 3 was never seen being born
    source.emit(born("animal", 8, 3))
    source.animals = [animal_view(3), animal_view(7), animal_view(8)]
    source.advance(24)
    assert recorder.history().samples()[-1].values["lineages.animal"] == 1


def test_the_lineage_roots_survive_a_restore():
    first = Scripted()
    part = Recorder(first, SMALL)
    first.animals = [animal_view(1), animal_view(2)]
    first.emit(born("animal", 3, 2, 1))
    first.animals.append(animal_view(3))
    feed_state = json.loads(json.dumps(part.to_dict()))
    assert feed_state["roots"]["animal"] == [[3, 1]]

    second = Scripted()
    resumed = Recorder.restore(second, feed_state)
    for source, recorder in ((first, part), (second, resumed)):
        source.animals = [animal_view(2), animal_view(3)]
        source.advance(24)
    assert resumed.history() == part.history()
    assert resumed.history().samples()[-1].values["lineages.animal"] == 2
    assert resumed.to_dict() == part.to_dict()


def test_a_real_world_has_as_many_lineages_as_founders_to_begin_with():
    world = hourly_world(seed=2)
    world.populate(animals=6, plants=20)
    recorder = Recorder(world)
    for _ in range(24):
        world.step()
    sample = recorder.history().samples()[0]
    assert 1 <= sample.values["lineages.animal"] <= sample.values["animals"] <= 6
    assert 1 <= sample.values["lineages.plant"] <= sample.values["plants"]


# --- the format -----------------------------------------------------------------------------


def format_one(data):
    """What a format-1 file looked like: five-number statistics, no lineages, no roots."""
    data = json.loads(json.dumps(data))
    data["format"] = 1
    data.pop("roots", None)
    tiers = data["tiers"]
    for tier in tiers:
        for sample in tier["samples"] if isinstance(tier, dict) else tier:
            sample["stats"] = {k: v[:5] for k, v in sample["stats"].items()}
            sample["values"] = {
                k: v for k, v in sample["values"].items() if not k.startswith("lineages.")
            }
    return data


def recorded() -> Recorder:
    source = Scripted(columns=lambda kind: {"gene.g": [0.2, 0.4, 0.9], "trait.t": [1.0, 3.0]})
    recorder = Recorder(source, SMALL)
    feed(source, recorder, 40)
    return recorder


def test_the_current_format_is_two_and_both_load():
    assert HISTORY_FORMAT == 2 and READABLE_FORMATS == (1, 2)
    history = recorded().history()
    assert history.to_dict()["format"] == 2
    stat = history.samples()[-1].stats["animal.gene.g"]
    assert stat.p10 is not None and stat.p90 is not None


def test_format_one_history_loads_without_percentiles_and_saves_as_two(tmp_path):
    history = recorded().history()
    old = format_one(history.to_dict())
    loaded = HistorySamples.from_dict(old)
    sample = loaded.samples()[-1]
    assert sample.stats["animal.gene.g"].p10 is None
    assert "lineages.animal" not in sample.values
    assert sample.stats["animal.gene.g"].mean == history.samples()[-1].stats["animal.gene.g"].mean
    path = save_history(loaded, tmp_path / "again.json.gz")
    again = load_history_data(path)
    assert again["format"] == 2
    assert HistorySamples.from_dict(again) == loaded


def test_a_format_one_saved_recorder_resumes_and_then_records_the_new_way():
    straight = recorded()
    old = format_one(straight.to_dict())
    source = Scripted(columns=lambda kind: {"gene.g": [0.2, 0.4, 0.9], "trait.t": [1.0, 3.0]})
    source.tick = straight._source.tick
    resumed = Recorder.restore(source, old)
    assert resumed.history().samples()[-1].stats["animal.gene.g"].p10 is None
    feed(source, resumed, 5)
    newest = resumed.history().samples()[-1]
    assert newest.values["lineages.animal"] >= 1
    assert resumed.to_dict()["format"] == 2


def test_an_unknown_format_is_still_refused():
    with pytest.raises(ValueError):
        HistorySamples.from_dict({"format": 3})
    with pytest.raises(ValueError):
        Recorder.restore(Scripted(), {"format": 3, "kind": "recorder"})
