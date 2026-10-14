"""The read-only history of a saved run (UX.18): its facts, its checkpoints and its charts.

A window of its own, so several runs can be looked at side by side and the live screens are not
touched. The charts come from the charts panel when it offers a ``history_view(samples)`` function
(UX.16 builds the live charts and the same widgets then show a finished run); until then a plain
population chart stands in.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.history import HistorySamples
from evolution_simulator.runs import CheckpointInfo, RunSummary
from evolution_simulator.world.timescale import format_duration

log = logging.getLogger(__name__)

POPULATION_SERIES = (("animals", "Animals", "#d95f02"), ("plants", "Plants", "#1b9e77"))
"""(history value, label, colour) of the stand-in chart."""


def charts_history_view() -> Callable[[HistorySamples], QWidget] | None:
    """``history_view`` of the charts panel when it has one."""
    try:
        module = importlib.import_module("evolution_simulator.viewer.panels.charts")
    except Exception:
        log.exception("The charts panel could not be loaded for the run history")
        return None
    factory = getattr(module, "history_view", None)
    return factory if callable(factory) else None


def population_chart(samples: HistorySamples) -> QWidget:
    """Animals and plants over simulated days, read only (zoom and pan with the mouse)."""
    import pyqtgraph as pg

    plot = pg.PlotWidget()
    plot.setBackground(None)
    plot.showGrid(x=True, y=True, alpha=0.25)
    plot.setLabel("bottom", "Simulated days")
    plot.setLabel("left", "Alive")
    plot.addLegend(offset=(10, 10))
    for name, label, colour in POPULATION_SERIES:
        days, values = samples.series(name)
        if days:
            plot.plot(list(days), list(values), pen=pg.mkPen(colour, width=2), name=label)
    return plot


class RunHistoryWindow(QDialog):
    resume_requested = Signal(str, str)
    """(run id, checkpoint name) when the user asks to carry on from a checkpoint."""

    def __init__(
        self,
        summary: RunSummary,
        samples: HistorySamples | None,
        checkpoints: list[CheckpointInfo],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.summary = summary
        self.setWindowTitle(f"History - {summary.name}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self.resize(760, 640)

        layout = QVBoxLayout(self)
        self.facts = QLabel(self._facts_text(summary, samples))
        self.facts.setTextFormat(Qt.TextFormat.PlainText)
        self.facts.setWordWrap(True)
        layout.addWidget(self.facts)

        self.chart: QWidget | None = None
        if samples is not None and len(samples) > 0:
            factory = charts_history_view() or population_chart
            try:
                self.chart = factory(samples)
            except Exception:
                log.exception("The history charts could not be built; using the plain chart")
                self.chart = population_chart(samples)
            layout.addWidget(self.chart, stretch=1)
        else:
            empty = QLabel("This run has no recorded history yet.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty, stretch=1)

        layout.addWidget(QLabel("Checkpoints (the world can be resumed from any of them):"))
        self.table = QTableWidget(len(checkpoints), 5)
        self.table.setHorizontalHeaderLabels(
            ["Checkpoint", "Simulated time", "Animals", "Plants", "Written"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.checkpoints = checkpoints
        for row, info in enumerate(checkpoints):
            cells = [
                f"tick {info.tick:,}",
                format_duration(info.simulated_seconds),
                f"{info.animals:,}",
                f"{info.plants:,}",
                info.written.replace("T", " ").replace("Z", " UTC"),
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (2, 3):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
        self.table.setMaximumHeight(160)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.resume_button = QPushButton("Resume from the selected checkpoint")
        self.resume_button.setEnabled(False)
        self.resume_button.clicked.connect(self._resume)
        self.table.itemSelectionChanged.connect(
            lambda: self.resume_button.setEnabled(self.selected_checkpoint() is not None)
        )
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(self.resume_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    @staticmethod
    def _facts_text(summary: RunSummary, samples: HistorySamples | None) -> str:
        lines = [
            f"{summary.name}    seed {summary.seed}    made by version {summary.program_version}",
            (
                f"Simulated {summary.elapsed or 'nothing yet'} ({summary.tick:,} ticks), "
                f"{summary.animals:,} animals and {summary.plants:,} plants at the last save."
            ),
            (
                f"Started {summary.created.replace('T', ' ')[:-1]} UTC, last saved "
                f"{summary.updated.replace('T', ' ')[:-1]} UTC, "
                f"{summary.checkpoints} checkpoints kept."
            ),
        ]
        if samples is not None and len(samples) > 0:
            lines.append(f"{len(samples):,} history samples.")
        return "\n".join(lines)

    def selected_checkpoint(self) -> CheckpointInfo | None:
        rows = self.table.selectionModel().selectedRows()
        return self.checkpoints[rows[0].row()] if rows else None

    def _resume(self) -> None:
        info = self.selected_checkpoint()
        if info is not None:
            self.resume_requested.emit(self.summary.id, info.name)
