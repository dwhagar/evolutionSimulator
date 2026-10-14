"""The world view canvas and panel (UX.12), on Qt's offscreen platform."""

import math
from array import array
from dataclasses import replace

import numpy as np
import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
QtGui = pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
QtTest = pytest.importorskip("PySide6.QtTest", exc_type=ImportError)
pytest.importorskip("numpy")

from worldview_support import WORLD, animal, make_frame, status

from evolution_simulator.session import (
    ANIMAL_COLUMNS,
    FakeSimulation,
    Pause,
    Play,
    Select,
    Session,
    SetSpeed,
)
from evolution_simulator.session.snapshot import Block
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.registry import ViewerContext
from evolution_simulator.viewer.worldview import palette
from evolution_simulator.viewer.worldview.camera import Camera
from evolution_simulator.viewer.worldview.canvas import WorldCanvas
from evolution_simulator.viewer.worldview.panel import WorldPanel
from evolution_simulator.world.views import CorpseView, PlantView


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def canvas(qapp, clock):
    widget = WorldCanvas(clock=clock)
    widget.resize(400, 400)
    widget.show()
    yield widget
    widget.close()


CENTRE = (200, 200)
"""Where a world (50, 50) lands when 100 by 100 units are fitted to a 400 pixel canvas."""


def pixel(widget, x, y):
    image = widget.grab().toImage()
    colour = image.pixelColor(int(x), int(y))
    return colour.red(), colour.green(), colour.blue()


def near(rgb, target, tolerance=40):
    return all(abs(a - b) <= tolerance for a, b in zip(rgb, target, strict=True))


def show(canvas, *animals, plants=None, **kw):
    frame = make_frame(animals, plants=plants, **kw)
    canvas.set_frame(frame, frame.plants)
    return frame


def test_it_says_so_before_the_first_frame(canvas):
    assert canvas.frame is None and canvas.animal_at(200, 200) is None
    assert pixel(canvas, 200, 200) == palette.OUTSIDE


def test_the_ground_is_tinted_by_the_daylight_and_the_wall_marks_the_edge(canvas):
    show(canvas, daylight=1.0)
    assert near(pixel(canvas, *CENTRE), palette.GROUND_DAY, 2)
    assert pixel(canvas, 5, 5) == palette.OUTSIDE
    show(canvas, daylight=0.0)
    assert near(pixel(canvas, *CENTRE), palette.GROUND_NIGHT, 2)
    left, _ = canvas.camera.to_screen(0.0, 50.0, (400.0, 400.0))
    assert near(pixel(canvas, left, 200), palette.WALL, 30)


def test_an_animal_is_a_triangle_pointing_along_its_heading_coloured_by_the_mode(canvas):
    show(canvas, animal(heading=0.0, diet=1.0))
    ahead, behind = (
        pixel(canvas, CENTRE[0] + 30, CENTRE[1]),
        pixel(canvas, CENTRE[0] - 52, CENTRE[1]),
    )
    assert near(ahead, palette.DIET_STOPS[-1], 25)
    assert near(behind, palette.GROUND_DAY, 8)
    show(canvas, animal(heading=math.pi / 2, diet=1.0))  # north: up the screen
    assert near(pixel(canvas, CENTRE[0], CENTRE[1] - 30), palette.DIET_STOPS[-1], 25)
    assert near(pixel(canvas, CENTRE[0], CENTRE[1] + 52), palette.GROUND_DAY, 8)


def test_the_colour_mode_changes_the_colour(canvas):
    show(canvas, animal(diet=1.0, sex=1))
    assert canvas.set_colour_mode("sex")
    assert near(pixel(canvas, *CENTRE), palette.FEMALE, 25)
    assert canvas.set_colour_mode("diet") and near(
        pixel(canvas, *CENTRE), palette.DIET_STOPS[-1], 25
    )
    assert canvas.set_colour_mode("family") and canvas.colour_mode == "family"
    assert not canvas.set_colour_mode("nonsense") and canvas.colour_mode == "family"


def test_a_sleeping_animal_is_dimmed_and_a_pregnant_one_has_a_dot(canvas):
    show(canvas, animal())
    awake = pixel(canvas, CENTRE[0] + 20, CENTRE[1])
    show(canvas, animal(asleep=True))
    asleep = pixel(canvas, CENTRE[0] + 20, CENTRE[1])
    assert sum(abs(a - g) for a, g in zip(asleep, palette.GROUND_DAY, strict=True)) < sum(
        abs(a - g) for a, g in zip(awake, palette.GROUND_DAY, strict=True)
    )
    show(canvas, animal(pregnant=True))
    assert near(pixel(canvas, *CENTRE), (255, 255, 255), 20)


