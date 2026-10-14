"""The creature inspector panel and its tabs (UX.14), on Qt's offscreen platform."""

from dataclasses import replace

import numpy as np
import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
QtTest = pytest.importorskip("PySide6.QtTest", exc_type=ImportError)
pytest.importorskip("numpy")

from evolution_simulator.deaths import DeathCause
from evolution_simulator.session import (
    Deselect,
    FakeSimulation,
    Select,
    Session,
    SessionRules,
    Step,
)
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.inspector import describe, tabs
from evolution_simulator.viewer.inspector.panel import DESELECT
from evolution_simulator.viewer.inspector.tab_genes import NOT_NAMEABLE
from evolution_simulator.viewer.window import MainWindow
from evolution_simulator.world import World, WorldConfig


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


def make_controller(simulation, clock):
    session = Session(simulation, rules=SessionRules(work_budget=30.0), clock=clock)
    return ViewerController(LocalBackend(session))


@pytest.fixture(params=["world", "fake"])
def controller(request, qapp, clock):
    if request.param == "world":
        world = World(WorldConfig(seed=1))
        world.populate(animals=20, plants=80)
        ctl = make_controller(world, clock)
    else:
        ctl = make_controller(FakeSimulation(30, 100, seed=3), clock)
    ctl.real = request.param == "world"
    yield ctl
    ctl.backend.close()


@pytest.fixture
def real(qapp, clock):
    world = World(WorldConfig(seed=1))
    world.populate(animals=20, plants=80)
    ctl = make_controller(world, clock)
    yield ctl
    ctl.backend.close()


