"""The Family tab (UX.14): parents, children, the closest relatives alive, each one a link that
selects that creature."""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from evolution_simulator.session import Frame, Select
from evolution_simulator.viewer.inspector import describe
from evolution_simulator.viewer.inspector.familytree import FamilyTreeWindow
from evolution_simulator.viewer.inspector.tabs import TabPage, TabSpec
from evolution_simulator.viewer.inspector.widgets import IdLinks
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.viewer.worldview.layers import Layer
from evolution_simulator.world.views import AnimalDetail

PARENT_SLOTS = 4
CHILD_SLOTS = 12
RELATIVE_SLOTS = 8
NO_KEY = "This frame has no family key, so closest relatives cannot be found."


class FamilyTab(TabPage):
    def __init__(self, context: ViewerContext, parent: QWidget) -> None:
        super().__init__(parent)
        self.context = context
        self.detail: AnimalDetail | None = None
        self.frame: Frame | None = None
        self.alive_ids: np.ndarray = np.empty(0, dtype="<u4")
        self._relatives_for: tuple[int, int] | None = None
        self.tree: FamilyTreeWindow | None = None
        layout = QVBoxLayout(self)
        self.tree_button = QPushButton("Show the family tree", self)
        self.tree_button.setToolTip(
            "Open a window with its ancestors above and its descendants below, dead ones too"
        )
        self.tree_button.clicked.connect(self.open_tree)
        layout.addWidget(self.tree_button)
        self.parents = self._section(layout, "Parents", PARENT_SLOTS)
        self.partner_title = QLabel("<b>Father of the young it carries</b>", self)
        layout.addWidget(self.partner_title)
        self.partner = IdLinks(self, 1)
        layout.addWidget(self.partner)
        self.children = self._section(layout, "Living children", CHILD_SLOTS)
        self.relatives = self._section(layout, "Closest relatives alive", RELATIVE_SLOTS)
        self.note = QLabel("", self)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)
        for links in (self.parents, self.partner, self.children, self.relatives):
            links.chosen.connect(self._select)

    def open_tree(self) -> FamilyTreeWindow:
        """Open the family tree window (made the first time), on top."""
        if self.tree is None:
            self.tree = FamilyTreeWindow(self.context, self)
        self.tree.show()
        self.tree.raise_()
        self.tree.activateWindow()
        return self.tree

    def _section(self, layout: QVBoxLayout, title: str, slots: int) -> IdLinks:
        layout.addWidget(QLabel(f"<b>{title}</b>", self))
        links = IdLinks(self, slots)
        layout.addWidget(links)
        return links

    def can_select(self, animal_id: int) -> bool:
        return bool(np.any(self.alive_ids == animal_id))

    def _select(self, animal_id: int) -> None:
        self.context.send(Select(animal_id))

    def show_frame(self, frame: Frame) -> None:
        self.frame = frame
        self.alive_ids = Layer(frame.animals).ids

    def show_detail(self, detail: AnimalDetail | None) -> None:
        self.detail = detail
        if detail is None:
            return
        self.parents.set_ids(detail.parents, self.can_select)
        has_partner = detail.partner is not None
        self.partner_title.setVisible(has_partner)
        self.partner.setVisible(has_partner)
        if has_partner:
            self.partner.set_ids([detail.partner], self.can_select)
        self.children.set_ids(detail.children, self.can_select)
        self._show_relatives(detail)

    def _show_relatives(self, detail: AnimalDetail) -> None:
        mark = (detail.id, detail.tick)
        if mark == self._relatives_for:
            return
        self._relatives_for = mark
        found = describe.closest_relatives(self.frame, detail.id, RELATIVE_SLOTS)
        if found is None:
            self.relatives.set_ids([], self.can_select)
            self.note.setText(NO_KEY if self.frame is not None else "")
            return
        self.note.setText("")
        self.relatives.set_ids(
            [r.id for r in found],
            self.can_select,
            {r.id: describe.relative_text(r) for r in found},
        )


TAB = TabSpec(id="family", title="Family", factory=FamilyTab, order=30)
