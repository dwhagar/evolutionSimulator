"""The setup screen and the form behind it (UX.17), on Qt's offscreen platform."""

from dataclasses import dataclass, field

import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)

from evolution_simulator.session import (
    CommandError,
    FakeSimulation,
    NewRun,
    Play,
    RunStarted,
    Session,
    SessionRules,
    SetSpeed,
    Step,
)
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.config_form import ConfigError, ConfigForm
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.panels import setup as setup_screen
from evolution_simulator.viewer.panels.setup import LAST_KEY, PRESETS_KEY, SetupPanel
from evolution_simulator.viewer.presets import BUILTIN_PRESETS, RunSetup
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.viewer.window import MainWindow
from evolution_simulator.world import World, WorldConfig


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


# --- the generic form -------------------------------------------------------------------


@dataclass(frozen=True)
class Gear:
    """The gear."""

    teeth: int = 12
    """How many teeth."""
    ratio: float = 0.5

    def __post_init__(self) -> None:
        if self.teeth < 1:
            raise ValueError("a gear needs teeth")


@dataclass(frozen=True)
class Machine:
    name: str = "m"
    on: bool = True
    size: tuple[float, ...] = (10.0, 20.0)
    gear: Gear = field(default_factory=Gear)
    spare: Gear | None = None
    limit: float | None = None
    seed: int = 0


def test_a_form_is_made_from_any_dataclass_and_gives_back_the_same_value(qapp):
    form = ConfigForm(Machine())
    assert form.value() == Machine()
    assert set(form.fields()) == {
        "name",
        "on",
        "size",
        "gear.teeth",
        "gear.ratio",
        "spare.teeth",
        "spare.ratio",
        "limit",
        "seed",
    }
    assert form.modified() == []


def test_editing_a_box_changes_the_value_and_marks_the_field(qapp):
    form = ConfigForm(Machine())
    changes = []
    form.changed.connect(lambda: changes.append(1))
    form.fields()["gear.teeth"].setText("20")
    form.fields()["on"].setChecked(False)
    form.fields()["size"].setText("5, 6, 7")
    assert form.value() == Machine(on=False, size=(5.0, 6.0, 7.0), gear=Gear(teeth=20))
    assert set(form.modified()) == {"gear.teeth", "on", "size"}
    assert changes


def test_a_bad_box_is_named_and_a_bad_combination_is_named_by_its_section(qapp):
    form = ConfigForm(Machine())
    form.fields()["gear.ratio"].setText("lots")
    error = form.error()
    assert isinstance(error, ConfigError) and error.path == "gear.ratio"
    assert "expected a number" in str(error)
    form.fields()["gear.ratio"].setText("0.25")
    form.fields()["gear.teeth"].setText("0")
    error = form.error()
    assert error is not None and error.path == "gear" and "needs teeth" in str(error)
    form.fields()["gear.teeth"].setText("1.5")
    assert "whole number" in str(form.error())


def test_an_optional_section_is_off_when_its_default_is_none_and_can_be_switched_on(qapp):
    form = ConfigForm(Machine())
    assert form.value().spare is None
    form._root.children["spare"].enabled.setChecked(True)
    assert form.value().spare == Gear()
    assert form.modified() == []  # on, but its fields are as they were; the header counts it
    form.fields()["spare.teeth"].setText("3")
    assert form.value().spare == Gear(teeth=3)
    form.set_value(Machine(spare=None))
    assert form.value().spare is None


def test_an_optional_value_is_none_when_its_box_is_empty(qapp):
    form = ConfigForm(Machine())
    form.fields()["limit"].setText("2.5")
    assert form.value().limit == 2.5
    form.fields()["limit"].setText("none")
    assert form.value().limit is None
    form.fields()["limit"].setText("")
    assert form.value().limit is None


def test_set_value_fills_every_box_and_reset_goes_back(qapp):
    form = ConfigForm(Machine())
    other = Machine(name="z", on=False, size=(1.0,), gear=Gear(7, 2.0), spare=Gear(), limit=4.0)
    form.set_value(other)
    assert form.value() == other
    form.reset()
    assert form.value() == Machine()


def test_skipped_fields_are_left_out_and_keep_their_default(qapp):
    form = ConfigForm(Machine(seed=5), skip={"seed"})
    assert "seed" not in form.fields()
    assert form.value().seed == 5


