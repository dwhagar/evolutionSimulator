"""The colour modes and their colours (UX.12).

A mode turns the animals of a frame into one colour each. Every colour is picked to stay readable
for the common kinds of colour blindness: the categorical pair (sex) uses the Okabe-Ito blue and
reddish purple, the two ramps (energy, age) change in lightness as well as hue, and the diverging
ramp (diet) runs from blue to vermillion through a pale middle, the Okabe-Ito pair that stays apart
for red-green colour blindness. Nothing means anything by colour alone: sex also changes the shape
(females have a notch at the back), sleep dims and rings the animal, pregnancy puts a dot on it.

``MODES`` is the menu. A mode that needs columns the frame does not carry (the family colour needs the
two family numbers of UX.30) is listed but reported unavailable.
"""

from __future__ import annotations

import colorsys
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from evolution_simulator.session.snapshot import ANIMAL_FLAGS
from evolution_simulator.viewer.worldview.layers import Layer

Colours = np.ndarray
"""``(n, 3)`` uint8: red, green, blue of each animal."""

ENERGY_STOPS = ((122, 74, 164), (45, 128, 180), (30, 170, 150), (150, 210, 80), (253, 231, 37))
"""Low energy (purple) to full (yellow): lightness climbs the whole way."""
AGE_STOPS = ((250, 240, 170), (235, 170, 40), (185, 85, 110), (110, 60, 150))
"""Newborn (pale) to worn out (deep purple)."""
DIET_STOPS = ((0, 114, 178), (225, 228, 232), (213, 94, 0))
"""Plant eater (blue) through a pale middle to meat eater (vermillion)."""
MALE = (86, 180, 233)
FEMALE = (204, 121, 167)


def ramp(stops: tuple[tuple[int, int, int], ...], t: np.ndarray) -> Colours:
    """Colours along ``stops`` for ``t`` in 0 to 1."""
    points = np.asarray(stops, dtype=np.float64)
    positions = np.linspace(0.0, 1.0, len(points))
    t = np.clip(np.nan_to_num(t.astype(np.float64)), 0.0, 1.0)
    channels = [np.interp(t, positions, points[:, c]) for c in range(3)]
    return np.rint(np.stack(channels, axis=1)).astype(np.uint8)


def _column(name: str, stops) -> Callable[[Layer], Colours]:
    return lambda layer: ramp(stops, layer.col(name))


def _sex(layer: Layer) -> Colours:
    female = layer.flag(ANIMAL_FLAGS["female"])
    return np.where(female[:, None], np.uint8(FEMALE), np.uint8(MALE)).astype(np.uint8)


def _unit(values: np.ndarray) -> np.ndarray:
    """``values`` stretched over 0 to 1 by the range of the middle 90% of the frame (5th to 95th
    percentile, the rest clipped, so one far-off animal does not squash everyone else's colours;
    all 0 when there is no spread), which is how the frame's family key is meant to be read
    (``lineage.family_key``)."""
    if len(values) == 0:
        return values.astype(np.float64)
    low, high = (float(v) for v in np.percentile(values, [5.0, 95.0]))
    if high - low < 1e-9:
        return np.zeros(len(values))
    return np.clip((values.astype(np.float64) - low) / (high - low), 0.0, 1.0)


def _family(layer: Layer) -> Colours:
    """Relatives get alike colours: the first family number sets the hue, the second the lightness
    (so two lineages of the same hue still differ, also without colour vision)."""
    hue = 0.8 * _unit(layer.col("family_a"))  # stops short of a full turn, so the ends differ
    value = 0.6 + 0.4 * _unit(layer.col("family_b"))
    rgb = [colorsys.hsv_to_rgb(float(h), 0.7, float(v)) for h, v in zip(hue, value, strict=True)]
    return np.rint(np.asarray(rgb, dtype=np.float64).reshape(-1, 3) * 255).astype(np.uint8)


@dataclass(frozen=True)
class ColourMode:
    id: str
    label: str
    colours: Callable[[Layer], Colours]
    needs: tuple[str, ...] = ()
    """The columns the frame must carry for this mode to work."""

    def available(self, columns: tuple[str, ...]) -> bool:
        return all(name in columns for name in self.needs)


MODES: tuple[ColourMode, ...] = (
    ColourMode("diet", "Diet", _column("diet", DIET_STOPS)),
    ColourMode("sex", "Sex", _sex),
    ColourMode("energy", "Energy", _column("energy_ratio", ENERGY_STOPS)),
    ColourMode("age", "Age", _column("age_ratio", AGE_STOPS)),
    ColourMode("family", "Family", _family, needs=("family_a", "family_b")),
)
MODES_BY_ID = {mode.id: mode for mode in MODES}
DEFAULT_MODE = "diet"

# The ground, the plants and the corpses. The ground goes from night to day with the daylight.
GROUND_NIGHT = (22, 28, 46)
GROUND_DAY = (62, 70, 64)
OUTSIDE = (18, 20, 24)
WALL = (235, 235, 235)
PLANT_DIM = (80, 140, 66)
PLANT_FULL = (160, 225, 100)
CORPSE = (214, 170, 130)


def ground(daylight: float) -> tuple[int, int, int]:
    """The ground colour at this daylight (0 night, 1 full day)."""
    t = min(max(daylight, 0.0), 1.0)
    r, g, b = (round(n + (d - n) * t) for n, d in zip(GROUND_NIGHT, GROUND_DAY, strict=True))
    return r, g, b
