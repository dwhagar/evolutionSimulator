"""The viewer shell (UX.11), run on Qt's offscreen platform against ``FakeSimulation``."""

import logging

import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)

from evolution_simulator.session import (
    CommandError,
    FakeSimulation,
    Play,
    Select,
    Session,
    SessionRules,
    SetSpeed,
    Status,
    Step,
)
from evolution_simulator.viewer import registry
from evolution_simulator.viewer.app import main, parse_args
from evolution_simulator.viewer.backend import Batch, LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.registry import PanelSpec, discover_panels
from evolution_simulator.viewer.window import MainWindow, format_speed


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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
def settings(tmp_path):
    return QtCore.QSettings(str(tmp_path / "viewer.ini"), QtCore.QSettings.Format.IniFormat)


@pytest.fixture
def window(controller, settings):
    win = MainWindow(controller, run_label="fake, seed 3", settings=settings)
    win.show()
    yield win
    win.close()


def record(signal):
    got = []
    signal.connect(got.append)
    return got


# --- finding the panels ------------------------------------------------------------


def test_the_shell_ships_a_placeholder_in_each_default_slot(qapp):
    specs = {spec.id: spec for spec in discover_panels()}
    assert {sid: spec.area for sid, spec in specs.items()}.items() >= {
        "world": "center",
        "controls": "top",
        "inspector": "right",
        "charts": "right",
    }.items()
    right = [spec.id for spec in discover_panels() if spec.area == "right"]
    assert right == ["inspector", "charts"]


def test_a_module_that_fails_to_import_is_skipped_and_logged(qapp, monkeypatch, caplog):
    class Info:
        name = "no_such_screen"

    real = registry.pkgutil.iter_modules
    monkeypatch.setattr(registry.pkgutil, "iter_modules", lambda path: [Info(), *real(path)])
    with caplog.at_level(logging.ERROR):
        specs = discover_panels()
    assert "no_such_screen" in caplog.text
    assert {spec.id for spec in specs} >= {"world", "controls", "inspector", "charts"}


def test_two_panels_with_one_id_are_refused(qapp, monkeypatch):
    spec = PanelSpec("world", "World", "center", lambda ctx: None)

    class Module:
        PANEL = (spec, spec)

    class Info:
        name = "twice"

    monkeypatch.setattr(registry.pkgutil, "iter_modules", lambda path: [Info()])
    monkeypatch.setattr(registry.importlib, "import_module", lambda name: Module)
    with pytest.raises(ValueError, match="share the id"):
        discover_panels()


# --- the controller ----------------------------------------------------------------


def test_the_controller_emits_frames_and_status_and_keeps_the_latest(controller, clock):
    frames, statuses = record(controller.frame_received), record(controller.status_changed)
    controller.poll()  # a paused session still publishes its first frame
    assert len(frames) == 1 and controller.frame is frames[0]
    assert controller.plants is not None and controller.plants.count == 100
    assert frames[0].animal_count == 30

    controller.send(SetSpeed("day"))
    controller.send(Play())
    assert statuses[-1].running and statuses[-1].speed_preset == "day"
    assert controller.status.running and controller.status.speed_preset == "day"
    clock.advance(0.5)
    controller.poll()
    assert controller.frame.tick == 12


def test_a_frame_without_plants_leaves_the_last_plants_in_place(controller, clock):
    controller.poll()
    first = controller.plants
    controller.send(SetSpeed("day"))
    controller.send(Play())
    clock.advance(0.1)  # under the plant interval, so this frame carries none
    controller.poll()
    assert controller.frame.plants is None
    assert controller.plants is first


def test_a_refused_command_is_reported_and_changes_nothing(controller):
    failures = record(controller.command_failed)
    assert controller.send(SetSpeed("sometimes")) is False
    assert controller.send(Select(10**9)) is False
    assert len(failures) == 2 and "Unknown speed" in failures[0]
    assert not controller.status.running


