"""The slots a screen fills (UX.11).

Every module in ``evolution_simulator.viewer.panels`` whose name does not start with an underscore
exposes ``PANEL``, a ``PanelSpec`` (or a tuple of them). The window finds them with
``discover_panels()`` and puts each in its slot, so the screens of UX.12 to UX.17 are each their own
module and the shell has no list to edit. A panel is built with a ``ViewerContext``: connect to
``context.controller``'s signals, send commands with ``context.send``.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget

from evolution_simulator.session import Command
from evolution_simulator.viewer import panels
from evolution_simulator.viewer.controller import ViewerController

log = logging.getLogger(__name__)

Area = Literal["center", "left", "right", "top", "bottom"]
"""Where a panel docks. ``center`` is the one big slot (the world view); the rest are docks that
can be dragged, floated, closed and brought back from the View menu."""


class ViewerContext:
    """What a panel is given: the controller, the window's actions and its message line."""

    def __init__(
        self,
        controller: ViewerController,
        actions: dict[str, QAction],
        show_message: Callable[[str, int], None],
    ) -> None:
        self.controller = controller
        self.actions = actions
        """The window's actions by name (``play_pause``, ``step`` ...), so a button can share
        the menu's action, its shortcut and its enabled state instead of making a second one."""
        self._show_message = show_message

    def send(self, command: Command) -> bool:
        return self.controller.send(command)

    def show_message(self, text: str, timeout_ms: int = 5000) -> None:
        """Say something on the status bar for a while."""
        self._show_message(text, timeout_ms)


@dataclass(frozen=True)
class PanelSpec:
    id: str
    """Stable name, used to save the layout; never change it once released."""
    title: str
    area: Area
    factory: Callable[[ViewerContext], QWidget]
    order: int = 100
    """Panels in the same area are stacked in this order, lowest first."""
    visible: bool = True
    """Shown in the default layout."""


def discover_panels() -> list[PanelSpec]:
    """The ``PANEL`` of each module in the ``panels`` package, in order. A module that fails to
    import is logged and skipped, so one broken screen does not take the window down."""
    found: list[PanelSpec] = []
    for info in pkgutil.iter_modules(panels.__path__):
        if info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"{panels.__name__}.{info.name}")
        except Exception:
            log.exception("The panel module %s could not be loaded", info.name)
            continue
        spec = getattr(module, "PANEL", None)
        if spec is None:
            continue
        found.extend(spec if isinstance(spec, tuple) else (spec,))
    ids = [spec.id for spec in found]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"Two panels share the id {duplicates[0]!r}.")
    return sorted(found, key=lambda spec: (spec.order, spec.id))
