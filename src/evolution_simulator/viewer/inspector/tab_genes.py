"""The Genes tab (UX.14): the genome as named genes, grouped by cluster, each against the
population's average."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.history import HistorySamples
from evolution_simulator.viewer.inspector import describe
from evolution_simulator.viewer.inspector.tabs import TabPage, TabSpec
from evolution_simulator.viewer.inspector.widgets import MeterRow
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.world.views import AnimalDetail

LEGEND = (
    "Each bar is the gene's level, 0 to 1. The tick is the average of the animals alive; an orange "
    "bar is far from that average (more than two standard deviations)."
)
NOT_NAMEABLE = "This genome is not one the animal layout describes, so its genes cannot be named."


class GeneRowWidget(MeterRow):
    """One gene: name, bar, value, and (when asked) its raw digits."""

    def __init__(self, parent: QWidget, row: describe.GeneRow) -> None:
        super().__init__(parent, row.name, row.meaning)
        self.digits = QLabel("", self)
        self.digits.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.layout().addWidget(self.digits)
        self.digits.hide()


class GeneList(QWidget):
    """The gene rows in their groups, made once for a genome and filled in as it changes."""

    def __init__(self, parent: QWidget, genes: describe.Genes) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.rows: dict[str, GeneRowWidget] = {}
        for group in genes.groups:
            layout.addWidget(QLabel(f"<b>{group.title}</b>", self))
            for row in group.rows:
                widget = GeneRowWidget(self, row)
                self.rows[row.id] = widget
                layout.addWidget(widget)
        self.brain_label = QLabel("", self)
        self.brain_digits = QPlainTextEdit(self)
        self.brain_digits.setReadOnly(True)
        self.brain_digits.setMaximumHeight(110)
        self.brain_digits.hide()
        layout.addWidget(QLabel("<b>Brain</b>", self))
        layout.addWidget(self.brain_label)
        layout.addWidget(self.brain_digits)
        self.signature = tuple((g.cluster, tuple(r.id for r in g.rows)) for g in genes.groups)

    def fill(self, genes: describe.Genes, raw: bool) -> None:
        for group in genes.groups:
            for row in group.rows:
                widget = self.rows[row.id]
                widget.set(row.level, row.text, row.population, row.unusual)
                widget.digits.setText(row.digits)
                widget.digits.setVisible(raw)
        count = len(genes.brain_digits)
        self.brain_label.setText(
            f"The wiring of its network: {count:,} digits." if count else "No brain genes."
        )
        if self.brain_digits.toPlainText() != genes.brain_digits:
            self.brain_digits.setPlainText(genes.brain_digits)
        self.brain_digits.setVisible(raw and count > 0)


class GenesTab(TabPage):
    def __init__(self, context: ViewerContext, parent: QWidget) -> None:
        super().__init__(parent)
        self.context = context
        self.genome = ""
        self.genes: describe.Genes | None = None
        self.population: dict[str, tuple[float, float]] = {}
        self.list: GeneList | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.legend = QLabel(LEGEND, self)
        self.legend.setWordWrap(True)
        self.raw_box = QCheckBox("Show the raw digits", self)
        self.raw_box.setToolTip("Each gene's digits (base 4), as they are stored in the genome")
        self.raw_box.toggled.connect(self._refill)
        self.message = QLabel("", self)
        self.message.setWordWrap(True)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.holder = QWidget(self.scroll)
        self.holder_layout = QVBoxLayout(self.holder)
        self.scroll.setWidget(self.holder)
        for widget in (self.legend, self.raw_box, self.message, self.scroll):
            outer.addWidget(widget)

    def show_history(self, history: HistorySamples) -> None:
        population = describe.population_genes(history)
        if population != self.population:
            self.population = population
            self._read()

    def show_detail(self, detail: AnimalDetail | None) -> None:
        genome = "" if detail is None else detail.genome
        if genome != self.genome:
            self.genome = genome
            self._read()

    def _read(self) -> None:
        self.genes = describe.read_genes(self.genome, self.population) if self.genome else None
        self._refill()

    def _refill(self) -> None:
        genes = self.genes
        self.message.setText("" if genes is not None or not self.genome else NOT_NAMEABLE)
        self.message.setVisible(bool(self.message.text()))
        self.scroll.setVisible(genes is not None)
        if genes is None:
            return
        signature = tuple((g.cluster, tuple(r.id for r in g.rows)) for g in genes.groups)
        if self.list is None or self.list.signature != signature:
            if self.list is not None:
                self.list.hide()
                self.list.setParent(None)
                self.list.deleteLater()
            self.list = GeneList(self.holder, genes)
            self.holder_layout.addWidget(self.list)
        self.list.fill(genes, self.raw_box.isChecked())


TAB = TabSpec(id="genes", title="Genes", factory=GenesTab, order=20)