def test_a_backend_that_raises_stops_polling_and_says_so(qapp):
    class Broken:
        status = Status(False, 0, 1.0, "real-time", None, False, 0, None)

        def send(self, command):
            raise CommandError("no")

        def poll(self):
            raise RuntimeError("boom")

    controller = ViewerController(Broken())
    failures = record(controller.backend_failed)
    controller.start()
    assert controller.polling
    controller.poll()
    assert failures == ["RuntimeError: boom"] and not controller.polling


def test_the_timer_polls_without_being_asked(controller, qapp):
    frames = record(controller.frame_received)
    controller.start()
    deadline = QtCore.QDeadlineTimer(2000)
    while not frames and not deadline.hasExpired():
        qapp.processEvents()
    controller.stop()
    assert frames


def test_the_local_backend_reports_events_once(clock):
    session = Session(FakeSimulation(30, 10, seed=1, period=20), clock=clock)
    backend = LocalBackend(session)
    session.handle(Step(40))
    batch = backend.poll()
    assert isinstance(batch, Batch) and batch.events and not batch.empty
    assert not backend.poll().events
    backend.close()


# --- the window --------------------------------------------------------------------


def test_the_window_puts_each_panel_in_its_slot(window):
    assert set(window.panels) >= {"world", "controls", "inspector", "charts"}
    assert window.centralWidget() is window.panels["world"]
    assert set(window.docks) >= {"controls", "inspector", "charts"}
    areas = {sid: window.dockWidgetArea(dock) for sid, dock in window.docks.items()}
    assert areas["controls"] == QtCore.Qt.DockWidgetArea.TopDockWidgetArea
    assert areas["inspector"] == areas["charts"] == QtCore.Qt.DockWidgetArea.RightDockWidgetArea
    assert window.windowTitle() == "Evolution Simulator - fake, seed 3"


def test_the_menus_are_there_and_every_dock_can_be_toggled_from_the_view_menu(window):
    titles = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert titles == ["File", "Run", "View", "Help"]
    toggles = [
        a for a in window.view_menu.actions() if a.text() in ("Controls", "Inspector", "Charts")
    ]
    assert len(toggles) == 3
    charts = next(a for a in toggles if a.text() == "Charts")
    charts.trigger()
    assert window.docks["charts"].isHidden()
    charts.trigger()
    assert not window.docks["charts"].isHidden()


def test_the_panels_follow_the_frames(window, controller):
    controller.poll()
    world = window.panels["world"]
    assert "30 animals" in world.live.text() and "100 plants" in world.live.text()
    counts = window.status_labels["counts"].text()
    assert "Animals 30" in counts and "Plants 100" in counts
    assert "Tick 0" in window.status_labels["clock"].text()


def test_a_panel_built_after_the_first_frame_starts_from_it(controller, settings, qapp):
    controller.poll()
    win = MainWindow(controller, settings=settings)
    assert "30 animals" in win.panels["world"].live.text()
    win.close()


def test_the_run_menu_drives_the_session(window, controller, clock):
    actions = window.actions
    assert actions["play_pause"].text() == "&Play"
    actions["speed_day"].trigger()
    assert controller.status.speed_preset == "day" and actions["speed_day"].isChecked()
    actions["play_pause"].trigger()
    assert controller.status.running and actions["play_pause"].text() == "&Pause"
    clock.advance(0.5)
    controller.poll()
    assert "Speed day/s" in window.status_labels["speed"].text()
    actions["play_pause"].trigger()
    assert not controller.status.running
    ticks = controller.backend.session.simulation.tick
    actions["step"].trigger()
    controller.poll()
    assert controller.backend.session.simulation.tick == ticks + 1
    actions["speed_max"].trigger()
    assert actions["speed_max"].isChecked() and not actions["speed_day"].isChecked()
    assert "as fast as possible" in window.status_labels["speed"].text()


