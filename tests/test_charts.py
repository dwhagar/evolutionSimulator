"""The charts screen (UX.16), run on Qt's offscreen platform against real and made-up histories."""

import pytest

pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
pytest.importorskip("pyqtgraph", exc_type=ImportError)

import numpy as np
from PySide6.QtCore import QDeadlineTimer
from world_support import hourly_world

from evolution_simulator.history import HistorySamples, Recorder, RecorderRules, Sample, Stat, Tier
from evolution_simulator.session import FakeSimulation, Session, Step
from evolution_simulator.viewer.backend import Batch, LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.panels import charts
from evolution_simulator.viewer.panels.charts import (
    ChartsPanel,
    death_causes,
    histogram_days,
    histogram_names,
    histogram_shares,
    pretty_stat,
    spread_band,
    stats_of_kind,
    time_axis,
)
from evolution_simulator.viewer.window import MainWindow

DAY = 86400.0


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(scope="module")
def real_history() -> HistorySamples:
    """Ten days of a real world: trait and gene statistics, histograms on days 1, 5 and 9."""
    world = hourly_world()
    world.populate(animals=20, plants=60)
    recorder = Recorder(world, RecorderRules(histogram_every=4))
    for _ in range(24 * 10):
        world.step()
    return recorder.history()


def made_up(days: int, per_day: float = DAY, **values: float) -> HistorySamples:
    samples = tuple(
        Sample(day=d, span=1, tick=d * 24, values={k: v * d for k, v in values.items()})
        for d in range(1, days + 1)
    )
    return HistorySamples(per_day, (Tier("day", 1, samples),))


@pytest.fixture
def controller(qapp):
    backend = LocalBackend(Session(FakeSimulation(30, 100, seed=3), clock=Clock()))
    yield ViewerController(backend)
    backend.close()


@pytest.fixture
def panel(qapp, controller):
    widget = ChartsPanel(controller)
    widget.resize(700, 500)
    widget.show()
    yield widget
    widget.close()


def curves(tab) -> list[str]:
    return [item.name() for item in tab.plot.getPlotItem().listDataItems()]


def show_tab(panel: ChartsPanel, title: str):
    for index, tab in enumerate(panel.chart_tabs):
        if tab.title == title:
            panel.tabs.setCurrentIndex(index)
            return tab
    raise AssertionError(title)


# --- the plain helpers ---------------------------------------------------------------------------


def test_the_axis_is_in_days_until_the_run_is_two_years_old():
    assert time_axis(None).unit == "days"
    assert time_axis(made_up(10, animals=1.0)).unit == "days"
    young = time_axis(made_up(729, animals=1.0))
    old = time_axis(made_up(731, animals=1.0))
    assert young.unit == "days" and old.unit == "years"
    assert old.per_period == pytest.approx(1 / 365)
    assert old.text(365 * 3) == "year 3.00" and young.text(12) == "day 12"


def test_a_period_longer_than_a_day_is_scaled_to_days():
    axis = time_axis(made_up(5, per_day=7 * DAY, animals=1.0))
    assert axis.unit == "days" and axis.per_period == 7.0
    assert list(axis.x([1, 2])) == [7.0, 14.0]


def test_statistics_are_named_for_a_person_and_listed_in_a_fixed_order():
    assert pretty_stat("animal.trait.max_speed") == "max speed (trait)"
    assert pretty_stat("plant.gene.seed_range") == "seed range (gene)"
    assert pretty_stat("animal.age_at_death") == "age at death"
    stat = Stat(1, 0.5, 0.0, 0.5, 0.5)
    sample = Sample(
        1,
        1,
        0,
        stats={
            "animal.gene.size": stat,
            "animal.trait.mass": stat,
            "animal.age_at_death": stat,
            "plant.gene.size": stat,
        },
    )
    history = HistorySamples(DAY, (Tier("day", 1, (sample,)),))
    assert stats_of_kind(history, "animal") == [
        "animal.age_at_death",
        "animal.trait.mass",
        "animal.gene.size",
    ]
    assert stats_of_kind(history, "plant") == ["plant.gene.size"]


def test_the_spread_band_stays_inside_the_range_seen():
    low, high = spread_band(
        np.array([0.5, 0.1]), np.array([0.3, 0.3]), np.array([0.3, 0.0]), np.array([0.9, 0.2])
    )
    assert list(low) == pytest.approx([0.3, 0.0]) and list(high) == pytest.approx([0.8, 0.2])


def test_distribution_helpers_find_the_genes_days_and_shares(real_history):
    names = histogram_names(real_history, "animal")
    assert names and all(n.startswith("animal.gene.") for n in names)
    assert histogram_days(real_history, names[0]) == [1, 5, 9]
    assert histogram_names(real_history, "plant")
    assert histogram_days(real_history, "animal.gene.nope") == []
    assert histogram_shares([1, 3]).tolist() == [0.25, 0.75]
    assert histogram_shares([0, 0]).tolist() == [0.0, 0.0]


