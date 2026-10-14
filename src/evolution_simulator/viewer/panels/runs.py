"""Saved runs (UX.18): the run list, Save run now, Resume, Delete, and a read-only history view.

A dock (hidden until asked for: File, Saved runs, or the View menu) holding one row per saved run
with its name, seed, program version, simulated time, last save, population, size and a small
population chart. The buttons open a run's history (``_run_history``), resume it (the window then
shows that world, paused), copy its settings into a new run with a fresh seed (*Copy with new seed*,
through the setup screen's ``start_run_from``), export its history as a table, or delete it. File gets Save run now
(Ctrl+S) and Saved runs (Ctrl+O). The size warning (UX.25: 5 GB by default) shows above the list.
All the work is the ``RunManager``'s; this module is the screen.
"""

from __future__ import annotations

import logging
import random
from dataclasses import replace

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.runs import RunError, RunSummary
from evolution_simulator.viewer.panels._run_history import RunHistoryWindow
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext
from evolution_simulator.viewer.run_manager import RunManager, format_ago, format_bytes, parse_utc
from evolution_simulator.world.timescale import format_duration

log = logging.getLogger(__name__)

SEED_LIMIT = 2**32

COLUMNS = (
    "Run",
    "Seed",
    "Version",
    "Simulated",
    "Last saved",
    "Animals",
    "Plants",
    "Size",
    "Population",
)
SPARK_SIZE = (96, 22)
NUMERIC = {"Seed", "Animals", "Plants", "Size"}


def sparkline(values: tuple[float, ...], colour: str = "#d95f02") -> QIcon:
    """A tiny line of a run's animal count across its history."""
    pixmap = QPixmap(*SPARK_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    if len(values) >= 2:
        low, high = min(values), max(values)
        span = (high - low) or 1.0
        width, height = SPARK_SIZE
        points = QPolygonF(
            [
                QPointF(
                    2 + i * (width - 4) / (len(values) - 1),
                    height - 3 - (v - low) / span * (height - 6),
                )
                for i, v in enumerate(values)
            ]
        )
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(colour), 1.5))
        painter.drawPolyline(points)
        painter.end()
    return QIcon(pixmap)


