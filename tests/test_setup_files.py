"""Preset files and "Copy with new seed" (UX.35), on Qt's offscreen platform."""

import json
from dataclasses import replace

import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)

from evolution_simulator.runs import RunStore
from evolution_simulator.session import FakeSimulation, Session, SessionRules, Step
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.presets import BUILTIN_PRESETS, RunSetup
from evolution_simulator.viewer.run_manager import RunManager
from evolution_simulator.viewer.window import MainWindow
from evolution_simulator.world import WorldConfig


class Clock:
    """Every look at it is a twentieth of a second later, so frames get published."""

    now = 1_700_000_000.0

    def __call__(self) -> float:
        self.now += 0.05
        return self.now


@pytest.fixture
def controller(qapp, tmp_path):
    session = Session(
        FakeSimulation(30, 100, seed=3), rules=SessionRules(work_budget=30.0), clock=Clock()
    )
    backend = LocalBackend(session)
    controller = ViewerController(backend)
    RunManager.install(controller, RunStore(tmp_path / "runs"))  # never the user's own folder
    yield controller
    backend.close()


@pytest.fixture
def window(controller, tmp_path):
    settings = QtCore.QSettings(str(tmp_path / "viewer.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(controller, run_label="fake, seed 3", settings=settings)
    win.show()
    yield win
    win.close()


@pytest.fixture
def setup_panel(window):
    panel = window.panels["setup"]
    panel._confirm = lambda text: True
    return panel


@pytest.fixture
def runs_panel(window):
    panel = window.panels["runs"]
    panel.confirm = lambda title, text: True
    return panel


# --- preset files ----------------------------------------------------------------------------


def test_a_setup_is_written_to_a_file_and_read_back(setup_panel, tmp_path):
    setup_panel.animals.setValue(7)
    setup_panel.plants.setValue(21)
    setup_panel.seed.setText("123")
    setup_panel.seeded.setChecked(False)
    path = tmp_path / "mine.json"
    assert setup_panel.save_to_file(str(path))
    assert RunSetup.from_json(path.read_text()) == setup_panel.setup()

    setup_panel.choose_preset("Small and quick")
    assert setup_panel.load_from_file(str(path))
    setup = setup_panel.setup()
    assert (setup.animals, setup.plants, setup.config.seed, setup.seeded) == (7, 21, 123, False)
    assert setup_panel.presets.currentText() == "mine"  # kept among the presets
    assert "Loaded from mine.json" in setup_panel.note.text()
    assert setup_panel.delete_button.isEnabled()


def test_a_loaded_file_stays_a_preset_for_next_time(setup_panel, tmp_path):
    path = tmp_path / "shared.json"
    path.write_text(RunSetup(5, 9).to_json())
    assert setup_panel.load_from_file(str(path))
    setup_panel._load_presets()  # as when the screen is opened again
    assert "shared" in [setup_panel.presets.itemText(i) for i in range(setup_panel.presets.count())]


def test_a_file_named_like_a_builtin_preset_does_not_take_its_place(setup_panel, tmp_path):
    path = tmp_path / "Default.json"
    path.write_text(RunSetup(5, 9).to_json())
    assert setup_panel.load_from_file(str(path))
    assert setup_panel.presets.currentText() == "Default (file)"
    assert BUILTIN_PRESETS[0].setup == RunSetup()


def test_the_file_dialogs_are_asked_when_no_path_is_given(setup_panel, tmp_path):
    path = tmp_path / "asked.json"
    setup_panel.choose_file_to_save = lambda suggestion: str(path)
    assert setup_panel.save_to_file()
    setup_panel.choose_file_to_open = lambda: str(path)
    assert setup_panel.load_from_file()
    setup_panel.choose_file_to_save = lambda suggestion: None  # cancelled
    setup_panel.choose_file_to_open = lambda: None
    assert not setup_panel.save_to_file() and not setup_panel.load_from_file()


@pytest.mark.parametrize(
    "text",
    ["", "not json", "[1, 2]", "{}", '{"animals": "many"}', '{"config": {"seed": "x"}}'],
)
def test_a_file_that_is_not_a_setup_changes_nothing(window, setup_panel, tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    before = setup_panel.setup()
    count = setup_panel.presets.count()
    assert not setup_panel.load_from_file(str(path))
    assert setup_panel.setup() == before and setup_panel.presets.count() == count
    assert "Could not read a setup" in window.statusBar().currentMessage()


def test_a_missing_file_or_counts_over_the_cap_are_said(window, setup_panel, tmp_path):
    assert not setup_panel.load_from_file(str(tmp_path / "nope.json"))
    path = tmp_path / "huge.json"
    path.write_text(json.dumps({"animals": 10**9}))
    assert not setup_panel.load_from_file(str(path))
    assert "Could not read a setup" in window.statusBar().currentMessage()


def test_an_unwritable_place_is_said(window, setup_panel, tmp_path):
    assert not setup_panel.save_to_file(str(tmp_path / "no" / "such" / "folder.json"))
    assert "Could not write" in window.statusBar().currentMessage()


def test_a_setup_that_does_not_fit_is_not_written(window, setup_panel, tmp_path):
    setup_panel.seed.setText("abc")
    path = tmp_path / "x.json"
    assert not setup_panel.save_to_file(str(path)) and not path.exists()


def test_an_older_file_missing_fields_still_loads(setup_panel, tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"animals": 11, "config": {"seed": 4, "gone": 1}}))
    assert setup_panel.load_from_file(str(path))
    setup = setup_panel.setup()
    assert (setup.animals, setup.plants, setup.config.seed) == (11, 600, 4)


def test_the_buttons_use_the_file_dialogs(setup_panel, tmp_path):
    path = tmp_path / "button.json"
    setup_panel.choose_file_to_save = lambda suggestion: str(path)
    setup_panel.file_save_button.click()
    assert path.is_file()
    setup_panel.choose_file_to_open = lambda: str(path)
    setup_panel.file_load_button.click()
    assert setup_panel.presets.currentText() == "button"


# --- copy with a new seed ----------------------------------------------------------------------


def advance(controller, ticks: int) -> None:
    """Run exactly this many ticks (polling until the session has done them)."""
    controller.send(Step(ticks))
    for _ in range(10_000):
        controller.poll()
        if controller.backend.status.steps_left == 0:
            return
    raise AssertionError("the steps never finished")


def start_and_run(window, controller, setup_panel, *, seed, animals, plants, name=""):
    setup_panel.animals.setValue(animals)
    setup_panel.plants.setValue(plants)
    setup_panel.seed.setText(str(seed))
    setup_panel.name.setText(name)
    assert setup_panel.start()
    controller.poll()


def only_run(manager, run_id=None):
    runs = manager.list_runs()
    return next(r for r in runs if r.id == run_id) if run_id else runs[0]


def test_copy_with_new_seed_starts_a_run_with_the_old_settings(
    window, controller, setup_panel, runs_panel
):
    manager = RunManager.for_controller(controller)
    setup_panel.choose_preset("Small and quick")  # a non-default world
    start_and_run(window, controller, setup_panel, seed=11, animals=8, plants=25)
    old = manager.current_run
    old_config = old.config
    assert old_config.bounds.size == (500.0, 500.0)
    advance(controller, 20)
    runs_panel.refresh()
    runs_panel.select(old.id)
    assert runs_panel.copy_button.isEnabled()

    assert runs_panel.copy_with_new_seed()
    controller.poll()
    new = manager.current_run
    assert new.id != old.id
    assert new.config.seed != 11
    assert replace(new.config, seed=11) == old_config
    assert (controller.frame.animal_count, controller.plants.count) == (8, 25)
    assert controller.frame.tick == 0  # a fresh world, not the old one's state
    assert len(manager.list_runs()) == 2
    assert f"seed {new.config.seed}" in new.name  # unnamed, so it is named after its seed
    # the setup screen shows what was started
    assert setup_panel.setup().config == new.config


def test_a_named_run_gives_its_copy_a_name_with_the_new_seed(
    window, controller, setup_panel, runs_panel
):
    manager = RunManager.for_controller(controller)
    start_and_run(window, controller, setup_panel, seed=5, animals=4, plants=10, name="Hot desert")
    old = manager.current_run
    runs_panel.refresh()
    assert runs_panel.copy_with_new_seed(old.id)
    new = manager.current_run
    assert new.name == f"Hot desert, seed {new.config.seed}"


def test_the_copy_never_reuses_the_seed(window, controller, setup_panel, runs_panel, monkeypatch):
    import random

    manager = RunManager.for_controller(controller)
    start_and_run(window, controller, setup_panel, seed=0, animals=4, plants=10)
    old = manager.current_run
    runs_panel.refresh()

    class Fixed(random.SystemRandom):
        def randrange(self, *args, **kwargs):  # the draw that would be the old seed
            return 0

    monkeypatch.setattr("evolution_simulator.viewer.panels.runs.random.SystemRandom", Fixed)
    assert runs_panel.copy_with_new_seed(old.id)
    assert manager.current_run.config.seed != 0


def test_copying_asks_before_losing_an_unsaved_world(window, controller, setup_panel, runs_panel):
    manager = RunManager.for_controller(controller)
    start_and_run(window, controller, setup_panel, seed=5, animals=4, plants=10)
    old = manager.current_run
    runs_panel.refresh()
    manager.detach()
    advance(controller, 30)  # an unsaved world with progress on screen
    assert controller.frame.tick > 0
    assert controller.frame.tick > 0
    asked = []
    setup_panel._confirm = lambda text: asked.append(text) or False
    assert not runs_panel.copy_with_new_seed(old.id)
    assert asked and "not saved" in asked[0]
    assert len(manager.list_runs()) == 1


def test_nothing_to_copy_without_a_selection(runs_panel):
    runs_panel.refresh()
    assert not runs_panel.copy_button.isEnabled()
    assert not runs_panel.copy_with_new_seed()


def test_a_run_whose_files_are_gone_is_said(window, controller, setup_panel, runs_panel):
    import shutil

    manager = RunManager.for_controller(controller)
    start_and_run(window, controller, setup_panel, seed=5, animals=4, plants=10)
    old = manager.current_run
    runs_panel.refresh()
    manager.detach()
    shutil.rmtree(old.path)
    assert not runs_panel.copy_with_new_seed(old.id)
    assert "Could not read the run" in window.statusBar().currentMessage()


def test_starting_counts_come_from_the_first_checkpoint_or_the_history(
    window, controller, setup_panel
):
    manager = RunManager.for_controller(controller)
    start_and_run(window, controller, setup_panel, seed=5, animals=9, plants=33)
    run = manager.current_run
    assert manager.starting_counts(run.id) == (9, 33)
    for checkpoint in run.checkpoints():  # as if the first checkpoint had been pruned
        if checkpoint.tick == 0:
            import shutil

            shutil.rmtree(checkpoint.path)
    counts = manager.starting_counts(run.id)
    assert counts is None or all(isinstance(n, int) for n in counts)


def test_the_world_config_default_is_used_when_copying_a_default_run(
    window, controller, setup_panel, runs_panel
):
    manager = RunManager.for_controller(controller)
    start_and_run(window, controller, setup_panel, seed=2, animals=4, plants=10)
    old = manager.current_run
    runs_panel.refresh()
    assert runs_panel.copy_with_new_seed(old.id)
    assert replace(manager.current_run.config, seed=2) == WorldConfig(seed=2)