def test_the_filter_hides_fields_that_do_not_match_and_shows_sections_with_matches(qapp):
    form = ConfigForm(Machine())
    form.show()
    form.set_filter("teeth")
    assert not form.fields()["name"].isVisible() and form.fields()["gear.teeth"].isVisible()
    assert not form.fields()["gear.ratio"].isVisible()
    form.set_filter("how many")  # the explanation under the field counts
    assert form.fields()["gear.teeth"].isVisible()
    form.set_filter("gear")  # a section's own name shows all of it
    assert form.fields()["gear.ratio"].isVisible() and not form.fields()["name"].isVisible()
    form.set_filter("")
    assert form.fields()["name"].isVisible()


def test_tooltips_carry_the_explanation_and_the_default(qapp):
    form = ConfigForm(Machine())
    tip = form.fields()["gear.teeth"].toolTip()
    assert "How many teeth." in tip and "Default: 12" in tip


def test_the_world_config_form_covers_every_field_and_returns_the_default(qapp):
    form = ConfigForm(WorldConfig(), skip={"seed"})
    assert form.value() == WorldConfig()
    paths = form.fields()
    assert (
        "traits.life.wear_base" in paths
        and "bounds.size" in paths
        and "traits.attack.damage" in paths
    )
    assert "traits.day_cycle.night_below" in paths
    assert len(paths) > 100


# --- the screen ------------------------------------------------------------------------------


@pytest.fixture
def context(controller, settings):
    actions = {}
    messages = []
    ctx = ViewerContext(
        controller, actions, lambda text, ms: messages.append(text), settings=settings
    )
    ctx.messages = messages
    return ctx


def make_panel(context, *, answer=True, name="mine"):
    asked = []

    def confirm(text):
        asked.append(text)
        return answer

    panel = SetupPanel(context, confirm=confirm, ask_name=lambda: name)
    panel.asked = asked
    return panel


def test_the_screen_opens_on_the_default_preset(qapp, context):
    panel = make_panel(context)
    assert panel.setup() == RunSetup()
    assert panel.presets.currentText() == "Default"
    assert [panel.presets.itemText(i) for i in range(panel.presets.count())] == [
        p.name for p in BUILTIN_PRESETS
    ]
    assert panel.start_button.isEnabled()
    assert "120 animals, 600 plants, seed 0" in panel.status.text()


def test_choosing_a_preset_fills_the_boxes_and_keeps_the_seed(qapp, context):
    panel = make_panel(context)
    panel.seed.setText("77")
    panel.choose_preset("Small and quick")
    setup = panel.setup()
    assert (setup.animals, setup.plants, setup.config.seed) == (40, 200, 77)
    assert setup.config.bounds.size == (500.0, 500.0)
    assert "(edited)" not in panel.note.text()
    panel.animals.setValue(41)
    assert panel.note.text().endswith("(edited)")
    panel.reset()
    assert panel.animals.value() == 40 and panel.seed.text() == "77"


def test_no_night_turns_the_optional_section_off(qapp, context):
    panel = make_panel(context)
    panel.choose_preset("No night")
    assert panel.setup().config.day_cycle is None
    panel.choose_preset("Default")
    assert panel.setup().config.day_cycle is not None


def test_a_random_seed_is_a_whole_number_in_range(qapp, context):
    panel = make_panel(context)
    panel.pick_random_seed()
    assert 0 <= int(panel.seed.text()) < setup_screen.SEED_LIMIT


def test_what_does_not_fit_disables_start_and_says_why(qapp, context):
    panel = make_panel(context)
    panel.seed.setText("abc")
    assert not panel.start_button.isEnabled() and "seed" in panel.status.text()
    panel.seed.setText("1")
    panel.form.fields()["max_animals"].setText("10")
    assert not panel.start_button.isEnabled()  # 120 animals do not fit a cap of 10
    assert "at most 10 animals" in panel.status.text()
    assert panel.start() is False
    assert any("Cannot start" in m for m in context.messages)
    panel.animals.setValue(10)
    assert panel.start_button.isEnabled()
    panel.form.fields()["traits.life.wear_base"].setText("x")
    assert not panel.start_button.isEnabled() and "wear_base" in panel.status.text()


def test_start_sends_a_new_run_and_the_world_is_replaced(qapp, context, controller):
    panel = make_panel(context)
    panel.animals.setValue(8)
    panel.plants.setValue(25)
    panel.seed.setText("42")
    panel.form.fields()["traits.world.graze_amount"].setText("7.5")
    assert panel.start() is True
    controller.poll()
    world = controller.backend.session.simulation
    assert isinstance(world, World) and world.tick == 0
    assert world.config.seed == 42 and world.config.traits.world.graze_amount == 7.5
    assert len(world.animal_views()) == 8 and world.plant_count == 25
    assert controller.frame.animal_count == 8 and controller.plants.count == 25
    assert not controller.status.running
    assert any("Started a new run" in m for m in context.messages)


