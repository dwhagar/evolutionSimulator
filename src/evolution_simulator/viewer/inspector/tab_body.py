"""The Body tab (UX.14): condition, state, what it decided and its traits in their units."""

from __future__ import annotations

import math

from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from evolution_simulator.session import Frame
from evolution_simulator.viewer.inspector import describe
from evolution_simulator.viewer.inspector.tabs import TabPage, TabSpec
from evolution_simulator.viewer.inspector.widgets import FieldGrid, MeterRow
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.world.views import AnimalDetail


class TraitTable(QWidget):
    """The trait groups as a grid, rebuilt only when the set of trait names changes."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.names: tuple[str, ...] = ()
        self.body: QWidget | None = None
        self.grid: FieldGrid | None = None

    def update_traits(self, traits: dict[str, float]) -> None:
        names = tuple(traits)
        if names != self.names or self.body is None:
            self._rebuild(traits)
            self.names = names
        assert self.grid is not None
        for group in describe.trait_groups(traits):
            for row in group.rows:
                self.grid.set_text(row.id, row.text)

    def _rebuild(self, traits: dict[str, float]) -> None:
        if self.body is not None:
            self.body.hide()
            self.body.setParent(None)
            self.body.deleteLater()
        body = QWidget(self)
        self.layout_.addWidget(body)
        inner = QVBoxLayout(body)
        inner.setContentsMargins(0, 0, 0, 0)
        grid = FieldGrid(body)
        for group in describe.trait_groups(traits):
            heading = QLabel(f"<b>{group.title}</b>", grid)
            grid.grid.addWidget(heading, grid.grid.rowCount(), 0, 1, 2)
            for row in group.rows:
                grid.add(row.id, row.name, row.meaning)
        inner.addWidget(grid)
        self.body, self.grid = body, grid


class BodyTab(TabPage):
    def __init__(self, context: ViewerContext, parent: QWidget) -> None:
        super().__init__(parent)
        self.context = context
        self.tick_seconds: float | None = None
        self.detail: AnimalDetail | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        scroll.setWidget(content)

        self.energy = MeterRow(content, "Energy", "Energy in store, out of what its body can hold")
        self.health = MeterRow(content, "Health", "Health, out of its most")
        self.vitality = MeterRow(content, "Vitality", "1 in its prime, falling as wear builds up")
        for row in (self.energy, self.health, self.vitality):
            layout.addWidget(row)

        self.fields = FieldGrid(content)
        for key, label, tip in (
            ("age", "Age", "How long it has lived and how much of its lifespan that is"),
            ("state", "State", "Asleep, carrying young, ready to mate"),
            ("decision", "Decision", "What its brain decided on the latest tick"),
            ("brain", "Brain run", "Its inputs and hidden values come from its last brain run"),
            ("body", "Body", "Mass and diet"),
            ("place", "Position", "Where it is, and the way it faces (0 degrees is +x)"),
            ("mating", "Matings", "How many times it has mated"),
        ):
            self.fields.add(key, label, tip)
        layout.addWidget(self.fields)
        self.traits = TraitTable(content)
        layout.addWidget(self.traits)
        layout.addStretch(1)

    def show_frame(self, frame: Frame) -> None:
        self.tick_seconds = describe.seconds_per_tick(frame)

    def show_detail(self, detail: AnimalDetail | None) -> None:
        self.detail = detail
        if detail is None:
            return
        self.energy.set(
            detail.energy / detail.max_energy if detail.max_energy > 0 else 0.0,
            f"{describe.number_text(detail.energy)} / {describe.number_text(detail.max_energy)}",
        )
        self.health.set(
            detail.health / detail.max_health if detail.max_health > 0 else 0.0,
            f"{describe.number_text(detail.health)} / {describe.number_text(detail.max_health)}",
        )
        self.vitality.set(detail.vitality, f"{detail.vitality * 100:.0f}%")
        fields = self.fields
        fields.set_text("age", describe.age_text(detail, self.tick_seconds))
        fields.set_text("state", ", ".join(describe.state_words(detail)))
        fields.set_text("decision", describe.decision_words(detail))
        fields.set_text("brain", self._brain_text(detail))
        fields.set_text(
            "body", f"mass {describe.number_text(detail.mass)}, {describe.diet_text(detail.diet)}"
        )
        degrees = math.degrees(detail.heading)
        fields.set_text(
            "place",
            f"({detail.x:.1f}, {detail.y:.1f}) facing {degrees:.0f}°",
        )
        fields.set_text("mating", str(detail.matings))
        self.traits.update_traits(detail.traits)

    @staticmethod
    def _brain_text(detail: AnimalDetail) -> str:
        if not detail.alive:
            return "-"
        if detail.brain is None:
            return "waiting: its brain has not run since it was selected"
        return "traced (inputs and hidden values are in hand)"


TAB = TabSpec(id="body", title="Body", factory=BodyTab, order=10)
