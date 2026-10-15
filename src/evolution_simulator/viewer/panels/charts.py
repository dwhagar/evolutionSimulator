"""Charts and history (UX.16): pyqtgraph line charts of the recorded statistics.

Seven tabs read the ``HistorySamples`` the controller publishes (``controller.history``, one new
sample per simulated day): population, births and deaths (by cause), condition (energy, health and
the shares asleep, pregnant and ready), lineages (founders that still have descendants alive), species
(the biggest or most diverged species of plants or animals, UX.41), a trait or gene over time (mean,
the middle 80 percent from the 10th to the 90th percentile, and the range), and a gene distribution
that can be scrubbed through time. Genes and traits carry the display names
and units of the catalogue (``evolution_simulator.catalogue``). Everything is read from
``evolution_simulator.history``; nothing here touches the world.

The time axis is in simulated days, and in years once the run is more than two years old. Charts
zoom and pan with the mouse (right-click for pyqtgraph's own menu, which also exports an image), and
"Reset view" fits the data again.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.catalogue import Description, describe_gene, describe_trait
from evolution_simulator.history import HistorySamples
from evolution_simulator.history.species_view import (
    SpeciesView,
    chosen_ids,
    has_species,
    species_view,
)
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext

DAY_SECONDS = 86400.0
YEAR_DAYS = 365.0
YEARS_FROM = 2 * YEAR_DAYS
"""The axis switches from days to years once the run is this many days old."""
REDRAW_MS = 200
"""The most often the charts are redrawn when samples arrive in a rush (a fast-forward)."""

# The Okabe and Ito colour-blind-safe palette, without black so it reads on a dark window too.
BLUE, VERMILION, GREEN, ORANGE, PINK, SKY, YELLOW = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#E69F00",
    "#CC79A7",
    "#56B4E9",
    "#F0E442",
)

GREY = "#999999"

SPECIES_COLOURS = (
    BLUE,
    VERMILION,
    GREEN,
    ORANGE,
    PINK,
    SKY,
    YELLOW,
    "#882255",
    "#44AA99",
    "#999933",
    "#332288",
    "#AA4499",
)
"""What the lines of the species tab take their colours from (Okabe and Ito, then Paul Tol's)."""

KIND_NAMES = {"animal": "Animals", "plant": "Plants"}
KIND_COLOURS = {"animal": BLUE, "plant": GREEN}
CAUSE_COLOURS = {
    "starvation": ORANGE,
    "old_age": SKY,
    "predation": VERMILION,
    "poison": PINK,
    "eaten": GREEN,
    "damage": YELLOW,
}
"""One colour per ``DeathCause`` value, so a cause keeps its colour on every chart."""


# --- plain helpers (no drawing) -------------------------------------------------------------------


@dataclass(frozen=True)
class TimeAxis:
    """How recorded periods are shown: as simulated days, or as years for a long run."""

    unit: str
    """``"days"`` or ``"years"``."""
    per_period: float
    """Axis units in one recorded period (a period is a day unless the recorder was told otherwise)."""

    @property
    def label(self) -> str:
        return f"Simulated time ({self.unit})"

    def x(self, periods: Sequence[float]) -> np.ndarray:
        return np.asarray(periods, dtype=float) * self.per_period

    def text(self, period: float) -> str:
        value = period * self.per_period
        if self.unit == "years":
            return f"year {value:.2f}"
        return f"day {value:.0f}"


def time_axis(history: HistorySamples | None) -> TimeAxis:
    """Days, or years once the newest sample is more than two years in."""
    seconds = DAY_SECONDS if history is None else history.period_seconds
    days_per_period = seconds / DAY_SECONDS
    latest = None if history is None else history.latest
    run_days = 0.0 if latest is None else latest.day * days_per_period
    if run_days >= YEARS_FROM:
        return TimeAxis("years", days_per_period / YEAR_DAYS)
    return TimeAxis("days", days_per_period)


def describe_stat(name: str) -> Description | None:
    """The catalogue's name, unit and meaning of a recorded gene or trait
    (``animal.gene.speed``, ``plant.trait.canopy_radius``), or ``None`` for anything else."""
    _, _, rest = name.partition(".")
    group, _, field = rest.partition(".")
    try:
        if group == "gene" and field:
            return describe_gene(field)
        if group == "trait" and field:
            return describe_trait(field)
    except KeyError:
        return None
    return None


def pretty_stat(name: str) -> str:
    """A readable name for a recorded statistic: the catalogue's display name for a gene or trait
    (``animal.gene.sight_fov`` -> ``Field of vision (gene)``), else the name made readable
    (``animal.trait.max_speed`` -> ``max speed (trait)``)."""
    _, _, rest = name.partition(".")
    if rest == "age_at_death":
        return "age at death"
    group, _, field = rest.partition(".")
    if group in ("trait", "gene") and field:
        described = describe_stat(name)
        if described is not None:
            return f"{described.name} ({group})"
        return f"{field.replace('_', ' ')} ({group})"
    return rest.replace(".", " ").replace("_", " ")


def stat_label(name: str) -> str:
    """The vertical-axis label of a statistic: its name and, when the catalogue has one, its unit."""
    described = describe_stat(name)
    if described is None or not described.unit:
        return pretty_stat(name)
    return f"{pretty_stat(name)}, {described.unit}"


def stats_of_kind(history: HistorySamples, kind: str) -> list[str]:
    """The statistic names of one kind ("animal" or "plant"): age at death, traits, then genes."""
    order = {"age_at_death": 0, "trait": 1, "gene": 2}
    names = [n for n in history.stat_names() if n.startswith(f"{kind}.")]

    def key(name: str) -> tuple[int, str]:
        rest = name.partition(".")[2]
        return order.get(rest.partition(".")[0], 3), rest

    return sorted(names, key=key)


def histogram_names(history: HistorySamples, kind: str) -> list[str]:
    """The genes of one kind that have a recorded distribution."""
    found: set[str] = set()
    for sample in history.samples():
        found.update(n for n in sample.histograms if n.startswith(f"{kind}."))
    return sorted(found)


def histogram_days(history: HistorySamples, name: str) -> list[int]:
    """The periods that have a distribution of this gene, oldest first (what the slider walks)."""
    return [s.day for s in history.samples() if name in s.histograms]


def histogram_shares(counts: Sequence[int]) -> np.ndarray:
    """Bin counts as shares of the whole (all zero for an empty histogram)."""
    values = np.asarray(counts, dtype=float)
    total = values.sum()
    return values / total if total > 0 else values


def spread_band(means: np.ndarray, stds: np.ndarray, los: np.ndarray, his: np.ndarray):
    """The lower and upper edge of mean plus or minus one deviation, kept inside the range seen."""
    return np.maximum(means - stds, los), np.minimum(means + stds, his)


def percentile_band(
    means: np.ndarray,
    stds: np.ndarray,
    los: np.ndarray,
    his: np.ndarray,
    p10s: np.ndarray,
    p90s: np.ndarray,
):
    """The lower and upper edge of the middle 80 percent (10th to 90th percentile). Where a sample
    has no percentiles (history recorded before they were kept, a nan here), the edge is the mean
    plus or minus one deviation, as ``spread_band`` gives."""
    fallback_low, fallback_high = spread_band(means, stds, los, his)
    return (
        np.where(np.isnan(p10s), fallback_low, p10s),
        np.where(np.isnan(p90s), fallback_high, p90s),
    )


def death_causes(history: HistorySamples, kind: str) -> list[str]:
    """Causes of death of this kind that have happened at least once, in a fixed order."""
    causes = []
    for cause in CAUSE_COLOURS:
        _, values = history.series(f"deaths.{kind}.{cause}")
        if any(values):
            causes.append(cause)
    return causes


class ColourBook:
    """A colour for each species id that stays the same for as long as the chart lives, and that no
    two species drawn together share while the palette has a free one."""

    def __init__(self) -> None:
        self._given: dict[int, str] = {}

    def colour(self, species_id: int, drawn: Sequence[int] = ()) -> str:
        if species_id not in self._given:
            taken = {self._given[i] for i in drawn if i in self._given}
            free = [c for c in SPECIES_COLOURS if c not in taken]
            self._given[species_id] = (
                free[0] if free else SPECIES_COLOURS[species_id % len(SPECIES_COLOURS)]
            )
        return self._given[species_id]


def age_text(axis: TimeAxis, periods: float) -> str:
    """How long ago, in the axis' unit: ``340 days`` or ``1.2 years`` (``new`` for none)."""
    value = periods * axis.per_period
    if periods <= 0:
        return "new"
    return f"{value:.1f} years" if axis.unit == "years" else f"{value:.0f} days"


def species_label(view: SpeciesView, species_id: int, axis: TimeAxis) -> str:
    """The legend text of a species: its id, age, parent and how far it has drifted from the
    founders of its kind (gone species say so)."""
    age = view.days[-1] - view.days[view.first_index(species_id)]
    parent = view.parents.get(species_id)
    divergence = view.last_divergence(species_id)
    text = (
        f"#{species_id} \u00b7 age {age_text(axis, age)} \u00b7 "
        f"parent {'none' if parent is None else f'#{parent}'}"
    )
    if divergence is not None:
        text += f" \u00b7 {divergence * 100:.1f}% from founders"
    return text if view.alive_at_end(species_id) else f"{text} \u00b7 gone"


# --- drawing ---------------------------------------------------------------------------------------


def _colour(value: str) -> QColor:
    return QColor(value)


class ChartPlot(pg.PlotWidget):
    """A plot in the window's own colours, with a legend, a grid and the usual mouse zoom."""

    def __init__(self, parent: QWidget, y_label: str = "") -> None:
        super().__init__(parent)
        item = self.getPlotItem()
        for side in ("left", "bottom"):
            item.getAxis(side).enableAutoSIPrefix(False)  # a share of 0.15 is not "150 (x0.001)"
        item.showGrid(x=True, y=True, alpha=0.25)
        self.legend = item.addLegend(offset=(10, 10))
        self.apply_palette()
        if y_label:
            item.setLabel("left", y_label)

    def apply_palette(self) -> None:
        """Take the background and text colours from the window's palette (again, when the theme
        changes)."""
        palette = self.palette()
        background, foreground = palette.window().color(), palette.windowText().color()
        self.setBackground(background)
        item = self.getPlotItem()
        for side in ("left", "bottom"):
            axis = item.getAxis(side)
            axis.setPen(foreground)
            axis.setTextPen(foreground)
        self.legend.setLabelTextColor(foreground)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        palette_changed = event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        )
        if palette_changed and hasattr(self, "legend"):  # (not yet, while it is being built)
            self.apply_palette()

    def reset(self) -> None:
        """Clear the curves and the legend, ready to draw again."""
        self.getPlotItem().clear()
        self.legend.clear()

    def line(
        self,
        x: np.ndarray,
        y: np.ndarray,
        colour: str,
        name: str | None = None,
        width: int = 2,
        style: Qt.PenStyle = Qt.PenStyle.SolidLine,
    ) -> pg.PlotDataItem:
        pen = pg.mkPen(_colour(colour), width=width, style=style)
        lone = len(x) == 1  # a single point would draw nothing
        return self.getPlotItem().plot(
            x,
            y,
            pen=pen,
            name=name,
            symbol="o" if lone else None,
            symbolSize=6,
            symbolBrush=_colour(colour),
        )

    def fit(self) -> None:
        self.getPlotItem().autoRange()


