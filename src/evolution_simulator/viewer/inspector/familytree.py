"""The family tree window (UX.39): the selected animal's ancestors above it and its descendants
below, alive and dead, each one a button that selects that animal.

The window is opened by the Family tab. It follows the session's selection: pick another animal (in
the world, in the Family tab or by a button of the tree) and the tree is drawn around that one. The
tree itself is worked out in ``treelayout`` from the ``FamilyView`` in the animal's details.

An animal shows by more than its colour: its fill is its family colour (the same colours the world view
uses for the family mode, so a dead ancestor matches its living kin), a glyph says male or female, a
dagger and a dashed border say it is dead, and the selected one has a thick border. A button is greyed
out and cannot be pressed for an animal that is not in the frame (a dead one, or one not drawn yet).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.session import Frame, Select
from evolution_simulator.viewer.inspector import describe
from evolution_simulator.viewer.inspector.treelayout import MAX_NODES, TreeLayout, build_layout
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.viewer.worldview.layers import Layer
from evolution_simulator.viewer.worldview.palette import FamilyScale
from evolution_simulator.world.views import AnimalDetail, KinView

NODE_W = 92
NODE_H = 30
GAP_X = 12
GAP_Y = 34
MARGIN = 16
MALE_GLYPH = "♂"
FEMALE_GLYPH = "♀"
DEAD_GLYPH = "†"
NEUTRAL = (200, 200, 200)
"""The fill of an animal when the frame has no family key to colour it by."""

LEGEND = (
    f"{MALE_GLYPH} male, {FEMALE_GLYPH} female, {DEAD_GLYPH} dead (dashed border). The colour is the "
    "family colour of the world view: close relatives look alike. Click an animal to select it."
)


GREY = (190, 190, 190)
GREYED = 0.4
"""How far toward grey the colour of an animal that cannot be selected is mixed."""


def mixed(
    rgb: tuple[int, int, int], other: tuple[int, int, int], share: float
) -> tuple[int, int, int]:
    """``rgb`` moved ``share`` of the way to ``other``."""
    return (
        int(rgb[0] + (other[0] - rgb[0]) * share),
        int(rgb[1] + (other[1] - rgb[1]) * share),
        int(rgb[2] + (other[2] - rgb[2]) * share),
    )


def text_colour(rgb: tuple[int, int, int]) -> str:
    """Black or white, whichever reads better on ``rgb``."""
    red, green, blue = (c / 255.0 for c in rgb)
    return "#000000" if 0.2126 * red + 0.7152 * green + 0.0722 * blue > 0.45 else "#ffffff"


class NodeButton(QPushButton):
    """One animal of the tree. The style is set only when it changes."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.animal_id: int | None = None
        self.style_key: tuple | None = None
        self.setFixedSize(NODE_W, NODE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide()

    def show_kin(
        self,
        kin: KinView,
        rgb: tuple[int, int, int],
        enabled: bool,
        centre: bool,
        tip: str,
    ) -> None:
        self.animal_id = kin.id
        if not enabled and not centre:  # greyed: a dead animal, or one not in the frame
            rgb = mixed(rgb, GREY, GREYED)
        glyph = FEMALE_GLYPH if kin.sex == 1 else MALE_GLYPH
        dead = kin.died is not None
        text = f"{glyph} #{kin.id}" + (f" {DEAD_GLYPH}" if dead else "")
        if self.text() != text:
            self.setText(text)
        self.setToolTip(tip)
        self.setEnabled(enabled)
        key = (rgb, dead, centre)
        if key != self.style_key:
            self.style_key = key
            border = (
                "3px solid #000000"
                if centre
                else "1px dashed #555555"
                if dead
                else "1px solid #333333"
            )
            colour = text_colour(rgb)
            fill = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
            self.setStyleSheet(
                f"QPushButton {{ background: {fill}; color: {colour}; border: {border};"
                f" border-radius: 5px; font-weight: {'bold' if centre else 'normal'}; }}"
                f"QPushButton:disabled {{ background: {fill}; color: {colour}; border: {border}; }}"
                f"QPushButton:hover:enabled {{ border: 2px solid #000000; }}"
            )
        self.show()


class Board(QWidget):
    """The canvas the buttons sit on; it draws the lines between parents and children."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.buttons = [NodeButton(self) for _ in range(MAX_NODES)]
        self.layout_: TreeLayout | None = None

    def place(self, layout: TreeLayout) -> None:
        self.layout_ = layout
        top = layout.rows[0]
        for button, placed in zip(self.buttons, layout.nodes, strict=False):
            x = MARGIN + placed.column * (NODE_W + GAP_X)
            y = MARGIN + (placed.row - top) * (NODE_H + GAP_Y)
            button.move(int(x), int(y))
        self.setMinimumSize(
            int(2 * MARGIN + layout.width * (NODE_W + GAP_X) - GAP_X),
            int(2 * MARGIN + (layout.rows[1] - top + 1) * (NODE_H + GAP_Y) - GAP_Y),
        )
        self.update()

    def clear(self) -> None:
        self.layout_ = None
        for button in self.buttons:
            button.hide()
        self.update()

    def paintEvent(self, _event) -> None:
        layout = self.layout_
        if layout is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 2.0))
        shown = self.buttons
        for upper, lower in layout.edges:
            a, b = shown[upper], shown[lower]
            start = QPoint(a.x() + NODE_W // 2, a.y() + NODE_H)
            end = QPoint(b.x() + NODE_W // 2, b.y())
            middle = (start.y() + end.y()) // 2
            painter.drawLine(start, QPoint(start.x(), middle))
            painter.drawLine(QPoint(start.x(), middle), QPoint(end.x(), middle))
            painter.drawLine(QPoint(end.x(), middle), end)
        painter.end()


class FamilyTreeWindow(QDialog):
    """A window beside the main one, not modal; reopen it from the Family tab."""

    def __init__(self, context: ViewerContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("Family tree")
        self.resize(760, 520)
        self.detail: AnimalDetail | None = None
        self.frame: Frame | None = None
        self.layout_: TreeLayout | None = None
        self._shown: tuple | None = None
        outer = QVBoxLayout(self)
        self.heading = QLabel("", self)
        self.legend = QLabel(LEGEND, self)
        self.legend.setWordWrap(True)
        self.note = QLabel("", self)
        self.note.setWordWrap(True)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.board = Board(self.scroll)
        self.scroll.setWidget(self.board)
        for widget in (self.heading, self.legend, self.scroll, self.note):
            outer.addWidget(widget)
        for button in self.board.buttons:
            button.clicked.connect(lambda _checked=False, b=button: self._pick(b))
        controller = context.controller
        controller.detail_received.connect(self.show_detail)
        controller.frame_received.connect(self.show_frame)
        controller.backend_replaced.connect(lambda _backend: self.show_detail(None))
        if controller.frame is not None:
            self.frame = controller.frame
        self.show_detail(controller.detail)

    # -- what the controller says

    def show_frame(self, frame: Frame) -> None:
        self.frame = frame
        self._redraw()

    def show_detail(self, detail: AnimalDetail | None) -> None:
        self.detail = detail
        self._redraw()

    def _pick(self, button: NodeButton) -> None:
        if button.animal_id is not None:
            self.context.send(Select(button.animal_id))

    # -- drawing

    def _redraw(self) -> None:
        if not self.isVisible():
            return
        detail = self.detail
        family = None if detail is None else detail.family
        if detail is None or family is None:
            self._shown = None
            self.board.clear()
            self.heading.setText("")
            self.note.setText(
                "Nothing selected: click an animal in the world."
                if detail is None
                else "This simulation keeps no family record."
            )
            return
        layer = Layer(self.frame.animals) if self.frame is not None else None
        alive = frozenset(int(i) for i in layer.ids) if layer is not None else frozenset()
        mark = (family, alive, layer is not None)
        if mark == self._shown:
            return
        self._shown = mark
        layout = build_layout(family)
        self.layout_ = layout
        scale = FamilyScale.of(layer) if layer is not None else None
        keys = np.array([[k.family_a, k.family_b] for k in (p.kin for p in layout.nodes)])
        if scale is not None and "family_a" in layer.columns:
            colours = scale.colours(keys[:, 0], keys[:, 1])
            fills = [tuple(int(c) for c in row) for row in colours]
        else:
            fills = [NEUTRAL] * len(layout.nodes)
        tick_seconds = describe.seconds_per_tick(self.frame)
        for button, placed, fill in zip(self.board.buttons, layout.nodes, fills, strict=False):
            kin = placed.kin
            centre = placed is layout.nodes[0]
            button.show_kin(
                kin,
                fill,
                enabled=kin.id in alive and not centre,
                centre=centre,
                tip=describe.kin_text(kin, tick_seconds),
            )
        for button in self.board.buttons[len(layout.nodes) :]:
            button.hide()
        self.board.place(layout)
        self.heading.setText(f"<b>Family of #{family.center}</b>")
        self.note.setText(self._note(layout))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._shown = None
        self._redraw()

    @staticmethod
    def _note(layout: TreeLayout) -> str:
        notes = []
        if layout.forgotten:
            notes.append("Older ancestors are not remembered.")
        if layout.cut:
            notes.append("The tree is cut: some animals are not shown.")
        return " ".join(notes)
