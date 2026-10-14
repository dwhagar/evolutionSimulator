"""Small widgets the inspector's tabs share (UX.14).

Every widget here is given its parent when it is made, and a layout is set on its owner before it is
filled: Qt frees a child of an unparented widget twice at exit otherwise (see ``ux.md``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

UNUSUAL = QColor("#E69F00")
"""Okabe and Ito orange: a gene far from the population's."""
MARKER = QColor("#D55E00")
BAR_HEIGHT = 14


class Meter(QWidget):
    """A thin bar from 0 to 1 with an optional tick for the population's average."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.level = 0.0
        self.marker: float | None = None
        self.unusual = False
        self.setMinimumWidth(80)
        self.setFixedHeight(BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_level(self, level: float, marker: float | None = None, unusual: bool = False) -> None:
        level = min(1.0, max(0.0, level))
        marker = None if marker is None else min(1.0, max(0.0, marker))
        if (level, marker, unusual) == (self.level, self.marker, self.unusual):
            return
        self.level, self.marker, self.unusual = level, marker, unusual
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        palette = self.palette()
        area = QRectF(0.5, 3.5, self.width() - 1.0, self.height() - 7.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(palette.color(QPalette.ColorRole.Mid))
        painter.drawRoundedRect(area, 3.0, 3.0)
        fill = QColor(UNUSUAL if self.unusual else palette.color(QPalette.ColorRole.Highlight))
        painter.setBrush(fill)
        painter.drawRoundedRect(
            QRectF(area.x(), area.y(), area.width() * self.level, area.height()), 3.0, 3.0
        )
        if self.marker is not None:
            x = area.x() + area.width() * self.marker
            painter.setPen(palette.color(QPalette.ColorRole.WindowText))
            painter.drawLine(int(x), 0, int(x), self.height())
        painter.end()


class IdLinks(QWidget):
    """A row of "#id" buttons, a fixed number of them made up front and shown as needed. A button
    sends its animal's id on ``chosen``; one for an animal that cannot be selected is disabled."""

    chosen = Signal(int)

    def __init__(self, parent: QWidget, slots: int) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.none_label = QLabel("none", self)
        self.more_label = QLabel("", self)
        layout.addWidget(self.none_label)
        self.buttons: list[QPushButton] = []
        self.ids: list[int] = []
        for slot in range(slots):
            button = QPushButton(self)
            button.setFlat(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, at=slot: self.chosen.emit(self.ids[at]))
            layout.addWidget(button)
            self.buttons.append(button)
        layout.addWidget(self.more_label)
        layout.addStretch(1)
        self.set_ids([], lambda _id: False)

    def set_ids(
        self,
        ids: Sequence[int],
        can_select: Callable[[int], bool],
        tips: Mapping[int, str] | None = None,
    ) -> None:
        shown = list(ids[: len(self.buttons)])
        self.ids = shown
        self.none_label.setVisible(not ids)
        for button, animal_id in zip(self.buttons, shown, strict=False):
            ok = can_select(animal_id)
            button.setText(f"#{animal_id}")
            button.setEnabled(ok)
            tip = (tips or {}).get(animal_id, "")
            button.setToolTip((tip or "Select this creature") if ok else "No longer alive")
            button.show()
        for button in self.buttons[len(shown) :]:
            button.hide()
        extra = len(ids) - len(shown)
        self.more_label.setText(f"and {extra} more" if extra > 0 else "")
        self.more_label.setVisible(extra > 0)


class FieldGrid(QWidget):
    """Label and value pairs in two columns: ``add`` makes a row and returns its value label."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setColumnStretch(1, 1)
        self.values: dict[str, QLabel] = {}

    def add(self, key: str, label: str, tip: str = "") -> QLabel:
        row = self.grid.rowCount()
        name = QLabel(label, self)
        value = QLabel("", self)
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if tip:
            name.setToolTip(tip)
            value.setToolTip(tip)
        self.grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
        self.grid.addWidget(value, row, 1)
        self.values[key] = value
        return value

    def set_text(self, key: str, text: str) -> None:
        label = self.values[key]
        if label.text() != text:
            label.setText(text)


class MeterRow(QWidget):
    """A name, a bar and a value, in one line."""

    def __init__(self, parent: QWidget, name: str, tip: str = "") -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel(name, self)
        self.name.setMinimumWidth(110)
        self.meter = Meter(self)
        self.value = QLabel("", self)
        self.value.setMinimumWidth(90)
        layout.addWidget(self.name)
        layout.addWidget(self.meter, 1)
        layout.addWidget(self.value)
        if tip:
            self.setToolTip(tip)

    def set(
        self, level: float, text: str, marker: float | None = None, unusual: bool = False
    ) -> None:
        self.meter.set_level(level, marker, unusual)
        if self.value.text() != text:
            self.value.setText(text)