class ChartTab(QWidget):
    """One tab of the panel: its own controls (a row above the plot) and a ``ChartPlot``."""

    title = ""

    def __init__(self, parent: QWidget, y_label: str = "") -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.plot = ChartPlot(self, y_label)
        self.controls = QHBoxLayout()
        self.controls.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.controls)
        layout.addWidget(self.plot, 1)
        self.history: HistorySamples | None = None
        self.axis = TimeAxis("days", 1.0)

    def add_check(self, text: str, checked: bool = True, colour: str | None = None) -> QCheckBox:
        box = QCheckBox(text, self)
        box.setChecked(checked)
        if colour is not None:
            box.setStyleSheet(f"QCheckBox {{ color: {colour}; font-weight: bold; }}")
        box.toggled.connect(lambda _checked: self.redraw())
        self.controls.addWidget(box)
        return box

    def add_combo(self, on_change: Callable[[], None] | None = None) -> QComboBox:
        combo = QComboBox(self)
        combo.currentIndexChanged.connect(lambda _index: (on_change or self.redraw)())
        self.controls.addWidget(combo)
        return combo

    def update_history(self, history: HistorySamples, axis: TimeAxis) -> None:
        self.history, self.axis = history, axis
        self.plot.getPlotItem().setLabel("bottom", axis.label)
        self.redraw()

    def redraw(self) -> None:
        if self.history is not None:
            self.draw(self.history, self.axis)

    def fit(self) -> None:
        """Fit the chart to all of its data again."""
        self.plot.fit()

    def draw(self, history: HistorySamples, axis: TimeAxis) -> None:  # pragma: no cover
        raise NotImplementedError


