"""The time and speed controls (UX.13), on Qt's offscreen platform against ``FakeSimulation``."""

import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
QtTest = pytest.importorskip("PySide6.QtTest", exc_type=ImportError)

from evolution_simulator.session import (
    MAX_SPEED,
    FakeSimulation,
    Session,
    SessionRules,
    SetSpeed,
    Status,
)
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.panels import controls
from evolution_simulator.viewer.window import MainWindow
from evolution_simulator.world.timescale import DAY, SPEED_PRESETS


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def status(**changes):
    base = {
        "running": False,
        "steps_left": 0,
        "speed_asked": 3_600.0,
        "speed_preset": "hour",
        "speed_achieved": None,
        "behind": False,
        "ticks_dropped": 0,
        "selected": None,
    }
    return Status(**{**base, **changes})


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def controller(qapp, clock):
    session = Session(
        FakeSimulation(30, 100, seed=3), rules=SessionRules(work_budget=10.0), clock=clock
    )
    backend = LocalBackend(session)
    yield ViewerController(backend)
    backend.close()


@pytest.fixture
def window(controller, tmp_path):
    settings = QtCore.QSettings(str(tmp_path / "viewer.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(controller, settings=settings)
    win.show()
    yield win
    win.close()


@pytest.fixture
def panel(window):
    return window.panels["controls"]


def press(window, key, modifier=QtCore.Qt.KeyboardModifier.NoModifier):
    window.activateWindow()
    QtTest.QTest.qWaitForWindowActive(window)
    QtTest.QTest.keyClick(window, key, modifier)


# --- plain logic -------------------------------------------------------------------


def test_neighbour_speed_walks_the_presets_and_stops_at_the_ends():
    assert controls.neighbour_speed(status(), 1) == "day"
    assert controls.neighbour_speed(status(), -1) == "minute"
    first = status(speed_asked=1.0, speed_preset="real-time")
    assert controls.neighbour_speed(first, -1) is None
    top = status(speed_asked=SPEED_PRESETS["millennium"], speed_preset="millennium")
    assert controls.neighbour_speed(top, 1) == MAX_SPEED
    fastest = status(speed_asked=None, speed_preset=MAX_SPEED)
    assert controls.neighbour_speed(fastest, 1) is None
    assert controls.neighbour_speed(fastest, -1) == "millennium"


def test_a_custom_speed_moves_to_the_nearest_preset_on_that_side():
    custom = status(speed_asked=2 * DAY, speed_preset=None)
    assert controls.neighbour_speed(custom, 1) == "week"
    assert controls.neighbour_speed(custom, -1) == "day"


def test_ticks_per_day_follows_the_tick_length_the_frames_imply():
    class F:
        tick = 10
        simulated_seconds = 10 * 3_600.0

    assert controls.ticks_per_day(None) == 24
    assert controls.ticks_per_day(F()) == 24
    F.simulated_seconds = 10 * 60.0  # a one-minute tick
    assert controls.ticks_per_day(F()) == 1_440
    F.simulated_seconds = 10 * 2 * DAY  # a tick longer than a day still steps at least one
    assert controls.ticks_per_day(F()) == 1


def test_the_readouts_say_asked_got_and_behind():
    running = status(running=True, speed_achieved=3_600.0, speed_preset="day", speed_asked=DAY)
    assert controls.asked_text(running) == "day/s"
    assert controls.got_text(running) == "01:00:00/s"
    assert controls.got_text(status(running=True, speed_achieved=60.0, behind=True)).endswith(
        "(behind)"
    )
    assert controls.got_text(status()) == "-"
    assert controls.asked_text(status(speed_asked=None, speed_preset=MAX_SPEED)) == (
        "as fast as possible"
    )
    assert controls.state_text(status()) == "Paused"
    assert controls.state_text(status(steps_left=3)) == "Stepping, 3 left"
    assert controls.state_text(status(running=True)) == "Running"


def test_only_a_decade_a_second_and_faster_is_a_fast_forward():
    assert not controls.is_fast_forward(status(speed_asked=SPEED_PRESETS["year"]))
    assert controls.is_fast_forward(status(speed_asked=SPEED_PRESETS["decade"]))
    assert controls.is_fast_forward(status(speed_asked=None))


# --- the panel ---------------------------------------------------------------------


def test_the_panel_replaces_the_placeholder_in_the_top_dock(window):
    assert type(window.panels["controls"]).__name__ == "ControlsPanel"
    area = window.dockWidgetArea(window.docks["controls"])
    assert area == QtCore.Qt.DockWidgetArea.TopDockWidgetArea
    assert controls.PANEL.id == "controls" and controls.PANEL.area == "top"


def test_every_preset_and_max_has_a_button_that_sets_the_speed(panel, controller):
    assert list(panel.buttons) == [*SPEED_PRESETS, MAX_SPEED]
    for name, button in panel.buttons.items():
        button.click()
        assert controller.status.speed_preset == name
        assert button.isChecked()
        assert [n for n, b in panel.buttons.items() if b.isChecked()] == [name]


def test_the_checked_button_follows_the_menu(panel, window, controller):
    window.actions["speed_week"].trigger()
    assert panel.buttons["week"].isChecked()
    controller.send(SetSpeed(1234.0))  # no preset has this speed
    assert not any(b.isChecked() for b in panel.buttons.values())


def test_play_and_step_share_the_windows_actions(panel, window, controller, clock):
    controller.poll()
    buttons = {
        b.defaultAction(): b
        for b in panel.findChildren(QtCore.QObject)
        if hasattr(b, "defaultAction")
    }
    play, step = window.actions["play_pause"], window.actions["step"]
    assert play in buttons and step in buttons  # the buttons are the window's own actions
    assert panel.state.text() == "Paused"
    play.trigger()
    assert panel.state.text() == "Running"
    play.trigger()
    ticks = controller.backend.session.simulation.tick
    step.trigger()
    controller.poll()
    assert controller.backend.session.simulation.tick == ticks + 1


def test_step_a_day_runs_a_day_of_ticks_and_pauses(window, controller):
    controller.poll()
    start = controller.backend.session.simulation.tick
    window.actions["step_day"].trigger()
    controller.poll()
    assert controller.backend.session.simulation.tick == start + 24
    assert not controller.status.running


def test_speed_asked_is_shown_next_to_speed_got(panel, window, controller, clock):
    window.actions["speed_day"].trigger()
    window.actions["play_pause"].trigger()
    assert panel.asked.text() == "Speed asked: day/s"
    clock.advance(0.5)
    controller.poll()
    clock.advance(0.6)
    controller.poll()
    assert panel.got.text().startswith("got: ") and panel.got.text() != "got: -"
    window.actions["play_pause"].trigger()
    assert panel.got.text() == "got: -"


def test_the_clock_and_day_night_readout_follow_the_frames(panel, window, controller, clock):
    assert panel.clock.text() == "Waiting for the simulation"
    controller.poll()
    assert (
        "Elapsed" in panel.clock.text()
        and ", day (" in panel.clock.text()
        or "night (" in (panel.clock.text())
    )
    window.actions["speed_day"].trigger()
    window.actions["play_pause"].trigger()
    clock.advance(0.5)
    controller.poll()
    frame = controller.frame
    assert frame.elapsed in panel.clock.text()
    assert f"Day {frame.day}" in panel.clock.text()


def test_a_custom_speed_is_sent_in_simulated_seconds(panel, controller):
    panel.custom_value.setValue(3.0)
    panel.custom_unit.setCurrentText("hours")
    panel.custom_set.click()
    assert controller.status.speed_asked == 3 * 3_600.0
    assert controller.status.speed_preset is None
    panel.custom_value.setValue(1.0)
    panel.custom_unit.setCurrentText("days")
    panel.apply_custom_speed()
    assert controller.status.speed_preset == "day"


def test_no_draw_switch_and_the_note(panel, window, controller):
    actions = window.actions
    assert panel.note.isHidden()
    status_now = controller.status
    assert not controls.world_drawing_paused(actions, status_now)
    actions[controls.NO_DRAW].setChecked(True)
    actions["speed_decade"].trigger()
    assert panel.note.isHidden()  # not running yet
    actions["play_pause"].trigger()
    assert not panel.note.isHidden()
    assert controls.world_drawing_paused(actions, controller.status)
    actions["speed_year"].trigger()  # slow enough to watch again
    assert panel.note.isHidden()
    assert not controls.world_drawing_paused(actions, controller.status)
    actions["speed_max"].trigger()
    assert controls.world_drawing_paused(actions, controller.status)
    actions[controls.NO_DRAW].setChecked(False)
    assert not controls.world_drawing_paused(actions, controller.status)
    assert panel.note.isHidden()


def test_a_dead_backend_disables_the_controls(controller, tmp_path, qapp):
    controller.backend.poll = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    settings = QtCore.QSettings(str(tmp_path / "v.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(controller, settings=settings)
    controller.poll()
    panel = win.panels["controls"]
    assert not any(b.isEnabled() for b in panel.buttons.values())
    assert not panel.custom_set.isEnabled()
    assert not win.actions["step_day"].isEnabled()
    win.close()


# --- the keyboard ------------------------------------------------------------------


def test_every_key_in_the_map_is_on_an_action_and_no_key_is_used_twice(window):
    seen = {}
    for name, keys in controls.KEY_MAP.items():
        assert [k.toString() for k in window.actions[name].shortcuts()] == list(keys)
        for key in keys:
            assert key not in seen, f"{key} is on {seen[key]} and {name}"
            seen[key] = name


def test_the_new_actions_are_in_the_run_menu(window):
    titles = {a.text().replace("&", "") for a in window.run_menu.actions()}
    assert "Step a day" in titles
    speed_menu = next(a.menu() for a in window.run_menu.actions() if a.menu() is not None)
    speed_titles = {a.text().replace("&", "") for a in speed_menu.actions()}
    assert {"Faster", "Slower", "Don't draw when fast"} <= speed_titles


def test_the_keys_drive_the_session(window, controller):
    controller.poll()
    press(window, QtCore.Qt.Key.Key_Space)
    assert controller.status.running
    press(window, QtCore.Qt.Key.Key_Space)
    assert not controller.status.running

    start = controller.backend.session.simulation.tick
    press(window, QtCore.Qt.Key.Key_Right)
    controller.poll()
    assert controller.backend.session.simulation.tick == start + 1
    press(window, QtCore.Qt.Key.Key_Right, QtCore.Qt.KeyboardModifier.ShiftModifier)
    controller.poll()
    assert controller.backend.session.simulation.tick == start + 25

    press(window, QtCore.Qt.Key.Key_Plus)
    assert controller.status.speed_preset == "minute"  # one up from the real-time default
    press(window, QtCore.Qt.Key.Key_Plus)
    assert controller.status.speed_preset == "hour"
    press(window, QtCore.Qt.Key.Key_Minus)
    assert controller.status.speed_preset == "minute"
    press(window, QtCore.Qt.Key.Key_M)
    assert controller.status.speed_preset == MAX_SPEED


def test_faster_and_slower_say_so_at_the_ends(window, controller):
    controller.send(SetSpeed(MAX_SPEED))
    window.actions["speed_faster"].trigger()
    assert "fastest" in window.statusBar().currentMessage()
    controller.send(SetSpeed("real-time"))
    window.actions["speed_slower"].trigger()
    assert "slowest" in window.statusBar().currentMessage()


def test_the_panel_works_alone_without_a_window(controller, qapp):
    from evolution_simulator.viewer.registry import ViewerContext

    actions = {}
    from PySide6.QtGui import QAction

    for name in ("play_pause", "step", *(f"speed_{s}" for s in (*SPEED_PRESETS, MAX_SPEED))):
        actions[name] = QAction(name)
    context = ViewerContext(controller, actions, lambda text, ms: None)
    widget = controls.build(context)
    assert "step_day" in actions and widget.clock.text() == "Waiting for the simulation"
