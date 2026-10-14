"""The shortcuts window and the About box (UX.21).

The shortcuts list is built from ``KEY_MAP`` (``panels/controls.py``, where every key of the viewer
is named), plus every other action of the window that has a shortcut (Quit, New run, Save run
now ...), read from the actions themselves, so a key added later shows up here by itself; a test
fails when a ``KEY_MAP`` entry has no description in ``KEY_TEXT``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from evolution_simulator.viewer import about
from evolution_simulator.viewer.panels.controls import KEY_MAP

KEY_TEXT: dict[str, str] = {
    "play_pause": "Play or pause",
    "step": "Step one tick (and pause)",
    "step_day": "Step one simulated day (and pause)",
    "speed_faster": "Faster: the next speed up",
    "speed_slower": "Slower: the next speed down",
    "speed_max": "As fast as possible",
    "follow_selected": "Keep the selected creature in the middle of the world view",
    "deselect": "Deselect the creature",
}
"""What each key of ``KEY_MAP`` does, in the words of the shortcuts window."""

MOUSE_ROWS: tuple[tuple[str, str], ...] = (
    ("Drag the world view", "Pan"),
    ("Mouse wheel over the world view", "Zoom around the pointer"),
    ("Double-click the world view", "Fit the whole world"),
    ("Click a creature", "Select it and show it in the inspector"),
    ("Mouse wheel or drag on a chart", "Zoom or pan the chart (right-click for more)"),
)


@dataclass(frozen=True)
class ShortcutRow:
    label: str
    keys: tuple[str, ...]
    """The keys that do it, as written on this platform (Ctrl+Q, Space ...)."""


def key_text(sequence: QKeySequence) -> str:
    return sequence.toString(QKeySequence.SequenceFormat.NativeText)


def shortcut_rows(actions: Mapping[str, QAction]) -> list[ShortcutRow]:
    """The keyboard shortcuts: the ``KEY_MAP`` ones first, in its order, then every other action
    of the window that has a key. A ``KEY_MAP`` entry whose action is missing (a panel that did
    not load) is still listed, with the key map's own keys."""
    rows: list[ShortcutRow] = []
    for name, keys in KEY_MAP.items():
        action = actions.get(name)
        shown = tuple(key_text(s) for s in action.shortcuts()) if action is not None else keys
        rows.append(ShortcutRow(KEY_TEXT.get(name, name.replace("_", " ")), shown or keys))
    for name, action in actions.items():
        if name in KEY_MAP:
            continue
        keys = tuple(key_text(s) for s in action.shortcuts())
        if keys:
            rows.append(ShortcutRow(action.text().replace("&", ""), keys))
    return rows


def shortcuts_html(actions: Mapping[str, QAction]) -> str:
    """The shortcuts window's text."""
    lines = ["<h3>Keyboard</h3><table cellspacing='6'>"]
    for row in shortcut_rows(actions):
        keys = " or ".join(f"<b>{escape(k)}</b>" for k in row.keys)
        lines.append(f"<tr><td>{keys}</td><td>{escape(row.label)}</td></tr>")
    lines.append("</table><h3>Mouse</h3><table cellspacing='6'>")
    for gesture, result in MOUSE_ROWS:
        lines.append(f"<tr><td>{escape(gesture)}</td><td>{escape(result)}</td></tr>")
    lines.append("</table>")
    return "".join(lines)


class TextDialog(QDialog):
    """A window of read-only rich text with a Close button; it is not modal, so it can stay open
    beside the world."""

    def __init__(self, parent: QWidget, title: str, size: tuple[int, int] = (520, 460)) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(*size)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser, 1)
        self.buttons = QHBoxLayout()
        self.buttons.addStretch(1)
        layout.addLayout(self.buttons)
        self.close_button = QPushButton("Close", self)
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.close)
        self.buttons.addWidget(self.close_button)


class ShortcutsDialog(TextDialog):
    def __init__(self, parent: QWidget, actions: Mapping[str, QAction]) -> None:
        super().__init__(parent, "Keyboard shortcuts and mouse", (560, 600))
        self.browser.setHtml(shortcuts_html(actions))


class NoticesDialog(TextDialog):
    def __init__(self, parent: QWidget, text: str | None = None) -> None:
        super().__init__(parent, "Third-party notices", (620, 520))
        self.browser.setMarkdown(about.notices_text() if text is None else text)


class AboutDialog(TextDialog):
    def __init__(self, parent: QWidget, version: str | None = None) -> None:
        super().__init__(parent, f"About {about.APP_NAME}", (460, 340))
        self.browser.setHtml(
            about.about_html(about.program_version() if version is None else version)
        )
        self.notices_button = QPushButton("Third-party notices...", self)
        self.notices_button.clicked.connect(self.show_notices)
        self.buttons.insertWidget(0, self.notices_button)
        self.notices: NoticesDialog | None = None

    def show_notices(self) -> None:
        if self.notices is None:
            self.notices = NoticesDialog(self)
            self.notices.setWindowModality(Qt.WindowModality.NonModal)
        self.notices.show()
        self.notices.raise_()