class SeriesTab(ChartTab):
    """Lines for a fixed list of recorded values, each with a check box."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        y_label: str,
        series: Sequence[tuple[str, str, str]],
        checked: Sequence[str] | None = None,
    ) -> None:
        super().__init__(parent, y_label)
        self.title = title
        self.series = series
        self.checks = {
            name: self.add_check(label, checked is None or name in checked, colour)
            for name, label, colour in series
        }
        self.controls.addStretch(1)

    def draw(self, history: HistorySamples, axis: TimeAxis) -> None:
        self.plot.reset()
        for name, label, colour in self.series:
            if not self.checks[name].isChecked():
                continue
            days, values = history.series(name)
            if days:
                self.plot.line(axis.x(days), np.asarray(values), colour, label)


class PopulationTab(SeriesTab):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(
            parent,
            "Population",
            "Count",
            [
                ("animals", "Animals", BLUE),
                ("plants", "Plants", GREEN),
                ("corpses", "Corpses", ORANGE),
            ],
        )


class ConditionTab(SeriesTab):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(
            parent,
            "Condition",
            "Average of the animals (0 to 1)",
            [
                ("animal.energy", "Energy", ORANGE),
                ("animal.health", "Health", GREEN),
                ("animal.age", "Age", BLUE),
                ("animal.diet", "Diet (meat share)", VERMILION),
                ("animal.asleep", "Asleep", SKY),
                ("animal.pregnant", "Pregnant", PINK),
                ("animal.ready", "Ready to mate", YELLOW),
            ],
            checked=["animal.energy", "animal.health", "animal.age", "animal.diet"],
        )


class LineagesTab(SeriesTab):
    """How many founders still have a line of descent alive (through the mother, or the seeding
    plant). It falls when a line dies out, so it shows diversity being lost."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(
            parent,
            "Lineages",
            "Founder lines still alive",
            [("lineages.animal", "Animals", BLUE), ("lineages.plant", "Plants", GREEN)],
        )


