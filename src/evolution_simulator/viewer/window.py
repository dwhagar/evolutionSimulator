"""The main window (UX.11): dock slots, a menu bar, a status bar and a layout that is remembered.

The window knows no screen by name. It builds each ``PanelSpec`` it is given (by default what
``discover_panels()`` finds) into its slot: ``center`` is the central widget, the other areas are
dock widgets the user can drag, float, close and bring back from the View menu. The actions of the
Run menu are kept in ``window.actions`` and handed to the panels in their ``ViewerContext``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QWidget,
)

from evolution_simulator.session import MAX_SPEED, Frame, Pause, Play, SetSpeed, Status, Step
from evolution_simulator.viewer import theme
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.help import AboutDialog, ShortcutsDialog
from evolution_simulator.viewer.registry import (
    Area,
    MenuName,
    PanelSpec,
    ViewerContext,
    discover_panels,
)
from evolution_simulator.world.timescale import SPEED_PRESETS, format_duration

log = logging.getLogger(__name__)

APP_NAME = "Evolution Simulator"
THEME_KEY = "appearance/theme"
"""Where the theme is kept in the settings (not under ``window``, which Reset layout clears)."""
LAYOUT_VERSION = 1
"""Bump when the default docks change in a way an old saved layout would get wrong."""
DEFAULT_SIZE = (1280, 800)

_DOCK_AREAS: dict[Area, Qt.DockWidgetArea] = {
    "left": Qt.DockWidgetArea.LeftDockWidgetArea,
    "right": Qt.DockWidgetArea.RightDockWidgetArea,
    "top": Qt.DockWidgetArea.TopDockWidgetArea,
    "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
}


def tidy_message(text: str) -> str:
    """A status message as a sentence: first letter capital, ending in a full stop unless it
    already ends in a mark."""
    text = " ".join(text.split())
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?:…" else text + "."


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
        self.crash_box: QMessageBox | None = None
        self.about_dialog: AboutDialog | None = None
        self.shortcuts_dialog: ShortcutsDialog | None = None
        self._theme_actions: dict[str, QAction] = {}
        """The dialog shown when the simulation process fails, while it is open."""
        self.close_guards: list[Callable[[], bool]] = []
        """Asked in turn when the window closes; any that returns ``False`` keeps it open."""
        self.ask_before_close = True
        """``False`` closes without asking (a smoke test that closes the window itself)."""

        self.setWindowTitle(APP_NAME if run_label is None else f"{APP_NAME} - {run_label}")
        self.resize(*DEFAULT_SIZE)
        self._build_status_bar()
        self._build_actions()
        self._build_menus()
        self.set_theme(self.saved_theme(), save=False)

        context = ViewerContext(
            controller,
            self.actions,
            self.show_message,
            self.add_menu_action,
            self.set_run_label,
            self.settings,
            self.close_guards.append,
        )
        self._build_panels(discover_panels() if specs is None else list(specs), context)
        self._default_state = self.saveState(LAYOUT_VERSION)
        self._restore_layout()

        controller.frame_received.connect(self._on_frame)
        controller.status_changed.connect(self._on_status)
        controller.command_failed.connect(lambda text: self.show_message(text, 8000))
        controller.backend_failed.connect(self._on_backend_failed)
        controller.backend_replaced.connect(self._on_backend_replaced)
        controller.backend_crashed.connect(self._on_backend_crashed)
        self._on_status(controller.status)
        if controller.frame is not None:
            self._on_frame(controller.frame)

    # -------------------------------------------------------------------------
    # Building
    # -------------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self.status_labels = {name: QLabel(bar) for name in ("run", "clock", "counts", "speed")}
        tips = {
            "run": "The run on screen",
            "clock": "Simulated time, day or night, and the tick",
            "counts": "Creatures alive now",
            "speed": "The speed asked for and the speed the simulation is reaching",
        }
        for name, label in self.status_labels.items():
            label.setToolTip(tips[name])
            bar.addPermanentWidget(label)
        self.status_labels["run"].setText(self.run_label or "")
        self.status_labels["clock"].setText(self._waiting_text())

    def _waiting_text(self) -> str:
        return (
            "Starting the simulation" if self.controller.starting else "Waiting for the simulation"
        )

    def _action(
        self,
        name: str,
        text: str,
        slot,
        shortcut: str | QKeySequence.StandardKey | None = None,
        tip: str = "",
    ) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setStatusTip(tip)
            action.setToolTip(tip)
        self.actions[name] = action
        return action

    def _build_actions(self) -> None:
        self._action("quit", "&Quit", self.close, QKeySequence.StandardKey.Quit, "Close the window")
        self._action(
            "play_pause", "&Play", self._toggle_running, "Space", "Run or pause the simulation"
        )
        self._action(
            "step",
            "&Step",
            lambda: self.controller.send(Step(1)),
            "Right",
            "Run one tick, then pause",
        )
        group = QActionGroup(self)
        group.setExclusive(True)
        for speed in (*SPEED_PRESETS, MAX_SPEED):
            label = "As fast as possible" if speed == MAX_SPEED else f"1 {speed} a second"
            action = self._action(
                f"speed_{speed}",
                label,
                lambda _=False, s=speed: self.controller.send(SetSpeed(s)),
                tip="Set the simulation speed",
            )
            action.setCheckable(True)
            group.addAction(action)
            self._speed_actions[speed] = action
        self._action(
            "reset_layout",
            "&Reset layout",
            self.reset_layout,
            tip="Put the panels back where they started",
        )
        for mode in theme.THEMES:
            action = self._action(
                f"theme_{mode}",
                theme.THEME_TEXT[mode],
                lambda _=False, m=mode: self.set_theme(m),
                tip="Change the colours of the window",
            )
            action.setCheckable(True)
            self._theme_actions[mode] = action
        self._action(
            "shortcuts",
            "&Keyboard shortcuts",
            self.show_shortcuts,
            "F1",
            "List the keys and mouse actions",
        )
        self._action("about", "&About", self.show_about, tip="Version, licence and notices")

    def _build_menus(self) -> None:
        bar = self.menuBar()
        self.file_menu = bar.addMenu("&File")
        self._file_end = self.file_menu.addSeparator()
        self.file_menu.addAction(self.actions["quit"])
        self.run_menu = bar.addMenu("&Run")
        self.run_menu.addAction(self.actions["play_pause"])
        self.run_menu.addAction(self.actions["step"])
        self.run_menu.addSeparator()
        speed_menu = self.run_menu.addMenu("S&peed")
        for action in self._speed_actions.values():
            speed_menu.addAction(action)
        self.view_menu = bar.addMenu("&View")
        self.theme_menu = QMenu("&Theme", self.view_menu)
        group = QActionGroup(self.theme_menu)
        group.setExclusive(True)
        for action in self._theme_actions.values():
            group.addAction(action)
            self.theme_menu.addAction(action)
        self.help_menu = bar.addMenu("&Help")
        self.help_menu.addAction(self.actions["shortcuts"])
        self.help_menu.addAction(self.actions["about"])

    def add_menu_action(self, menu: MenuName, action: QAction) -> None:
        """Add an action to a menu (a screen asks through its ``ViewerContext``). In the File menu
        it goes above the separator that sits over Quit."""
        if menu == "file":
            self.file_menu.insertAction(self._file_end, action)
        else:
            {"run": self.run_menu, "view": self.view_menu, "help": self.help_menu}[menu].addAction(
                action
            )

    def show_message(self, text: str, timeout_ms: int = 5000) -> None:
        """Say something on the status bar for a while, as a sentence (see ``tidy_message``)."""
        self.statusBar().showMessage(tidy_message(text), timeout_ms)

    def set_run_label(self, text: str) -> None:
        self.run_label = text or None
        self.status_labels["run"].setText(text)
        self.setWindowTitle(APP_NAME if not text else f"{APP_NAME} - {text}")

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
            self.setCentralWidget(QWidget(self))
        self.view_menu.addSeparator()
        self.view_menu.addMenu(self.theme_menu)
        self.view_menu.addAction(self.actions["reset_layout"])
        self._size_docks()

    def _make_widget(self, spec: PanelSpec, context: ViewerContext) -> QWidget:
        try:
            return spec.factory(context)
        except Exception as error:
            log.exception("The panel %s could not be built", spec.id)
            label = QLabel(
                f"The {spec.title} panel failed to start:\n{type(error).__name__}: {error}", self
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
        if self.ask_before_close and not all(guard() for guard in self.close_guards):
            event.ignore()
            return
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

    def _on_backend_replaced(self, _backend) -> None:
        for name in ("play_pause", "step", *(f"speed_{s}" for s in self._speed_actions)):
            self.actions[name].setEnabled(True)
        self._on_status(self.controller.status)
        labels = self.status_labels
        labels["clock"].setText(self._waiting_text())
        labels["counts"].setText("")

    def _on_backend_crashed(self, report: str) -> None:
        """The simulation process failed: say so, with the traceback a click away, and offer a
        fresh start (from the run's newest checkpoint when it was saved into a run)."""
        self.show_message("The simulation stopped unexpectedly.")
        for name in ("play_pause", "step", *(f"speed_{s}" for s in self._speed_actions)):
            self.actions[name].setEnabled(False)
        box = QMessageBox(self)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(APP_NAME)
        box.setText("The simulation stopped unexpectedly.")
        box.setInformativeText(
            "Restart carries on from the newest saved checkpoint of the run if it was saved, "
            "and otherwise starts the same world again."
        )
        box.setDetailedText(report)
        restart = box.addButton("Restart", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Leave it stopped", QMessageBox.ButtonRole.RejectRole)
        box.finished.connect(lambda _code: self._after_crash_choice(box, restart))
        self.crash_box = box
        box.open()

    def _after_crash_choice(self, box: QMessageBox, restart) -> None:
        if box.clickedButton() is restart and not self.controller.restart():
            self.show_message("This simulation cannot be restarted.")

    def _on_backend_failed(self, text: str) -> None:
        self.show_message(f"The simulation stopped: {text}")
        for name in ("play_pause", "step", *(f"speed_{s}" for s in self._speed_actions)):
            self.actions[name].setEnabled(False)

    # -------------------------------------------------------------------------
    # Themes and help
    # -------------------------------------------------------------------------

    def saved_theme(self) -> str:
        """The theme kept in the settings (``"system"`` when there is none, or it is not one)."""
        value = self.settings.value(THEME_KEY, theme.DEFAULT_THEME)
        return value if value in theme.THEMES else theme.DEFAULT_THEME

    def set_theme(self, mode: str, *, save: bool = True) -> None:
        """Restyle the whole program as ``mode`` ("system", "light" or "dark") and remember it."""
        theme.apply_theme(QApplication.instance(), mode)
        for name, action in self._theme_actions.items():
            action.setChecked(name == mode)
        if save:
            self.settings.setValue(THEME_KEY, mode)
            self.settings.sync()

    def show_shortcuts(self) -> None:
        """The window that lists the keys and the mouse (rebuilt each time, so it is current)."""
        if self.shortcuts_dialog is not None:
            self.shortcuts_dialog.close()
            self.shortcuts_dialog.deleteLater()
        self.shortcuts_dialog = ShortcutsDialog(self, self.actions)
        self.shortcuts_dialog.show()

    def show_about(self) -> None:
        if self.about_dialog is None:
            self.about_dialog = AboutDialog(self)
        self.about_dialog.show()
        self.about_dialog.raise_()
