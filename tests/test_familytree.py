"""The family tree window and the Family tab's button for it (UX.39), on Qt's offscreen platform."""

import numpy as np
import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
QtTest = pytest.importorskip("PySide6.QtTest", exc_type=ImportError)
pytest.importorskip("numpy")

from evolution_simulator.deaths import DeathCause
from evolution_simulator.session import FakeSimulation, Select, Session, SessionRules
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.inspector import describe, familytree
from evolution_simulator.viewer.window import MainWindow
from evolution_simulator.viewer.worldview import palette
from evolution_simulator.viewer.worldview.layers import Layer
from evolution_simulator.world import World, WorldConfig
from evolution_simulator.world.views import KinView


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


@pytest.fixture
def world():
    world = World(WorldConfig(seed=1))
    world.populate(animals=12, plants=40)
    world.run(3)
    return world


def add_kin(world, animal_id, parents, sex, born, died=None):
    book = world.ancestry
    book.born(animal_id, parents, sex, born, (0.01 * animal_id, 0.02 * animal_id))
    if died is not None:
        book.died(animal_id, died, DeathCause.OLD_AGE)


@pytest.fixture
def family(world):
    """Animal ``a`` has one living parent ``b``, a dead one and dead grandparents above them; it has
    one dead child and one living grandchild that is not in the world (so cannot be selected)."""
    a, b = (animal.id for animal in world.animals[:2])
    add_kin(world, 5001, (), 0, 0, died=2)
    add_kin(world, 5002, (), 1, 0, died=2)
    add_kin(world, 5003, (5001, 5002), 1, 1, died=3)
    world.ancestry.get(a).parents = (b, 5003)
    world.ancestry._children.setdefault(b, []).append(a)
    world.ancestry._children.setdefault(5003, []).append(a)
    add_kin(world, 5101, (a,), 0, 3, died=3)
    add_kin(world, 5102, (5101,), 1, 3)
    return world, a, b


@pytest.fixture
def controller(qapp, clock, family):
    world, *_ = family
    ctl = make_controller(world, clock)
    yield ctl
    ctl.backend.close()


