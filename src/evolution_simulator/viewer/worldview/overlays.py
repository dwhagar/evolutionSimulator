"""Overlays on the world view (UX.15): what the selected creature's senses cover.

The world canvas knows nothing of senses and the inspector knows nothing of the canvas, so they meet
here. ``hub_for(controller)`` is the one ``OverlayHub`` of a window: the Brain tab sets the sense
geometry and which senses to show; the canvas (given the hub by its panel) calls ``paint`` after the
ground and before the animals, and repaints when the hub says it ``changed``.

Every sense is told apart by line style and a label as well as by colour: vision is a wedge (the
field of view) with a solid edge, hearing a dashed circle, smell a dotted circle and touch a thin
solid ring.
"""

from __future__ import annotations

import math
import weakref
from dataclasses import dataclass

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from evolution_simulator.viewer.inspector.brainview import SenseGeometry
from evolution_simulator.viewer.worldview.camera import Camera

SENSES: tuple[str, ...] = ("vision", "hearing", "smell", "touch")
SENSE_COLOURS: dict[str, QColor] = {
    "vision": QColor(240, 228, 66),  # Okabe and Ito yellow
    "hearing": QColor(86, 180, 233),  # sky blue
    "smell": QColor(204, 121, 167),  # reddish purple
    "touch": QColor(255, 255, 255),
}
SENSE_STYLES: dict[str, Qt.PenStyle] = {
    "vision": Qt.PenStyle.SolidLine,
    "hearing": Qt.PenStyle.DashLine,
    "smell": Qt.PenStyle.DotLine,
    "touch": Qt.PenStyle.SolidLine,
}
DEFAULT_SHOWN = ("vision", "hearing", "smell")
"""The senses drawn until the user switches some off."""


@dataclass(frozen=True)
class SelectedPose:
    """Where the selected animal is drawn right now (the glide included), in world units."""

    x: float
    y: float
    heading: float
    """Radians counter-clockwise from +x."""


class OverlayHub(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.geometry: SenseGeometry | None = None
        self.shown: set[str] = set(DEFAULT_SHOWN)

    def set_geometry(self, geometry: SenseGeometry | None) -> None:
        if geometry != self.geometry:
            self.geometry = geometry
            self.changed.emit()

    def set_shown(self, sense: str, shown: bool) -> None:
        if sense not in SENSES:
            raise ValueError(f"No sense {sense!r}; choose from {SENSES}.")
        if shown == (sense in self.shown):
            return
        (self.shown.add if shown else self.shown.discard)(sense)
        self.changed.emit()

    @property
    def active(self) -> bool:
        geometry = self.geometry
        return geometry is not None and geometry.any and bool(self.shown)

    # -- painting

    def paint(
        self, painter: QPainter, camera: Camera, size: tuple[float, float], pose: SelectedPose
    ) -> None:
        """Draw the shown senses around ``pose``; touches nothing else of the painter's state."""
        geometry = self.geometry
        if geometry is None or not self.active:
            return
        centre = QPointF(*camera.to_screen(pose.x, pose.y, size))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        try:
            for sense in SENSES:
                if sense in self.shown:
                    self._paint_sense(painter, camera, centre, pose, geometry, sense)
        finally:
            painter.restore()

    def _paint_sense(
        self,
        painter: QPainter,
        camera: Camera,
        centre: QPointF,
        pose: SelectedPose,
        geometry: SenseGeometry,
        sense: str,
    ) -> None:
        reach = {
            "vision": geometry.vision_range,
            "hearing": geometry.hearing_range,
            "smell": geometry.smell_range,
            "touch": geometry.touch_range,
        }[sense]
        if reach is None or reach <= 0.0:
            return
        radius = reach * camera.scale
        colour = SENSE_COLOURS[sense]
        fill = QColor(colour)
        fill.setAlpha(34 if sense != "touch" else 0)
        path = QPainterPath()
        box = QRectF(centre.x() - radius, centre.y() - radius, 2.0 * radius, 2.0 * radius)
        half = geometry.fov_half_degrees if sense == "vision" else None
        wedge = half is not None and half < 180.0
        if wedge:
            facing = math.degrees(pose.heading)  # world and screen both count counter-clockwise
            path.moveTo(centre)
            path.arcTo(box, facing - half, 2.0 * half)
            path.closeSubpath()
        else:
            path.addEllipse(box)
        painter.setBrush(fill)
        painter.setPen(
            QPen(QColor(0, 0, 0, 150), 3.0)
        )  # a dark edge keeps it visible on light ground
        painter.drawPath(path)
        pen = QPen(colour, 1.6 if sense != "touch" else 1.2)
        pen.setStyle(SENSE_STYLES[sense])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        label_at = QPointF(centre.x() + radius * 0.72, centre.y() - radius * 0.72)
        if wedge:  # on the wedge's own bisector
            angle = pose.heading
            label_at = QPointF(
                centre.x() + math.cos(angle) * radius * 0.8,
                centre.y() - math.sin(angle) * radius * 0.8,
            )
        painter.setPen(QPen(QColor(0, 0, 0, 230), 1))
        painter.drawText(label_at + QPointF(1.0, 1.0), sense)
        painter.setPen(QPen(colour, 1))
        painter.drawText(label_at, sense)


_HUBS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def hub_for(controller: QObject) -> OverlayHub:
    """The overlay hub shared by everything built on this controller (made on first use)."""
    hub = _HUBS.get(controller)
    if hub is None:
        hub = OverlayHub(controller)
        _HUBS[controller] = hub
    return hub