class FlowsTab(ChartTab):
    """Births and deaths per period, and the deaths split by cause."""

    title = "Births and deaths"

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "Per day")
        self.kind = self.add_combo()
        for kind, text in KIND_NAMES.items():
            self.kind.addItem(text, kind)
        self.births = self.add_check("Births", True, GREEN)
        self.deaths = self.add_check("Deaths", True, GREY)
        self.by_cause = self.add_check("Deaths by cause", True)
        self.controls.addStretch(1)

    def draw(self, history: HistorySamples, axis: TimeAxis) -> None:
        self.plot.reset()
        kind = self.kind.currentData()
        self.plot.getPlotItem().setLabel("left", f"{KIND_NAMES[kind]} per day")
        if self.births.isChecked():
            self._series(history, axis, f"births.{kind}", GREEN, "Births")
        if self.deaths.isChecked():
            self._series(history, axis, f"deaths.{kind}", GREY, "Deaths", width=3)
        if self.by_cause.isChecked():
            for cause in death_causes(history, kind):
                label = cause.replace("_", " ").capitalize()
                self._series(
                    history, axis, f"deaths.{kind}.{cause}", CAUSE_COLOURS[cause], label, width=1
                )

    def _series(
        self, history: HistorySamples, axis: TimeAxis, name: str, colour: str, label: str, **kw
    ) -> None:
        days, values = history.series(name)
        if days:
            self.plot.line(axis.x(days), np.asarray(values), colour, label, **kw)