def test_the_selected_animal_gets_a_ring(canvas):
    show(canvas, animal(), status=status(selected=1))
    assert canvas.selected == 1
    reach = 10.0 * 2.2 * canvas.camera.scale * 0.85
    assert near(pixel(canvas, CENTRE[0], CENTRE[1] - reach), (255, 255, 255), 30)
    canvas.set_selected(None)
    assert near(pixel(canvas, CENTRE[0], CENTRE[1] - reach), palette.GROUND_DAY, 8)


def test_plants_and_corpses_can_be_switched_off(canvas):
    plants = [PlantView(5, 20.0, 80.0, 6.0, 1.0, False)]
    corpse = CorpseView(6, 80.0, 20.0, 3.0, 5.0)
    show(canvas, plants=plants, corpses=[corpse])
    plant_at = tuple(int(v) for v in canvas.camera.to_screen(20.0, 80.0, (400.0, 400.0)))
    corpse_at = tuple(int(v) for v in canvas.camera.to_screen(80.0, 20.0, (400.0, 400.0)))
    assert near(pixel(canvas, *plant_at), palette.PLANT_FULL, 40)
    assert near(pixel(canvas, *corpse_at), palette.CORPSE, 40)
    canvas.set_option("show_plants", False)
    canvas.set_option("show_corpses", False)
    assert near(pixel(canvas, *plant_at), palette.GROUND_DAY, 6)
    assert near(pixel(canvas, *corpse_at), palette.GROUND_DAY, 6)
    with pytest.raises(ValueError):
        canvas.set_option("show_everything", True)


def test_the_plant_layer_is_painted_once_and_reused_until_something_changes(canvas):
    plants = [PlantView(5, 20.0, 80.0, 6.0, 1.0, False)]
    frame = make_frame([animal()], plants=plants)
    canvas.set_frame(frame, frame.plants)
    canvas.grab()
    first = canvas._cache
    assert first is not None
    canvas.grab()
    assert canvas._cache is first  # the same painting
    later = make_frame([animal(x=60.0)], tick=1)  # no plants in this frame
    canvas.set_frame(later, frame.plants)
    canvas.grab()
    assert canvas._cache is first  # moving animals do not repaint the plants
    canvas.camera.zoom_at(1.5, 100.0, 100.0, (400.0, 400.0), WORLD)
    canvas.grab()
    assert canvas._cache is not first  # a new view does
    third = canvas._cache
    fresh = make_frame([animal()], plants=[PlantView(5, 30.0, 80.0, 6.0, 1.0, False)], tick=2)
    canvas.set_frame(fresh, fresh.plants)
    canvas.grab()
    assert canvas._cache is not third  # and so do new plants


def test_a_click_finds_the_animal_under_the_pointer(canvas):
    show(canvas, animal(1, x=50.0, y=50.0), animal(2, x=80.0, y=80.0))
    canvas.grab()
    assert canvas.animal_at(*CENTRE) == 1
    near_two = canvas.camera.to_screen(80.0, 80.0, (400.0, 400.0))
    assert canvas.animal_at(near_two[0] + 3, near_two[1] - 2) == 2
    assert canvas.animal_at(20, 380) is None
    clicks = []
    canvas.animal_clicked.connect(clicks.append)
    QtTest.QTest.mouseClick(canvas, QtCore.Qt.MouseButton.LeftButton, pos=QtCore.QPoint(*CENTRE))
    QtTest.QTest.mouseClick(canvas, QtCore.Qt.MouseButton.LeftButton, pos=QtCore.QPoint(20, 380))
    assert clicks == [1, None]


def test_dragging_pans_instead_of_selecting_and_a_double_click_fits(canvas):
    show(canvas, animal())
    canvas.grab()
    clicks = []
    canvas.animal_clicked.connect(clicks.append)
    start = canvas.camera.key()
    button = QtCore.Qt.MouseButton.LeftButton
    QtTest.QTest.mousePress(canvas, button, pos=QtCore.QPoint(*CENTRE))
    QtTest.QTest.mouseMove(canvas, QtCore.QPoint(CENTRE[0] + 30, CENTRE[1] + 10))
    QtTest.QTest.mouseRelease(canvas, button, pos=QtCore.QPoint(CENTRE[0] + 30, CENTRE[1] + 10))
    assert clicks == [] and canvas.camera.key() != start
    assert not canvas._auto_fit
    QtTest.QTest.mouseDClick(canvas, button, pos=QtCore.QPoint(*CENTRE))
    assert canvas.camera.key() == start and canvas._auto_fit


