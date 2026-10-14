"""The widget that draws the world (UX.12).

``WorldCanvas`` paints with ``QPainter`` in world coordinates turned into pixels by a ``Camera``:
the ground (tinted by the daylight), an optional grid, the plants, the corpses, the animals and the
wall. It knows nothing of the session; the panel feeds it frames (``set_frame``) and listens for
clicks (``animal_clicked``).

Speed notes:

- The plants change slowly and are many, so they are painted once into a pixmap that is reused for
  as long as the plants, the camera and the size stay the same. A frame that carries no plants
  (most of them) costs nothing for them.
- Animals are grouped by colour and drawn as one path per colour, so a thousand animals are a
  few dozen draw calls.
- Drawing one tick behind: the last two frames are kept and the animals are shown a fraction of the
  way from the earlier pose to the later one (see ``glide``); a timer repaints while that goes on.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from evolution_simulator.session import Frame
from evolution_simulator.session.snapshot import ANIMAL_FLAGS, PLANT_FLAGS, Block
from evolution_simulator.viewer.worldview import glide, palette
from evolution_simulator.viewer.worldview.camera import Camera, nice_step
from evolution_simulator.viewer.worldview.layers import Layer

MIN_ANIMAL_PX = 9.0
"""Animals are never drawn smaller than this, tip to back, so a zoomed-out world stays readable."""
DRAG_PX = 4
"""A press that moves less than this is a click, not a drag."""
TIMER_MS = 16
ZOOM_PER_NOTCH = 1.0015
"""Zoom factor for each unit of wheel angle (a notch is 120: about 1.2 times)."""
PLANT_BUCKETS = 8
CACHE_MARGIN = 0.25
"""The plant pixmap is painted this fraction of the window larger on every side, so a pan (or
following a creature) slides the same painting until it runs out of margin."""


def _qcolor(rgb, alpha: int = 255) -> QColor:
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), alpha)


def _path() -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)  # overlapping shapes fill, never cut holes
    return path


class WorldCanvas(QWidget):
    animal_clicked = Signal(object)
    """The id of the animal clicked, or ``None`` for a click on nothing."""
    follow_changed = Signal(bool)
    """Following was switched off by dragging the view."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(240, 200)
        self.setMouseTracking(False)
        self._clock = clock
        self.camera = Camera()
        self.colour_mode = palette.DEFAULT_MODE
        self.show_plants = True
        self.show_corpses = True
        self.show_animals = True
        self.show_grid = False
        self.follow = False
        """Keep the selected animal in the middle of the view."""
        self.drawing = True
        """False while the world is not being drawn (fast-forwarding with drawing switched off)."""
        self.selected: int | None = None

        self._frame: Frame | None = None
        self._animals: Layer | None = None
        self._corpses: Layer | None = None
        self._plants: Layer | None = None
        self._plants_block: Block | None = None
        self._plants_version = 0
        self._colours: np.ndarray | None = None
        self._prev: glide.Pose | None = None
        self._arrived = 0.0
        self._glide: float | None = None
        self._shown: glide.Pose | None = None
        self._auto_fit = True
        self._cache_key: tuple | None = None
        self._cache: QPixmap | None = None
        self._cache_centre = (0.0, 0.0)
        self._press: QPointF | None = None
        self._last: QPointF | None = None
        self._dragged = False
        self._timer = QTimer(self)
        self._timer.setInterval(TIMER_MS)
        self._timer.timeout.connect(self._on_timer)

    # -------------------------------------------------------------------------
    # Feeding it
    # -------------------------------------------------------------------------

    @property
    def frame(self) -> Frame | None:
        return self._frame

    @property
    def world(self) -> tuple[float, float]:
        size = self._frame.world_size if self._frame is not None else (1000.0, 1000.0)
        return float(size[0]), float(size[1])

    @property
    def gliding(self) -> bool:
        return self._glide is not None and self._glide_fraction() < 1.0

    def set_frame(self, frame: Frame, plants: Block | None) -> None:
        """Show this frame. ``plants`` is the last plants block sent (frames carry it only now and
        then)."""
        first = self._frame is None
        previous = self._frame
        if self._animals is not None:
            self._prev = self._shown_pose()
        self._frame = frame
        self._animals = Layer(frame.animals)
        self._corpses = Layer(frame.corpses)
        self.selected = frame.status.selected
        if plants is not self._plants_block and plants is not None:
            self._plants_block = plants
            self._plants = Layer(plants)
            self._plants_version += 1
        self._glide = None
        if previous is not None:
            status = frame.status
            speed = status.speed_achieved if status.behind and status.speed_achieved else None
            self._glide = glide.duration(
                frame.simulated_seconds - previous.simulated_seconds,
                speed if speed is not None else status.speed_asked,
                running=status.running,
            )
        self._arrived = self._clock()
        self._colours = self._compute_colours()
        if first and self._auto_fit:
            self.fit_view()
        if self._glide is not None:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def set_selected(self, animal_id: int | None) -> None:
        if animal_id != self.selected:
            self.selected = animal_id
            self.update()

    def available_modes(self) -> list[palette.ColourMode]:
        columns = self._animals.columns if self._animals is not None else ()
        return [mode for mode in palette.MODES if mode.available(columns)]

    def set_colour_mode(self, mode_id: str) -> bool:
        """Colour the animals by this mode; ``False`` if there is no such mode or the frame lacks
        what it needs."""
        mode = palette.MODES_BY_ID.get(mode_id)
        if mode is None or (
            self._animals is not None and not mode.available(self._animals.columns)
        ):
            return False
        self.colour_mode = mode_id
        self._colours = self._compute_colours()
        self.update()
        return True

    def _compute_colours(self) -> np.ndarray | None:
        if self._animals is None:
            return None
        mode = palette.MODES_BY_ID[self.colour_mode]
        if not mode.available(self._animals.columns):
            mode = palette.MODES_BY_ID[palette.DEFAULT_MODE]
        return mode.colours(self._animals)

    def set_drawing(self, drawing: bool) -> None:
        """Stop painting the world (and the glide timer with it), or start again."""
        if drawing != self.drawing:
            self.drawing = drawing
            self.update()

    def set_follow(self, follow: bool) -> None:
        self.follow = follow
        if follow:
            self._auto_fit = False
        self.update()

    def set_option(self, name: str, value: bool) -> None:
        if name not in ("show_plants", "show_corpses", "show_animals", "show_grid"):
            raise ValueError(f"No view option {name!r}.")
        setattr(self, name, value)
        self.update()

    # -------------------------------------------------------------------------
    # The camera
    # -------------------------------------------------------------------------

    def _size(self) -> tuple[float, float]:
        return float(self.width()), float(self.height())

    def fit_view(self) -> None:
        """Show the whole world and keep it fitted as the window changes size."""
        self._auto_fit = True
        self.camera.fit(self.world, self._size())
        self.update()

    def resizeEvent(self, event) -> None:
        if self._auto_fit:
            self.camera.fit(self.world, self._size())
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:
        factor = ZOOM_PER_NOTCH ** event.angleDelta().y()
        position = event.position()
        self._auto_fit = False
        self.camera.zoom_at(factor, position.x(), position.y(), self._size(), self.world)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = self._last = event.position()
            self._dragged = False

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press is None or self._last is None:
            return
        here = event.position()
        if not self._dragged and (here - self._press).manhattanLength() > DRAG_PX:
            self._dragged = True
        if self._dragged:
            self._auto_fit = False
            if self.follow:
                self.follow = False
                self.follow_changed.emit(False)
            self.camera.pan_pixels(here.x() - self._last.x(), here.y() - self._last.y(), self.world)
            self.update()
        self._last = here

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        clicked = not self._dragged
        self._press = self._last = None
        if clicked:
            position = event.position()
            self.animal_clicked.emit(self.animal_at(position.x(), position.y()))

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.fit_view()

    def animal_at(self, px: float, py: float) -> int | None:
        """The animal nearest the pixel, if one is close enough to count as clicked."""
        pose = self._shown
        if pose is None or pose.count == 0 or self._animals is None:
            return None
        sx, sy = self.camera.to_screen(pose.x, pose.y, self._size())
        reach = np.maximum(self._lengths() * 0.6, 8.0)
        distance = np.hypot(sx - px, sy - py)
        hit = np.where(distance <= reach, distance, np.inf)
        best = int(np.argmin(hit))
        return int(pose.ids[best]) if np.isfinite(hit[best]) else None

    # -------------------------------------------------------------------------
    # One tick behind
    # -------------------------------------------------------------------------

    def _glide_fraction(self) -> float:
        if self._glide is None:
            return 1.0
        return min(max((self._clock() - self._arrived) / self._glide, 0.0), 1.0)

    def _shown_pose(self) -> glide.Pose:
        assert self._animals is not None
        return glide.blend(self._prev, self._animals, self._glide_fraction())

    def _on_timer(self) -> None:
        if not self.gliding:
            self._timer.stop()
        self.update()

    # -------------------------------------------------------------------------
    # Painting
    # -------------------------------------------------------------------------

    def _lengths(self) -> np.ndarray:
        assert self._animals is not None
        return np.maximum(self._animals.col("radius") * 2.2 * self.camera.scale, MIN_ANIMAL_PX)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = self._size()
        painter.fillRect(self.rect(), _qcolor(palette.OUTSIDE))
        frame = self._frame
        if frame is None or self._animals is None:
            painter.setPen(_qcolor((200, 200, 200)))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for the simulation"
            )
            return
        if not self.drawing:
            painter.setPen(_qcolor((200, 200, 200)))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Not drawing while fast-forwarding"
            )
            return
        self._shown = self._shown_pose()
        self._follow_selected()
        self._paint_ground(painter, frame, size)
        if self.show_grid:
            self._paint_grid(painter, size)
        if self.show_plants and self._plants is not None:
            self._plant_layer(painter, size)
        if self.show_corpses and self._corpses is not None:
            self._paint_corpses(painter, size)
        if self.show_animals:
            self._paint_animals(painter, size)
        self._paint_wall(painter, size)
        self._paint_scale_bar(painter, size)

    def _follow_selected(self) -> None:
        """Centre the view on the selected animal, if asked to and it is there."""
        pose = self._shown
        if not self.follow or self.selected is None or pose is None:
            return
        found = np.flatnonzero(pose.ids == self.selected)
        if len(found):
            self.camera.cx, self.camera.cy = float(pose.x[found[0]]), float(pose.y[found[0]])
            self.camera.clamp(self.world)

    def _world_rect(self, size) -> QRectF:
        w, h = self.world
        left, top = self.camera.to_screen(0.0, h, size)
        right, bottom = self.camera.to_screen(w, 0.0, size)
        return QRectF(QPointF(left, top), QPointF(right, bottom))

    def _paint_ground(self, painter: QPainter, frame: Frame, size) -> None:
        painter.fillRect(self._world_rect(size), _qcolor(palette.ground(frame.daylight)))

    def _paint_grid(self, painter: QPainter, size) -> None:
        step = nice_step(80.0 / self.camera.scale)
        x0, y0, x1, y1 = self.camera.visible(size)
        w, h = self.world
        rect = self._world_rect(size)
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
        for gx in np.arange(max(0.0, math.floor(x0 / step) * step), min(w, x1) + step, step):
            sx, _ = self.camera.to_screen(gx, 0.0, size)
            painter.drawLine(QPointF(sx, rect.top()), QPointF(sx, rect.bottom()))
        for gy in np.arange(max(0.0, math.floor(y0 / step) * step), min(h, y1) + step, step):
            _, sy = self.camera.to_screen(0.0, gy, size)
            painter.drawLine(QPointF(rect.left(), sy), QPointF(rect.right(), sy))

    def _plant_layer(self, painter: QPainter, size) -> None:
        """Draw the plants from the pixmap, painting it again only when they, the zoom or the
        window change or the view has slid past the margin."""
        ratio = self.devicePixelRatioF()
        margin = (size[0] * CACHE_MARGIN, size[1] * CACHE_MARGIN)
        key = (self._plants_version, self.camera.scale, size, ratio)
        camera = self.camera
        if key == self._cache_key and self._cache is not None:
            shift_x = (self._cache_centre[0] - camera.cx) * camera.scale
            shift_y = (camera.cy - self._cache_centre[1]) * camera.scale
            if abs(shift_x) <= margin[0] and abs(shift_y) <= margin[1]:
                painter.drawPixmap(QPointF(shift_x - margin[0], shift_y - margin[1]), self._cache)
                return
        self._cache = self._paint_plants(size, margin, ratio)
        self._cache_key = key
        self._cache_centre = (camera.cx, camera.cy)
        painter.drawPixmap(QPointF(-margin[0], -margin[1]), self._cache)

    def _paint_plants(self, size, margin, ratio) -> QPixmap:
        """The plants on a transparent pixmap the size of the window plus the margin."""
        wide = (size[0] + 2.0 * margin[0], size[1] + 2.0 * margin[1])
        pixmap = QPixmap(int(wide[0] * ratio), int(wide[1] * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        plants = self._plants
        assert plants is not None
        sx, sy = self.camera.to_screen(plants.col("x"), plants.col("y"), size)
        sx, sy = sx + margin[0], sy + margin[1]
        radius = np.maximum(plants.col("radius") * self.camera.scale, 1.2)
        on_screen = (
            (sx >= -radius) & (sx <= wide[0] + radius) & (sy >= -radius) & (sy <= wide[1] + radius)
        )
        bucket = np.minimum(
            (np.clip(plants.col("biomass_ratio"), 0.0, 1.0) * (PLANT_BUCKETS - 1)).astype(int),
            PLANT_BUCKETS - 1,
        )
        shades = palette.ramp(
            (palette.PLANT_DIM, palette.PLANT_FULL), np.linspace(0.0, 1.0, PLANT_BUCKETS)
        )
        for level in np.unique(bucket[on_screen]):
            chosen = on_screen & (bucket == level)
            painter.setBrush(_qcolor(shades[level], 225))
            for x, y, r in zip(
                sx[chosen].tolist(), sy[chosen].tolist(), radius[chosen].tolist(), strict=True
            ):
                painter.drawEllipse(QPointF(x, y), r, r)  # far faster than one big path
        seeding = on_screen & plants.flag(PLANT_FLAGS["ready_to_seed"]) & (radius >= 3.0)
        painter.setBrush(QColor(255, 250, 200, 235))
        for x, y, r in zip(
            sx[seeding].tolist(), sy[seeding].tolist(), radius[seeding].tolist(), strict=True
        ):
            painter.drawEllipse(QPointF(x, y), r * 0.35, r * 0.35)
        painter.end()
        return pixmap

    def _paint_corpses(self, painter: QPainter, size) -> None:
        corpses = self._corpses
        assert corpses is not None
        if corpses.count == 0:
            return
        sx, sy = self.camera.to_screen(corpses.col("x"), corpses.col("y"), size)
        reach = np.maximum(corpses.col("radius") * self.camera.scale * 1.3, 3.5)
        path = _path()
        for x, y, r in zip(sx.tolist(), sy.tolist(), reach.tolist(), strict=True):
            path.addPolygon(
                QPolygonF(
                    [QPointF(x, y - r), QPointF(x + r, y), QPointF(x, y + r), QPointF(x - r, y)]
                )
            )
            path.closeSubpath()
        painter.setPen(QPen(QColor(40, 30, 25, 200), 1))
        painter.setBrush(_qcolor(palette.CORPSE, 230))
        painter.drawPath(path)

    def _paint_animals(self, painter: QPainter, size) -> None:
        layer, pose, colours = self._animals, self._shown, self._colours
        assert layer is not None and pose is not None and colours is not None
        if layer.count == 0:
            return
        sx, sy = self.camera.to_screen(pose.x, pose.y, size)
        length = self._lengths()
        near = (sx > -length) & (sx < size[0] + length) & (sy > -length) & (sy < size[1] + length)
        asleep = layer.flag(ANIMAL_FLAGS["asleep"])
        female = layer.flag(ANIMAL_FLAGS["female"])
        pregnant = layer.flag(ANIMAL_FLAGS["pregnant"])
        dx, dy = np.cos(pose.heading), -np.sin(pose.heading)  # world y is up, screen y is down
        rgb = (colours >> 3).astype(np.int32)
        key = ((rgb[:, 0] << 10) | (rgb[:, 1] << 5) | rgb[:, 2]) * 2 + asleep.astype(np.int32)
        rings, dots = _path(), _path()
        groups: dict[int, QPainterPath] = {}
        sample: dict[int, np.ndarray] = {}
        for i in np.flatnonzero(near).tolist():
            x, y, long = float(sx[i]), float(sy[i]), float(length[i])
            ux, uy = float(dx[i]), float(dy[i])
            vx, vy = -uy, ux
            tip = QPointF(x + ux * long * 0.6, y + uy * long * 0.6)
            left = QPointF(
                x - ux * long * 0.4 + vx * long * 0.35, y - uy * long * 0.4 + vy * long * 0.35
            )
            right = QPointF(
                x - ux * long * 0.4 - vx * long * 0.35, y - uy * long * 0.4 - vy * long * 0.35
            )
            if female[i]:  # a notch at the back tells the sexes apart without colour
                notch = QPointF(x - ux * long * 0.12, y - uy * long * 0.12)
                shape = QPolygonF([tip, left, notch, right])
            else:
                shape = QPolygonF([tip, left, right])
            group = int(key[i])
            if group not in groups:
                groups[group] = _path()
                sample[group] = colours[i]
            groups[group].addPolygon(shape)
            groups[group].closeSubpath()
            if asleep[i]:
                rings.addEllipse(QPointF(x, y), long * 0.7, long * 0.7)
            if pregnant[i]:
                dots.addEllipse(QPointF(x, y), max(1.5, long * 0.14), max(1.5, long * 0.14))
        painter.setPen(QPen(QColor(0, 0, 0, 110), 1))
        for group, path in groups.items():
            painter.setBrush(_qcolor(sample[group], 105 if group & 1 else 240))
            painter.drawPath(path)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
        painter.drawPath(rings)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 245))
        painter.drawPath(dots)
        self._paint_selection(painter, sx, sy, length)

    def _paint_selection(self, painter: QPainter, sx, sy, length) -> None:
        pose = self._shown
        if self.selected is None or pose is None:
            return
        found = np.flatnonzero(pose.ids == self.selected)
        if len(found) == 0:
            return
        i = int(found[0])
        centre, reach = QPointF(float(sx[i]), float(sy[i])), float(length[i]) * 0.85
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 200), 4))
        painter.drawEllipse(centre, reach, reach)
        painter.setPen(QPen(QColor(255, 255, 255, 255), 2))
        painter.drawEllipse(centre, reach, reach)

    def _paint_wall(self, painter: QPainter, size) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_qcolor(palette.WALL), 2))
        painter.drawRect(self._world_rect(size))

    def _paint_scale_bar(self, painter: QPainter, size) -> None:
        units = nice_step(90.0 / self.camera.scale)
        pixels = units * self.camera.scale
        x, y = 16.0, size[1] - 16.0
        painter.setPen(QPen(QColor(0, 0, 0, 170), 4))
        painter.drawLine(QPointF(x, y), QPointF(x + pixels, y))
        painter.setPen(QPen(QColor(255, 255, 255, 240), 2))
        painter.drawLine(QPointF(x, y), QPointF(x + pixels, y))
        painter.drawText(QPointF(x, y - 6.0), f"{units:g} units")

    # -------------------------------------------------------------------------

    def save_screenshot(self, path: str) -> bool:
        """Save what the view shows as an image (the format follows the file's extension)."""
        return self.grab().save(path)
