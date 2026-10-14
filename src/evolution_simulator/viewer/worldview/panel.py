"""The world view with its toolbar (UX.12): what ``viewer/panels/world.py`` puts in the centre slot.

The toolbar has the colour mode, the layers that can be switched, "Fit" and a screenshot button. A
click on the canvas selects the animal under it through the ``Select`` command (``Deselect`` for a
click on bare ground); the selected animal is whichever the session says is selected, so the ring
follows the inspector and the other way round.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.session import Deselect, Frame, Select, Status
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.viewer.worldview import palette
from evolution_simulator.viewer.worldview.canvas import WorldCanvas

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
        self.canvas = canvas if canvas is not None else WorldCanvas()
        self.mode_box = QComboBox()
        for mode in palette.MODES:
            self.mode_box.addItem(mode.label, mode.id)
        self.mode_box.currentIndexChanged.connect(self._on_mode)
        self.layer_boxes: dict[str, QCheckBox] = {}
        self.fit_button = QPushButton("Fit")
        self.fit_button.setToolTip("Show the whole world (or double-click it)")
        self.fit_button.clicked.connect(self.canvas.fit_view)
        self.shot_button = QPushButton("Screenshot…")
        self.shot_button.clicked.connect(self.save_screenshot)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Colour by"))
        bar.addWidget(self.mode_box)
        for name, label, shown in LAYERS:
            box = QCheckBox(label)
            box.setChecked(shown)
            box.toggled.connect(lambda on, name=name: self.canvas.set_option(name, on))
            self.layer_boxes[name] = box
            bar.addWidget(box)
        bar.addStretch(1)
        bar.addWidget(self.fit_button)
        bar.addWidget(self.shot_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(bar)
        layout.addWidget(self.canvas, 1)

        self.canvas.animal_clicked.connect(self._on_click)
        controller = context.controller
        controller.frame_received.connect(self._on_frame)
        controller.status_changed.connect(self._on_status)
        if controller.frame is not None:
            self._on_frame(controller.frame)

    def _on_frame(self, frame: Frame) -> None:
        self.canvas.set_frame(frame, self.context.controller.plants)
        available = {mode.id for mode in self.canvas.available_modes()}
        model = self.mode_box.model()
        for row in range(self.mode_box.count()):
            item = model.item(row)
            mode_id = self.mode_box.itemData(row)
            item.setEnabled(mode_id in available)
            if mode_id == "family" and mode_id not in available:
                item.setToolTip("Needs the family colour key in the frame (UX.30)")
        if self.canvas.colour_mode not in available:
            self.mode_box.setCurrentIndex(self.mode_box.findData(palette.DEFAULT_MODE))

    def _on_status(self, status: Status) -> None:
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
