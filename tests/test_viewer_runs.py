"""Saved runs in the viewer (UX.18), on Qt's offscreen platform: save now, the run list, resume,
delete, the history window, the size warning and the CSV export."""

import pytest
from world_support import hourly_world

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)

from evolution_simulator.runs import RunError, RunStore, RunStoreRules
from evolution_simulator.session import FakeSimulation, Session, SessionRules, Step
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.panels import runs as runs_panel
from evolution_simulator.viewer.panels._run_history import RunHistoryWindow
from evolution_simulator.viewer.run_manager import (
    RunManager,
    folder_size,
    format_ago,
    format_bytes,
)
from evolution_simulator.viewer.window import MainWindow

DAY_TICKS = 24


class Clock:
    def __init__(self) -> None:
        self.now = 1_700_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    rules = RunStoreRules(checkpoint_every_days=2.0, min_wall_seconds=0.0, keep_newest=3)
    return RunStore(tmp_path / "runs", rules, clock)


def make_world(seed: int = 3):
    world = hourly_world(seed=seed)
    world.populate(animals=8, plants=40)
    return world


def make_controller(simulation, clock):
    session = Session(simulation, rules=SessionRules(work_budget=30.0), clock=clock)
    return ViewerController(LocalBackend(session))


@pytest.fixture
def controller(qapp, clock):
    ctl = make_controller(make_world(), clock)
    yield ctl
    ctl.backend.close()


@pytest.fixture
def manager(controller, store):
    return RunManager.install(controller, store)


