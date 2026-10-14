"""The statistics recorder (UX.8): samples, merging, bounded memory, and no effect on the run."""

import itertools
import json
import math
import random

import pytest
from persistence_support import SURE_CONCEPTION
from world_support import breeding_pair, hourly_world

from evolution_simulator.deaths import DeathCause
from evolution_simulator.history import (
    HISTORY_FORMAT,
    HistorySamples,
    Recorder,
    RecorderRules,
    Sample,
    Stat,
    TierRule,
    load_history_data,
    save_history,
)
from evolution_simulator.session import FakeSimulation
from evolution_simulator.world import Bounds, TimeScale, World, WorldConfig, persistence
from evolution_simulator.world.events import Born, Died
from evolution_simulator.world.views import AnimalView, CorpseView, PlantView

DAY = 86400.0


# --- a source with exactly the numbers a test wants -------------------------------------------


def animal_view(i: int, energy: float = 0.5) -> AnimalView:
    return AnimalView(i, 0.0, 0.0, 0.0, 1.0, energy, 1.0, 0.1, 0.0, False, False, True, False, 0)


class Scripted:
    """The part of a world the recorder reads, with the clock and the populations set by hand."""

    def __init__(self, seconds_per_tick: float = 3600.0, columns=None) -> None:
        self.tick = 0
        self.time_scale = TimeScale(seconds_per_tick=seconds_per_tick)
        self.animals: list[AnimalView] = []
        self.plants: list[PlantView] = []
        self.corpses: list[CorpseView] = []
        self.listeners = []
        self.step_listeners = []
        if columns is not None:
            self.trait_columns = columns

    @property
    def simulated_seconds(self) -> float:
        return self.tick * self.time_scale.seconds_per_tick

    def animal_views(self):
        return list(self.animals)

    def plant_views(self):
        return list(self.plants)

    def corpse_views(self):
        return list(self.corpses)

    def add_event_listener(self, listener):
        self.listeners.append(listener)

    def remove_event_listener(self, listener):
        self.listeners.remove(listener)

    def add_step_listener(self, listener):
        self.step_listeners.append(listener)

    def remove_step_listener(self, listener):
        self.step_listeners.remove(listener)

    def emit(self, event):
        for listener in self.listeners:
            listener(event)

    def advance(self, ticks: int = 1) -> None:
        for _ in range(ticks):
            self.tick += 1
            for listener in self.step_listeners:
                listener(None)


@pytest.fixture
def hourly() -> Scripted:
    return Scripted()


def born(tick=1, kind="animal", parents=(1,)):
    return Born(tick, kind, 9, 0.0, 0.0, parents)


def died(kind="animal", cause=DeathCause.STARVATION, age_ticks=48, tick=1):
    return Died(tick, kind, 9, 0.0, 0.0, cause, None, age_ticks)


# --- the arithmetic of merging ------------------------------------------------------------------


