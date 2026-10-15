"""The Species tab of the charts (UX.41): which species get a line, how they are drawn and told
apart, the ranking and kind switches, highlighting, and the empty states. The data helpers need no
window; the tab runs on Qt's offscreen platform."""

import pytest

from evolution_simulator.history import HistorySamples, Sample, Tier
from evolution_simulator.history.species_view import (
    chosen_ids,
    has_species,
    species_view,
    top_at,
)
from evolution_simulator.species import SpeciesRules, SpeciesTracker, _Species

DAY = 86400.0


class Nothing:
    tick = 0
    simulated_seconds = 0.0
    animals = ()
    plants = ()


def series_of(kind: str, specs) -> dict[str, float]:
    """The tracker's own history series for living species of one kind: ``specs`` is a list of
    ``(id, size, divergence, parent)``."""
    tracker = SpeciesTracker(Nothing(), SpeciesRules(), attach=False)
    for species_id, size, divergence, parent in specs:
        species = _Species(species_id, kind, parent, 0.0, 1.0, "0123")
        species.size, species.divergence = size, divergence
        tracker._species[species_id] = species
    tracker._founders[kind] = "0123"
    tracker._taken = 1
    return tracker.series_values()


def animals_on(day: int):
    specs = [(1, 60 - day, 0.001 * day, None)]
    if day >= 4:
        specs.append((2, 20 + day, 0.05 + 0.01 * (day - 4), 1))
    if 5 <= day <= 8:
        specs.append((8, 5, 0.50, 1))  # a short-lived line, far from the founders, then gone
    if day >= 7:
        specs.append((3, 5 + day, 0.10 + 0.005 * (day - 7), 2))
    if day >= 9:
        specs += [(4, 3, 0.02, 1), (5, 4, 0.03, 1), (6, 2, 0.04, 1), (7, 1, 0.20, 3)]
    return specs


def plants_on(day: int):
    return [(10, 100 + day, 0.0, None), (11, 40, 0.02 * day, 10)] if day >= 3 else []


def story(days: int = 12, plants: bool = True) -> HistorySamples:
    samples = []
    for day in range(1, days + 1):
        values = series_of("animal", animals_on(day))
        if plants and plants_on(day):
            values.update(series_of("plant", plants_on(day)))
        samples.append(Sample(day, 1, day * 24, values=values))
    return HistorySamples(DAY, (Tier("day", 1, tuple(samples)),))


def without_species(days: int = 5) -> HistorySamples:
    samples = tuple(Sample(d, 1, d * 24, values={"animals": 10.0 + d}) for d in range(1, days + 1))
    return HistorySamples(DAY, (Tier("day", 1, samples),))


# --- the data helpers, no window --------------------------------------------------------------


def test_the_view_has_a_column_for_every_species_and_none_where_it_has_no_series():
    view = species_view(story(), "animal")
    assert view is not None and view.kind == "animal"
    assert view.days == tuple(float(d) for d in range(1, 13))
    assert view.total[-1] == sum(size for _, size, _, _ in animals_on(12))
    assert view.count[0] == 1 and view.count[-1] == 7
    assert view.sizes[2][:3] == (None, None, None) and view.sizes[2][3] == 24
    assert view.divergence[2][-1] == pytest.approx(0.13)
    assert view.sizes[8][4:8] == (5, 5, 5, 5) and view.sizes[8][8] is None
    assert view.parents[1] is None and view.parents[2] == 1 and view.parents[7] == 3
    # what is outside the five of each ranking is the sum of the rest, as the tracker wrote it
    top = top_at(view, 11, "size")
    assert view.rest["size"][-1] == view.total[-1] - sum(view.sizes[i][-1] for i in top)
    assert view.first_index(2) == 3 and view.first_index(1) == 0 and view.first_index(7) == 8
    assert view.alive_at_end(2) and not view.alive_at_end(8)
    assert view.last_divergence(8) == pytest.approx(0.5)


def test_a_history_without_species_has_no_view_and_a_kind_with_none_neither():
    assert not has_species(without_species())
    assert species_view(without_species(), "animal") is None
    animals_only = story(plants=False)
    assert has_species(animals_only)
    assert species_view(animals_only, "plant") is None and species_view(animals_only, "animal")
    assert species_view(story(), "plant").days[0] == 3.0  # only the samples that have plants


