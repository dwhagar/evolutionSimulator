"""The Brain tab and the sense overlays (UX.15), on Qt's offscreen platform."""

import math
from dataclasses import replace

import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
QtGui = pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
pytest.importorskip("numpy")

from evolution_simulator.brain import DEFAULT_SHAPE, Brain
from evolution_simulator.brain_adapter import BrainDecision, BrainTrace
from evolution_simulator.sense_channels import INPUT_CHANNELS
from evolution_simulator.session import (
    FakeSimulation,
    Select,
    Session,
    SessionRules,
    SetSpeed,
    Step,
)
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.inspector import brainview, tabs
from evolution_simulator.viewer.inspector.brainview import SenseGeometry
from evolution_simulator.viewer.inspector.tab_brain import BarList, BrainTab
from evolution_simulator.viewer.window import MainWindow
from evolution_simulator.viewer.worldview import overlays
from evolution_simulator.viewer.worldview.camera import Camera
from evolution_simulator.viewer.worldview.overlays import OverlayHub, SelectedPose, hub_for
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


@pytest.fixture
def world():
    world = World(WorldConfig(seed=1))
    world.populate(animals=20, plants=80)
    return world


@pytest.fixture
def controller(qapp, world, clock):
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


def traced_detail(world):
    animal = world.animals[0]
    world.trace_brain(animal.id)
    for _ in range(30):
        world.step()
        detail = world.animal_detail(animal.id)
        if detail is not None and detail.brain is not None:
            return detail
    pytest.skip("the animal's brain did not run in 30 ticks")


# --- the plain data ----------------------------------------------------------------


def test_input_rows_follow_the_brains_order_and_carry_the_last_values(world):
    detail = traced_detail(world)
    rows = brainview.input_rows(detail)
    assert [r.key for r in rows] == [c.name for c in INPUT_CHANNELS]
    assert [r.value for r in rows] == list(detail.brain.inputs)
    by_key = {r.key: r for r in rows}
    assert by_key["energy_ratio"].group == "Body" and by_key["plant_closeness"].group == "Plant"
    assert by_key["daylight"].group == "Time and light" and by_key["touching"].group == "Touch"
    assert by_key["plant_direction"].signed and not by_key["plant_closeness"].signed
    assert by_key["plant_direction"].text.startswith(("+", "-"))
    assert "Bearing" in by_key["plant_direction"].tip


def test_input_rows_have_no_values_until_the_brain_has_run(world):
    detail = world.animal_detail(world.animals[0].id)
    assert detail.brain is None
    rows = brainview.input_rows(detail)
    assert len(rows) == len(INPUT_CHANNELS)
    assert all(r.value is None and r.text == "-" for r in rows)


def test_grouping_gathers_each_group_once_and_keeps_the_order_inside_it(world):
    rows = brainview.input_rows(world.animal_detail(world.animals[0].id))
    grouped = brainview.grouped(rows)
    assert sorted(r.key for r in grouped) == sorted(r.key for r in rows)
    headings = [
        g for i, g in enumerate(r.group for r in grouped) if i == 0 or g != grouped[i - 1].group
    ]
    assert len(headings) == len(set(headings))
    body = [r.key for r in grouped if r.group == "Body"]
    assert body == [r.key for r in rows if r.group == "Body"]


def test_output_rows_show_the_decision_and_the_proposal_when_it_wandered(world):
    detail = traced_detail(world)
    decision = BrainDecision(0.5, 0.4, 0.9, 0.0, 0.0, 0.0, wandering=True)
    trace = BrainTrace(
        detail.brain.inputs,
        detail.brain.hidden,
        (0.1, 0.2, 0.0, 0.0, 0.0, 0.0),
        (0.5, 0.4, 0.9, 0.0, 0.0, 0.0),
    )
    rows = brainview.output_rows(replace(detail, decision=decision, brain=trace))
    assert [r.key for r in rows] == [
        "turn",
        "speed",
        "eat_or_attack",
        "seek_mating",
        "alarm_call",
        "mating_call",
    ]
    turn, speed, eat = rows[0], rows[1], rows[2]
    assert turn.signed and turn.value == 0.5 and turn.marker == 0.1
    assert speed.marker == 0.2 and "wander" in speed.tip
    assert eat.threshold == 0.5 and eat.value == 0.9 and not eat.signed
    calm = brainview.output_rows(replace(detail, decision=replace(decision, wandering=False)))
    assert all(r.marker is None for r in calm)


