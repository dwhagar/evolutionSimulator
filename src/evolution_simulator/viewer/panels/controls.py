"""Time and speed controls (UX.13), the top dock.

Play or pause and single step (the window's own actions, so the menu, the buttons and the keys are
one thing), "step a day", a button for every speed preset and for as fast as possible, a custom
speed, the speed asked next to the speed got, and a readout of the simulated clock, the day or
night and what the run is doing. This module also owns the keyboard map (``KEY_MAP``).

"Don't draw while fast-forwarding" is a checkable action (``NO_DRAW`` in ``context.actions``). The
world view asks ``world_drawing_paused(context.actions, status)`` before it paints; this panel only
shows the note. Stopping the session from packing frames needs UX.7's ``want`` command.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.session import MAX_SPEED, Frame, SetSpeed, Status, Step
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext
from evolution_simulator.world.timescale import (
    DAY,
    DEFAULT_SECONDS_PER_TICK,
    HOUR,
    MINUTE,
    SPEED_PRESETS,
    YEAR,
    format_duration,
)

NO_DRAW = "no_draw_fast_forward"
"""Name of the checkable action, in ``ViewerContext.actions``, that turns the world view off while
fast-forwarding."""

KEY_MAP: dict[str, tuple[str, ...]] = {
    "play_pause": ("Space",),
    "step": ("Right",),
    "step_day": ("Shift+Right",),
    "speed_faster": ("+", "="),
    "speed_slower": ("-",),
    "speed_max": ("M",),
    "follow_selected": ("F",),
    "deselect": ("Esc",),
}
"""Every key of the viewer, by action name. ``play_pause`` and ``step`` are made by the window and
get their keys there (the same ones); the rest are made here, except ``follow_selected`` (``F``),
which the world view makes (UX.12), and ``deselect`` (``Esc``), which the inspector makes (UX.14)."""

SPEED_ORDER: tuple[str, ...] = (*SPEED_PRESETS, MAX_SPEED)
"""The presets from slowest to fastest, then as fast as possible."""

BUTTON_TEXT = {
    "real-time": "1 s",
    "minute": "1 min",
    "hour": "1 h",
    "day": "1 d",
    "week": "1 wk",
    "month": "1 mo",
    "year": "1 yr",
    "decade": "10 yr",
    "century": "100 yr",
    "millennium": "1000 yr",
    MAX_SPEED: "Max",
}
"""The short label of each speed button (a second of real time is this much simulated time)."""

FAST_FORWARD_FROM = SPEED_PRESETS["decade"]
"""Simulated seconds per real second from which the eye cannot follow the world (ux.md, "Speed and
what the window shows"); as fast as possible counts too."""

CUSTOM_UNITS: tuple[tuple[str, float], ...] = (
    ("seconds", 1.0),
    ("minutes", MINUTE),
    ("hours", HOUR),
    ("days", DAY),
    ("years", YEAR),
)


# --- plain logic, no Qt state -------------------------------------------------------


def is_fast_forward(status: Status) -> bool:
    """Whether the speed asked for is past what the eye can follow."""
    return status.speed_asked is None or status.speed_asked >= FAST_FORWARD_FROM


def world_drawing_paused(actions: dict[str, QAction], status: Status) -> bool:
    """True while the world view should not paint: the user switched drawing off, the run is going
    and the speed is a fast-forward."""
    action = actions.get(NO_DRAW)
    if action is None or not action.isChecked():
        return False
    return status.running and is_fast_forward(status)


def neighbour_speed(status: Status, direction: int) -> str | None:
    """The preset one step faster (``direction`` 1) or slower (-1) than the speed now, or ``None``
    at the end of the list. A custom speed moves to the nearest preset on that side of it."""
    if status.speed_asked is None:
        current = float("inf")
    else:
        current = status.speed_asked
    if direction > 0:
        for name in SPEED_ORDER:
            value = float("inf") if name == MAX_SPEED else SPEED_PRESETS[name]
            if value > current:
                return name
        return None
    for name in reversed(SPEED_ORDER):
        value = float("inf") if name == MAX_SPEED else SPEED_PRESETS[name]
        if value < current:
            return name
    return None


def ticks_per_day(frame: Frame | None) -> int:
    """How many ticks make a simulated day, read from the length of a tick the frame implies (the
    default hour before any tick has run); at least one."""
    if frame is not None and frame.tick > 0 and frame.simulated_seconds > 0.0:
        per_tick = frame.simulated_seconds / frame.tick
    else:
        per_tick = DEFAULT_SECONDS_PER_TICK
    return max(1, round(DAY / per_tick))


def asked_text(status: Status) -> str:
    if status.speed_asked is None:
        return "as fast as possible"
    if status.speed_preset is not None:
        return f"{status.speed_preset}/s"
    return f"{format_duration(status.speed_asked)}/s"


def got_text(status: Status) -> str:
    """The speed measured, "-" while paused or before enough has run to measure."""
    if not status.running or status.speed_achieved is None:
        return "-"
    text = f"{format_duration(status.speed_achieved)}/s"
    return f"{text} (behind)" if status.behind else text


def state_text(status: Status) -> str:
    if status.running:
        return "Running"
    if status.steps_left > 0:
        return f"Stepping, {status.steps_left:,} left"
    return "Paused"


def clock_text(frame: Frame | None) -> str:
    if frame is None:
        return "Waiting for the simulation"
    phase = "night" if frame.is_night else "day"
    return f"Elapsed {frame.elapsed}  |  Day {frame.day}, {phase} ({frame.daylight:.0%} light)"


# --- the panel ----------------------------------------------------------------------


def _separator(parent: QWidget) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


class ControlsPanel(QWidget):
    def __init__(self, context: ViewerContext) -> None:
        super().__init__()
        self.context = context
        self.controller = context.controller
        self._attached = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(2)
        actions = context.actions
        self._make_actions()

        self.buttons: dict[str, QToolButton] = {}
        self._group = QButtonGroup(self)  # exclusive, so clicking the checked one keeps it checked
        self._group.setExclusive(True)
        top = QHBoxLayout()
        top.setSpacing(4)
        for name in ("play_pause", "step", "step_day"):
            top.addWidget(self._action_button(actions[name]))
        top.addWidget(_separator(self))
        for speed in SPEED_ORDER:
            top.addWidget(self._speed_button(speed))
        top.addWidget(_separator(self))
        self._build_custom(top)
        top.addStretch(1)

        self.state = QLabel(self)
        self.clock = QLabel(self)
        self.asked = QLabel(self)
        self.got = QLabel(self)
        self.note = QLabel("The world is not drawn while fast-forwarding.", self)
        self.no_draw = QToolButton(self)
        self.no_draw.setDefaultAction(actions[NO_DRAW])
        self.no_draw.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.no_draw.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        for label in (self.state, self.clock, self.asked, self.got):
            bottom.addWidget(label)
        bottom.addStretch(1)
        bottom.addWidget(self.note)
        bottom.addWidget(self.no_draw)

        layout.addLayout(top)
        layout.addLayout(bottom)

        self.controller.status_changed.connect(self._on_status)
        self.controller.frame_received.connect(self._show_clock)
        self.controller.backend_failed.connect(lambda _text: self._set_enabled(False))
        actions[NO_DRAW].toggled.connect(lambda _on: self._on_status(self.controller.status))
        self._on_status(self.controller.status)
        self._show_clock(self.controller.frame)

    # -- building

    def _make_actions(self) -> None:
        """Make the actions this panel adds to the window's (the window's own are in the dict)."""
        context = self.context

        def make(name: str, text: str, slot, tip: str, checkable: bool = False) -> None:
            if name in context.actions:
                return
            action = QAction(text, self)
            action.setToolTip(tip)
            action.setStatusTip(tip)
            action.setCheckable(checkable)
            keys = KEY_MAP.get(name)
            if keys:
                action.setShortcuts([QKeySequence(key) for key in keys])
            if checkable:
                action.toggled.connect(slot)
            else:
                action.triggered.connect(slot)
            context.actions[name] = action

        speed_max = context.actions.get(f"speed_{MAX_SPEED}")
        if speed_max is not None:  # the window made this one; the key map is ours
            speed_max.setShortcuts([QKeySequence(key) for key in KEY_MAP["speed_max"]])
        make("step_day", "Step a &day", self._step_day, "Run one simulated day, then pause")
        make("speed_faster", "&Faster", lambda: self._nudge(1), "The next faster speed")
        make("speed_slower", "S&lower", lambda: self._nudge(-1), "The next slower speed")
        make(
            NO_DRAW,
            "Don't draw when fast",
            lambda _on: None,
            "Stop drawing the world at a decade a second and faster, so all the time goes to "
            "the simulation. The charts keep updating.",
            checkable=True,
        )

    def _action_button(self, action: QAction) -> QToolButton:
        button = QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def _speed_button(self, speed: str) -> QToolButton:
        action = self.context.actions[f"speed_{speed}"]
        button = QToolButton(self)
        button.setText(BUTTON_TEXT[speed])
        button.setToolTip(action.text().replace("&", ""))
        button.setCheckable(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda _checked=False, a=action: a.trigger())
        self._group.addButton(button)
        self.buttons[speed] = button
        return button

    def _build_custom(self, row: QHBoxLayout) -> None:
        self.custom_value = QDoubleSpinBox(self)
        self.custom_value.setRange(0.01, 100_000.0)
        self.custom_value.setDecimals(2)
        self.custom_value.setValue(1.0)
        self.custom_value.setToolTip("A speed of your own: this much simulated time a second")
        self.custom_unit = QComboBox(self)
        for name, seconds in CUSTOM_UNITS:
            self.custom_unit.addItem(name, seconds)
        self.custom_unit.setCurrentText("days")
        self.custom_set = QToolButton(self)
        self.custom_set.setText("Set speed")
        self.custom_set.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.custom_set.clicked.connect(self.apply_custom_speed)
        self.custom_value.lineEdit().returnPressed.connect(self.apply_custom_speed)
        for widget in (self.custom_value, self.custom_unit, self.custom_set):
            row.addWidget(widget)

    # -- keeping the window's actions in one place

    def _attach(self) -> None:
        """Put the shortcuts on the main window (and in its Run menu), not on this dock, so the
        keys still work when the dock is closed or floating."""
        if self._attached:
            return
        window = self.parentWidget()
        while window is not None and not isinstance(window, QMainWindow):
            window = window.parentWidget()
        if window is None:
            return
        self._attached = True
        actions = self.context.actions
        for name in ("step_day", "speed_faster", "speed_slower"):
            window.addAction(actions[name])
        run_menu = getattr(window, "run_menu", None)
        if run_menu is None:
            return
        entries = run_menu.actions()
        separator = next((a for a in entries if a.isSeparator()), None)
        run_menu.insertAction(separator, actions["step_day"])
        speed_menu = next((a.menu() for a in entries if a.menu() is not None), None)
        if speed_menu is not None:
            speed_menu.addSeparator()
            for name in ("speed_faster", "speed_slower", NO_DRAW):
                speed_menu.addAction(actions[name])

    def event(self, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.ParentChange, QEvent.Type.Show):
            self._attach()
        return super().event(event)

    # -- doing

    def _step_day(self) -> None:
        self.context.send(Step(ticks_per_day(self.controller.frame)))

    def _nudge(self, direction: int) -> None:
        name = neighbour_speed(self.controller.status, direction)
        if name is None:
            self.context.show_message(
                "Already at the " + ("fastest" if direction > 0 else "slowest")
            )
            return
        self.context.send(SetSpeed(name))

    def apply_custom_speed(self) -> None:
        seconds = self.custom_unit.currentData()
        self.context.send(SetSpeed(self.custom_value.value() * seconds))

    # -- showing

    def _set_enabled(self, enabled: bool) -> None:
        for button in self.buttons.values():
            button.setEnabled(enabled)
        for widget in (self.custom_value, self.custom_unit, self.custom_set):
            widget.setEnabled(enabled)
        for name in ("step_day", "speed_faster", "speed_slower"):
            self.context.actions[name].setEnabled(enabled)

    def _on_status(self, status: Status) -> None:
        self._group.setExclusive(False)  # an exclusive group cannot show "none" (a custom speed)
        for speed, button in self.buttons.items():
            button.setChecked(speed == status.speed_preset)
        self._group.setExclusive(True)
        self.state.setText(state_text(status))
        self.asked.setText(f"Speed asked: {asked_text(status)}")
        self.got.setText(f"got: {got_text(status)}")
        self.note.setVisible(world_drawing_paused(self.context.actions, status))

    def _show_clock(self, frame: Frame | None) -> None:
        self.clock.setText(clock_text(frame))


def build(context: ViewerContext) -> ControlsPanel:
    return ControlsPanel(context)


PANEL = PanelSpec(id="controls", title="Controls", area="top", factory=build, order=10)