def test_the_top_five_are_the_furthest_from_the_founders_or_the_biggest():
    view = species_view(story(), "animal")
    assert top_at(view, 11, "divergence") == [7, 2, 3, 6, 5]
    assert top_at(view, 11, "size") == [1, 2, 3, 5, 4]
    assert top_at(view, 11, "size", count=2) == [1, 2]
    assert top_at(view, 0, "size") == [1]  # fewer species than five
    with pytest.raises(ValueError, match="Rank by"):
        top_at(view, 0, "colour")


def test_ties_go_to_the_lower_id():
    values = series_of("animal", [(5, 10, 0.1, None), (3, 10, 0.1, None), (4, 10, 0.1, None)])
    view = species_view(
        HistorySamples(DAY, (Tier("day", 1, (Sample(1, 1, 0, values=values),)),)), "animal"
    )
    assert top_at(view, 0, "size") == [3, 4, 5] and top_at(view, 0, "divergence") == [3, 4, 5]


def test_the_lines_are_the_newest_top_five_then_those_that_were_in_it_longest():
    view = species_view(story(), "animal")
    by_divergence = chosen_ids(view, "divergence")
    assert by_divergence[:5] == [7, 2, 3, 6, 5]  # the newest top five, first in front
    assert by_divergence[5:] == [1, 8]  # then the long-time and the short-lived earlier ones
    assert 4 not in by_divergence  # never in the top five by distance
    by_size = chosen_ids(view, "size")
    assert by_size[:5] == [1, 2, 3, 5, 4]
    assert 8 in by_size[5:] and 7 not in by_size
    assert chosen_ids(view, "divergence", cap=6) == [7, 2, 3, 6, 5, 1]
    assert len(chosen_ids(view, "divergence", cap=3)) == 5  # the newest top five always stay


def test_samples_merged_into_a_week_still_read_back():
    days = story(8, plants=False).tiers[0].samples
    week = days[0]
    for later in days[1:7]:
        week = week.merge(later)
    history = HistorySamples(DAY, (Tier("week", 7, (week, days[7])),))
    view = species_view(history, "animal")
    assert view.days == (7.0, 8.0)
    # species 2 was in 4 of the 7 days: its size counts as nothing on the others, but its distance
    # is only averaged over the days that had it (so it stays between the values it had)
    assert view.sizes[2][0] == pytest.approx(sum(20 + d for d in range(4, 8)) / 7)
    assert 0.05 <= view.divergence[2][0] <= 0.08
    assert view.parents[2] == 1


# --- the tab ---------------------------------------------------------------------------------


qtwidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtCore import Qt

pytest.importorskip("pyqtgraph", exc_type=ImportError)

from evolution_simulator.viewer.panels.charts import (
    SPECIES_COLOURS,
    ChartsPanel,
    ColourBook,
    TimeAxis,
    age_text,
    history_view,
    species_label,
)


def species_tab(panel: ChartsPanel):
    for index, tab in enumerate(panel.chart_tabs):
        if tab.title == "Species":
            panel.tabs.setCurrentIndex(index)
            return tab
    raise AssertionError("no Species tab")


@pytest.fixture
def panel(qapp):
    widget = history_view(story())
    widget.resize(800, 500)
    yield widget
    widget.close()


@pytest.fixture
def tab(panel):
    return species_tab(panel)


def names(tab) -> list[str]:
    return [item.name() for item in tab.plot.getPlotItem().listDataItems()]


def pen_of(curve):
    return curve.opts["pen"]


def test_the_tab_sits_between_lineages_and_the_traits(panel):
    titles = [t.title for t in panel.chart_tabs]
    assert titles.index("Species") == titles.index("Lineages") + 1
    assert titles[titles.index("Species") + 1] == "Traits and genes"


def test_the_tab_draws_a_total_the_others_and_a_line_for_each_top_species(tab):
    # animals ranked by distance from the founders, the first choice
    assert tab.kind.currentData() == "animal" and tab.rank.currentData() == "divergence"
    assert set(tab.lines) == {7, 2, 3, 6, 5, 1, 8}
    assert names(tab)[:2] == ["Total", "Others"]
    assert len(names(tab)) == 2 + 7
    total = tab.plot.getPlotItem().listDataItems()[0]
    assert list(total.getData()[1])[-1] == sum(size for _, size, _, _ in animals_on(12))
    assert tab.message.isHidden() and not tab.plot.isHidden()