class RunsPanel(QWidget):
    def __init__(self, context: ViewerContext, manager: RunManager) -> None:
        super().__init__()
        self.context = context
        self.manager = manager
        self.rows: list[RunSummary] = []
        self.windows: list[RunHistoryWindow] = []

        layout = QVBoxLayout(self)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #c0392b; font-weight: bold;")
        self.warning.hide()
        self.usage = QLabel()
        layout.addWidget(self.warning)
        layout.addWidget(self.usage)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.setIconSize(QSize(*SPARK_SIZE))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda _item: self.show_history())
        layout.addWidget(self.table, stretch=1)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Save run now")
        self.resume_button = QPushButton("Resume")
        self.history_button = QPushButton("History")
        self.copy_button = QPushButton("Copy with new seed")
        self.copy_button.setToolTip(
            "Start a new run with this run's settings and a different seed."
        )
        self.export_button = QPushButton("Export history (CSV)...")
        self.delete_button = QPushButton("Delete")
        self.refresh_button = QPushButton("Refresh")
        self.save_button.clicked.connect(self.save_now)
        self.resume_button.clicked.connect(lambda: self.resume())
        self.history_button.clicked.connect(lambda: self.show_history())
        self.copy_button.clicked.connect(lambda: self.copy_with_new_seed())
        self.export_button.clicked.connect(lambda: self.export_history())
        self.delete_button.clicked.connect(lambda: self.delete())
        self.refresh_button.clicked.connect(self.refresh)
        for button in (
            self.save_button,
            self.resume_button,
            self.history_button,
            self.copy_button,
            self.export_button,
            self.delete_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.refresh_button)
        layout.addLayout(buttons)

        self._stale = True
        manager.changed.connect(self._on_changed)
        context.controller.backend_replaced.connect(lambda _b: self._update_buttons())
        self._update_buttons()

    def _on_changed(self) -> None:
        """Refresh at once when shown, else when next shown (the list reads every run's size)."""
        if self.isVisible():
            self.refresh()
        else:
            self._stale = True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._stale:
            self.refresh()

    # ---- the list ----------------------------------------------------------------------------

    def refresh(self) -> None:
        self._stale = False
        keep = self.selected_id()
        self.rows = self.manager.list_runs()
        current = self.manager.current_run.id if self.manager.current_run else None
        now = self.manager.store.clock()
        self.table.setRowCount(len(self.rows))
        for row, run in enumerate(self.rows):
            name = f"{run.name}  (on screen)" if run.id == current else run.name
            cells = {
                "Run": name,
                "Seed": str(run.seed),
                "Version": run.program_version,
                "Simulated": format_duration(run.simulated_seconds) if run.tick else "not started",
                "Last saved": self._saved_text(run, now),
                "Animals": f"{run.animals:,}",
                "Plants": f"{run.plants:,}",
                "Size": format_bytes(self.manager.size_of(run)),
                "Population": "",
            }
            for column, title in enumerate(COLUMNS):
                item = QTableWidgetItem(cells[title])
                if title in NUMERIC:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if title == "Run":
                    item.setData(Qt.ItemDataRole.UserRole, run.id)
                    if run.id == current:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                if title == "Population":
                    item.setIcon(sparkline(run.animal_history))
                    item.setToolTip("Animals over the run's recorded history")
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        if keep is not None:
            self.select(keep)
        warning = self.manager.space_warning()
        self.warning.setText(warning or "")
        self.warning.setVisible(warning is not None)
        used = sum(self.manager.size_of(run) for run in self.rows)
        self.usage.setText(
            f"{len(self.rows)} saved run{'s' if len(self.rows) != 1 else ''}, {format_bytes(used)} in "
            f"{self.manager.store.root}"
        )
        self._update_buttons()

    @staticmethod
    def _saved_text(run: RunSummary, now: float) -> str:
        when = parse_utc(run.updated)
        stamp = run.updated.replace("T", " ")[:16] + " UTC"
        return stamp if when is None else f"{stamp} ({format_ago(max(0.0, now - when))})"

    def selected_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def select(self, run_id: str) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == run_id:
                self.table.selectRow(row)
                return

    def _update_buttons(self) -> None:
        picked = self.selected_id() is not None
        for button in (
            self.resume_button,
            self.history_button,
            self.copy_button,
            self.export_button,
            self.delete_button,
        ):
            button.setEnabled(picked)
        self.save_button.setEnabled(self.manager.can_save)
        self.save_button.setToolTip(
            ""
            if self.manager.can_save
            else "This simulation is not a real world, so it cannot be saved."
        )

    # ---- asking -------------------------------------------------------------------------------

    def confirm(self, title: str, text: str) -> bool:
        """Ask a yes or no question; tests replace this."""
        answer = QMessageBox.question(
            self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        return answer == QMessageBox.StandardButton.Yes

    def choose_export_path(self, suggestion: str) -> str | None:
        """Where to write the table; tests replace this."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export history", suggestion, "CSV files (*.csv)"
        )
        return path or None

    def fail(self, text: str) -> None:
        self.context.show_message(text, 10000)

    def ask_to_save(self, never_saved: bool) -> QMessageBox.StandardButton:
        """Ask whether to keep the world on screen as it closes; tests replace this."""
        what = (
            "This world has never been saved."
            if never_saved
            else "This run has gone on since its last checkpoint."
        )
        return QMessageBox.question(
            self,
            "Save this run?",
            f"{what} Save it before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

    def confirm_close(self) -> bool:
        """The window is closing: offer to save a world that would be lost. ``False`` keeps the
        window open (Cancel, or a save that failed)."""
        if not self.manager.unsaved_on_close:
            return True
        answer = self.ask_to_save(self.manager.current_run is None)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_now()
        return answer == QMessageBox.StandardButton.Discard

    # ---- the actions -------------------------------------------------------------------------

    def save_now(self) -> bool:
        try:
            self.manager.save_now()
        except (RunError, OSError) as error:
            self.fail(f"Could not save: {error}")
            return False
        return True

    def resume(self, run_id: str | None = None, checkpoint: str | None = None) -> bool:
        run_id = run_id or self.selected_id()
        if run_id is None:
            return False
        current = self.manager.current_run
        if current is not None and current.id == run_id:
            if not self.confirm(
                "Resume this run",
                "This run is on screen. Resuming goes back to its last saved checkpoint and drops "
                "everything simulated since. Continue?",
            ):
                return False
        elif (
            current is None
            and self.manager.unsaved_progress
            and not self.confirm(
                "Replace the world on screen",
                "The world on screen has never been saved and will be lost. Resume anyway?",
            )
        ):
            return False
        try:
            self.manager.resume(run_id, checkpoint)
        except (RunError, OSError) as error:
            self.fail(f"Could not resume: {error}")
            return False
        return True

    def show_history(self, run_id: str | None = None) -> RunHistoryWindow | None:
        run_id = run_id or self.selected_id()
        summary = next((r for r in self.rows if r.id == run_id), None)
        if summary is None:
            return None
        try:
            window = RunHistoryWindow(
                summary,
                self.manager.history(summary.id),
                self.manager.checkpoints(summary.id),
                self,
            )
        except (RunError, OSError, ValueError, KeyError) as error:
            self.fail(f"Could not open the history: {error}")
            return None
        window.resume_requested.connect(lambda rid, name: self.resume(rid, name))
        window.destroyed.connect(lambda *_: self._forget(window))
        self.windows.append(window)
        window.show()
        return window

    def copy_with_new_seed(self, run_id: str | None = None) -> bool:
        """Start a new run with a run's settings and a different, random seed. The starting
        counts are the run's own when they can still be found, else the setup screen's; the choice
        of seeded founders is not kept with a run, so the setup screen's is used."""
        run_id = run_id or self.selected_id()
        summary = next((r for r in self.rows if r.id == run_id), None)
        start = self.context.services.get("start_run_from")
        if summary is None or start is None:
            return False
        try:
            config = self.manager.run_config(summary.id)
            counts = self.manager.starting_counts(summary.id)
        except (RunError, OSError, ValueError, KeyError) as error:
            self.fail(f"Could not read the run: {error}")
            return False
        seed = random.SystemRandom().randrange(SEED_LIMIT - 1)
        seed += seed >= summary.seed  # any seed but the old one
        animals, plants = counts if counts is not None else (None, None)
        name = None if summary.name == f"seed {summary.seed}" else f"{summary.name}, seed {seed}"
        return start(replace(config, seed=seed), animals, plants, name)

    def _forget(self, window: RunHistoryWindow) -> None:
        if window in self.windows:
            self.windows.remove(window)

    def export_history(self, run_id: str | None = None) -> bool:
        run_id = run_id or self.selected_id()
        if run_id is None:
            return False
        path = self.choose_export_path(f"{run_id}-history.csv")
        if path is None:
            return False
        try:
            rows = self.manager.export_csv(run_id, path)
        except (RunError, OSError) as error:
            self.fail(f"Could not export: {error}")
            return False
        self.context.show_message(f"Wrote {rows:,} history rows to {path}")
        return True

    def delete(self, run_id: str | None = None) -> bool:
        run_id = run_id or self.selected_id()
        summary = next((r for r in self.rows if r.id == run_id), None)
        if summary is None:
            return False
        current = self.manager.current_run
        extra = (
            " It is the run on screen: the world carries on but will no longer be saved."
            if current is not None and current.id == run_id
            else ""
        )
        if not self.confirm(
            "Delete this run",
            f"Delete '{summary.name}' (seed {summary.seed}) and all its checkpoints and history "
            f"for good?{extra}",
        ):
            return False
        try:
            self.manager.delete(run_id)
        except (RunError, OSError) as error:
            self.fail(f"Could not delete: {error}")
            return False
        for window in [w for w in self.windows if w.summary.id == run_id]:
            window.close()
        return True

    def show_dock(self) -> None:
        """Bring the dock this panel sits in to the front (File, Saved runs)."""
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, QDockWidget):
            parent = parent.parentWidget()
        if parent is not None:
            parent.show()
            parent.raise_()
        self.refresh()


def build(context: ViewerContext) -> RunsPanel:
    manager = RunManager.for_controller(context.controller)
    panel = RunsPanel(context, manager)

    save = QAction("&Save run now", panel)
    save.setShortcut(QKeySequence(QKeySequence.StandardKey.Save))
    save.triggered.connect(lambda: panel.save_now())
    show = QAction("Saved &runs...", panel)
    show.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
    show.triggered.connect(panel.show_dock)
    context.actions["save_run"] = save
    context.actions["show_runs"] = show
    context.add_menu_action("file", save)
    context.add_menu_action("file", show)
    context.add_close_guard(panel.confirm_close)

    def update_enabled(*_args) -> None:
        save.setEnabled(manager.can_save)

    manager.changed.connect(update_enabled)
    context.controller.backend_replaced.connect(update_enabled)
    update_enabled()
    manager.label_changed.connect(context.set_run_label)
    manager.message.connect(context.show_message)
    return panel


PANEL = PanelSpec(
    id="runs", title="Saved runs", area="bottom", factory=build, order=60, visible=False
)
