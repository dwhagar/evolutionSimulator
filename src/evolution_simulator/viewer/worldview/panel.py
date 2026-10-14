"""The world view with its toolbar (UX.12): what ``viewer/panels/world.py`` puts in the centre slot.

The toolbar has the colour mode, the layers that can be switched, "Fit" and a screenshot button. A
click on the canvas selects the animal under it through the ``Select`` command (``Deselect`` for a
click on bare ground); the selected animal is whichever the session says is selected, so the ring
follows the inspector and the other way round.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.session import Deselect, Frame, Select, Status
from evolution_simulator.viewer.panels.controls import KEY_MAP, NO_DRAW, world_drawing_paused
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.viewer.worldview import palette
from evolution_simulator.viewer.worldview.canvas import WorldCanvas

FOLLOW = "follow_selected"
"""Name of the checkable action (key ``F``) that keeps the selected creature in the middle."""

LAYERS = (
    ("show_plants", "Plants", True),
    ("show_corpses", "Corpses", True),
    ("show_animals", "Animals", True),
    ("show_grid", "Grid", False),
)


class WorldPanel(QWidget):
    def __init__(self, context: ViewerContext, canvas: WorldCanvas | None = None) -> None:
        super().__init__()
        self.context = context
        # Every widget gets its parent when it is made, so no Python wrapper is left believing it
        # owns something the panel also owns (freed twice, the heap is corrupted).
        self.canvas = canvas if canvas is not None else WorldCanvas(parent=self)
        self.canvas.setParent(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        layout.addLayout(bar)
        layout.addWidget(self.canvas, 1)

        bar.addWidget(QLabel("Colour by", self))
        self.mode_box = QComboBox(self)
        # Built by hand and kept, not read back with ``model().item(row)``: PySide6 hands that
        # item to Python as an owner, and freeing it twice corrupts the heap.
        self.mode_model = QStandardItemModel(self.mode_box)
        self.mode_items: dict[str, QStandardItem] = {}
        for mode in palette.MODES:
            item = QStandardItem(mode.label)
            item.setData(mode.id, Qt.ItemDataRole.UserRole)
            self.mode_model.appendRow(item)
            self.mode_items[mode.id] = item
        self.mode_box.setModel(self.mode_model)
        self.mode_box.currentIndexChanged.connect(self._on_mode)
        bar.addWidget(self.mode_box)
        self.layer_boxes: dict[str, QCheckBox] = {}
        for name, label, shown in LAYERS:
            box = QCheckBox(label, self)
            box.setChecked(shown)
            box.toggled.connect(lambda on, name=name: self.canvas.set_option(name, on))
            self.layer_boxes[name] = box
            bar.addWidget(box)
        bar.addStretch(1)
        self.fit_button = QPushButton("Fit", self)
        self.fit_button.setToolTip("Show the whole world (or double-click it)")
        self.fit_button.clicked.connect(self.canvas.fit_view)
        bar.addWidget(self.fit_button)
        self.shot_button = QPushButton("Screenshot…", self)
        self.shot_button.clicked.connect(self.save_screenshot)
        bar.addWidget(self.shot_button)

        self.follow_action = self._make_follow_action()
        self.canvas.animal_clicked.connect(self._on_click)
        self._attached = False
        self._no_draw_connected = False
        controller = context.controller
        controller.frame_received.connect(self._on_frame)
        controller.status_changed.connect(self._on_status)
        if controller.frame is not None:
            self._on_frame(controller.frame)

    def _make_follow_action(self) -> QAction:
        actions = self.context.actions
        if FOLLOW in actions:
            return actions[FOLLOW]
        action = QAction("&Follow selected creature", self)
        action.setCheckable(True)
        action.setToolTip("Keep the selected creature in the middle of the view")
        action.setShortcuts([QKeySequence(key) for key in KEY_MAP[FOLLOW]])
        action.toggled.connect(self.canvas.set_follow)
        self.canvas.follow_changed.connect(action.setChecked)
        actions[FOLLOW] = action
        return action

    def _attach(self) -> None:
        """Put the follow key on the main window (and in its View menu), so it works whichever
        panel has the focus."""
        if self._attached:
            return
        window = self.parentWidget()
        while window is not None and not isinstance(window, QMainWindow):
            window = window.parentWidget()
        if window is None:
            return
        self._attached = True
        window.addAction(self.follow_action)
        view_menu = getattr(window, "view_menu", None)
        if view_menu is not None:
            separator = next((a for a in view_menu.actions() if a.isSeparator()), None)
            view_menu.insertAction(separator, self.follow_action)

    def event(self, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.ParentChange, QEvent.Type.Show):
            self._attach()
        return super().event(event)

    def _refresh_drawing(self, status: Status) -> None:
        """Stop painting while the controls' "don't draw when fast" switch says so."""
        action = self.context.actions.get(NO_DRAW)
        if action is not None and not self._no_draw_connected:
            self._no_draw_connected = True
            action.toggled.connect(
                lambda _on: self._refresh_drawing(self.context.controller.status)
            )
        self.canvas.set_drawing(not world_drawing_paused(self.context.actions, status))

    def _on_frame(self, frame: Frame) -> None:
        self._refresh_drawing(frame.status)
        self.canvas.set_frame(frame, self.context.controller.plants)
        available = {mode.id for mode in self.canvas.available_modes()}
        for mode_id, item in self.mode_items.items():
            item.setEnabled(mode_id in available)
            item.setToolTip("" if mode_id in available else "This frame has no family key")
        if self.mode_box.currentData() != self.canvas.colour_mode:  # the canvas fell back
            self.mode_box.setCurrentIndex(self.mode_box.findData(self.canvas.colour_mode))

    def _on_status(self, status: Status) -> None:
        self._refresh_drawing(status)
        self.canvas.set_selected(status.selected)

    def _on_mode(self, index: int) -> None:
        self.canvas.set_colour_mode(self.mode_box.itemData(index))

    def _on_click(self, animal_id: int | None) -> None:
        self.context.send(Deselect() if animal_id is None else Select(animal_id))

    def save_screenshot(self) -> None:
        frame = self.canvas.frame
        stem = f"world-tick{frame.tick}" if frame is not None else "world"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save screenshot",
            f"{stem}-{datetime.now().astimezone():%H%M%S}.png",
            "PNG image (*.png)",
        )
        if not path:
            return
        if self.canvas.save_screenshot(path):
            self.context.show_message(f"Saved {path}")
        else:
            self.context.show_message(f"Could not save {path}")