class SpeciesTab(ChartTab):
    """The species of plants or animals through time (UX.41): the total, the top five by distance
    from the founding genome or by size as lines (a stable colour for each, a legend with id, age,
    parent and divergence), what the others add up to, and a click on a line to highlight it."""

    title = "Species"
    HIGHLIGHT_WIDTH = 4
    DIM_ALPHA = 70

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "Members")
        self.kind = self.add_combo(self._kind_changed)
        for kind, text in KIND_NAMES.items():
            self.kind.addItem(text, kind)
        self.rank = self.add_combo()
        self.rank.addItem("Top species by distance from the founders", "divergence")
        self.rank.addItem("Top species by size", "size")
        self.rank.setToolTip(
            "Which species get a line: the five furthest from the genome the world started with, "
            "or the five biggest."
        )
        self.show_what = self.add_combo()
        self.show_what.addItem("Show members", "size")
        self.show_what.addItem("Show distance from the founders", "divergence")
        self.total = self.add_check("Total", True)
        self.rest = self.add_check("Others", True)
        self.rest.setToolTip("Members outside the five species with lines")
        self.clear = QPushButton("Clear highlight", self)
        self.clear.setToolTip("Click a line to highlight its species; click it again to clear")
        self.clear.setEnabled(False)
        self.clear.clicked.connect(lambda _checked=False: self.highlight(None))
        self.controls.addWidget(self.clear)
        self.controls.addStretch(1)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.hide()
        self.layout().insertWidget(1, self.message, 1)  # type: ignore[union-attr]
        self.view: SpeciesView | None = None
        self.lines: dict[int, pg.PlotDataItem] = {}
        """The drawn species lines by species id."""
        self.highlighted: int | None = None
        self._colours = ColourBook()
        self._looks: dict[int, tuple[str, Qt.PenStyle]] = {}

    def _kind_changed(self) -> None:
        self.highlighted = None
        self.redraw()

    def _say(self, text: str | None) -> None:
        """Show a message instead of the chart, or (with ``None``) the chart."""
        self.message.setVisible(text is not None)
        self.message.setText(text or "")
        self.plot.setVisible(text is None)

    def draw(self, history: HistorySamples, axis: TimeAxis) -> None:
        self.plot.reset()
        self.lines, self._looks = {}, {}
        kind = self.kind.currentData()
        view = self.view = species_view(history, kind)
        if view is None:
            noun = KIND_NAMES[kind].lower()
            self._say(
                f"No {noun[:-1]} species recorded yet: the tracker takes its first sample after "
                "some simulated days."
                if has_species(history)
                else "No species in this history: it was recorded before species were tracked, "
                "or with species tracking turned off."
            )
            self.clear.setEnabled(False)
            return
        self._say(None)
        members = self.show_what.currentData() == "size"
        self.total.setEnabled(members)
        self.rest.setEnabled(members)
        item = self.plot.getPlotItem()
        item.setLabel(
            "left",
            f"{KIND_NAMES[kind]} per species (estimated)"
            if members
            else "From the founding genome (%)",
        )
        days = axis.x(view.days)
        if members and self.total.isChecked():
            self.plot.line(days, np.asarray(view.total), GREY, "Total", width=3)
        if members and self.rest.isChecked():
            rest = view.rest[self.rank.currentData()]
            self.plot.line(
                days, np.asarray(rest), GREY, "Others", width=1, style=Qt.PenStyle.DotLine
            )
        ids = chosen_ids(view, self.rank.currentData())
        for species_id in ids:
            start = view.first_index(species_id)
            if members:
                column = view.sizes[species_id][start:]
                x, y = days[start:], np.array([0.0 if v is None else v for v in column])
            else:
                points = [
                    (d, v * 100) for d, v in zip(days, view.divergence[species_id]) if v is not None
                ]
                x, y = np.array([p[0] for p in points]), np.array([p[1] for p in points])
            if not len(x):
                continue
            colour = self._colours.colour(species_id, ids)
            style = Qt.PenStyle.SolidLine if view.alive_at_end(species_id) else Qt.PenStyle.DashLine
            curve = self.plot.line(
                x, y, colour, species_label(view, species_id, axis), width=2, style=style
            )
            curve.setCurveClickable(True, width=10)
            curve.sigClicked.connect(lambda _item, _event, i=species_id: self.highlight(i))
            self.lines[species_id] = curve
            self._looks[species_id] = (colour, style)
        if self.highlighted not in self.lines:
            self.highlighted = None
        self._restyle()

    def highlight(self, species_id: int | None) -> None:
        """Make this species' line stand out (the others fade), or with ``None`` (or the species
        already highlighted) show all lines alike. The curves are restyled where they are, not drawn
        again, so this is safe to call from the click on a curve."""
        if species_id == self.highlighted or species_id not in self.lines:
            species_id = None
        self.highlighted = species_id
        self._restyle()

    def _restyle(self) -> None:
        self.clear.setEnabled(self.highlighted is not None)
        for species_id, curve in self.lines.items():
            colour, style = self._looks[species_id]
            pen_colour = _colour(colour)
            width = 2
            if self.highlighted is not None:
                if species_id == self.highlighted:
                    width = self.HIGHLIGHT_WIDTH
                else:
                    width = 1
                    pen_colour.setAlpha(self.DIM_ALPHA)
            curve.setPen(pg.mkPen(pen_colour, width=width, style=style))