def test_output_rows_without_a_decision_fall_back_to_the_traced_action(world):
    detail = traced_detail(world)
    rows = brainview.output_rows(replace(detail, decision=None))
    assert [r.value for r in rows] == list(detail.brain.action)
    empty = brainview.output_rows(replace(detail, decision=None, brain=None))
    assert all(r.value is None for r in empty)


def test_the_network_model_leaves_out_connections_that_are_off():
    values = [0.0] * DEFAULT_SHAPE.weight_count
    brain = Brain.from_values(DEFAULT_SHAPE, values)
    empty = brainview.network_model(brain.network())
    assert empty.input_edges == () and empty.output_edges == () and empty.max_weight == 0.0
    assert (empty.inputs, empty.hidden, empty.outputs) == (28, 8, 6)
    values[1 + 3] = 1.5  # hidden 0: input 3
    values[1 + DEFAULT_SHAPE.inputs + 2] = -0.5  # hidden 0: output 2
    model = brainview.network_model(
        Brain.from_values(DEFAULT_SHAPE, values).network((0, 1, 2, 3, 4, 5, 6, 7), 16)
    )
    assert [(e.source, e.target, e.weight) for e in model.input_edges] == [(3, 0, 1.5)]
    assert [(e.source, e.target, e.weight) for e in model.output_edges] == [(0, 2, -0.5)]
    assert model.max_weight == 1.5 and model.slots == tuple(range(8))


def test_the_sense_geometry_matches_what_the_animal_senses(world):
    animal = world.animals[0]
    detail = world.animal_detail(animal.id)
    geometry = brainview.sense_geometry(detail)
    traits = animal.traits
    assert geometry.vision_range == pytest.approx(traits.current_sight_range)
    assert geometry.hearing_range == pytest.approx(traits.current_hearing_range)
    assert geometry.smell_range == pytest.approx(traits.smell_range)
    assert geometry.touch_range == pytest.approx(traits.tactile_range)
    assert geometry.fov_half_degrees == pytest.approx(traits.fov_half_degrees)
    old = brainview.sense_geometry(replace(detail, vitality=0.0))
    assert old.vision_range < geometry.vision_range and old.hearing_range < geometry.hearing_range
    assert old.smell_range == geometry.smell_range  # smell does not weaken with age


def test_a_detail_without_sense_traits_gives_no_geometry(qapp):
    sim = FakeSimulation(5, 5, seed=1)
    detail = sim.animal_detail(next(iter(sim.animal_views())).id)
    assert not brainview.sense_geometry(detail).any


# --- the overlays ------------------------------------------------------------------


def paint_to_image(hub, pose, scale=2.0, size=(400, 400)):
    image = QtGui.QImage(size[0], size[1], QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor(0, 0, 0, 0))
    painter = QtGui.QPainter(image)
    camera = Camera(scale=scale, cx=pose.x, cy=pose.y)
    hub.paint(painter, camera, (float(size[0]), float(size[1])), pose)
    painter.end()
    return image