def test_a_run_that_has_not_started_is_replaced_without_asking(qapp, context, controller):
    controller.poll()
    panel = make_panel(context)
    panel.start()
    assert panel.asked == []


def test_a_run_in_progress_is_only_thrown_away_after_a_yes(qapp, context, controller, clock):
    controller.send(Step(3))
    controller.poll()
    assert controller.frame.tick == 3
    panel = make_panel(context, answer=False)
    assert panel.start() is False
    assert len(panel.asked) == 1 and "tick 3" in panel.asked[0]
    assert controller.backend.session.simulation.tick == 3
    panel = make_panel(context, answer=True)
    assert panel.start() is True
    assert controller.backend.session.simulation.tick == 0


def test_a_refused_command_is_reported_and_keeps_the_old_run(qapp, context, controller):
    failures = []
    controller.command_failed.connect(failures.append)

    def refuse(command):
        raise CommandError("out of memory")

    controller.backend.session._new_run = refuse
    panel = make_panel(context)
    assert panel.start() is False
    assert failures == ["out of memory"]
    assert isinstance(controller.backend.session.simulation, FakeSimulation)


def test_the_last_run_started_comes_back_next_time(qapp, context, settings):
    panel = make_panel(context)
    panel.animals.setValue(15)
    panel.seed.setText("9")
    panel.start()
    assert LAST_KEY in settings.allKeys()
    again = make_panel(context)
    assert again.animals.value() == 15 and again.seed.text() == "9"


def test_a_damaged_last_run_is_ignored(qapp, context, settings):
    settings.setValue(LAST_KEY, "{ not json")
    assert make_panel(context).setup() == RunSetup()


def test_the_users_own_presets_are_saved_listed_and_deleted(qapp, context, settings):
    panel = make_panel(context, name="Tiny")
    panel.animals.setValue(5)
    panel.form.fields()["traits.world.birth_scatter"].setText("2.0")
    assert panel.save_preset() is True
    assert panel.presets.currentText() == "Tiny" and panel.delete_button.isEnabled()
    assert PRESETS_KEY in settings.allKeys()
    again = make_panel(context)
    assert "Tiny" in [again.presets.itemText(i) for i in range(again.presets.count())]
    again.choose_preset("Tiny")
    assert again.animals.value() == 5 and again.setup().config.traits.world.birth_scatter == 2.0
    assert again.delete_preset() is True
    assert "Tiny" not in [again.presets.itemText(i) for i in range(again.presets.count())]
    last = make_panel(context)
    assert "Tiny" not in [last.presets.itemText(i) for i in range(last.presets.count())]
    assert again.delete_preset() is False  # a built-in cannot be deleted


def test_a_preset_cannot_take_a_built_in_name_or_no_name(qapp, context):
    assert make_panel(context, name="Default").save_preset() is False
    assert make_panel(context, name="  ").save_preset() is False
    assert make_panel(context, name=None).save_preset() is False


def test_unreadable_saved_presets_are_ignored(qapp, context, settings):
    settings.setValue(PRESETS_KEY, "[1, 2")
    panel = make_panel(context)
    assert panel.presets.count() == len(BUILTIN_PRESETS)


# --- in the window ---------------------------------------------------------------------------


@pytest.fixture
def window(controller, settings):
    win = MainWindow(controller, run_label="fake, seed 3", settings=settings)
    win.show()
    yield win
    win.close()


def test_the_window_has_the_setup_dock_closed_at_first(window):
    assert "setup" in window.docks and window.docks["setup"].isHidden()
    assert isinstance(window.panels["setup"], SetupPanel)
    assert window.panels["setup"].settings is window.settings


def test_file_new_run_opens_the_dock(window):
    window.actions["new_run"].trigger()
    assert not window.docks["setup"].isHidden()
    assert window.actions["new_run"].shortcut().toString() == "Ctrl+N"
    assert window.file_menu.actions()[0].text() == "&New run..."


def test_starting_a_run_renames_the_window_and_the_counts(window, controller):
    panel = window.panels["setup"]
    panel._confirm = lambda text: True
    panel.animals.setValue(4)
    panel.plants.setValue(12)
    panel.seed.setText("31")
    panel.start()
    controller.poll()
    assert window.windowTitle() == "Evolution Simulator - world, seed 31"
    assert window.status_labels["run"].text() == "world, seed 31"
    assert "Animals 4" in window.status_labels["counts"].text()
    assert "Tick 0" in window.status_labels["clock"].text()