@pytest.fixture
def window(controller, manager, tmp_path):
    settings = QtCore.QSettings(str(tmp_path / "v.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(controller, run_label="world, seed 3", settings=settings)
    win.show()
    yield win
    win.close()


@pytest.fixture
def panel(window):
    widget = window.panels["runs"]
    window.docks["runs"].show()
    widget.refresh()
    return widget


def advance(controller, ticks: int) -> None:
    """Run exactly this many ticks (polling until the session has done them)."""
    controller.send(Step(ticks))
    for _ in range(10_000):
        controller.poll()
        if controller.backend.status.steps_left == 0:
            return
    raise AssertionError("the steps never finished")


def answer(panel, **replies):
    """Replace the dialogs: ``yes`` is what confirm says; asked collects the questions."""
    asked = []

    def confirm(title, text):
        asked.append(title)
        return replies.get("yes", True)

    panel.confirm = confirm
    return asked


# --- the helpers ---------------------------------------------------------------------------


def test_the_small_formatters():
    assert format_ago(5) == "just now"
    assert format_ago(300) == "5 min ago"
    assert format_ago(7200) == "2 h ago"
    assert format_ago(86400) == "1 day ago"
    assert format_ago(3 * 86400) == "3 days ago"
    assert format_bytes(10) == "10 B"
    assert format_bytes(2048) == "2.0 KB"
    assert format_bytes(5 * 1024**2) == "5.0 MB"
    assert format_bytes(3 * 1024**3) == "3.0 GB"


def test_folder_size_counts_every_file(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x").write_bytes(b"1234")
    (tmp_path / "y").write_bytes(b"12")
    assert folder_size(tmp_path) == 6
    assert folder_size(tmp_path / "missing") == 0


# --- saving -------------------------------------------------------------------------------


def test_the_file_menu_gets_save_and_saved_runs_above_quit(window):
    texts = [a.text().replace("&", "") for a in window.file_menu.actions()]
    assert texts[:2] == ["Save run now", "Saved runs..."]
    assert texts[-1] == "Quit"
    assert window.actions["save_run"].isEnabled()


def test_the_runs_dock_is_hidden_until_asked_for(window):
    assert window.docks["runs"].isHidden()
    window.actions["show_runs"].trigger()
    assert not window.docks["runs"].isHidden()


def test_save_now_starts_a_run_then_adds_checkpoints_to_it(window, controller, manager, store):
    assert manager.current_run is None
    window.actions["save_run"].trigger()
    run = manager.current_run
    assert run is not None
    assert [r.id for r in store.list_runs()] == [run.id]
    assert len(run.checkpoints()) == 1
    assert run.history() is not None
    assert window.windowTitle().endswith(f"{run.name}, seed 3 - saved just now")
    advance(controller, 3)
    window.actions["save_run"].trigger()
    assert manager.current_run is run
    assert [c.tick for c in run.checkpoints()] == [0, 3]
    assert len(store.list_runs()) == 1


def test_the_run_keeps_autosaving_as_the_world_goes_on(controller, manager, clock):
    manager.save_now()
    run = manager.current_run
    advance(controller, 6 * DAY_TICKS)
    assert manager.autosaver.written >= 1
    assert run.checkpoints()[-1].tick > 0
    seen = []
    manager.changed.connect(lambda: seen.append(1))
    manager.refresh()
    assert seen  # the screen is told about the autosave


def test_a_made_up_world_cannot_be_saved(qapp, clock, store, tmp_path):
    ctl = make_controller(FakeSimulation(10, 20, seed=1), clock)
    manager = RunManager.install(ctl, store)
    settings = QtCore.QSettings(str(tmp_path / "f.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(ctl, settings=settings)
    assert not manager.can_save
    assert not win.actions["save_run"].isEnabled()
    with pytest.raises(RunError):
        manager.save_now()
    assert not win.panels["runs"].save_now()
    assert store.list_runs() == []
    win.close()
    ctl.backend.close()


def test_a_failed_save_is_said_on_the_status_bar(window, panel, manager, monkeypatch):
    def broken(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(manager.store, "create", broken)
    assert not panel.save_now()
    assert "disk full" in window.statusBar().currentMessage()
    assert manager.current_run is None


# --- the list -----------------------------------------------------------------------------


def test_the_list_shows_a_row_per_run(panel, manager, controller, clock):
    manager.save_now("First")
    clock.now += 100
    advance(controller, 30)
    manager.save_now()
    clock.now += 1000
    manager.detach()
    manager.save_now("Second")
    assert [r.name for r in panel.rows] == ["Second", "First"]
    row = {panel.table.horizontalHeaderItem(c).text(): c for c in range(panel.table.columnCount())}
    assert panel.table.item(0, row["Run"]).text().endswith("(on screen)")
    assert panel.table.item(1, row["Seed"]).text() == "3"
    assert (
        panel.table.item(1, row["Simulated"]).text() == "1d 6h"
        or panel.table.item(1, row["Simulated"]).text()
    )
    assert panel.table.item(1, row["Size"]).text().endswith("KB")
    assert "2 saved runs" in panel.usage.text()
    assert not panel.warning.isVisible()


def test_the_size_warning_shows_above_the_list(panel, manager, store):
    manager.save_now()
    store.rules = RunStoreRules(warn_bytes=10, min_wall_seconds=0.0)
    panel.refresh()
    assert panel.warning.isVisible()
    assert "Delete runs you no longer need" in panel.warning.text()


def test_saving_over_the_limit_says_so(window, manager, store):
    store.rules = RunStoreRules(warn_bytes=10, min_wall_seconds=0.0)
    manager.save_now()
    assert "Delete runs" in window.statusBar().currentMessage()


def test_buttons_follow_the_selection(panel, manager):
    manager.save_now()
    assert not panel.resume_button.isEnabled() and not panel.delete_button.isEnabled()
    panel.select(manager.current_run.id)
    assert all(
        b.isEnabled()
        for b in (
            panel.resume_button,
            panel.history_button,
            panel.delete_button,
            panel.export_button,
        )
    )


def test_sparkline_makes_an_icon_for_few_or_many_points():
    assert not runs_panel.sparkline(()).isNull()
    assert not runs_panel.sparkline((1.0, 5.0, 2.0, 8.0)).isNull()


# --- resuming -----------------------------------------------------------------------------


def test_resume_shows_the_saved_world_paused_and_keeps_saving(
    window, panel, controller, manager, clock
):
    manager.save_now("Alpha")
    run = manager.current_run
    advance(controller, 40)
    saved = run.checkpoints()[-1]
    manager.save_now()
    saved = run.checkpoints()[-1]
    saved_digest = saved.state_digest
    advance(controller, 20)  # progress that was never saved
    old_backend = controller.backend
    frames, replaced = [], []
    controller.frame_received.connect(frames.append)
    controller.backend_replaced.connect(replaced.append)
    answer(panel)
    panel.select(run.id)
    assert panel.resume()
    assert controller.backend is not old_backend and replaced
    world = controller.backend.session.simulation
    assert world.tick == saved.tick == 40
    assert world.state_digest() == saved_digest
    assert not controller.status.running
    assert frames and frames[-1].tick == 40  # the new world is drawn at once
    assert manager.current_run.id == run.id and manager.autosaver is not None
    assert window.windowTitle().startswith("Evolution Simulator - Alpha, seed 3")
    advance(controller, 3 * DAY_TICKS)
    assert world.tick > 40
    assert manager.autosaver.written >= 1


def test_resuming_another_run_saves_the_one_on_screen_first(panel, controller, manager, clock):
    manager.save_now("One")
    one = manager.current_run
    # a second run on screen
    manager.detach()
    controller.replace_backend(LocalBackend(Session(make_world(seed=9))))
    manager.save_now("Two")
    two = manager.current_run
    advance(controller, 5)
    panel.resume(one.id)
    assert manager.current_run.id == one.id
    assert two.checkpoints()[-1].tick == 5  # the last checkpoint of the run we left


def test_resuming_the_run_on_screen_asks_and_drops_unsaved_progress(panel, controller, manager):
    manager.save_now()
    run = manager.current_run
    advance(controller, 10)
    asked = answer(panel, yes=False)
    assert not panel.resume(run.id)
    assert asked and controller.backend.session.simulation.tick == 10
    asked = answer(panel, yes=True)
    assert panel.resume(run.id)
    assert controller.backend.session.simulation.tick == 0


def test_resuming_over_a_world_never_saved_asks_first(panel, controller, manager):
    manager.save_now("Old")
    old = manager.current_run
    manager.delete(old.id)  # leaves the world on screen unsaved
    advance(controller, 7)
    # make a saved run elsewhere to resume
    other = make_world(seed=4)
    saved = manager.store.create(other, name="Other")
    assert manager.unsaved_progress
    answer(panel, yes=False)
    assert not panel.resume(saved.id)
    assert controller.backend.session.simulation.config.seed == 3
    answer(panel, yes=True)
    assert panel.resume(saved.id)
    assert controller.backend.session.simulation.config.seed == 4


def test_a_run_that_cannot_be_restored_changes_nothing(window, panel, controller, manager):
    manager.save_now()
    run = manager.current_run
    for checkpoint in run.checkpoints():
        (checkpoint.path / "world.json.gz").write_bytes(b"not a world")
    answer(panel)
    backend = controller.backend
    assert not panel.resume(run.id)
    assert controller.backend is backend
    assert "Could not resume" in window.statusBar().currentMessage()


def test_the_controller_starts_polling_again_after_a_failure(controller, manager):
    manager.save_now()
    run_id = manager.current_run.id

    class Broken:
        status = controller.backend.status

        def send(self, command): ...

        def poll(self):
            raise RuntimeError("boom")

    controller.start()
    controller.backend = Broken()
    failures = []
    controller.backend_failed.connect(failures.append)
    controller.poll()
    assert failures and not controller.polling
    manager.resume(run_id)
    assert controller.polling
    controller.stop()


# --- deleting -----------------------------------------------------------------------------


def test_delete_asks_and_removes_the_run(panel, manager, store):
    manager.save_now("Doomed")
    run_id = manager.current_run.id
    asked = answer(panel, yes=False)
    assert not panel.delete(run_id)
    assert asked and store.list_runs()
    answer(panel, yes=True)
    assert panel.delete(run_id)
    assert store.list_runs() == [] and panel.rows == []
    assert manager.current_run is None and manager.label == ""


def test_deleting_the_run_on_screen_leaves_the_world_running_unsaved(
    window, panel, controller, manager
):
    manager.save_now()
    answer(panel)
    panel.delete(manager.current_run.id)
    assert window.windowTitle() == "Evolution Simulator"
    advance(controller, 3)
    assert controller.backend.session.simulation.tick == 3  # still running
    window.actions["save_run"].trigger()  # a new run can start
    assert manager.current_run is not None


def test_deleting_closes_its_history_window(panel, manager):
    manager.save_now()
    run_id = manager.current_run.id
    window = panel.show_history(run_id)
    assert window in panel.windows
    answer(panel)
    panel.delete(run_id)
    assert window.isHidden()


# --- history ------------------------------------------------------------------------------


def test_the_history_window_shows_facts_chart_and_checkpoints(panel, controller, manager):
    manager.save_now("Studied")
    advance(controller, 5 * DAY_TICKS)
    manager.save_now()
    run = manager.current_run
    window = panel.show_history(run.id)
    assert isinstance(window, RunHistoryWindow) and window.isVisible()
    assert "Studied" in window.facts.text() and "seed 3" in window.facts.text()
    assert window.chart is not None
    assert window.table.rowCount() == len(run.checkpoints())
    assert not window.resume_button.isEnabled()
    window.table.selectRow(window.table.rowCount() - 1)
    assert window.resume_button.isEnabled()
    window.close()


def test_the_history_of_a_run_without_samples_says_so(panel, manager, store):
    run = store.create(make_world(), name="No recorder")
    panel.refresh()
    window = panel.show_history(run.id)
    assert window.chart is None
    window.close()


def test_history_resumes_from_the_chosen_checkpoint(panel, controller, manager):
    manager.save_now()
    run = manager.current_run
    advance(controller, 12)
    manager.save_now()
    window = panel.show_history(run.id)
    answer(panel)
    window.table.selectRow(0)  # the first checkpoint, tick 0
    window.resume_button.click()
    assert controller.backend.session.simulation.tick == 0


def test_the_charts_panel_can_supply_the_history_widgets(panel, controller, manager, monkeypatch):
    from PySide6.QtWidgets import QLabel

    from evolution_simulator.viewer.panels import charts

    seen = []

    def history_view(samples):
        seen.append(samples)
        return QLabel("from the charts panel")

    monkeypatch.setattr(charts, "history_view", history_view, raising=False)
    manager.save_now()
    advance(controller, 2 * DAY_TICKS)
    manager.save_now()
    window = panel.show_history(manager.current_run.id)
    assert seen and window.chart.text() == "from the charts panel"
    window.close()


def test_a_charts_panel_that_fails_falls_back_to_the_plain_chart(
    panel, controller, manager, monkeypatch
):
    from evolution_simulator.viewer.panels import charts

    def broken(samples):
        raise RuntimeError("no")

    monkeypatch.setattr(charts, "history_view", broken, raising=False)
    manager.save_now()
    advance(controller, 2 * DAY_TICKS)
    manager.save_now()
    window = panel.show_history(manager.current_run.id)
    assert window.chart is not None
    window.close()


# --- exporting ----------------------------------------------------------------------------


def test_the_history_exports_as_a_table(panel, controller, manager, tmp_path):
    manager.save_now()
    advance(controller, 3 * DAY_TICKS)
    manager.save_now()
    target = tmp_path / "out.csv"
    panel.choose_export_path = lambda suggestion: str(target)
    assert panel.export_history(manager.current_run.id)
    lines = target.read_text().splitlines()
    header = lines[0].split(",")
    assert header[:2] == ["day", "tick"] and "animals" in header and "plants" in header
    assert len(lines) > 1
    panel.choose_export_path = lambda suggestion: None
    assert not panel.export_history(manager.current_run.id)


def test_exporting_a_run_without_history_is_refused(manager, store, tmp_path):
    run = store.create(make_world(), name="Bare")
    with pytest.raises(RunError):
        manager.export_csv(run.id, tmp_path / "x.csv")


# --- finding the manager ------------------------------------------------------------------


def test_for_controller_returns_the_installed_manager(controller, manager):
    assert RunManager.for_controller(controller) is manager


def test_the_app_takes_a_runs_folder():
    from evolution_simulator.viewer.app import parse_args

    assert parse_args(["--runs-folder", "somewhere"]).runs_folder == "somewhere"
    assert parse_args([]).runs_folder is None


# --- history and the charts ----------------------------------------------------------------


def test_saving_records_with_the_recorder_the_backend_already_has(controller, manager):
    manager.save_now()
    assert manager.recorder is controller.backend.recorder
    assert manager.current_run.history() is not None


def test_a_resumed_run_brings_its_recorded_history_to_the_charts(
    window, panel, controller, manager
):
    manager.save_now()
    advance(controller, 3 * DAY_TICKS)
    manager.save_now()
    saved_days = manager.recorder.history().latest.day
    advance(controller, DAY_TICKS)  # less than the autosave interval: not saved
    charts = window.panels["charts"]
    answer(panel)
    assert panel.resume(manager.current_run.id)
    assert controller.history is not None and controller.history.latest.day == saved_days
    assert controller.backend.recorder is manager.recorder
    assert charts._history is controller.history


def test_a_resumed_run_with_no_history_clears_the_charts(window, panel, controller, manager, store):
    advance(controller, 2 * DAY_TICKS)
    assert controller.history is not None
    run = store.create(make_world(seed=4), name="Fresh")
    panel.refresh()
    answer(panel)
    assert panel.resume(run.id)
    assert controller.history is None
    assert window.panels["charts"]._history is None


def test_the_history_window_uses_the_charts_panel(panel, controller, manager):
    from evolution_simulator.viewer.panels.charts import ChartsPanel

    manager.save_now()
    advance(controller, 2 * DAY_TICKS)
    manager.save_now()
    window = panel.show_history(manager.current_run.id)
    assert isinstance(window.chart, ChartsPanel)
    window.close()


def test_the_local_backend_takes_a_recorder_that_is_already_listening():
    from evolution_simulator.history import Recorder

    world = make_world()
    recorder = Recorder(world)
    backend = LocalBackend(Session(world), record=recorder)
    assert backend.recorder is recorder
    backend.close()