class TraitTab(ChartTab):
    """One trait or gene over time: its mean, the middle 80 percent, and the range seen."""

    title = "Traits and genes"

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.kind = self.add_combo(self._kind_changed)
        for kind, text in KIND_NAMES.items():
            self.kind.addItem(text, kind)
        self.stat = self.add_combo()
        self.show_range = self.add_check("Range (lowest to highest)", True)
        self.show_band = self.add_check("Middle 80% (10th to 90th percentile)", True)
        self.show_band.setToolTip(
            "Where history was recorded before percentiles were kept, the band is the mean "
            "plus or minus one deviation instead."
        )
        self.controls.addStretch(1)
        self._listed: tuple[str, ...] = ()

    def update_history(self, history: HistorySamples, axis: TimeAxis) -> None:
        self._fill(history)
        super().update_history(history, axis)

    def _kind_changed(self) -> None:
        if self.history is not None:
            self._fill(self.history)
        self.redraw()

    def _fill(self, history: HistorySamples) -> None:
        """List the statistics of the chosen kind, keeping the selection when it is still there."""
        names = tuple(stats_of_kind(history, self.kind.currentData()))
        if names == self._listed:
            return
        keep = self.stat.currentData()
        self.stat.blockSignals(True)
        self.stat.clear()
        for name in names:
            self.stat.addItem(pretty_stat(name), name)
            described = describe_stat(name)
            if described is not None:
                self.stat.setItemData(
                    self.stat.count() - 1, described.meaning, Qt.ItemDataRole.ToolTipRole
                )
        index = self.stat.findData(keep)
        self.stat.setCurrentIndex(index if index >= 0 else (0 if names else -1))
        self.stat.blockSignals(False)
        self._listed = names

    def draw(self, history: HistorySamples, axis: TimeAxis) -> None:
        self.plot.reset()
        name = self.stat.currentData()
        if name is None:
            return
        self.plot.getPlotItem().setLabel("left", stat_label(name))
        days, stats = history.stat_series(name)
        if not days:
            return
        x = axis.x(days)
        mean = np.array([s.mean for s in stats])
        std = np.array([s.std for s in stats])
        lo = np.array([s.lo for s in stats])
        hi = np.array([s.hi for s in stats])
        colour = KIND_COLOURS[self.kind.currentData()]
        if self.show_range.isChecked():
            self.plot.line(x, hi, colour, "Highest", width=1, style=Qt.PenStyle.DashLine)
            self.plot.line(x, lo, colour, "Lowest", width=1, style=Qt.PenStyle.DashLine)
        if len(x) > 1 and self.show_band.isChecked():
            p10 = np.array([np.nan if s.p10 is None else s.p10 for s in stats])
            p90 = np.array([np.nan if s.p90 is None else s.p90 for s in stats])
            low, high = percentile_band(mean, std, lo, hi, p10, p90)
            top, bottom = pg.PlotCurveItem(x, high), pg.PlotCurveItem(x, low)
            fill = _colour(colour)
            fill.setAlpha(60)
            self.plot.getPlotItem().addItem(pg.FillBetweenItem(top, bottom, brush=fill))
        self.plot.line(x, mean, colour, "Mean")