def test_the_hub_is_one_per_controller_and_tells_when_it_changes(controller):
    hub = hub_for(controller)
    assert hub is hub_for(controller) and not hub.active
    seen = []
    hub.changed.connect(lambda: seen.append(1))
    hub.set_geometry(SenseGeometry(vision_range=50.0, fov_half_degrees=45.0))
    assert hub.active and len(seen) == 1
    hub.set_geometry(SenseGeometry(vision_range=50.0, fov_half_degrees=45.0))
    assert len(seen) == 1  # the same geometry is not news
    hub.set_shown("vision", False)
    assert set(hub.shown) == {"hearing", "smell"} and len(seen) == 2
    hub.set_shown("vision", False)
    assert len(seen) == 2
    with pytest.raises(ValueError):
        hub.set_shown("taste", True)
    hub.set_geometry(None)
    assert not hub.active


def test_vision_is_a_wedge_that_points_the_way_the_animal_faces(qapp):
    hub = OverlayHub()
    hub.set_geometry(SenseGeometry(vision_range=80.0, fov_half_degrees=40.0))
    for sense in ("hearing", "smell", "touch"):
        hub.set_shown(sense, False)
    for heading in (0.0, math.pi / 2, math.pi, -math.pi / 2):
        image = paint_to_image(hub, SelectedPose(100.0, 100.0, heading))
        ahead_x = (
            200 + math.cos(heading) * 60.0
        )  # 60 units at scale 2 is 120 px; stay inside 80 units
        ahead_y = 200 - math.sin(heading) * 60.0
        behind_x = 200 - math.cos(heading) * 60.0
        behind_y = 200 + math.sin(heading) * 60.0
        assert image.pixelColor(int(ahead_x), int(ahead_y)).alpha() > 0, heading
        assert image.pixelColor(int(behind_x), int(behind_y)).alpha() == 0, heading


def test_a_wide_field_or_the_other_senses_are_circles(qapp):
    hub = OverlayHub()
    hub.set_geometry(SenseGeometry(vision_range=40.0, fov_half_degrees=180.0, hearing_range=30.0))
    hub.set_shown("smell", False)
    image = paint_to_image(hub, SelectedPose(100.0, 100.0, 0.0))
    for dx, dy in ((30, 0), (-30, 0), (0, 30), (0, -30)):
        assert image.pixelColor(200 + dx, 200 + dy).alpha() > 0


def test_nothing_is_painted_when_nothing_is_shown_or_known(qapp):
    hub = OverlayHub()
    pose = SelectedPose(100.0, 100.0, 0.0)
    assert paint_to_image(hub, pose).pixelColor(200, 200).alpha() == 0
    hub.set_geometry(SenseGeometry(vision_range=40.0, fov_half_degrees=40.0))
    for sense in overlays.SENSES:
        hub.set_shown(sense, False)
    image = paint_to_image(hub, pose)
    assert all(image.pixelColor(x, 200).alpha() == 0 for x in range(0, 400, 7))


# --- the tab -----------------------------------------------------------------------


def test_the_tab_is_discovered_after_the_family_tab(qapp):
    specs = {spec.id: spec for spec in tabs.discover_tabs()}
    assert "brain" in specs and specs["brain"].title == "Brain"
    order = [spec.id for spec in tabs.discover_tabs()]
    assert order.index("brain") > order.index("body")


def select_and_run(controller, clock, world, ticks=3):
    animal = world.animals[0]
    controller.poll()
    controller.send(Select(animal.id))
    controller.send(SetSpeed("hour"))
    controller.send(Step(ticks))
    for _ in range(6):
        clock.now += 0.2
        controller.poll()
    return animal