def test_the_wheel_zooms_around_the_pointer(canvas):
    show(canvas, animal())
    anchor = QtCore.QPointF(100.0, 100.0)
    before = canvas.camera.to_world(100.0, 100.0, (400.0, 400.0))
    event = QtGui.QWheelEvent(
        anchor,
        anchor,
        QtCore.QPoint(0, 0),
        QtCore.QPoint(0, 120),
        QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
        QtCore.Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    scale = canvas.camera.scale
    canvas.wheelEvent(event)
    assert canvas.camera.scale > scale * 1.1
    assert canvas.camera.to_world(100.0, 100.0, (400.0, 400.0)) == pytest.approx(before)


def test_creatures_slide_between_ticks_while_playing_and_the_slide_carries_on_from_where_it_is(
    canvas, clock
):
    running = status(running=True)
    show(canvas, animal(x=10.0), tick=0, seconds=0.0, status=running)
    show(canvas, animal(x=20.0), tick=1, seconds=3600.0, status=running)  # an hour a second
    assert canvas.gliding and canvas._timer.isActive()
    assert canvas._shown_pose().x.tolist() == [10.0]
    clock.now += 0.5
    assert canvas._shown_pose().x.tolist() == [15.0]
    show(canvas, animal(x=30.0), tick=2, seconds=7200.0, status=running)  # arrives mid-slide
    assert canvas._shown_pose().x.tolist() == [15.0]  # starts from the picture, no jump
    clock.now += 1.0
    assert canvas._shown_pose().x.tolist() == [30.0] and not canvas.gliding


def test_a_paused_world_is_shown_exactly_and_a_fast_one_does_not_slide(canvas):
    show(canvas, animal(x=10.0), tick=0, seconds=0.0)
    show(canvas, animal(x=20.0), tick=1, seconds=3600.0)  # not running
    assert not canvas.gliding and canvas._shown_pose().x.tolist() == [20.0]
    assert not canvas._timer.isActive()
    fast = status(running=True, speed_asked=86_400.0, speed_preset="day")
    show(canvas, animal(x=30.0), tick=2, seconds=7200.0, status=fast)
    assert not canvas.gliding and canvas._shown_pose().x.tolist() == [30.0]


def test_when_the_computer_falls_behind_the_slide_follows_the_speed_it_manages(canvas, clock):
    slow = status(running=True, behind=True, speed_achieved=1800.0)  # asked 3600, got 1800
    show(canvas, animal(x=0.0), tick=0, seconds=0.0, status=slow)
    show(canvas, animal(x=10.0), tick=1, seconds=3600.0, status=slow)
    clock.now += 1.0
    assert canvas._shown_pose().x.tolist() == [5.0]  # a tick takes two seconds


def test_a_screenshot_is_the_size_of_the_view_and_a_file(canvas, tmp_path):
    show(canvas, animal())
    path = tmp_path / "world.png"
    assert canvas.save_screenshot(str(path))
    image = QtGui.QImage(str(path))
    assert (image.width(), image.height()) == (400, 400)
    assert not canvas.save_screenshot(str(tmp_path / "missing" / "world.png"))


def test_the_grid_and_the_scale_bar_draw_without_trouble_when_zoomed_far_in_and_out(canvas):
    show(canvas, animal())
    canvas.set_option("show_grid", True)
    for factor in (30.0, 0.01, 1.0):
        canvas.camera.zoom_at(factor, 200.0, 200.0, (400.0, 400.0), WORLD)
        assert canvas.grab().width() == 400


def test_an_empty_world_draws(canvas):
    show(canvas)
    assert near(pixel(canvas, *CENTRE), palette.GROUND_DAY, 2)


# --- the panel ---------------------------------------------------------------------


@pytest.fixture
def panel(qapp, clock):
    session = Session(FakeSimulation(25, 80, seed=4), clock=clock)
    backend = LocalBackend(session)
    controller = ViewerController(backend)
    messages = []
    context = ViewerContext(controller, {}, lambda text, ms: messages.append(text))
    view = WorldPanel(context, WorldCanvas(clock=clock))
    view.messages = messages
    view.resize(500, 520)
    view.show()
    controller.poll()
    view.canvas.fit_view()
    yield view
    view.close()
    backend.close()


def test_the_panel_draws_what_the_controller_receives(panel):
    assert panel.canvas.frame is panel.context.controller.frame
    assert panel.canvas._plants is not None and panel.canvas._plants.count == 80


def test_clicking_an_animal_selects_it_and_clicking_the_ground_deselects(panel):
    controller = panel.context.controller
    canvas = panel.canvas
    canvas.grab()
    ids = canvas._shown.ids
    target = int(ids[0])
    x, y = canvas.camera.to_screen(
        canvas._shown.x[0], canvas._shown.y[0], (canvas.width(), canvas.height())
    )
    button = QtCore.Qt.MouseButton.LeftButton
    QtTest.QTest.mouseClick(canvas, button, pos=QtCore.QPoint(round(x), round(y)))
    assert controller.status.selected == target and canvas.selected == target
    QtTest.QTest.mouseClick(canvas, button, pos=QtCore.QPoint(2, 2))
    assert controller.status.selected is None and canvas.selected is None


def test_the_toolbar_changes_the_colour_mode_and_the_layers(panel):
    box = panel.mode_box
    box.setCurrentIndex(box.findData("energy"))
    assert panel.canvas.colour_mode == "energy"
    panel.layer_boxes["show_grid"].setChecked(True)
    assert panel.canvas.show_grid
    panel.layer_boxes["show_plants"].setChecked(False)
    assert not panel.canvas.show_plants


def old_frame():
    """A frame from before UX.30: eight animal columns, no family numbers."""
    block = Block(
        ANIMAL_COLUMNS[:8],
        array("I", [1, 2]).tobytes(),
        array("f", [*[1, 1, 0, 1, 0.5, 1, 0.2, 0.5], *[2, 2, 0, 1, 0.5, 1, 0.2, 0.5]]).tobytes(),
        bytes(2),
    )
    return replace(make_frame([animal(1), animal(2)]), animals=block)


def test_the_family_mode_is_greyed_out_for_a_frame_without_the_family_numbers(panel):
    box = panel.mode_box
    assert panel.mode_items["family"].isEnabled()
    panel.canvas.set_colour_mode("family")
    frame = old_frame()
    panel.canvas.set_frame(frame, None)
    panel._on_frame(frame)
    assert not panel.mode_items["family"].isEnabled()
    assert box.currentData() == "diet" and panel.canvas.colour_mode == "diet"
    assert not panel.canvas.set_colour_mode("family")
    assert panel.canvas.grab().width() > 0  # and it still draws


def test_the_screenshot_button_saves_a_png_where_asked(panel, tmp_path, monkeypatch):
    from evolution_simulator.viewer.worldview import panel as module

    path = tmp_path / "shot.png"
    monkeypatch.setattr(module.QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    panel.save_screenshot()
    assert path.exists() and panel.messages[-1].startswith("Saved ")
    monkeypatch.setattr(module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    panel.save_screenshot()  # cancelled: nothing happens
    assert len(panel.messages) == 1


def test_the_fit_button_shows_the_whole_world_again(panel):
    panel.canvas.camera.zoom_at(4.0, 100.0, 100.0, (500.0, 520.0), (1000.0, 1000.0))
    panel.canvas._auto_fit = False
    panel.fit_button.click()
    assert panel.canvas._auto_fit
    assert panel.canvas.camera.scale == pytest.approx(
        Camera.fit_scale(panel.canvas.world, panel.canvas._size())
    )


def test_the_view_keeps_up_with_a_playing_fake_world(panel, clock):
    controller = panel.context.controller
    controller.send(SetSpeed("day"))
    controller.send(Play())
    for _ in range(40):
        clock.now += 0.05
        controller.poll()
        panel.canvas.grab()
    assert panel.canvas.frame.tick > 0
    assert np.isfinite(panel.canvas._shown.x).all()


# --- panning without repainting the plants, following, not drawing -----------------


def test_a_pan_inside_the_margin_slides_the_plant_painting_and_a_long_one_repaints_it(canvas):
    plants = [PlantView(5, 20.0, 80.0, 6.0, 1.0, False)]
    frame = make_frame([animal()], plants=plants)
    canvas.set_frame(frame, frame.plants)
    canvas.grab()
    first = canvas._cache
    canvas.camera.pan_pixels(60.0, 0.0, WORLD)  # under a quarter of the window
    canvas.grab()
    assert canvas._cache is first
    plant_at = canvas.camera.to_screen(20.0, 80.0, (400.0, 400.0))
    assert near(pixel(canvas, *plant_at), palette.PLANT_FULL, 40)  # still where the plant is
    canvas.camera.pan_pixels(200.0, 0.0, WORLD)
    canvas.grab()
    assert canvas._cache is not first


def test_following_keeps_the_selected_animal_in_the_middle_until_the_view_is_dragged(canvas):
    running = status(running=True, selected=1)
    show(canvas, animal(1, x=30.0, y=40.0), tick=0, seconds=0.0, status=running)
    canvas.set_follow(True)
    canvas.grab()
    assert (canvas.camera.cx, canvas.camera.cy) == pytest.approx((30.0, 40.0))
    show(canvas, animal(1, x=35.0, y=45.0), tick=1, seconds=0.0, status=status(selected=1))
    canvas.grab()
    assert (canvas.camera.cx, canvas.camera.cy) == pytest.approx((35.0, 45.0))
    changes = []
    canvas.follow_changed.connect(changes.append)
    button = QtCore.Qt.MouseButton.LeftButton
    QtTest.QTest.mousePress(canvas, button, pos=QtCore.QPoint(100, 100))
    QtTest.QTest.mouseMove(canvas, QtCore.QPoint(140, 100))
    QtTest.QTest.mouseRelease(canvas, button, pos=QtCore.QPoint(140, 100))
    assert not canvas.follow and changes == [False]


def test_following_with_nothing_selected_leaves_the_view_alone(canvas):
    show(canvas, animal(1, x=30.0, y=40.0))
    canvas.set_follow(True)
    before = canvas.camera.key()
    canvas.grab()
    assert canvas.camera.key() == before


def test_not_drawing_paints_only_a_note(canvas):
    show(canvas, animal())
    canvas.set_drawing(False)
    assert pixel(canvas, 30, 30) == palette.OUTSIDE
    assert near(pixel(canvas, 100, 100), palette.OUTSIDE, 1)  # no ground, plants or animals
    canvas.set_drawing(True)
    assert near(pixel(canvas, 100, 100), palette.GROUND_DAY, 3)


@pytest.fixture
def window(controller_for_window, tmp_path, qapp):
    from evolution_simulator.viewer.window import MainWindow

    settings = QtCore.QSettings(str(tmp_path / "v.ini"), QtCore.QSettings.Format.IniFormat)
    win = MainWindow(controller_for_window, settings=settings)
    win.show()
    yield win
    win.close()


@pytest.fixture
def controller_for_window(qapp, clock):
    backend = LocalBackend(Session(FakeSimulation(25, 80, seed=4), clock=clock))
    yield ViewerController(backend)
    backend.close()


def test_the_controls_switch_stops_the_drawing_only_while_fast_forwarding(window, clock):
    controller = window.controller
    panel = window.panels["world"]
    controller.poll()
    assert panel.canvas.drawing
    window.actions["no_draw_fast_forward"].setChecked(True)
    assert panel.canvas.drawing  # switched on, but the world is not running fast
    controller.send(SetSpeed("century"))
    controller.send(Play())
    assert not panel.canvas.drawing
    window.actions["no_draw_fast_forward"].setChecked(False)
    assert panel.canvas.drawing
    window.actions["no_draw_fast_forward"].setChecked(True)
    assert not panel.canvas.drawing
    controller.send(SetSpeed("day"))
    assert panel.canvas.drawing


def press_f(window):
    window.activateWindow()
    QtTest.QTest.qWaitForWindowActive(window)
    QtTest.QTest.keyClick(window, QtCore.Qt.Key.Key_F)


def test_the_f_key_follows_the_selected_creature_and_is_in_the_view_menu(window):
    controller = window.controller
    controller.poll()
    controller.send(Select(int(window.panels["world"].canvas._animals.ids[0])))
    assert [k.toString() for k in window.actions["follow_selected"].shortcuts()] == ["F"]
    press_f(window)
    assert window.panels["world"].canvas.follow and window.actions["follow_selected"].isChecked()
    assert window.actions["follow_selected"] in window.view_menu.actions()
    press_f(window)
    assert not window.panels["world"].canvas.follow


def test_while_the_world_is_not_drawn_the_session_is_asked_for_fewer_frames_and_then_for_plants(
    window,
):
    controller = window.controller
    session = controller.backend.session
    controller.poll()
    assert session.rules.frame_interval == pytest.approx(1 / 30)
    window.actions["no_draw_fast_forward"].setChecked(True)
    controller.send(SetSpeed("century"))
    controller.send(Play())
    assert not window.panels["world"].canvas.drawing
    assert session.rules.frame_interval == pytest.approx(0.5)  # a couple a second, not thirty
    controller.send(SetSpeed("day"))
    assert window.panels["world"].canvas.drawing
    assert session.rules.frame_interval == pytest.approx(1 / 30)
    controller.send(Pause())
    controller.poll()
    assert controller.frame.plants is not None  # the plants missed while away came back
