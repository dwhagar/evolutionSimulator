"""The creature inspector panel (UX.14): a header and the tabs of ``tab_*.py``.

The selected creature is whichever the session says is selected (``status.selected``); its details
arrive on ``controller.detail_received``. When the creature dies, the details arrive once more
marked dead and stay on screen until another creature is chosen or ``Esc`` clears the panel. A
creature that is no longer selected for any other reason (a click on bare ground) clears it.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.history import HistorySamples
from evolution_simulator.session import Deselect, Frame, Status
from evolution_simulator.viewer.inspector import describe
from evolution_simulator.viewer.inspector.tabs import TabPage, TabSpec, discover_tabs
from evolution_simulator.viewer.panels.controls import KEY_MAP
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.world.views import AnimalDetail

DESELECT = "deselect"
"""Name of the action (key ``Esc``) that clears the selection."""

EMPTY_TEXT = "Nothing selected.\nClick a creature in the world to see it here."


class InspectorPanel(QWidget):
    def __init__(self, context: ViewerContext, specs: list[TabSpec] | None = None) -> None:
        super().__init__()
        self.context = context
        self.detail: AnimalDetail | None = None
        self.tick_seconds: float | None = None
        self._clear_pending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack)

        self.empty = QLabel(EMPTY_TEXT, self.stack)
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.empty)

        self.page = QWidget(self.stack)
        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        page_layout.addLayout(head)
        self.header = QLabel("", self.page)
        self.header.setWordWrap(True)
        self.deselect_button = QPushButton("Deselect", self.page)
        self.deselect_button.setToolTip("Stop following this creature's details (Esc)")
        head.addWidget(self.header, 1)
        head.addWidget(self.deselect_button)
        self.tabs = QTabWidget(self.page)
        page_layout.addWidget(self.tabs)
        self.stack.addWidget(self.page)

        self.pages: dict[str, TabPage] = {}
        for spec in specs if specs is not None else discover_tabs():
            tab = spec.factory(context, self.tabs)
            self.pages[spec.id] = tab
            self.tabs.addTab(tab, spec.title)

        self.deselect_action = self._make_action()
        self.deselect_button.clicked.connect(self.deselect_action.trigger)
        controller = context.controller
        controller.detail_received.connect(self._on_detail)
        controller.status_changed.connect(self._on_status)
        controller.frame_received.connect(self._on_frame)
        controller.history_received.connect(self._on_history)
        controller.backend_replaced.connect(lambda _backend: self.clear())
        if controller.history is not None:
            self._on_history(controller.history)
        if controller.frame is not None:
            self._on_frame(controller.frame)
        if controller.detail is not None:
            self._on_detail(controller.detail)
        self._show()

    # -- the Esc key

    def _make_action(self) -> QAction:
        actions = self.context.actions
        if DESELECT in actions:
            return actions[DESELECT]
        action = QAction("&Deselect creature", self)
        action.setToolTip("Stop following the selected creature's details")
        action.setShortcuts([QKeySequence(key) for key in KEY_MAP[DESELECT]])
        action.triggered.connect(self.deselect)
        actions[DESELECT] = action
        self.context.add_menu_action("view", action)
        return action

    def deselect(self) -> None:
        """Esc: clear the panel and tell the session to stop sending details."""
        self.context.send(Deselect())
        self.clear()

    def clear(self) -> None:
        self.detail = None
        self._clear_pending = False
        for page in self.pages.values():
            page.show_detail(None)
        self._show()

    # -- what the controller says

    def _on_frame(self, frame: Frame) -> None:
        self.tick_seconds = describe.seconds_per_tick(frame)
        for page in self.pages.values():
            page.show_frame(frame)

    def _on_history(self, history: HistorySamples) -> None:
        for page in self.pages.values():
            page.show_history(history)

    def _on_status(self, status: Status) -> None:
        selected = status.selected
        if selected is None:
            # A creature that died sends its last details after this; wait for them.
            if self.detail is not None and self.detail.alive and not self._clear_pending:
                self._clear_pending = True
                QTimer.singleShot(0, self._settle)
        else:
            self._clear_pending = False
            if self.detail is not None and self.detail.id != selected:
                self.clear()
        self._show()

    def _settle(self) -> None:
        if self._clear_pending:
            self.clear()

    def _on_detail(self, detail: AnimalDetail) -> None:
        self.detail = detail
        if not detail.alive:
            self._clear_pending = False
        for page in self.pages.values():
            page.show_detail(detail)
        self._show()

    # -- showing it

    def _show(self) -> None:
        detail = self.detail
        self.stack.setCurrentWidget(self.page if detail is not None else self.empty)
        selected = self.context.controller.status.selected
        self.deselect_action.setEnabled(detail is not None or selected is not None)
        if detail is None:
            return
        self.header.setText(self._header_text(detail))
        self.deselect_button.setText("Clear" if not detail.alive else "Deselect")

    @staticmethod
    def _header_text(detail: AnimalDetail) -> str:
        sex = describe.sex_name(detail.sex)
        if not detail.alive:
            return f"<b>Animal #{detail.id}</b> ({sex}) - dead: {describe.death_text(detail.death_cause)}"
        return f"<b>Animal #{detail.id}</b> - {sex}, {describe.life_stage(detail.age_ratio)}"