def test_the_legend_gives_each_species_its_id_age_parent_and_distance(tab):
    labels = {i: curve.name() for i, curve in tab.lines.items()}
    assert labels[2] == "#2 · age 8 days · parent #1 · 13.0% from founders"
    assert labels[1].startswith("#1 · age 11 days · parent none · 1.2%")
    assert labels[7].startswith("#7 · age 3 days · parent #3 · 20.0%")
    assert labels[8].endswith("· 50.0% from founders · gone")
    assert "gone" not in labels[2]


def test_a_gone_species_is_dashed_and_starts_where_it_first_appeared(tab):
    gone = tab.lines[8]
    assert pen_of(gone).style() == Qt.PenStyle.DashLine
    assert pen_of(tab.lines[2]).style() == Qt.PenStyle.SolidLine
    days, sizes = gone.getData()
    assert days[0] == 5.0 and days[-1] == 12.0
    assert list(sizes) == [5, 5, 5, 5, 0, 0, 0, 0]  # nothing in a sample that does not list it


def test_the_age_is_given_in_the_units_of_the_axis():
    assert age_text(TimeAxis("days", 1.0), 0) == "new"
    assert age_text(TimeAxis("days", 7.0), 3) == "21 days"
    assert age_text(TimeAxis("years", 1 / 365), 730) == "2.0 years"
    view = species_view(story(), "animal")
    assert "age 1.0 years" in species_label(view, 1, TimeAxis("years", 1 / 11))


def test_ranking_by_size_chooses_other_species(tab):
    tab.rank.setCurrentIndex(tab.rank.findData("size"))
    assert set(tab.lines) == {1, 2, 3, 5, 4, 8}
    assert 7 not in tab.lines and 6 not in tab.lines
    rest = tab.plot.getPlotItem().listDataItems()[1]
    view = species_view(story(), "animal")
    assert list(rest.getData()[1]) == list(view.rest["size"])  # the others of this ranking


def test_the_kind_switch_shows_plants_with_their_own_total_and_species(tab):
    tab.kind.setCurrentIndex(tab.kind.findData("plant"))
    assert set(tab.lines) == {10, 11}
    assert names(tab)[:2] == ["Total", "Others"]
    days, totals = tab.plot.getPlotItem().listDataItems()[0].getData()
    assert days[0] == 3.0 and list(totals)[-1] == 112 + 40


def test_the_total_and_the_others_can_be_switched_off(tab):
    tab.total.setChecked(False)
    tab.rest.setChecked(False)
    assert names(tab) == [curve.name() for curve in tab.lines.values()]


def test_showing_the_distance_draws_percent_and_leaves_out_the_sums(tab):
    tab.show_what.setCurrentIndex(tab.show_what.findData("divergence"))
    assert not tab.total.isEnabled() and not tab.rest.isEnabled()
    assert len(names(tab)) == len(tab.lines)  # no Total, no Others
    days, values = tab.lines[7].getData()
    assert days[0] == 9.0 and list(values)[-1] == pytest.approx(20.0)
    tab.show_what.setCurrentIndex(tab.show_what.findData("size"))
    assert tab.total.isEnabled() and names(tab)[0] == "Total"


# --- colours ---------------------------------------------------------------------------------


def test_a_species_keeps_its_colour_and_species_drawn_together_differ(panel, tab):
    colours = {i: looks[0] for i, looks in tab._looks.items()}
    assert len(set(colours.values())) == len(colours) and set(colours.values()) <= set(
        SPECIES_COLOURS
    )
    tab.rank.setCurrentIndex(tab.rank.findData("size"))
    tab.kind.setCurrentIndex(tab.kind.findData("plant"))
    tab.kind.setCurrentIndex(tab.kind.findData("animal"))
    tab.rank.setCurrentIndex(tab.rank.findData("divergence"))
    assert {i: looks[0] for i, looks in tab._looks.items()} == colours
    panel.set_history(story(13))  # the run goes on
    panel.refresh()
    assert {i: tab._looks[i][0] for i in colours if i in tab._looks} == {
        i: c for i, c in colours.items() if i in tab._looks
    }


def test_the_colour_book_hands_out_free_colours_and_remembers_them():
    book = ColourBook()
    first = [book.colour(i, [1, 2, 3]) for i in (1, 2, 3)]
    assert len(set(first)) == 3 and book.colour(2) == first[1]
    many = list(range(1, len(SPECIES_COLOURS) + 4))
    assert all(book.colour(i, many) in SPECIES_COLOURS for i in many)  # past the palette it cycles


# --- highlighting ----------------------------------------------------------------------------


def alpha_and_width(curve):
    pen = pen_of(curve)
    return pen.color().alpha(), pen.width()