class DistributionTab(ChartTab):
    """The spread of one gene across the population, with a slider to scrub through time."""

    title = "Gene distribution"

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "Share of the population")
        self.kind = self.add_combo(self._kind_changed)
        for kind, text in KIND_NAMES.items():
            self.kind.addItem(text, kind)
        self.gene = self.add_combo(self._gene_changed)
        self.controls.addStretch(1)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(0, 0)
        self.slider.setSingleStep(1)
        self.slider.valueChanged.connect(lambda _value: self.redraw())
        self.when = QLabel(self)
        scrub = QHBoxLayout()
        scrub.addWidget(QLabel("Time:", self))
        scrub.addWidget(self.slider, 1)
        scrub.addWidget(self.when)
        self.layout().addLayout(scrub)  # type: ignore[union-attr]
        self.plot.getPlotItem().setLabel("bottom", "Gene value (0 to 1)")
        self._listed: tuple[str, ...] = ()
        self._days: list[int] = []

    def update_history(self, history: HistorySamples, axis: TimeAxis) -> None:
        self.history, self.axis = history, axis
        self._fill(history)
        self._sync_slider(follow=True)
        self.redraw()

    def _kind_changed(self) -> None:
        if self.history is not None:
            self._fill(self.history)
            self._sync_slider(follow=True)
        self.redraw()

    def _gene_changed(self) -> None:
        self._sync_slider(follow=True)
        self.redraw()

    def _fill(self, history: HistorySamples) -> None:
        names = tuple(histogram_names(history, self.kind.currentData()))
        if names == self._listed:
            return
        keep = self.gene.currentData()
        self.gene.blockSignals(True)
        self.gene.clear()
        for name in names:
            self.gene.addItem(pretty_stat(name), name)
        index = self.gene.findData(keep)
        self.gene.setCurrentIndex(index if index >= 0 else (0 if names else -1))
        self.gene.blockSignals(False)
        self._listed = names

    def _sync_slider(self, follow: bool) -> None:
        """Make the slider walk the days that have this gene's distribution. It stays on the newest
        one when it was there, so a running world is followed unless the user scrubbed back."""
        name = self.gene.currentData()
        days = histogram_days(self.history, name) if self.history and name else []
        at_end = self.slider.value() >= self.slider.maximum()
        self._days = days
        self.slider.blockSignals(True)
        self.slider.setEnabled(len(days) > 1)
        self.slider.setRange(0, max(0, len(days) - 1))
        if follow and at_end:
            self.slider.setValue(self.slider.maximum())
        self.slider.blockSignals(False)

    def draw(self, history: HistorySamples, axis: TimeAxis) -> None:
        self.plot.reset()
        name = self.gene.currentData()
        if name is None or not self._days:
            self.when.setText("no distribution recorded yet")
            return
        index = min(self.slider.value(), len(self._days) - 1)
        day = self._days[index]
        counts = history.histogram_at(name, day)
        self.when.setText(f"{axis.text(day)} ({index + 1} of {len(self._days)})")
        if counts is None:
            return
        bins = len(counts)
        shares = histogram_shares(counts)
        centres = (np.arange(bins) + 0.5) / bins
        colour = KIND_COLOURS[self.kind.currentData()]
        bars = pg.BarGraphItem(
            x=centres, height=shares, width=0.9 / bins, brush=_colour(colour), pen=None
        )
        item = self.plot.getPlotItem()
        item.addItem(bars)
        item.setXRange(0, 1, padding=0.02)
        item.setYRange(0, max(float(shares.max()), 0.05) * 1.1, padding=0)

    def fit(self) -> None:
        self.redraw()  # redrawing sets the ranges again