def test_a_refused_command_shows_on_the_status_bar(window, controller):
    controller.send(SetSpeed("sometimes"))
    assert "Unknown speed" in window.statusBar().currentMessage()


def test_a_dead_backend_disables_the_run_actions(controller, settings, qapp):
    controller.backend.poll = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    win = MainWindow(controller, settings=settings)
    controller.poll()
    assert "boom" in win.statusBar().currentMessage()
    assert not win.actions["play_pause"].isEnabled() and not win.actions["step"].isEnabled()
    win.close()


def test_a_panel_that_fails_to_build_is_replaced_by_a_message(controller, settings, qapp):
    def broken(context):
        raise RuntimeError("no screen today")

    specs = [
        PanelSpec("world", "World", "center", broken),
        PanelSpec("side", "Side", "right", broken),
    ]
    win = MainWindow(controller, settings=settings, specs=specs)
    assert "no screen today" in win.panels["world"].text()
    assert "Side" in win.panels["side"].text()
    win.close()


def test_only_one_panel_can_take_the_centre(controller, settings, qapp):
    one = PanelSpec("a", "A", "center", lambda ctx: None)
    two = PanelSpec("b", "B", "center", lambda ctx: None)
    with pytest.raises(ValueError, match="centre"):
        MainWindow(controller, settings=settings, specs=[one, two])


def test_the_layout_is_remembered_and_can_be_reset(controller, settings, qapp):
    first = MainWindow(controller, settings=settings)
    first.show()
    first.docks["charts"].hide()
    first.docks["inspector"].setFloating(True)
    first.close()

    second = MainWindow(controller, settings=settings)
    second.show()
    assert second.docks["charts"].isHidden()
    assert second.docks["inspector"].isFloating()

    second.reset_layout()
    assert not second.docks["charts"].isHidden()
    assert not second.docks["inspector"].isFloating()
    assert settings.value("window/state") is None
    second.close()


def test_a_saved_layout_from_another_version_is_ignored(controller, settings, qapp):
    settings.setValue("window/state", QtCore.QByteArray(b"not a layout"))
    win = MainWindow(controller, settings=settings)
    assert set(win.docks) >= {"controls", "inspector", "charts"}  # the default layout stands
    assert not win.docks["charts"].isHidden()
    win.close()


def test_the_about_box_opens(window):
    window.actions["about"].trigger()
    boxes = window.findChildren(
        QtCore.QObject, options=QtCore.Qt.FindChildOption.FindDirectChildrenOnly
    )
    assert any(type(box).__name__ == "QMessageBox" for box in boxes)


def test_format_speed_names_the_preset_the_achieved_speed_and_when_behind():
    base = Status(True, 0, 86_400.0, "day", 3_600.0, False, 0, None)
    assert format_speed(base) == "Speed day/s, got 01:00:00/s"
    assert format_speed(Status(True, 0, 123.0, None, 90.0, True, 4, None)) == (
        "Speed 00:02:03/s, got 00:01:30/s (behind)"
    )
    assert format_speed(Status(False, 0, None, "max", None, False, 0, None)) == (
        "Speed as fast as possible"
    )


# --- the command line --------------------------------------------------------------


def test_the_command_line_defaults_to_the_fake_simulation():
    args = parse_args([])
    assert not args.world and args.seed == 0 and args.quit_after is None


def test_main_opens_the_window_and_returns_when_it_closes(qapp, tmp_path):
    code = main(["--quit-after", "50", "--settings", str(tmp_path / "layout.ini")])
    assert code == 0
    assert (tmp_path / "layout.ini").exists()  # the layout was saved on close


def test_main_can_run_the_real_world(qapp, tmp_path):
    code = main(
        [
            "--world",
            "--animals",
            "5",
            "--plants",
            "20",
            "--quit-after",
            "50",
            "--settings",
            str(tmp_path / "layout.ini"),
        ]
    )
    assert code == 0