def test_the_new_run_can_be_played(window, controller, clock):
    panel = window.panels["setup"]
    panel._confirm = lambda text: True
    panel.animals.setValue(6)
    panel.plants.setValue(20)
    panel.start()
    controller.send(SetSpeed("day"))
    controller.send(Play())
    clock.advance(0.5)
    controller.poll()
    assert controller.frame.tick > 0


def test_the_controller_drops_the_old_run_when_a_new_one_starts(controller):
    controller.poll()
    old_frame = controller.frame
    assert old_frame.animal_count == 30 and controller.plants.count == 100
    heard = []
    controller.event_received.connect(heard.append)
    controller.send(NewRun(WorldConfig(seed=2), 3, 10))
    controller.poll()
    assert [e.label for e in heard if isinstance(e, RunStarted)] == ["world, seed 2"]
    assert controller.frame is not old_frame
    assert controller.frame.animal_count == 3 and controller.plants.count == 10
    assert controller.detail is None


def test_a_new_run_starts_a_new_history_and_the_charts_follow(qapp, settings, clock):
    from evolution_simulator.session import build_world

    session = Session(
        build_world(NewRun(WorldConfig(seed=1), 10, 30)),
        rules=SessionRules(work_budget=10.0),
        clock=clock,
    )
    backend = LocalBackend(session)
    controller = ViewerController(backend)
    window = MainWindow(controller, settings=settings)
    try:
        controller.send(Step(50))  # two simulated days
        controller.poll()
        assert controller.history is not None and len(controller.history) >= 2
        old_days = len(controller.history)
        histories = []
        controller.history_received.connect(histories.append)
        controller.send(NewRun(WorldConfig(seed=2), 8, 25))
        controller.poll()
        assert histories and len(histories[-1]) == 0  # the old run's days are gone
        assert controller.history is histories[-1]
        controller.send(Step(30))
        clock.advance(0.1)  # a frame is due again
        controller.poll()
        assert 1 <= len(controller.history) <= old_days
        assert controller.frame.tick == 30
    finally:
        window.close()
        backend.close()


def test_a_saved_run_gets_its_last_checkpoint_before_a_new_run_replaces_it(
    qapp, settings, clock, tmp_path
):
    from evolution_simulator.runs import RunStore
    from evolution_simulator.session import build_world
    from evolution_simulator.viewer.run_manager import RunManager

    session = Session(
        build_world(NewRun(WorldConfig(seed=1), 10, 30)),
        rules=SessionRules(work_budget=10.0),
        clock=clock,
    )
    backend = LocalBackend(session)
    controller = ViewerController(backend)
    manager = RunManager.install(controller, RunStore(tmp_path / "runs"))
    messages = []
    context = ViewerContext(
        controller, {}, lambda text, ms: messages.append(text), settings=settings
    )
    asked = []
    panel = SetupPanel(context, confirm=lambda text: asked.append(text) or False)
    try:
        controller.send(Step(5))
        controller.poll()
        manager.save_now()
        controller.send(Step(7))
        clock.advance(0.1)
        controller.poll()
        assert manager.current_run is not None and controller.frame.tick == 12
        assert panel.start() is True, (
            messages,
            asked,
        )  # no question: the run is saved and gets its last checkpoint
        assert asked == []
        controller.poll()
        assert manager.current_run is None
        [summary] = manager.list_runs()
        assert summary.tick == 12  # the final checkpoint, written before the world was replaced
        assert controller.frame.tick == 0
    finally:
        backend.close()


def test_a_world_that_was_never_saved_is_only_replaced_after_a_yes(qapp, settings, clock, tmp_path):
    from evolution_simulator.runs import RunStore
    from evolution_simulator.session import build_world
    from evolution_simulator.viewer.run_manager import RunManager

    session = Session(
        build_world(NewRun(WorldConfig(seed=1), 10, 30)),
        rules=SessionRules(work_budget=10.0),
        clock=clock,
    )
    backend = LocalBackend(session)
    controller = ViewerController(backend)
    manager = RunManager.install(controller, RunStore(tmp_path / "runs"))
    context = ViewerContext(controller, {}, lambda text, ms: None, settings=settings)
    answers = iter([False, True])
    panel = SetupPanel(context, confirm=lambda text: next(answers))
    try:
        controller.send(Step(4))
        controller.poll()
        assert panel.start() is False and session.simulation.tick == 4
        assert panel.start() is True and session.simulation.tick == 0
        assert manager.list_runs() == []  # nothing was saved behind the user's back
    finally:
        backend.close()