@pytest.fixture
def window(controller, tmp_path):
    settings = QtCore.QSettings(str(tmp_path / "v.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(controller, settings=settings)
    win.show()
    yield win
    win.close()


def select(controller, clock, animal_id):
    controller.poll()
    controller.send(Select(animal_id))
    clock.now += 1.0
    controller.poll()
    controller.poll()


def shown(tree):
    return {b.animal_id: b for b in tree.board.buttons if b.isVisibleTo(tree.board)}


# --- the window --------------------------------------------------------------------


def test_the_tree_shows_the_animal_its_ancestors_and_descendants(controller, window, clock, family):
    _, a, b = family
    select(controller, clock, a)
    tree = window.panels["inspector"].pages["family"].open_tree()
    nodes = shown(tree)
    assert set(nodes) == {a, b, 5003, 5001, 5002, 5101, 5102}
    assert tree.heading.text() == f"<b>Family of #{a}</b>"
    assert tree.layout_.rows == (-2, 2)
    assert nodes[a].text() == f"♂ #{a}" or nodes[a].text() == f"♀ #{a}"


def test_only_a_living_animal_in_the_frame_can_be_pressed(controller, window, clock, family):
    _, a, b = family
    select(controller, clock, a)
    nodes = shown(window.panels["inspector"].pages["family"].open_tree())
    assert nodes[b].isEnabled()
    assert not nodes[a].isEnabled()  # already selected
    for gone in (5001, 5002, 5003, 5101, 5102):  # dead, or not in the frame
        assert not nodes[gone].isEnabled()
    assert all(nodes[i].text().endswith(familytree.DEAD_GLYPH) for i in (5001, 5003, 5101))
    assert not nodes[5102].text().endswith(familytree.DEAD_GLYPH)


def test_pressing_an_animal_selects_it_and_the_tree_moves_to_it(controller, window, clock, family):
    _, a, b = family
    select(controller, clock, a)
    tree = window.panels["inspector"].pages["family"].open_tree()
    shown(tree)[b].click()
    clock.now += 1.0
    controller.poll()
    controller.poll()
    assert controller.status.selected == b
    assert tree.heading.text() == f"<b>Family of #{b}</b>"
    assert a in shown(tree) and b in shown(tree)
    assert not shown(tree)[b].isEnabled() and shown(tree)[a].isEnabled()


def test_the_tooltip_says_who_it_is(controller, window, clock, family):
    _, a, _ = family
    select(controller, clock, a)
    nodes = shown(window.panels["inspector"].pages["family"].open_tree())
    assert nodes[5003].toolTip().startswith("#5003, female, born ")
    assert "old age on" in nodes[5003].toolTip()
    assert nodes[5102].toolTip().endswith("alive")


def test_a_dead_animal_is_a_greyed_copy_of_its_colour_and_an_enabled_one_is_not(
    controller, window, clock, family
):
    _, a, b = family
    select(controller, clock, a)
    nodes = shown(window.panels["inspector"].pages["family"].open_tree())
    assert nodes[b].style_key[0] != nodes[5001].style_key[0]
    assert nodes[b].style_key[1] is False and nodes[5001].style_key[1] is True
    assert "dashed" in nodes[5001].styleSheet() and "dashed" not in nodes[b].styleSheet()
    assert "3px" in nodes[a].styleSheet()


def test_with_nothing_selected_the_window_says_so(controller, window, clock):
    controller.poll()
    tree = window.panels["inspector"].pages["family"].open_tree()
    assert "Nothing selected" in tree.note.text() and not shown(tree)


def test_a_simulation_with_no_family_record_says_so(qapp, clock, tmp_path):
    ctl = make_controller(FakeSimulation(10, 10, seed=1), clock)
    settings = QtCore.QSettings(str(tmp_path / "v.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(ctl, settings=settings)
    win.show()
    try:
        ctl.poll()
        animal_id = int(np.frombuffer(ctl.frame.animals.ids, dtype="<u4")[0])
        select(ctl, clock, animal_id)
        tree = win.panels["inspector"].pages["family"].open_tree()
        assert "no family record" in tree.note.text() and not shown(tree)
    finally:
        ctl.backend.close()
        win.close()


def test_a_forgotten_ancestor_is_said_in_a_note(world, qapp, clock, tmp_path):
    a = world.animals[0].id
    world.ancestry.get(a).parents = (7777,)  # an ancestor the book no longer has
    ctl = make_controller(world, clock)
    settings = QtCore.QSettings(str(tmp_path / "v.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(ctl, settings=settings)
    win.show()
    try:
        select(ctl, clock, a)
        tree = win.panels["inspector"].pages["family"].open_tree()
        assert tree.note.text() == "Older ancestors are not remembered."
    finally:
        ctl.backend.close()
        win.close()


def test_the_window_opens_from_the_family_tab_and_comes_back_on_a_second_press(
    controller, window, clock, family
):
    _, a, _ = family
    select(controller, clock, a)
    tab = window.panels["inspector"].pages["family"]
    assert tab.tree is None
    tab.tree_button.click()
    first = tab.tree
    assert first is not None and first.isVisible()
    first.close()
    tab.tree_button.click()
    assert tab.tree is first and first.isVisible()


def test_a_tree_opened_late_draws_at_once(controller, window, clock, family):
    _, a, _ = family
    select(controller, clock, a)
    tab = window.panels["inspector"].pages["family"]
    tab.open_tree()
    tab.tree.close()
    controller.poll()
    clock.now += 1.0
    controller.poll()
    tab.tree.show()
    assert len(shown(tab.tree)) == 7


# --- colours -----------------------------------------------------------------------


def test_the_family_scale_colours_a_key_as_the_world_view_does(controller, family):
    controller.poll()
    layer = Layer(controller.frame.animals)
    scale = palette.FamilyScale.of(layer)
    by_scale = scale.colours(layer.col("family_a"), layer.col("family_b"))
    assert (by_scale == palette.MODES_BY_ID["family"].colours(layer)).all()
    assert scale.colours(np.array([]), np.array([])).shape == (0, 3)


def test_a_frame_without_the_family_key_gives_a_flat_scale():
    scale = palette.FamilyScale((0.0, 0.0), (0.0, 0.0))
    assert (
        scale.colours(np.array([5.0]), np.array([9.0]))
        == scale.colours(np.array([1.0]), np.array([2.0]))
    ).all()


def test_text_is_black_on_light_and_white_on_dark():
    assert familytree.text_colour((255, 255, 255)) == "#000000"
    assert familytree.text_colour((0, 0, 80)) == "#ffffff"
    assert familytree.mixed((0, 100, 200), (100, 100, 100), 0.5) == (50, 100, 150)


def test_kin_lines_name_the_animal_and_its_end():
    alive = KinView(4, (), 0, 48, None, None, 0.0, 0.0)
    dead = KinView(5, (4,), 1, 96, 120, DeathCause.POISON, 0.0, 0.0)
    assert describe.kin_text(alive, 3600.0) == "#4, male, born day 2, alive"
    assert (
        describe.kin_text(dead, 3600.0)
        == "#5, female, born day 4, was poisoned by its food on day 5"
    )
    assert describe.kin_text(alive, None) == "#4, male, born tick 48, alive"
