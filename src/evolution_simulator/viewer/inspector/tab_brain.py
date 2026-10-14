"""The Brain tab (UX.15): what the selected creature senses and decides, and the network behind it.

Following the default of [#133](https://github.com/dwhagar/evolutionSimulator/issues/133) (UX.27) it
shows both, bars first: the outputs and the inputs as labelled bars, then the network drawn with the
strength of each connection and the live values on the neurons. The values come from the brain's
last run, so they are empty ("waiting") until the creature has been selected through one run; the
wiring needs no run. A group of checkboxes switches the sense overlays (vision, hearing, smell,
touch) on the world view, which this tab feeds through ``worldview.overlays``.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QHelpEvent, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.sense_channels import INPUT_CHANNELS
from evolution_simulator.viewer.inspector import brainview
from evolution_simulator.viewer.inspector.brainview import BarRow, NetworkModel
from evolution_simulator.viewer.inspector.tabs import TabPage, TabSpec
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.viewer.worldview.overlays import SENSES, hub_for
from evolution_simulator.world.views import AnimalDetail

POSITIVE = QColor("#0072B2")
"""Okabe and Ito blue: a connection that pushes the next neuron up."""
NEGATIVE = QColor("#D55E00")
"""Okabe and Ito vermilion: one that pushes it down (also drawn dashed)."""

ROW_HEIGHT = 18.0
HEADING_HEIGHT = 20.0
LABEL_WIDTH = 118.0
VALUE_WIDTH = 46.0

WAITING = "Waiting: its brain has not run since it was selected, so the values are empty."


class BarList(QWidget):
    """Labelled bars in groups, painted in one widget (a few dozen rows at ten updates a second)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.rows: tuple[BarRow, ...] = ()
        self._layout: list[tuple[float, BarRow | str]] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_rows(self, rows: Sequence[BarRow]) -> None:
        rows = tuple(rows)
        if rows == self.rows:
            return
        changed_shape = [r.key for r in rows] != [r.key for r in self.rows]
        self.rows = rows
        if changed_shape:
            self._arrange()
        self.update()

    def _arrange(self) -> None:
        y, group = 0.0, None
        self._layout = []
        for row in self.rows:
            if row.group != group:
                group = row.group
                self._layout.append((y, group))
                y += HEADING_HEIGHT
            self._layout.append((y, row))
            y += ROW_HEIGHT
        self.setFixedHeight(int(y) + 2)

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(self.height())
        return hint

    def row_at(self, y: float) -> BarRow | None:
        for top, item in self._layout:
            if isinstance(item, BarRow) and top <= y < top + ROW_HEIGHT:
                return item
        return None

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            row = self.row_at(event.pos().y())
            if row is not None:
                QToolTip.showText(event.globalPos(), f"{row.label}: {row.tip}", self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        palette = self.palette()
        track_colour = palette.color(QPalette.ColorRole.Mid)
        fill_colour = palette.color(QPalette.ColorRole.Highlight)
        text_colour = palette.color(QPalette.ColorRole.WindowText)
        dim = QColor(text_colour)
        dim.setAlpha(150)
        bold = QFont(self.font())
        bold.setBold(True)
        bar_left = LABEL_WIDTH
        bar_width = max(20.0, self.width() - LABEL_WIDTH - VALUE_WIDTH - 6.0)
        for top, item in self._layout:
            if isinstance(item, str):
                painter.setFont(bold)
                painter.setPen(text_colour)
                painter.drawText(
                    QRectF(0.0, top, self.width(), HEADING_HEIGHT),
                    Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                    item,
                )
                continue
            painter.setFont(self.font())
            row = item
            painter.setPen(text_colour)
            painter.drawText(
                QRectF(0.0, top, LABEL_WIDTH - 4.0, ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                QFontMetricsF(self.font()).elidedText(
                    row.label, Qt.TextElideMode.ElideRight, LABEL_WIDTH - 6.0
                ),
            )
            track = QRectF(bar_left, top + 4.0, bar_width, ROW_HEIGHT - 8.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track_colour)
            painter.drawRoundedRect(track, 2.0, 2.0)
            span = row.high - row.low
            if row.value is not None and span > 0.0:
                painter.setBrush(fill_colour)
                level = min(1.0, max(0.0, (row.value - row.low) / span))
                if row.signed:
                    middle = track.x() + track.width() * (0.0 - row.low) / span
                    end = track.x() + track.width() * level
                    painter.drawRect(
                        QRectF(min(middle, end), track.y(), abs(end - middle), track.height())
                    )
                else:
                    painter.drawRect(
                        QRectF(track.x(), track.y(), track.width() * level, track.height())
                    )
            if row.signed:  # the zero line
                middle = track.x() + track.width() * (0.0 - row.low) / span
                painter.setPen(dim)
                painter.drawLine(
                    QPointF(middle, track.y() - 2.0), QPointF(middle, track.bottom() + 2.0)
                )
            if row.threshold is not None and span > 0.0:
                x = track.x() + track.width() * (row.threshold - row.low) / span
                painter.setPen(QPen(text_colour, 1, Qt.PenStyle.DotLine))
                painter.drawLine(QPointF(x, track.y() - 2.0), QPointF(x, track.bottom() + 2.0))
            if row.marker is not None and span > 0.0:
                x = track.x() + track.width() * (row.marker - row.low) / span
                painter.setPen(QPen(NEGATIVE, 2))
                painter.drawLine(QPointF(x, track.y() - 3.0), QPointF(x, track.bottom() + 3.0))
            painter.setPen(text_colour if row.value is not None else dim)
            painter.drawText(
                QRectF(bar_left + bar_width + 4.0, top, VALUE_WIDTH, ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                row.text,
            )
        painter.end()


class NetworkView(QWidget):
    """The wiring drawn as three columns: inputs, hidden neurons, outputs.

    A line is a connection (width and opacity grow with the weight, blue pushes up and solid, orange
    pushes down and dashed; a connection that is off is not drawn). A neuron is filled by its live
    value, hollow before the brain has run. An input with no connection has a faded label.
    """

    MARGIN = 8.0
    LEFT = 112.0
    RIGHT = 84.0

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.model: NetworkModel | None = None
        self.inputs: tuple[BarRow, ...] = ()
        self.outputs: tuple[BarRow, ...] = ()
        self.hidden: tuple[float, ...] | None = None
        self.hidden_biases: tuple[float, ...] = ()
        self.setMinimumHeight(len(INPUT_CHANNELS) * 15 + 24)
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def set_state(
        self,
        model: NetworkModel | None,
        inputs: Sequence[BarRow],
        outputs: Sequence[BarRow],
        hidden: tuple[float, ...] | None,
        hidden_biases: tuple[float, ...],
    ) -> None:
        state = (model, tuple(inputs), tuple(outputs), hidden, hidden_biases)
        if state == (self.model, self.inputs, self.outputs, self.hidden, self.hidden_biases):
            return
        self.model, self.inputs, self.outputs = state[0], state[1], state[2]
        self.hidden, self.hidden_biases = hidden, hidden_biases
        self.update()

    # -- where things are

    def _column(self, count: int, x: float) -> list[QPointF]:
        top, bottom = self.MARGIN + 6.0, self.height() - self.MARGIN - 6.0
        if count <= 1:
            return [QPointF(x, (top + bottom) / 2.0)] * count
        step = (bottom - top) / (count - 1)
        return [QPointF(x, top + step * i) for i in range(count)]

    def _points(self) -> tuple[list[QPointF], list[QPointF], list[QPointF]]:
        model = self.model
        assert model is not None
        left = self.LEFT
        right = max(left + 60.0, self.width() - self.RIGHT)
        middle = (left + right) / 2.0
        return (
            self._column(model.inputs, left),
            self._column(model.hidden, middle),
            self._column(model.outputs, right),
        )

    # -- tooltips

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            text = self._tip_at(event.pos()) if self.model is not None else ""
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def _tip_at(self, pos) -> str:
        ins, hid, outs = self._points()
        spot = QPointF(pos)

        def near(points: list[QPointF]) -> int | None:
            for i, point in enumerate(points):
                if abs(point.x() - spot.x()) <= 9.0 and abs(point.y() - spot.y()) <= 7.0:
                    return i
            return None

        i = near(ins)
        if i is not None and i < len(self.inputs):
            row = self.inputs[i]
            return f"{row.label}: {row.tip} Now: {row.text}"
        j = near(hid)
        if j is not None and self.model is not None:
            value = (
                "-" if self.hidden is None or j >= len(self.hidden) else f"{self.hidden[j]:+.2f}"
            )
            bias = f"{self.hidden_biases[j]:+.2f}" if j < len(self.hidden_biases) else "-"
            return (
                f"Hidden neuron {j + 1} (genome slot {self.model.slots[j]}): "
                f"bias {bias}, value now {value}"
            )
        k = near(outs)
        if k is not None and k < len(self.outputs):
            row = self.outputs[k]
            return f"{row.label}: {row.tip} Now: {row.text}"
        return ""

    # -- drawing

    @staticmethod
    def _fill(value: float | None, low: float, high: float) -> QColor | None:
        if value is None or high <= low:
            return None
        if low < 0.0:  # signed: blue above zero, orange below
            level = min(1.0, abs(value) / high)
            colour = QColor(POSITIVE if value >= 0.0 else NEGATIVE)
        else:
            level = min(1.0, max(0.0, (value - low) / (high - low)))
            colour = QColor(POSITIVE)
        colour.setAlpha(int(40 + 215 * level))
        return colour

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_colour = self.palette().color(QPalette.ColorRole.WindowText)
        model = self.model
        if model is None:
            painter.setPen(text_colour)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No network to draw")
            painter.end()
            return
        ins, hid, outs = self._points()
        biggest = model.max_weight or 1.0
        for edges, sources, targets in (
            (model.input_edges, ins, hid),
            (model.output_edges, hid, outs),
        ):
            for edge in edges:
                strength = min(1.0, abs(edge.weight) / biggest)
                colour = QColor(POSITIVE if edge.weight > 0 else NEGATIVE)
                colour.setAlpha(int(45 + 190 * strength))
                pen = QPen(colour, 0.5 + 2.5 * strength)
                if edge.weight < 0:
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(sources[edge.source], targets[edge.target])
        used = {e.source for e in model.input_edges}
        small = QFont(self.font())
        small.setPointSizeF(max(6.5, self.font().pointSizeF() - 1.5))
        painter.setFont(small)
        outline = QPen(text_colour, 1)
        for i, point in enumerate(ins):
            row = self.inputs[i] if i < len(self.inputs) else None
            self._node(
                painter,
                point,
                4.0,
                outline,
                self._fill(row.value, row.low, row.high) if row else None,
            )
            faded = QColor(text_colour)
            faded.setAlpha(255 if i in used else 90)
            painter.setPen(faded)
            painter.drawText(
                QRectF(0.0, point.y() - 8.0, point.x() - 8.0, 16.0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                row.label if row else f"input {i}",
            )
        for j, point in enumerate(hid):
            value = self.hidden[j] if self.hidden is not None and j < len(self.hidden) else None
            self._node(painter, point, 6.0, outline, self._fill(value, -1.0, 1.0))
        for k, point in enumerate(outs):
            row = self.outputs[k] if k < len(self.outputs) else None
            self._node(
                painter,
                point,
                5.0,
                outline,
                self._fill(row.value, row.low, row.high) if row else None,
            )
            painter.setPen(text_colour)
            painter.drawText(
                QRectF(point.x() + 9.0, point.y() - 8.0, self.RIGHT - 10.0, 16.0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                row.label if row else f"output {k}",
            )
        painter.end()

    @staticmethod
    def _node(
        painter: QPainter, point: QPointF, radius: float, outline: QPen, fill: QColor | None
    ) -> None:
        painter.setPen(outline)
        painter.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
        painter.drawEllipse(point, radius, radius)


def _heading(parent: QWidget, text: str) -> QLabel:
    label = QLabel(f"<b>{text}</b>", parent)
    return label


class BrainTab(TabPage):
    def __init__(self, context: ViewerContext, parent: QWidget) -> None:
        super().__init__(parent)
        self.context = context
        self.detail: AnimalDetail | None = None
        self.hub = hub_for(context.controller)
        self._network = None
        self._model: NetworkModel | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        scroll.setWidget(content)

        self.status = QLabel("", content)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        senses = QHBoxLayout()
        layout.addLayout(senses)
        senses.addWidget(QLabel("Show on the world:", content))
        self.sense_boxes: dict[str, QCheckBox] = {}
        for sense in SENSES:
            box = QCheckBox(sense.capitalize(), content)
            box.setChecked(sense in self.hub.shown)
            box.setToolTip(f"Draw how far its {sense} reaches around the selected creature")
            box.toggled.connect(lambda on, sense=sense: self.hub.set_shown(sense, on))
            senses.addWidget(box)
            self.sense_boxes[sense] = box
        senses.addStretch(1)

        self.outputs = BarList(content)
        layout.addWidget(self.outputs)
        layout.addWidget(_heading(content, "What it senses"))
        self.inputs = BarList(content)
        layout.addWidget(self.inputs)
        layout.addWidget(_heading(content, "The network"))
        self.legend = QLabel(
            "Lines are connections: wider is stronger, blue pushes up, dashed orange pushes down. "
            "Circles are neurons, filled by their value now.",
            content,
        )
        self.legend.setWordWrap(True)
        layout.addWidget(self.legend)
        self.network = NetworkView(content)
        layout.addWidget(self.network)
        layout.addStretch(1)
        self._empty()

    def _empty(self) -> None:
        self.status.setText("Nothing selected.")
        self.outputs.set_rows(())
        self.inputs.set_rows(())
        self.network.set_state(None, (), (), None, ())

    def show_detail(self, detail: AnimalDetail | None) -> None:
        self.detail = detail
        if detail is None:
            self.hub.set_geometry(None)
            self._empty()
            return
        self.hub.set_geometry(brainview.sense_geometry(detail) if detail.alive else None)
        input_rows = brainview.input_rows(detail)
        output_rows = brainview.output_rows(detail)
        self.inputs.set_rows(brainview.grouped(input_rows))
        self.outputs.set_rows(output_rows)
        if not detail.alive:
            self.status.setText("Dead: these are the last values it had.")
        elif detail.brain is None:
            self.status.setText(WAITING)
        else:
            self.status.setText(
                "Wandering: its brain could not decide, so a random turn replaced the steering."
                if detail.decision is not None and detail.decision.wandering
                else "Showing the last time its brain ran."
            )
        network = detail.network
        if network != self._network or self._model is None:
            self._network = network
            self._model = brainview.network_model(network)
        hidden = detail.brain.hidden if detail.brain is not None else None
        if hidden is not None and len(hidden) != self._model.hidden:
            hidden = None
        self.network.set_state(self._model, input_rows, output_rows, hidden, network.hidden_biases)


TAB = TabSpec(
    id="brain", title="Brain", factory=lambda ctx, parent: BrainTab(ctx, parent), order=40
)
