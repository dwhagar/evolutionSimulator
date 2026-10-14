"""Pan and zoom (UX.12): where the world is on the screen.

``scale`` is pixels per world unit and ``(cx, cy)`` the world point at the centre of the widget.
World y points up and screen y down, so the two are flipped here and nowhere else. Every method that
takes pixel positions takes the widget size too, so nothing in here depends on Qt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MARGIN = 24.0
"""Pixels of ground left around the world when it is fitted to the window."""
MAX_SCALE = 60.0
"""Most pixels per world unit: a plant a few units across fills a few hundred pixels."""
MIN_FIT_FRACTION = 0.5
"""Zooming out stops at half the scale at which the whole world fits."""


@dataclass
class Camera:
    scale: float = 1.0
    cx: float = 0.0
    cy: float = 0.0

    def key(self) -> tuple[float, float, float]:
        """Changes whenever the picture would."""
        return (self.scale, self.cx, self.cy)

    def to_screen(self, x, y, size: tuple[float, float]):
        """Pixels for world positions (numbers or arrays)."""
        return (x - self.cx) * self.scale + size[0] / 2.0, (self.cy - y) * self.scale + size[
            1
        ] / 2.0

    def to_world(self, px, py, size: tuple[float, float]):
        return (px - size[0] / 2.0) / self.scale + self.cx, self.cy - (
            py - size[1] / 2.0
        ) / self.scale

    @staticmethod
    def fit_scale(world: tuple[float, float], size: tuple[float, float]) -> float:
        room_x = max(size[0] - 2.0 * MARGIN, 1.0)
        room_y = max(size[1] - 2.0 * MARGIN, 1.0)
        return min(room_x / world[0], room_y / world[1])

    def fit(self, world: tuple[float, float], size: tuple[float, float]) -> None:
        """Show the whole world, centred."""
        self.scale = self.fit_scale(world, size)
        self.cx, self.cy = world[0] / 2.0, world[1] / 2.0

    def zoom_at(
        self,
        factor: float,
        px: float,
        py: float,
        size: tuple[float, float],
        world: tuple[float, float],
    ) -> None:
        """Zoom by ``factor`` keeping the world point under the pixel ``(px, py)`` where it is."""
        low = self.fit_scale(world, size) * MIN_FIT_FRACTION
        scale = min(max(self.scale * factor, low), max(MAX_SCALE, low))
        if scale == self.scale:
            return
        wx, wy = self.to_world(px, py, size)
        self.scale = scale
        self.cx = wx - (px - size[0] / 2.0) / scale
        self.cy = wy + (py - size[1] / 2.0) / scale
        self.clamp(world)

    def pan_pixels(self, dx: float, dy: float, world: tuple[float, float]) -> None:
        """Drag the picture by ``(dx, dy)`` pixels."""
        self.cx -= dx / self.scale
        self.cy += dy / self.scale
        self.clamp(world)

    def clamp(self, world: tuple[float, float]) -> None:
        """Keep the centre of the window inside the world, so it cannot be lost off the edge."""
        self.cx = min(max(self.cx, 0.0), world[0])
        self.cy = min(max(self.cy, 0.0), world[1])

    def visible(self, size: tuple[float, float]) -> tuple[float, float, float, float]:
        """The world rectangle on screen as ``(x0, y0, x1, y1)``."""
        x0, y1 = self.to_world(0.0, 0.0, size)
        x1, y0 = self.to_world(size[0], size[1], size)
        return x0, y0, x1, y1


def nice_step(target: float) -> float:
    """The 1, 2 or 5 times a power of ten at or just above ``target``, for grid lines and the
    scale bar."""
    if not target > 0.0 or not math.isfinite(target):
        return 1.0
    power = 10.0 ** math.floor(math.log10(target))
    for mantissa in (1.0, 2.0, 5.0, 10.0):
        if mantissa * power >= target:
            return mantissa * power
    return 10.0 * power  # pragma: no cover - the loop always returns