def test_a_stat_is_count_mean_spread_minimum_and_maximum():
    stat = Stat.of([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    assert (stat.n, stat.mean, stat.std, stat.lo, stat.hi) == (8, 5.0, 2.0, 2.0, 9.0)
    assert Stat.of([]) is None


@pytest.mark.parametrize("seed", range(5))
def test_merged_stats_are_the_stats_of_everything_together(seed):
    rng = random.Random(seed)
    parts = [
        [rng.gauss(rng.uniform(-5, 5), rng.uniform(0.1, 3)) for _ in range(rng.randint(1, 40))]
        for _ in range(6)
    ]
    merged = Stat.of(parts[0])
    for part in parts[1:]:
        merged = merged.merge(Stat.of(part))
    whole = Stat.of([v for part in parts for v in part])
    assert merged.n == whole.n
    assert merged.lo == whole.lo and merged.hi == whole.hi
    assert merged.mean == pytest.approx(whole.mean, abs=1e-9)
    assert merged.std == pytest.approx(whole.std, abs=1e-9)


def test_merging_adds_flows_and_averages_levels_by_the_time_they_cover():
    a = Sample(
        day=3,
        span=3,
        tick=72,
        values={"animals": 10.0, "births.animal": 4.0, "animal.energy": 0.2},
        stats={"animal.gene.size": Stat(2, 0.5, 0.0, 0.5, 0.5)},
        histograms={"animal.gene.size": (2, 0)},
    )
    b = Sample(
        day=4,
        span=1,
        tick=96,
        values={"animals": 20.0, "births.animal": 1.0, "deaths.animal": 2.0},
        stats={
            "animal.gene.size": Stat(2, 1.0, 0.0, 1.0, 1.0),
            "plant.gene.x": Stat(1, 3.0, 0.0, 3.0, 3.0),
        },
        histograms={"animal.gene.size": (0, 2)},
    )
    merged = a.merge(b)
    assert (merged.day, merged.span, merged.tick, merged.start) == (4, 4, 96, 0)
    assert merged.values["animals"] == pytest.approx((10 * 3 + 20 * 1) / 4)
    assert merged.values["births.animal"] == 5.0
    assert merged.values["deaths.animal"] == 2.0  # only one of them had deaths
    assert merged.values["animal.energy"] == 0.2  # only one of them had it
    assert merged.stats["animal.gene.size"] == Stat(4, 0.75, 0.25, 0.5, 1.0)
    assert merged.stats["plant.gene.x"] == Stat(1, 3.0, 0.0, 3.0, 3.0)
    assert merged.histograms["animal.gene.size"] == (2, 2)
    assert merged.rate("births.animal") == 5.0 / 4  # a flow is per period
    assert merged.rate("animals") == merged.values["animals"]


def test_the_rules_are_checked():
    with pytest.raises(ValueError):
        RecorderRules(period_seconds=0.0)
    with pytest.raises(ValueError):
        RecorderRules(tiers=(TierRule("week", 7, 10),))  # must start with single periods
    with pytest.raises(ValueError):
        RecorderRules(tiers=(TierRule("day", 1, 10), TierRule("again", 1, 10)))
    with pytest.raises(ValueError):
        RecorderRules(tiers=(TierRule("day", 1, 10), TierRule("week", 7, 1)))
    with pytest.raises(ValueError):
        TierRule("day", 0, 5)


# --- sampling ----------------------------------------------------------------------------------


def test_one_sample_is_taken_for_each_simulated_day(hourly):
    recorder = Recorder(hourly)
    hourly.animals = [animal_view(1, 0.25), animal_view(2, 0.75)]
    hourly.advance(23)
    assert recorder.sample_count == 0
    hourly.advance(1)
    (sample,) = recorder.history().samples()
    assert (sample.day, sample.span, sample.tick) == (1, 1, 24)
    assert sample.values["animals"] == 2.0
    assert sample.values["animal.energy"] == 0.5
    hourly.advance(24 * 3)
    assert recorder.sample_count == 4


def test_a_recorder_starting_late_counts_from_when_it_began(hourly):
    hourly.tick = 30
    recorder = Recorder(hourly)
    hourly.advance(17)
    assert recorder.sample_count == 0
    hourly.advance(1)  # tick 48, the end of day 2
    assert recorder.history().latest.day == 2


def test_a_tick_longer_than_a_period_gives_one_sample_that_covers_it():
    source = Scripted(seconds_per_tick=5 * DAY)
    recorder = Recorder(source)
    source.advance(1)
    source.tick = 2  # and a jump of two ticks at once
    recorder.observe()
    first, second = recorder.history().samples()
    assert (first.day, first.span) == (5, 5)
    assert (second.day, second.span) == (10, 5)
    assert recorder.history().series("animals")[0] == (5.0, 10.0)


def test_births_and_deaths_are_counted_by_cause_between_samples(hourly):
    recorder = Recorder(hourly)
    hourly.emit(born())
    hourly.emit(born())
    hourly.emit(born(kind="plant"))
    hourly.emit(born(parents=()))  # a founder put in by hand is not a birth
    hourly.emit(died(cause=DeathCause.STARVATION, age_ticks=24))
    hourly.emit(died(cause=DeathCause.PREDATION, age_ticks=72))
    hourly.emit(died(kind="plant", cause=DeathCause.EATEN, age_ticks=48))
    hourly.advance(24)
    hourly.emit(died(cause=DeathCause.OLD_AGE))
    hourly.advance(24)
    first, second = recorder.history().samples()
    assert first.values["births.animal"] == 2.0
    assert first.values["births.plant"] == 1.0
    assert first.values["deaths.animal"] == 2.0
    assert first.values["deaths.animal.starvation"] == 1.0
    assert first.values["deaths.animal.predation"] == 1.0
    assert first.values["deaths.animal.old_age"] == 0.0
    assert first.values["deaths.plant.eaten"] == 1.0
    assert first.stats["animal.age_at_death"] == Stat(2, 2.0, 1.0, 1.0, 3.0)  # in days
    assert "plant.age_at_death" in first.stats
    assert second.values["births.animal"] == 0.0  # counters start again after a sample
    assert second.values["deaths.animal.old_age"] == 1.0
    assert "animal.age_at_death" in second.stats and "plant.age_at_death" not in second.stats


def test_a_recorder_that_is_closed_stops_listening(hourly):
    recorder = Recorder(hourly)
    recorder.close()
    assert hourly.listeners == [] and hourly.step_listeners == []
    hourly.advance(48)
    assert recorder.sample_count == 0
    recorder.attach()
    hourly.advance(1)  # the days that passed while it was away come as one sample
    (sample,) = recorder.history().samples()
    assert (sample.day, sample.span) == (2, 2)


def test_stats_and_gene_histograms_come_from_the_trait_columns():
    values = [0.0, 0.1, 0.5, 0.99, 1.0]
    source = Scripted(
        columns=lambda kind: (
            {"gene.size": values, "trait.mass": [2.0, 4.0]} if kind == "animal" else {}
        )
    )
    rules = RecorderRules(histogram_every=2, bins=4)
    recorder = Recorder(source, rules)
    for _ in range(5):
        source.advance(24)
    samples = recorder.history().samples()
    assert samples[0].stats["animal.gene.size"] == Stat.of(values)
    assert samples[0].stats["animal.trait.mass"] == Stat(2, 3.0, 1.0, 2.0, 4.0)
    with_histograms = [i for i, s in enumerate(samples) if s.histograms]
    assert with_histograms == [0, 2, 4]  # the first sample and every second after
    assert samples[0].histograms == {"animal.gene.size": (2, 0, 1, 2)}  # 1.0 goes in the top bin
    assert "animal.trait.mass" not in samples[0].histograms  # traits get no histogram


def test_a_source_without_trait_columns_still_gets_levels_and_flows(hourly):
    recorder = Recorder(hourly)
    hourly.advance(24)
    assert recorder.history().latest.stats == {}


# --- bounded memory and the ring buffers ---------------------------------------------------------


SMALL = RecorderRules(
    tiers=(
        TierRule("day", 1, 10),
        TierRule("week", 7, 6),
        TierRule("month", 30, 4),
        TierRule("year", 365, 3),
    )
)


def feed(source, recorder, days, births_per_day=2):
    flows = 0
    for d in range(days):
        source.animals = [animal_view(i) for i in range(1 + d % 5)]
        for _ in range(births_per_day):
            source.emit(born())
        flows += births_per_day
        source.advance(24)
    return flows


def test_memory_stays_bounded_over_a_very_long_run():
    source = Scripted(columns=lambda kind: {"gene.a": [0.1, 0.9], "trait.b": [1.0]})
    recorder = Recorder(source, SMALL)
    seen = []
    for chunk in range(40):  # about 110 simulated years
        feed(source, recorder, 1000)
        seen.append(recorder.sample_count)
    assert max(seen) <= SMALL.capacity == 23
    assert seen[-1] == SMALL.capacity
    sizes = [len(t.samples) for t in recorder.history().tiers]
    assert sizes == [10, 6, 4, 3]


def test_the_default_rules_hold_a_few_hundred_samples_at_most():
    assert RecorderRules().capacity == 330


def test_every_period_is_in_exactly_one_sample_and_flows_are_conserved():
    source = Scripted()
    recorder = Recorder(source, SMALL)
    days = 5000
    births = feed(source, recorder, days)
    samples = recorder.history().samples()
    assert sum(s.span for s in samples) == days
    for earlier, later in itertools.pairwise(samples):
        assert earlier.day == later.start  # no gaps, no overlaps
    assert samples[-1].day == days
    assert sum(s.values["births.animal"] for s in samples) == births
    # the integral of a level over time is conserved by averaging with the span as weight
    assert sum(s.values["animals"] * s.span for s in samples) == pytest.approx(
        sum(1 + d % 5 for d in range(days))
    )


def test_tiers_hold_days_weeks_months_and_years():
    source = Scripted()
    recorder = Recorder(source, SMALL)
    feed(source, recorder, 3000)
    days, weeks, months, years = recorder.history().tiers
    assert all(s.span == 1 for s in days.samples)
    assert all(1 <= s.span <= 7 for s in weeks.samples)
    assert all(1 <= s.span <= 36 for s in months.samples)  # whole weeks, ending in the month
    assert all(s.span >= 1 for s in years.samples)
    assert [s.span for s in weeks.samples[:-1]] == [7] * (len(weeks.samples) - 1)
    # the oldest yearly samples have been merged in pairs once the tier was full
    assert max(s.span for s in years.samples) > 365


def test_gene_histograms_merge_by_adding_their_counts():
    source = Scripted(columns=lambda kind: {"gene.g": [0.1, 0.6, 0.9]} if kind == "animal" else {})
    recorder = Recorder(source, RecorderRules(histogram_every=1, bins=2, tiers=SMALL.tiers))
    for _ in range(30):
        source.advance(24)
    first_week = recorder.history().tiers[1].samples[0]
    assert sum(first_week.histograms["animal.gene.g"]) == 3 * first_week.span


def test_series_put_flows_per_period_on_one_scale_across_tiers():
    source = Scripted()
    recorder = Recorder(source, SMALL)
    feed(source, recorder, 400, births_per_day=3)
    days, values = recorder.history().series("births.animal")
    assert len(days) == len(values) > 10
    assert set(values) == {3.0}
    assert list(days) == sorted(days)
    assert recorder.history().series("nothing at all") == ((), ())


# --- reading and saving ------------------------------------------------------------------------


def recorded(days=400) -> Recorder:
    source = Scripted(columns=lambda kind: {"gene.g": [0.2, 0.4], "trait.t": [1.0, 3.0]})
    recorder = Recorder(source, SMALL)
    feed(source, recorder, days)
    return recorder


def test_history_round_trips_through_json_and_files(tmp_path):
    history = recorded().history()
    again = HistorySamples.from_dict(json.loads(json.dumps(history.to_dict())))
    assert again == history
    for name in ("h.json", "h.json.gz"):
        path = save_history(history, tmp_path / name)
        assert HistorySamples.from_dict(load_history_data(path)) == history
    assert history.to_dict()["format"] == HISTORY_FORMAT
    with pytest.raises(ValueError):
        HistorySamples.from_dict({"format": 99})


def test_a_restored_recorder_carries_on_exactly_as_one_that_never_stopped():
    straight = Scripted(columns=lambda kind: {"gene.g": [0.2, 0.4]})
    full = Recorder(straight, SMALL)
    feed(straight, full, 777)

    first = Scripted(columns=lambda kind: {"gene.g": [0.2, 0.4]})
    part = Recorder(first, SMALL)
    feed(first, part, 300)
    first.emit(born())  # counted but not yet in a sample
    first.emit(died())
    state = json.loads(json.dumps(part.to_dict()))

    second = Scripted(columns=lambda kind: {"gene.g": [0.2, 0.4]})
    second.tick = first.tick
    resumed = Recorder.restore(second, state)
    assert resumed.history() == part.history()
    # an identical remainder from both
    for source, recorder in ((first, part), (second, resumed)):
        feed(source, recorder, 477)
    assert resumed.history() == part.history()
    assert resumed.to_dict() == part.to_dict()
    assert full.sample_count == resumed.sample_count


def test_a_bad_saved_recorder_is_refused():
    with pytest.raises(ValueError):
        Recorder.restore(Scripted(), {"format": 99, "kind": "recorder"})
    with pytest.raises(ValueError):
        Recorder.restore(Scripted(), {"format": HISTORY_FORMAT, "kind": "history"})


def test_the_fake_simulation_can_be_recorded_by_hand():
    fake = FakeSimulation(animals=20, plants=50, seed=1)
    recorder = Recorder(fake)
    for _ in range(24 * 5):
        fake.step()
        recorder.observe()
    history = recorder.history()
    assert len(history) == 5
    assert history.series("animals")[1][0] > 0
    assert history.latest.stats == {}  # the fake has no genomes to measure


# --- with the real world -------------------------------------------------------------------------


def busy_world(seed=4) -> World:
    world = hourly_world(
        seed=seed, traits=SURE_CONCEPTION, bounds=Bounds((600.0, 600.0)), mating_reach=10.0
    )
    world.populate(animals=25, plants=150)
    for i in range(3):
        breeding_pair(world, x=300.0 + 10 * i)
    return world


def test_a_recorder_changes_nothing_about_the_run():
    plain = busy_world()
    watched = busy_world()
    recorder = Recorder(watched)
    plain_report = plain.run(24 * 12)
    watched_report = watched.run(24 * 12)
    assert watched_report == plain_report
    assert watched.state_digest() == plain.state_digest()
    assert recorder.sample_count == 12


def test_a_world_with_no_recorder_has_no_listeners_at_all():
    world = busy_world()
    world.run(30)
    assert world._event_listeners == [] and world._step_listeners == []
    recorder = Recorder(world)
    assert len(world._step_listeners) == 1
    recorder.close()
    assert world._event_listeners == [] and world._step_listeners == []


def test_the_samples_of_a_real_world_match_what_happened():
    world = busy_world()
    recorder = Recorder(world)
    report = world.run(24 * 15)
    history = recorder.history()
    samples = history.samples()
    assert [s.day for s in samples] == list(range(1, 16))
    totals = {
        name: sum(s.values[name] for s in samples)
        for name in ("births.animal", "births.plant", "deaths.animal", "deaths.plant")
    }
    assert totals["births.animal"] == report.animal_births
    assert totals["births.plant"] == report.plant_births
    assert totals["deaths.animal"] == report.animal_deaths
    assert totals["deaths.plant"] == report.plant_deaths
    causes = sum(
        s.values[f"deaths.{kind}.{cause.value}"]
        for s in samples
        for kind in ("animal", "plant")
        for cause in DeathCause
    )
    assert causes == report.animal_deaths + report.plant_deaths
    first = samples[0]
    assert first.values["animals"] == 31.0  # day 1, before anyone has died
    assert "animal.gene.size" in first.stats
    assert "animal.trait.mass" in first.stats and "plant.trait.max_biomass" in first.stats
    assert "animal.gene.brain" not in first.stats  # the block of brain weights is not a gene stat
    hist = first.histograms["animal.gene.size"]
    assert sum(hist) == first.stats["animal.gene.size"].n == 31
    assert all(0.0 <= s.hi <= 1.0 for name, s in first.stats.items() if ".gene." in name)
    assert math.isclose(
        first.stats["animal.gene.size"].mean,
        sum(a.traits.dna.value("size") for a in busy_world().animals) / 31,
    )


def test_a_world_saved_with_its_history_resumes_both_exactly(tmp_path):
    uninterrupted = busy_world()
    straight = Recorder(uninterrupted)
    uninterrupted.run(24 * 20)

    world = busy_world()
    recorder = Recorder(world)
    world.run(24 * 9 + 5)  # stopped part way through a day, with births and deaths pending
    world_file = persistence.save_world(world, tmp_path / "w.json.gz")
    history_file = save_history(recorder, tmp_path / "h.json.gz")

    restored = persistence.load_world(world_file)
    resumed = Recorder.restore(restored, load_history_data(history_file))
    restored.run(24 * 20 - restored.tick)

    assert restored.state_digest() == uninterrupted.state_digest()
    assert resumed.history() == straight.history()
    assert resumed.to_dict() == straight.to_dict()


def test_the_default_config_world_is_recordable_too():
    world = World(WorldConfig(seed=2))
    world.populate(animals=10, plants=40)
    recorder = Recorder(world)
    world.run(60)
    assert recorder.history().latest.day == 2