def test_clicking_a_line_highlights_it_and_fades_the_others(tab):
    assert not tab.clear.isEnabled() and tab.highlighted is None
    tab.lines[2].sigClicked.emit(tab.lines[2], None)  # what a click on the curve sends
    assert tab.highlighted == 2 and tab.clear.isEnabled()
    assert alpha_and_width(tab.lines[2]) == (255, tab.HIGHLIGHT_WIDTH)
    for species_id, curve in tab.lines.items():
        if species_id != 2:
            assert alpha_and_width(curve) == (tab.DIM_ALPHA, 1)


def test_clicking_the_line_again_or_the_button_shows_all_lines_alike(tab):
    tab.lines[3].sigClicked.emit(tab.lines[3], None)
    tab.lines[3].sigClicked.emit(tab.lines[3], None)
    assert tab.highlighted is None
    assert {alpha_and_width(c) for c in tab.lines.values()} == {(255, 2)}
    tab.highlight(5)
    tab.clear.click()
    assert tab.highlighted is None and not tab.clear.isEnabled()
    tab.highlight(999)  # not a line on the chart
    assert tab.highlighted is None


def test_the_highlight_stays_through_new_samples_and_a_ranking_that_still_draws_it(panel, tab):
    tab.highlight(2)
    panel.set_history(story(13))
    panel.refresh()
    assert tab.highlighted == 2 and alpha_and_width(tab.lines[2])[1] == tab.HIGHLIGHT_WIDTH
    tab.rank.setCurrentIndex(tab.rank.findData("size"))
    assert tab.highlighted == 2
    tab.rank.setCurrentIndex(tab.rank.findData("divergence"))
    tab.highlight(7)
    tab.rank.setCurrentIndex(tab.rank.findData("size"))  # 7 has no line by size
    assert tab.highlighted is None and not tab.clear.isEnabled()


def test_changing_the_kind_clears_the_highlight(tab):
    tab.highlight(2)
    tab.kind.setCurrentIndex(tab.kind.findData("plant"))
    assert tab.highlighted is None


# --- no species ------------------------------------------------------------------------------


def test_a_history_from_before_species_says_so_instead_of_drawing(qapp):
    panel = history_view(without_species())
    tab = species_tab(panel)
    assert tab.plot.isHidden() and not tab.message.isHidden()
    assert "No species in this history" in tab.message.text()
    assert tab.lines == {} and not tab.clear.isEnabled()
    panel.close()


def test_a_kind_without_species_yet_says_which(qapp):
    panel = history_view(story(2))  # plants come on day 3
    tab = species_tab(panel)
    tab.kind.setCurrentIndex(tab.kind.findData("plant"))
    assert not tab.message.isHidden() and tab.plot.isHidden()
    assert "No plant species recorded yet" in tab.message.text()
    tab.kind.setCurrentIndex(tab.kind.findData("animal"))
    assert tab.message.isHidden() and not tab.plot.isHidden()
    panel.close()


def test_a_chart_that_was_empty_fills_when_species_arrive(qapp):
    panel = history_view(without_species())
    tab = species_tab(panel)
    assert tab.lines == {}
    panel.set_history(story())
    panel.refresh()
    assert tab.message.isHidden() and len(tab.lines) == 7
    panel.close()


# --- a real recorder --------------------------------------------------------------------------


def test_a_real_worlds_history_draws_species_and_a_format_two_one_does_not(qapp):
    from persistence_support import rich_world

    from evolution_simulator.history import Recorder

    world = rich_world()
    recorder = Recorder(world)
    world.run(24 * 16)
    panel = history_view(recorder.history())
    tab = species_tab(panel)
    assert tab.message.isHidden() and tab.lines
    assert all(curve.name().startswith("#") for curve in tab.lines.values())
    animals_label = "Animals per species (estimated)"
    assert tab.plot.getPlotItem().getAxis("left").labelText == animals_label
    old = HistorySamples(  # the same samples as a format-2 history: no species values
        recorder.history().period_seconds,
        tuple(
            Tier(
                t.name,
                t.periods,
                tuple(
                    Sample(
                        s.day,
                        s.span,
                        s.tick,
                        {k: v for k, v in s.values.items() if not k.startswith("species.")},
                        s.stats,
                        s.histograms,
                    )
                    for s in t.samples
                ),
            )
            for t in recorder.history().tiers
        ),
        format=2,
    )
    panel.set_history(old)
    panel.refresh()
    assert tab.plot.isHidden() and "No species in this history" in tab.message.text()
    panel.close()
