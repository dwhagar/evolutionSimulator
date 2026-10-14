"""The main window (UX.11): dock slots, a menu bar, a status bar and a layout that is remembered.

The window knows no screen by name. It builds each ``PanelSpec`` it is given (by default what
``discover_panels()`` finds) into its slot: ``center`` is the central widget, the other areas are
dock widgets the user can drag, float, close and bring back from the View menu. The actions of the
Run menu are kept in ``window.actions`` and handed to the panels in their ``ViewerContext``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from evolution_simulator import __version__
from evolution_simulator.session import MAX_SPEED, Frame, Pause, Play, SetSpeed, Status, Step
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.registry import Area, PanelSpec, ViewerContext, discover_panels
from evolution_simulator.world.timescale import SPEED_PRESETS, format_duration

log = logging.getLogger(__name__)

APP_NAME = "Evolution Simulator"
LAYOUT_VERSION = 1
"""Bump when the default docks change in a way an old saved layout would get wrong."""
DEFAULT_SIZE = (1280, 800)

_DOCK_AREAS: dict[Area, Qt.DockWidgetArea] = {
    "left": Qt.DockWidgetArea.LeftDockWidgetArea,
    "right": Qt.DockWidgetArea.RightDockWidgetArea,
    "top": Qt.DockWidgetArea.TopDockWidgetArea,
    "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
}


def format_speed(status: Status) -> str:
    """The speed asked and, while running, the speed got, for the status bar."""
    if status.speed_asked is None:
        asked = "as fast as possible"
    elif status.speed_preset is not None:
        asked = f"{status.speed_preset}/s"
    else:
        asked = f"{format_duration(status.speed_asked)}/s"
    text = f"Speed {asked}"
    if status.running and status.speed_achieved is not None:
        text += f", got {format_duration(status.speed_achieved)}/s"
        if status.behind:
            text += " (behind)"
    return text


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: ViewerController,
        *,
        run_label: str | None = None,
        settings: QSettings | None = None,
        specs: Sequence[PanelSpec] | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.settings = (
            settings if settings is not None else QSettings("evolutionSimulator", "viewer")
        )
        self.run_label = run_label
        self.actions: dict[str, QAction] = {}
        self.docks: dict[str, QDockWidget] = {}
        self.panels: dict[str, QWidget] = {}
        self._speed_actions: dict[str, QAction] = {}

        self.setWindowTitle(APP_NAME if run_label is None else f"{APP_NAME} - {run_label}")
        self.resize(*DEFAULT_SIZE)
        self._build_status_bar()
        self._build_actions()
        self._build_menus()

        context = ViewerContext(controller, self.actions, self.statusBar().showMessage)
        self._build_panels(discover_panels() if specs is None else list(specs), context)
        self._default_state = self.saveState(LAYOUT_VERSION)
        self._restore_layout()

        controller.frame_received.connect(self._on_frame)
        controller.status_changed.connect(self._on_status)
        controller.command_failed.connect(lambda text: self.statusBar().showMessage(text, 8000))
        controller.backend_failed.connect(self._on_backend_failed)
        self._on_status(controller.status)
        if controller.frame is not None:
            self._on_frame(controller.frame)

    # -------------------------------------------------------------------------
    # Building
    # -------------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self.status_labels = {name: QLabel() for name in ("run", "clock", "counts", "speed")}
        for label in self.status_labels.values():
            bar.addPermanentWidget(label)
        self.status_labels["run"].setText(self.run_label or "")
        self.status_labels["clock"].setText("Waiting for the simulation")

    def _action(
        self, name: str, text: str, slot, shortcut: str | QKeySequence.StandardKey | None = None
    ) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        self.actions[name] = action
        return action

    def _build_actions(self) -> None:
        self._action("quit", "&Quit", self.close, QKeySequence.StandardKey.Quit)
        self._action("play_pause", "&Play", self._toggle_running, "Space")
        self._action("step", "&Step", lambda: self.controller.send(Step(1)), "Right")
        group = QActionGroup(self)
        group.setExclusive(True)
        for speed in (*SPEED_PRESETS, MAX_SPEED):
            label = "As fast as possible" if speed == MAX_SPEED else f"1 {speed} a second"
            action = self._action(
                f"speed_{speed}", label, lambda _=False, s=speed: self.controller.send(SetSpeed(s))
            )
            action.setCheckable(True)
            group.addAction(action)
            self._speed_actions[speed] = action
        self._action("reset_layout", "&Reset layout", self.reset_layout)
        self._action("about", "&About", self._about)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        self.file_menu = bar.addMenu("&File")
        self.file_menu.addAction(self.actions["quit"])
        self.run_menu = bar.addMenu("&Run")
        self.run_menu.addAction(self.actions["play_pause"])
        self.run_menu.addAction(self.actions["step"])
        self.run_menu.addSeparator()
        speed_menu = self.run_menu.addMenu("S&peed")
        for action in self._speed_actions.values():
            speed_menu.addAction(action)
        self.view_menu = bar.addMenu("&View")
        self.help_menu = bar.addMenu("&Help")
        self.help_menu.addAction(self.actions["about"])

    def _build_panels(self, specs: list[PanelSpec], context: ViewerContext) -> None:
        centre = [spec for spec in specs if spec.area == "center"]
        if len(centre) > 1:
            raise ValueError("Only one panel can take the centre slot.")
        for spec in specs:
            widget = self._make_widget(spec, context)
            self.panels[spec.id] = widget
            if spec.area == "center":
                self.setCentralWidget(widget)
                continue
            dock = QDockWidget(spec.title, self)
            dock.setObjectName(f"dock-{spec.id}")
            dock.setWidget(widget)
            self.addDockWidget(_DOCK_AREAS[spec.area], dock)
            self.docks[spec.id] = dock
            self.view_menu.addAction(dock.toggleViewAction())
            if not spec.visible:
                dock.hide()
        if not centre:
            self.setCentralWidget(QWidget())
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.actions["reset_layout"])
        self._size_docks()

    def _make_widget(self, spec: PanelSpec, context: ViewerContext) -> QWidget:
        try:
            return spec.factory(context)
        except Exception as error:
            log.exception("The panel %s could not be built", spec.id)
            label = QLabel(
                f"The {spec.title} panel failed to start:\n{type(error).__name__}: {error}"
            )
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return label

    def _size_docks(self) -> None:
        sides = [d for d, s in self.docks.items() if self.dockWidgetArea(s) == _DOCK_AREAS["right"]]
        if sides:
            self.resizeDocks(
                [self.docks[i] for i in sides], [420] * len(sides), Qt.Orientation.Horizontal
            )
        tops = [d for d, s in self.docks.items() if self.dockWidgetArea(s) == _DOCK_AREAS["top"]]
        if tops:
            self.resizeDocks(
                [self.docks[i] for i in tops], [60] * len(tops), Qt.Orientation.Vertical
            )

    # -------------------------------------------------------------------------
    # The layout
    # -------------------------------------------------------------------------

    def _restore_layout(self) -> None:
        geometry = self.settings.value("window/geometry")
        state = self.settings.value("window/state")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        if isinstance(state, QByteArray):
            self.restoreState(state, LAYOUT_VERSION)

    def save_layout(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState(LAYOUT_VERSION))
        self.settings.sync()

    def reset_layout(self) -> None:
        """Put every dock back where the window first had it, and forget the saved layout."""
        for dock in self.docks.values():
            dock.setFloating(False)
        self.restoreState(self._default_state, LAYOUT_VERSION)
        self.resize(*DEFAULT_SIZE)
        self.settings.remove("window")

    def closeEvent(self, event: QCloseEvent) -> None:
        self.controller.stop()
        self.save_layout()
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Following the simulation
    # -------------------------------------------------------------------------

    def _toggle_running(self) -> None:
        self.controller.send(Pause() if self.controller.status.running else Play())

    def _on_frame(self, frame: Frame) -> None:
        labels = self.status_labels
        labels["clock"].setText(
            f"{frame.elapsed}  |  {'Night' if frame.is_night else 'Day'} {frame.day}"
            f"  |  Tick {frame.tick:,}"
        )
        labels["counts"].setText(f"Animals {frame.animal_count:,}  Plants {frame.plant_count:,}")
        labels["speed"].setText(format_speed(frame.status))

    def _on_status(self, status: Status) -> None:
        self.actions["play_pause"].setText("&Pause" if status.running else "&Play")
        for speed, action in self._speed_actions.items():
            action.setChecked(speed == status.speed_preset)
        self.status_labels["speed"].setText(format_speed(status))

    def _on_backend_failed(self, text: str) -> None:
        self.statusBar().showMessage(f"The simulation stopped: {text}")
        for name in ("play_pause", "step", *(f"speed_{s}" for s in self._speed_actions)):
            self.actions[name].setEnabled(False)

    def _about(self) -> None:
        box = QMessageBox(self)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setText(f"<b>{APP_NAME}</b><br>Version {__version__}")
        box.setInformativeText("An evolution simulator. Released under CC0 1.0.")
        box.open()
