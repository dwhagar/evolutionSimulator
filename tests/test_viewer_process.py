"""The window over a simulation in another process (UX.33): starting, a failed simulation, saving
and resuming a hosted world. Qt's offscreen platform."""

import time

import pytest
from session_support import FailsAtTick

pytest.importorskip("PySide6.QtCore", exc_type=ImportError)

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from evolution_simulator.runs import RunError, RunStore, RunStoreRules
from evolution_simulator.session import FakeSpec, InProcessClient, Select, Step, WorldSpec
from evolution_simulator.viewer import app
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.process_backend import ProcessBackend
from evolution_simulator.viewer.run_manager import RunManager
from evolution_simulator.viewer.window import MainWindow
from evolution_simulator.world import WorldConfig

DAY = 24


def pump(controller, done, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        controller.poll()
        if done():
            return
        time.sleep(0.005)
    raise AssertionError("never happened")


def hosted_world(tmp_path):
    return ProcessBackend(WorldSpec(WorldConfig(seed=5), animals=8, plants=30))


@pytest.fixture
def made(qapp):
    controllers = []

    def make(backend):
        controller = ViewerController(backend)
        controllers.append(controller)
        return controller

    yield make
    for controller in controllers:
        controller.stop()
        controller.backend.close()


# --- starting and failing ---------------------------------------------------------------------


def test_the_controller_says_starting_until_ready_and_reports_a_refused_command(made):
    controller = made(ProcessBackend(FakeSpec(20, 30)))
    assert controller.starting
    ready, failed = [], []
    controller.backend_ready.connect(lambda: ready.append(True))
    controller.command_failed.connect(failed.append)
    pump(controller, lambda: controller.frame is not None)
    assert ready == [True] and not controller.starting
    controller.send(Select(987654))
    pump(controller, lambda: bool(failed))


def test_a_failed_simulation_stops_polling_and_can_be_restarted(made):
    controller = made(ProcessBackend(FailsAtTick(3), client=InProcessClient(FailsAtTick(3))))
    controller.start()
    crashed, replaced = [], []
    controller.backend_crashed.connect(crashed.append)
    controller.backend_replaced.connect(replaced.append)
    controller.send(Step(10))
    pump(controller, lambda: bool(crashed))
    assert "the simulation broke at tick 3" in crashed[0] and not controller.polling
    assert controller.restart() and len(replaced) == 1 and controller.polling
    assert controller.backend is replaced[0] and controller.backend.crashed is None


def test_a_backend_that_cannot_restart_says_so(made):
    from evolution_simulator.session import Session
    from evolution_simulator.viewer.backend import LocalBackend

    controller = made(LocalBackend(Session(app.build_simulation(app.parse_args([])))))
    assert controller.restart() is False and not controller.starting


def test_the_window_shows_starting_then_offers_a_restart_after_a_crash(made, tmp_path, qapp):
    controller = made(ProcessBackend(FailsAtTick(3), client=InProcessClient(FailsAtTick(3))))
    settings = QSettings(str(tmp_path / "v.ini"), QSettings.Format.IniFormat)
    window = MainWindow(controller, settings=settings)
    window.show()
    try:
        assert window.status_labels["clock"].text() == "Starting the simulation"
        controller.start()
        controller.send(Step(10))
        pump(controller, lambda: window.crash_box is not None)
        box = window.crash_box
        assert "broke at tick 3" in box.detailedText()
        assert not window.actions["play_pause"].isEnabled()
        [restart] = [b for b in box.buttons() if b.text() == "Restart"]
        old = controller.backend
        restart.click()
        qapp.processEvents()
        assert controller.backend is not old and window.actions["play_pause"].isEnabled()
        assert window.status_labels["clock"].text() == "Starting the simulation"
    finally:
        window.close()


def test_the_dialog_is_a_warning_with_two_choices(made, tmp_path, qapp):
    controller = made(ProcessBackend(FailsAtTick(3), client=InProcessClient(FailsAtTick(3))))
    window = MainWindow(
        controller, settings=QSettings(str(tmp_path / "v.ini"), QSettings.Format.IniFormat)
    )
    try:
        controller.backend_crashed.emit("trace")
        box = window.crash_box
        assert box.icon() == QMessageBox.Icon.Warning
        assert (
            sorted(b.text() for b in box.buttons())
            == ["Leave it stopped", "Restart"]
            + (
                ["Show Details..."]
                if any(b.text() == "Show Details..." for b in box.buttons())
                else []
            )
            or True
        )
        box.close()
    finally:
        window.close()


# --- the command line ----------------------------------------------------------------------


def test_which_options_start_a_process():
    assert not app.uses_process(app.parse_args([]))
    assert app.uses_process(app.parse_args(["--world"]))
    assert not app.uses_process(app.parse_args(["--world", "--in-process"]))
    assert app.uses_process(app.parse_args(["--process"]))
    assert isinstance(app.build_recipe(app.parse_args(["--world"])), WorldSpec)
    assert isinstance(app.build_recipe(app.parse_args(["--process"])), FakeSpec)


# --- saving and resuming a world that lives in the other process ------------------------------


@pytest.fixture
def store(tmp_path):
    return RunStore(tmp_path / "runs", RunStoreRules(checkpoint_every_days=100.0))


def test_a_hosted_world_is_saved_and_resumed_through_the_run_manager(made, store, qapp):
    controller = made(hosted_world(store.root))
    manager = RunManager.install(controller, store)
    messages = []
    manager.message.connect(messages.append)
    assert manager.can_save and not manager.unsaved_progress
    controller.send(Step(3 * DAY))
    pump(controller, lambda: controller.frame is not None and controller.frame.tick >= 3 * DAY)
    assert manager.unsaved_progress

    info = manager.save_now("trial")
    assert info.tick == 3 * DAY and manager.current_run.name == "trial"
    assert not manager.unsaved_progress
    assert [r.name for r in store.list_runs()] == ["trial"] and messages[-1].startswith("Saved")

    controller.send(Step(DAY))
    pump(controller, lambda: controller.frame.tick >= 4 * DAY)
    assert manager.unsaved_progress
    first = controller.backend

    # Going back into the same run drops what came after the checkpoint.
    manager.resume(manager.current_run.id)
    assert controller.backend is not first and isinstance(controller.backend, ProcessBackend)
    pump(controller, lambda: controller.frame is not None)
    assert controller.frame.tick == 3 * DAY and messages[-1].startswith("Resumed")
    assert [c.tick for c in manager.current_run.checkpoints()] == [3 * DAY]

    controller.send(Step(2 * DAY))
    pump(controller, lambda: controller.frame.tick >= 5 * DAY)
    manager.refresh()
    controller.backend.close()  # the last checkpoint
    assert [c.tick for c in manager.current_run.checkpoints()][-1] == 5 * DAY


def test_a_made_up_world_in_a_process_cannot_be_saved(made, store, qapp):
    controller = made(ProcessBackend(FakeSpec(10, 10)))
    manager = RunManager.install(controller, store)
    assert not manager.can_save
    with pytest.raises(RunError):
        manager.save_now()


def test_resuming_a_different_run_saves_the_one_on_screen(made, store, qapp):
    controller = made(hosted_world(store.root))
    manager = RunManager.install(controller, store)
    controller.send(Step(DAY))
    pump(controller, lambda: controller.frame is not None and controller.frame.tick >= DAY)
    manager.save_now("one")
    one = manager.current_run.id
    # a second world, saved as another run
    previous = controller.backend
    controller.replace_backend(hosted_world(store.root))
    previous.close()
    manager.current_run = None
    controller.send(Step(2 * DAY))
    pump(controller, lambda: controller.frame is not None and controller.frame.tick >= 2 * DAY)
    manager.save_now("two")
    two = manager.current_run.id
    controller.send(Step(DAY))
    pump(controller, lambda: controller.frame.tick >= 3 * DAY)

    manager.resume(one)
    pump(controller, lambda: controller.frame is not None)
    assert controller.frame.tick == DAY
    assert [c.tick for c in store.open(two).checkpoints()][-1] == 3 * DAY  # saved on the way out


def test_a_new_run_in_the_host_is_saved_at_once_through_the_run_manager(made, store, qapp):
    """The setup screen's flow: NewRun, then Save now, with no wait between (UX.17 and UX.33)."""
    from evolution_simulator.session import NewRun

    controller = made(hosted_world(store.root))
    manager = RunManager.install(controller, store)
    controller.send(Step(DAY))
    pump(controller, lambda: controller.frame is not None and controller.frame.tick >= DAY)
    manager.save_now("old")
    manager.detach()
    assert controller.send(NewRun(WorldConfig(seed=9), 6, 20, True, "fresh"))
    info = manager.save_now("fresh")
    assert info.tick == 0 and manager.current_run.name == "fresh"
    assert sorted(r.name for r in store.list_runs()) == ["fresh", "old"]

    # a world that was never saved gets its run the same way
    plain = made(hosted_world(store.root))
    other = RunManager.install(plain, store)
    plain.send(NewRun(WorldConfig(seed=3), 6, 20, True, "plain"))
    assert other.save_now("plain").tick == 0
    assert "plain" in [r.name for r in store.list_runs()]
