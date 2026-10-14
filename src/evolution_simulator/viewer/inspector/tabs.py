"""How the inspector finds its tabs (UX.14).

Every module in this package whose name starts with ``tab_`` exposes ``TAB``, a ``TabSpec`` (or a
tuple of them). ``discover_tabs()`` finds them, so UX.15 adds its Brain tab as ``tab_brain.py`` and
nothing shared is edited. A tab is a ``TabPage``: the panel tells it which creature is selected
(``show_detail``, about ten times a second while one is), which frame is newest (``show_frame``) and
what the history holds (``show_history``). All three do nothing unless the tab overrides them.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from evolution_simulator.history import HistorySamples
from evolution_simulator.session import Frame
from evolution_simulator.viewer import inspector
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.world.views import AnimalDetail

log = logging.getLogger(__name__)


class TabPage(QWidget):
    """A tab of the inspector. ``detail`` is ``None`` when nothing is selected."""

    def show_detail(self, detail: AnimalDetail | None) -> None:
        """The newest details of the selected creature (a dead one arrives once, marked dead)."""

    def show_frame(self, frame: Frame) -> None:
        """A new world frame, for what is read from the whole population."""

    def show_history(self, history: HistorySamples) -> None:
        """The recorder's newest samples."""


@dataclass(frozen=True)
class TabSpec:
    id: str
    title: str
    factory: Callable[[ViewerContext, QWidget], TabPage]
    """Builds the tab; the second argument is the parent it must be given at creation."""
    order: int = 100
    """Tabs are in this order, lowest first."""


def discover_tabs() -> list[TabSpec]:
    """The ``TAB`` of each ``tab_*`` module of this package, in order. A module that fails to import
    is logged and skipped."""
    found: list[TabSpec] = []
    for info in pkgutil.iter_modules(inspector.__path__):
        if not info.name.startswith("tab_"):
            continue
        try:
            module = importlib.import_module(f"{inspector.__name__}.{info.name}")
        except Exception:
            log.exception("The inspector tab module %s could not be loaded", info.name)
            continue
        spec = getattr(module, "TAB", None)
        if spec is None:
            continue
        found.extend(spec if isinstance(spec, tuple) else (spec,))
    ids = [spec.id for spec in found]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"Two inspector tabs share the id {duplicates[0]!r}.")
    return sorted(found, key=lambda spec: (spec.order, spec.id))