class ChartsPanel(QWidget):
    """The chart tabs over one ``ViewerController``."""

    def __init__(
        self, controller: ViewerController | None = None, parent: QWidget | None = None
    ) -> None:
        """Over a live ``controller``, or with none to show one finished history that is handed
        in with ``set_history`` (the run history window, ``history_view``)."""
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.chart_tabs: list[ChartTab] = [
            tab(self.tabs)
            for tab in (
                PopulationTab,
                FlowsTab,
                ConditionTab,
                LineagesTab,
                SpeciesTab,
                TraitTab,
                DistributionTab,
            )
        ]
        for tab in self.chart_tabs:
            self.tabs.addTab(tab, tab.title)
        self.status = QLabel(self)
        reset = QPushButton("Reset view", self)
        reset.setToolTip("Fit the chart to all of its data again")
        reset.clicked.connect(self.reset_view)
        footer = QHBoxLayout()
        footer.addWidget(self.status, 1)
        footer.addWidget(reset)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(footer)

        self._history: HistorySamples | None = None
        self._dirty = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REDRAW_MS)
        self._timer.timeout.connect(self._flush)
        self.tabs.currentChanged.connect(lambda _index: self.refresh())

        if controller is not None:
            controller.history_received.connect(self.set_history)
            controller.backend_replaced.connect(self._on_backend_replaced)
            self._history = controller.history  # a panel built late starts from the latest
        self.refresh()

    @property
    def current(self) -> ChartTab:
        return self.chart_tabs[self.tabs.currentIndex()]

    def set_history(self, history: HistorySamples) -> None:
        """Take the newest history; the charts are redrawn soon, but not more than a few times a
        second however fast the world is running."""
        self._history = history
        self.mark_dirty()

    def _on_backend_replaced(self, _backend) -> None:
        """A different run is shown (a resumed one): drop the old run's history until the new one's
        arrives with the next poll."""
        self._history = None if self.controller is None else self.controller.history
        self.mark_dirty()

    def mark_dirty(self) -> None:
        self._dirty = True
        if not self._timer.isActive():
            self._timer.start()

    def _flush(self) -> None:
        if self._dirty and self.isVisible():
            self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        """Redraw the tab in view from the newest history, now."""
        self._dirty = False
        history = self._history
        if history is None or history.latest is None:
            self.status.setText("No history yet: the first sample comes after one simulated day.")
            return
        axis = time_axis(history)
        self.current.update_history(history, axis)
        count = len(history)
        self.status.setText(
            f"{count} sample{'s' if count != 1 else ''}, up to {axis.text(history.latest.day)}"
        )

    def reset_view(self) -> None:
        self.current.fit()


def history_view(history: HistorySamples, parent: QWidget | None = None) -> ChartsPanel:
    """The charts over one finished history, read only, for the run history window (UX.18)."""
    panel = ChartsPanel(None, parent)
    panel.set_history(history)
    panel.refresh()
    return panel


def build(context: ViewerContext) -> ChartsPanel:
    return ChartsPanel(context.controller)


PANEL = PanelSpec(id="charts", title="Charts", area="right", factory=build, order=20)