def test_only_the_causes_that_happened_are_listed():
    sample = Sample(
        1,
        1,
        0,
        values={"deaths.animal.starvation": 2.0, "deaths.animal.old_age": 0.0},
    )
    history = HistorySamples(DAY, (Tier("day", 1, (sample,)),))
    assert death_causes(history, "animal") == ["starvation"]
    assert death_causes(history, "plant") == []


# --- the history reaching the screen ---------------------------------------------------------------


def test_the_backend_publishes_history_once_per_new_sample(qapp):
    backend = LocalBackend(Session(FakeSimulation(30, 10, seed=1), clock=Clock()))
    assert backend.poll().history is None  # no simulated day yet
    backend.session.handle(Step(30))  # a tick is an hour: day 1 is in
    first = backend.poll()
    assert first.history is not None and first.history.latest.day == 1
    assert backend.poll().history is None  # nothing new
    backend.session.handle(Step(24))
    assert backend.poll().history.latest.day == 2
    backend.close()


def test_a_backend_without_a_recorder_publishes_none(qapp):
    backend = LocalBackend(Session(FakeSimulation(30, 10, seed=1), clock=Clock()), record=False)
    backend.session.handle(Step(60))
    assert backend.poll().history is None and backend.recorder is None
    backend.close()


def test_a_batch_with_only_history_is_not_empty(real_history):
    assert not Batch(history=real_history).empty and Batch().empty


def test_the_controller_keeps_and_announces_the_history(controller):
    heard = []
    controller.history_received.connect(heard.append)
    assert controller.history is None
    controller.backend.session.handle(Step(30))
    controller.poll()
    assert len(heard) == 1 and controller.history is heard[0]
    assert controller.history.latest.day == 1


# --- the panel -------------------------------------------------------------------------------------


def test_the_panel_replaces_the_placeholder_in_its_slot(qapp, controller):
    spec = charts.PANEL
    assert (spec.id, spec.area) == ("charts", "right")
    window = MainWindow(controller, specs=[spec])
    assert isinstance(window.panels["charts"], ChartsPanel)
    window.close()


def test_with_no_history_the_panel_says_so_and_draws_nothing(panel):
    assert "first sample" in panel.status.text()
    assert curves(panel.chart_tabs[0]) == []


def test_the_population_tab_draws_the_three_counts_and_each_can_be_hidden(panel, real_history):
    panel.set_history(real_history)
    panel.refresh()
    tab = show_tab(panel, "Population")
    assert curves(tab) == ["Animals", "Plants", "Corpses"]
    assert "10 samples" in panel.status.text()
    tab.checks["plants"].setChecked(False)
    assert curves(tab) == ["Animals", "Corpses"]
    animals = tab.plot.getPlotItem().listDataItems()[0]
    x, y = animals.getData()
    days, counts = real_history.series("animals")
    assert list(x) == list(days) and list(y) == list(counts)


def test_the_axis_is_labelled_in_the_unit_in_use(panel):
    history = made_up(800, animals=1.0)
    panel.set_history(history)
    panel.refresh()
    tab = show_tab(panel, "Population")
    assert tab.plot.getPlotItem().getAxis("bottom").labelText.endswith("(years)")
    assert tab.plot.getPlotItem().listDataItems()[0].getData()[0][-1] == pytest.approx(800 / 365)


def test_the_flows_tab_shows_births_deaths_and_only_the_causes_that_happened(panel):
    samples = tuple(
        Sample(
            d,
            1,
            0,
            values={
                "births.animal": 3.0,
                "deaths.animal": 2.0,
                "deaths.animal.starvation": 2.0,
                "deaths.animal.old_age": 0.0,
                "births.plant": 1.0,
                "deaths.plant": 0.0,
            },
        )
        for d in (1, 2, 3)
    )
    panel.set_history(HistorySamples(DAY, (Tier("day", 1, samples),)))
    panel.refresh()
    tab = show_tab(panel, "Births and deaths")
    assert curves(tab) == ["Births", "Deaths", "Starvation"]
    tab.by_cause.setChecked(False)
    assert curves(tab) == ["Births", "Deaths"]
    tab.kind.setCurrentIndex(1)
    assert curves(tab) == ["Births", "Deaths"]
    assert tab.plot.getPlotItem().getAxis("left").labelText == "Plants per day"


def test_the_condition_tab_starts_with_the_four_main_levels(panel, real_history):
    panel.set_history(real_history)
    show_tab(panel, "Condition")
    panel.refresh()
    assert curves(panel.current) == ["Energy", "Health", "Age", "Diet (meat share)"]
    panel.current.checks["animal.asleep"].setChecked(True)
    assert "Asleep" in curves(panel.current)