def test_the_tab_waits_for_a_brain_run_then_shows_values(window, controller, world, clock):
    tab = window.panels["inspector"].pages["brain"]
    assert isinstance(tab, BrainTab) and tab.status.text() == "Nothing selected."
    animal = world.animals[0]
    controller.poll()
    controller.send(Select(animal.id))
    controller.poll()
    clock.now += 0.2
    controller.poll()
    detail = controller.detail
    assert detail is not None
    tab.show_detail(replace(detail, brain=None))
    assert "Waiting" in tab.status.text()
    assert all(r.value is None for r in tab.inputs.rows)
    assert len(tab.network.model.input_edges) > 0  # the wiring needs no run
    tab.show_detail(traced_detail(world))
    assert tab.status.text() != "Nothing selected." and "Waiting" not in tab.status.text()
    assert any(r.value is not None for r in tab.inputs.rows)
    assert len(tab.outputs.rows) == 6 and len(tab.inputs.rows) == len(INPUT_CHANNELS)
    assert tab.network.hidden is not None and len(tab.network.hidden) == tab.network.model.hidden


def test_clearing_the_selection_clears_the_tab_and_the_overlay(window, controller, world, clock):
    tab = window.panels["inspector"].pages["brain"]
    select_and_run(controller, clock, world)
    assert controller.detail is not None
    assert tab.hub.active
    window.panels["inspector"].deselect()
    assert tab.status.text() == "Nothing selected." and not tab.hub.active
    assert tab.inputs.rows == () and tab.network.model is None


def test_a_dead_creature_keeps_its_last_values_but_draws_no_overlay(window, world):
    tab = window.panels["inspector"].pages["brain"]
    detail = traced_detail(world)
    tab.show_detail(detail)
    assert tab.hub.active
    tab.show_detail(replace(detail, alive=False))
    assert "Dead" in tab.status.text() and not tab.hub.active
    assert any(r.value is not None for r in tab.inputs.rows)


def test_the_checkboxes_switch_the_overlays(window):
    tab = window.panels["inspector"].pages["brain"]
    hub = tab.hub
    assert {s for s, box in tab.sense_boxes.items() if box.isChecked()} == set(hub.shown)
    tab.sense_boxes["touch"].setChecked(True)
    tab.sense_boxes["vision"].setChecked(False)
    assert set(hub.shown) == {"hearing", "smell", "touch"}


def test_the_world_canvas_draws_the_overlay(window, controller, world, clock):
    canvas = window.panels["world"].canvas
    assert canvas.overlays is hub_for(controller)
    animal = select_and_run(controller, clock, world)
    canvas.camera.cx, canvas.camera.cy = animal.position.coords
    canvas.camera.scale = 4.0
    canvas._auto_fit = False
    hub = hub_for(controller)
    hub.set_shown("vision", False)
    hub.set_shown("smell", False)
    hub.set_shown("hearing", False)
    plain = canvas.grab().toImage()
    hub.set_shown("hearing", True)
    with_hearing = canvas.grab().toImage()
    assert plain != with_hearing
    hub.set_shown("hearing", False)
    assert canvas.grab().toImage() == plain


def test_the_bars_report_the_row_under_the_pointer(qapp, world):
    bars = BarList(None)
    rows = brainview.input_rows(world.animal_detail(world.animals[0].id))
    bars.set_rows(brainview.grouped(rows))
    first = bars._layout[1][0]  # the first row, under the first heading
    assert bars.row_at(first + 2).key == "energy_ratio"
    assert bars.row_at(0.0) is None  # a heading
    assert bars.height() > len(rows) * 10
    bars.set_rows(())
    assert bars.height() < 5 or bars._layout == []


def test_the_tab_works_on_a_stand_in_simulation(qapp, clock, tmp_path):
    ctl = make_controller(FakeSimulation(10, 20, seed=2), clock)
    settings = QtCore.QSettings(str(tmp_path / "f.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(ctl, settings=settings)
    win.show()
    ctl.poll()
    animal = ctl.frame.animals.ids
    ctl.send(Select(int.from_bytes(animal[:4], "little")))
    for _ in range(4):
        clock.now += 0.2
        ctl.poll()
    tab = win.panels["inspector"].pages["brain"]
    assert tab.network.model is not None and tab.network.model.input_edges
    assert not tab.hub.active  # a stand-in has no sense genes to draw
    win.close()
    ctl.backend.close()
