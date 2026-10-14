"""Light, dark and follow-the-system themes (UX.21).

``apply_theme(app, mode)`` restyles the whole application: ``"light"`` and ``"dark"`` put Qt's
Fusion style with a fixed palette over everything, ``"system"`` goes back to the style and palette
the program started with (and so follows the operating system, which Qt 6.5 and later does by
itself, Windows 11 included). Windows made of widgets pick the palette up by themselves, and a
widget that draws with palette colours (the charts) hears about it through a palette-change event.
The world view draws its own colours (ground, daylight, creatures) and is the same in every theme.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

THEMES: tuple[str, ...] = ("system", "light", "dark")
DEFAULT_THEME = "system"
THEME_TEXT = {"system": "Follow the system", "light": "Light", "dark": "Dark"}
"""The menu text of each theme."""

_native: tuple[str, QPalette] | None = None
"""The style name and palette the program started with, kept the first time a theme is applied."""
_applied = DEFAULT_THEME


def _dark_palette() -> QPalette:
    palette = QPalette()
    window, base, text = QColor(45, 45, 48), QColor(30, 30, 32), QColor(230, 230, 230)
    disabled = QColor(130, 130, 130)
    link = QColor(86, 180, 233)
    roles = {
        QPalette.ColorRole.Window: window,
        QPalette.ColorRole.WindowText: text,
        QPalette.ColorRole.Base: base,
        QPalette.ColorRole.AlternateBase: QColor(40, 40, 43),
        QPalette.ColorRole.ToolTipBase: QColor(25, 25, 27),
        QPalette.ColorRole.ToolTipText: text,
        QPalette.ColorRole.Text: text,
        QPalette.ColorRole.Button: QColor(60, 60, 64),
        QPalette.ColorRole.ButtonText: text,
        QPalette.ColorRole.BrightText: QColor(255, 90, 90),
        QPalette.ColorRole.Link: link,
        QPalette.ColorRole.LinkVisited: QColor(204, 121, 167),
        QPalette.ColorRole.Highlight: QColor(0, 114, 178),
        QPalette.ColorRole.HighlightedText: QColor(255, 255, 255),
        QPalette.ColorRole.PlaceholderText: disabled,
    }
    for role, colour in roles.items():
        palette.setColor(role, colour)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return palette


def _light_palette() -> QPalette:
    fusion = QStyleFactory.create("Fusion")
    return QPalette(fusion.standardPalette()) if fusion is not None else QPalette()


def palette_for(mode: str) -> QPalette:
    """The palette of ``"light"`` or ``"dark"``."""
    if mode == "dark":
        return _dark_palette()
    if mode == "light":
        return _light_palette()
    raise ValueError(f"{mode!r} has no palette of its own; the system theme uses Qt's.")


def _scheme(mode: str):
    """Qt's colour scheme for a theme (Qt 6.8 and later; it also colours the title bar)."""
    scheme = getattr(Qt, "ColorScheme", None)
    if scheme is None:
        return None
    return {"light": scheme.Light, "dark": scheme.Dark}.get(mode, scheme.Unknown)


def applied_theme() -> str:
    """The theme last applied (``"system"`` before any)."""
    return _applied


def apply_theme(app: QApplication | None, mode: str) -> None:
    """Restyle ``app`` as ``mode`` ("system", "light" or "dark")."""
    global _native, _applied
    if mode not in THEMES:
        raise ValueError(f"Unknown theme {mode!r}; the themes are {', '.join(THEMES)}.")
    if app is None:
        return
    if _native is None:
        _native = (app.style().objectName(), QPalette(app.palette()))
    if mode == _applied:
        return
    hints = QGuiApplication.styleHints()
    setter = getattr(hints, "setColorScheme", None)
    if mode == "system":
        name, palette = _native
        style = QStyleFactory.create(name)
        if style is not None:
            app.setStyle(style)
        app.setPalette(palette)
    else:
        fusion = QStyleFactory.create("Fusion")
        if fusion is not None:
            app.setStyle(fusion)
        app.setPalette(palette_for(mode))
    scheme = _scheme(mode)
    if setter is not None and scheme is not None:
        setter(scheme)
    _applied = mode