def test_the_trait_tab_lists_the_statistics_and_draws_mean_and_range(panel, real_history):
    panel.set_history(real_history)
    tab = show_tab(panel, "Traits and genes")
    panel.refresh()
    names = [tab.stat.itemData(i) for i in range(tab.stat.count())]
    assert names == stats_of_kind(real_history, "animal") and names
    assert curves(tab) == ["Highest", "Lowest", "Mean"]
    assert len(tab.plot.getPlotItem().items) > 3  # the spread band is in there as well
    tab.show_range.setChecked(False)
    assert curves(tab) == ["Mean"]
    tab.stat.setCurrentIndex(tab.stat.count() - 1)
    label = tab.plot.getPlotItem().getAxis("left").labelText
    assert label == pretty_stat(tab.stat.currentData())
    tab.kind.setCurrentIndex(1)
    assert tab.stat.currentData().startswith("plant.")


def test_the_selected_statistic_survives_new_history(panel, real_history):
    panel.set_history(real_history)
    tab = show_tab(panel, "Traits and genes")
    panel.refresh()
    tab.stat.setCurrentIndex(3)
    chosen = tab.stat.currentData()
    panel.set_history(real_history)
    panel.refresh()
    assert tab.stat.currentData() == chosen


def test_a_single_sample_still_shows_as_a_point(panel):
    panel.set_history(made_up(1, animals=1.0))
    panel.refresh()
    (item,) = show_tab(panel, "Population").plot.getPlotItem().listDataItems()
    assert item.opts["symbol"] == "o"


def test_the_distribution_tab_scrubs_through_the_days_that_have_one(panel, real_history):
    panel.set_history(real_history)
    tab = show_tab(panel, "Gene distribution")
    panel.refresh()
    assert tab.gene.count() and tab.slider.maximum() == 2
    assert tab.slider.value() == 2  # starts on the newest
    assert "day 9 (3 of 3)" in tab.when.text()
    tab.slider.setValue(0)
    assert "day 1 (1 of 3)" in tab.when.text()
    bars = [i for i in tab.plot.getPlotItem().items if type(i).__name__ == "BarGraphItem"]
    assert len(bars) == 1
    shares = bars[0].opts["height"]
    assert len(shares) == 20 and sum(shares) == pytest.approx(1.0)


def test_the_distribution_follows_new_days_unless_the_user_scrubbed_back(panel, real_history):
    tab = show_tab(panel, "Gene distribution")
    panel.set_history(real_history)
    panel.refresh()
    tab.slider.setValue(0)
    # a longer history arrives with another distribution on day 61
    extra = Sample(
        61,
        1,
        0,
        histograms={name: (1,) * 20 for name in histogram_names(real_history, "animal")},
    )
    longer = HistorySamples(DAY, (Tier("day", 1, (*real_history.samples(), extra)),))
    panel.set_history(longer)
    panel.refresh()
    assert tab.slider.maximum() == 3 and tab.slider.value() == 0  # stayed where it was put
    tab.slider.setValue(3)
    panel.set_history(longer)
    panel.refresh()
    assert tab.slider.value() == 3


def test_with_no_distribution_the_tab_says_so(panel):
    panel.set_history(made_up(3, animals=1.0))
    tab = show_tab(panel, "Gene distribution")
    panel.refresh()
    assert "no distribution" in tab.when.text() and not tab.slider.isEnabled()


def test_a_panel_built_after_the_history_starts_from_it(qapp, controller, real_history):
    controller.history = real_history
    late = ChartsPanel(controller)
    assert "10 samples" in late.status.text()
    assert curves(late.chart_tabs[0]) == ["Animals", "Plants", "Corpses"]
    late.close()


def test_samples_arriving_in_a_rush_redraw_once(qapp, panel, real_history, monkeypatch):
    drawn = []
    monkeypatch.setattr(panel, "refresh", lambda: drawn.append(1))
    for _ in range(20):
        panel.set_history(real_history)
    assert not drawn  # nothing yet: the redraw waits for the timer
    deadline = QDeadlineTimer(2000)
    while not drawn and not deadline.hasExpired():
        qapp.processEvents()
    assert drawn == [1]


def test_a_hidden_panel_does_not_draw_until_it_is_shown(qapp, controller, real_history):
    panel = ChartsPanel(controller)
    panel.set_history(real_history)
    panel._flush()  # hidden: nothing happens
    assert panel._dirty and curves(panel.chart_tabs[0]) == []
    panel.show()
    assert not panel._dirty and curves(panel.chart_tabs[0]) == ["Animals", "Plants", "Corpses"]
    panel.close()


def test_reset_view_fits_the_data_again(panel, real_history):
    panel.set_history(real_history)
    panel.refresh()
    tab = show_tab(panel, "Population")
    box = tab.plot.getPlotItem().getViewBox()
    box.setRange(xRange=(1000, 2000), padding=0)
    assert box.viewRange()[0][0] == pytest.approx(1000)
    panel.reset_view()
    low, high = box.viewRange()[0]
    assert low < 2 and high > 9


def test_the_panel_follows_a_running_window(qapp, controller):
    window = MainWindow(controller, specs=[charts.PANEL])
    window.show()
    charts_panel = window.panels["charts"]
    controller.backend.session.handle(Step(24 * 3 + 5))
    controller.poll()
    charts_panel.refresh()
    assert charts_panel.status.text() == "1 sample, up to day 3"  # the fake has no step hook
    window.close()