def open_window(ctl, tmp_path):
    settings = QtCore.QSettings(str(tmp_path / "v.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(ctl, settings=settings)
    win.show()
    return win


@pytest.fixture
def window(controller, tmp_path):
    win = open_window(controller, tmp_path)
    yield win
    win.close()


@pytest.fixture
def real_window(real, tmp_path):
    win = open_window(real, tmp_path)
    yield win
    win.close()


def ids_of(ctl):
    return [int(i) for i in np.frombuffer(ctl.frame.animals.ids, dtype="<u4")]


def run_a_little(ctl, clock, steps=3):
    ctl.poll()
    ctl.send(Step(steps))
    clock.now += 2.0
    ctl.poll()
    ctl.poll()


def select_first(ctl, clock):
    run_a_little(ctl, clock)
    animal_id = ids_of(ctl)[0]
    ctl.send(Select(animal_id))
    clock.now += 1.0
    ctl.poll()
    ctl.poll()
    return animal_id


def press(window, key):
    window.activateWindow()
    QtTest.QTest.qWaitForWindowActive(window)
    QtTest.QTest.keyClick(window, key)


# --- the panel --------------------------------------------------------------------


def test_the_panel_has_its_tabs_and_starts_empty(window):
    panel = window.panels["inspector"]
    assert [panel.tabs.tabText(i) for i in range(panel.tabs.count())] == [
        "Body",
        "Genes",
        "Family",
        "Brain",
    ]
    assert panel.stack.currentWidget() is panel.empty
    assert panel.detail is None
    assert not window.actions[DESELECT].isEnabled()


def test_selecting_shows_the_creature_in_the_header_and_the_body(controller, window, clock):
    animal_id = select_first(controller, clock)
    panel = window.panels["inspector"]
    assert panel.stack.currentWidget() is panel.page
    assert f"#{animal_id}" in panel.header.text()
    body = panel.pages["body"]
    assert body.energy.value.text().count("/") == 1
    assert body.fields.values["age"].text().endswith("of its life)")
    assert body.fields.values["decision"].text()
    assert window.actions[DESELECT].isEnabled()


def real_trace():
    from evolution_simulator.brain_adapter import BrainTrace

    return BrainTrace((0.0,), (0.0,), (0.0,), (0.0,))


def test_the_body_says_its_brain_is_waiting_until_it_has_run(controller, window, clock):
    select_first(controller, clock)
    panel = window.panels["inspector"]
    detail = panel.detail
    body = panel.pages["body"]
    controller.detail_received.emit(replace(detail, brain=None))
    assert body.fields.values["brain"].text().startswith("waiting")
    trace = real_trace()
    controller.detail_received.emit(replace(detail, brain=trace))
    assert body.fields.values["brain"].text().startswith("traced")


def test_the_body_shows_the_traits_in_their_units(real, real_window, clock):
    select_first(real, clock)
    grid = real_window.panels["inspector"].pages["body"].traits.grid
    assert grid.values["sight_reach"].text().endswith("world units")
    assert grid.values["mass"].text() != ""


def test_esc_deselects_and_clears_the_panel(controller, window, clock):
    select_first(controller, clock)
    panel = window.panels["inspector"]
    assert controller.status.selected is not None
    press(window, QtCore.Qt.Key.Key_Escape)
    assert controller.status.selected is None
    assert panel.detail is None and panel.stack.currentWidget() is panel.empty
    assert not window.actions[DESELECT].isEnabled()


def test_the_deselect_button_is_the_same_action(controller, window, clock):
    select_first(controller, clock)
    window.panels["inspector"].deselect_button.click()
    assert controller.status.selected is None


def test_esc_with_nothing_selected_sends_nothing(controller, window):
    sent = []
    original = controller.send
    controller.send = lambda command: sent.append(command) or original(command)
    press(window, QtCore.Qt.Key.Key_Escape)
    assert not any(isinstance(c, Deselect) for c in sent)


def test_a_click_on_bare_ground_clears_the_panel(controller, window, clock, qapp):
    select_first(controller, clock)
    controller.send(Deselect())
    qapp.processEvents()
    assert window.panels["inspector"].detail is None


def test_choosing_another_creature_replaces_the_one_shown(controller, window, clock):
    first = select_first(controller, clock)
    other = next(i for i in ids_of(controller) if i != first)
    controller.send(Select(other))
    clock.now += 1.0
    controller.poll()
    controller.poll()
    panel = window.panels["inspector"]
    assert panel.detail.id == other and f"#{other}" in panel.header.text()


def test_a_creature_that_dies_stays_on_screen_marked_dead(controller, window, clock, qapp):
    select_first(controller, clock)
    panel = window.panels["inspector"]
    alive = panel.detail
    dead = replace(alive, alive=False, death_cause=DeathCause.STARVATION)
    status = replace(controller.status, selected=None)
    controller.status = replace(controller.status, selected=alive.id)
    controller.status_changed.emit(status)  # the session announces the end first,
    controller.detail_received.emit(dead)  # then sends the last details
    qapp.processEvents()
    assert panel.detail is dead
    assert "dead: starved" in panel.header.text()
    assert panel.pages["body"].fields.values["state"].text() == "dead: starved"
    assert panel.deselect_button.text() == "Clear"
    panel.deselect()
    assert panel.detail is None


def test_a_real_death_shows_up_marked_dead(real, real_window, clock, qapp):
    animal_id = select_first(real, clock)
    world = real.backend.session.simulation
    next(a for a in world.animals if a.id == animal_id).traits.current_energy = 0.001
    real.send(Step(1))
    clock.now += 1.0
    real.poll()
    qapp.processEvents()
    panel = real_window.panels["inspector"]
    assert real.status.selected is None
    assert panel.detail is not None and not panel.detail.alive
    assert "dead: starved" in panel.header.text()


def test_a_new_run_clears_the_panel(controller, window, clock):
    select_first(controller, clock)
    controller.backend_replaced.emit(controller.backend)
    assert window.panels["inspector"].detail is None


# --- the genes tab ----------------------------------------------------------------


def test_the_genes_tab_shows_named_genes_for_a_real_genome(real, real_window, clock):
    select_first(real, clock)
    genes = real_window.panels["inspector"].pages["genes"]
    assert genes.list is not None and not genes.message.isVisibleTo(genes)
    assert {"size", "fear", "sex_strategy"} <= set(genes.list.rows)
    size = genes.list.rows["size"]
    assert size.value.text() == describe.number_text(size.meter.level)
    assert not size.digits.isVisibleTo(genes)
    genes.raw_box.setChecked(True)
    assert size.digits.isVisibleTo(genes) and size.digits.text() != ""
    assert genes.list.brain_digits.isVisibleTo(genes)
    assert len(genes.list.brain_digits.toPlainText()) == 1164


def test_the_population_average_is_drawn_once_the_history_has_one(real, real_window, clock):
    select_first(real, clock)
    genes = real_window.panels["inspector"].pages["genes"]
    assert genes.list.rows["size"].meter.marker is None
    stat_history = _history_with_gene("size", 0.4, 0.1)
    real.history_received.emit(stat_history)
    assert genes.list.rows["size"].meter.marker == pytest.approx(0.4)


def _history_with_gene(gene, mean, std):
    from evolution_simulator.history import HistorySamples
    from evolution_simulator.history.samples import Sample, Stat, Tier

    stats = {f"animal.gene.{gene}": Stat(5, mean, std, 0.0, 1.0)}
    return HistorySamples(86400.0, (Tier("days", 1, (Sample(1, 1, 24, stats=stats),)),))


def test_a_genome_the_layout_does_not_describe_says_so(controller, window, clock):
    if controller.real:
        pytest.skip("only the stand-in simulation has short genomes")
    select_first(controller, clock)
    genes = window.panels["inspector"].pages["genes"]
    assert genes.message.text() == NOT_NAMEABLE and genes.list is None
    assert not genes.scroll.isVisibleTo(genes)


# --- the family tab ---------------------------------------------------------------


def test_the_family_tab_lists_relatives_and_selects_on_click(real, real_window, clock):
    first = select_first(real, clock)
    family = real_window.panels["inspector"].pages["family"]
    shown = [b for b in family.relatives.buttons if b.isVisibleTo(family)]
    assert len(shown) == 8 and all(b.isEnabled() for b in shown)
    target = int(shown[0].text().lstrip("#"))
    assert target != first
    shown[0].click()
    clock.now += 1.0
    real.poll()
    real.poll()
    assert real.status.selected == target
    assert real_window.panels["inspector"].detail.id == target


def test_parents_and_children_are_links_and_a_gone_one_cannot_be_selected(real, real_window, clock):
    first = select_first(real, clock)
    panel = real_window.panels["inspector"]
    family = panel.pages["family"]
    alive = next(i for i in ids_of(real) if i != first)
    detail = replace(panel.detail, parents=(alive, 999_999), children=(alive,), partner=alive)
    real.detail_received.emit(detail)
    assert [b.text() for b in family.parents.buttons if b.isVisibleTo(family)] == [
        f"#{alive}",
        "#999999",
    ]
    live, gone = [b for b in family.parents.buttons if b.isVisibleTo(family)]
    assert live.isEnabled() and not gone.isEnabled()
    assert family.partner.isVisibleTo(family)
    assert [b.text() for b in family.children.buttons if b.isVisibleTo(family)] == [f"#{alive}"]
    live.click()
    real.poll()
    assert real.status.selected == alive


def test_a_long_list_of_children_is_cut_with_a_count(real, real_window, clock):
    select_first(real, clock)
    panel = real_window.panels["inspector"]
    family = panel.pages["family"]
    many = tuple(range(1000, 1020))
    real.detail_received.emit(replace(panel.detail, children=many, parents=()))
    shown = [b for b in family.children.buttons if b.isVisibleTo(family)]
    assert len(shown) == 12
    assert family.children.more_label.text() == "and 8 more"
    assert family.parents.none_label.isVisibleTo(family)


# --- the tabs ---------------------------------------------------------------------


def test_tabs_are_found_by_name_and_in_order():
    found = tabs.discover_tabs()
    assert [spec.id for spec in found][:3] == ["body", "genes", "family"]


def test_two_tabs_with_one_id_are_refused(monkeypatch):
    import types

    module = types.ModuleType("evolution_simulator.viewer.inspector.tab_dup")
    module.TAB = tabs.TabSpec("body", "Again", lambda c, p: tabs.TabPage(p))
    monkeypatch.setitem(__import__("sys").modules, module.__name__, module)
    monkeypatch.setattr(
        tabs.pkgutil,
        "iter_modules",
        lambda path: [
            types.SimpleNamespace(name="tab_body"),
            types.SimpleNamespace(name="tab_dup"),
        ],
    )
    with pytest.raises(ValueError, match="share the id"):
        tabs.discover_tabs()
