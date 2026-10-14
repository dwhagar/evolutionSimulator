"""Themes, the shortcuts window, the About box, tidy messages and the parenting rule (UX.21)."""

import ast
import re
from pathlib import Path

import pytest

QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)

from PySide6.QtGui import QAction, QKeySequence

from evolution_simulator import __version__
from evolution_simulator.session import FakeSimulation, Session
from evolution_simulator.viewer import about, help, theme
from evolution_simulator.viewer.backend import LocalBackend
from evolution_simulator.viewer.controller import ViewerController
from evolution_simulator.viewer.panels.controls import KEY_MAP
from evolution_simulator.viewer.window import THEME_KEY, MainWindow, tidy_message

VIEWER = Path(__file__).resolve().parent.parent / "src" / "evolution_simulator" / "viewer"


@pytest.fixture
def controller(qapp):
    backend = LocalBackend(Session(FakeSimulation(30, 100, seed=3)))
    yield ViewerController(backend)
    backend.close()


@pytest.fixture
def settings(tmp_path):
    return QtCore.QSettings(str(tmp_path / "viewer.ini"), QtCore.QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def native_theme(qapp):
    """Every test starts and ends on the system theme, so none leaves the application dark."""
    theme.apply_theme(qapp, "system")
    yield
    theme.apply_theme(qapp, "system")


@pytest.fixture
def window(controller, settings):
    win = MainWindow(controller, settings=settings)
    win.show()
    yield win
    win.close()


def window_colour(qapp) -> tuple[int, int, int]:
    colour = qapp.palette().window().color()
    return colour.red(), colour.green(), colour.blue()


# --- themes -------------------------------------------------------------------------------------


def test_dark_and_light_change_the_applications_palette_and_system_puts_it_back(qapp):
    native = window_colour(qapp)
    theme.apply_theme(qapp, "dark")
    dark = window_colour(qapp)
    assert sum(dark) < 3 * 100 and theme.applied_theme() == "dark"
    theme.apply_theme(qapp, "light")
    light = window_colour(qapp)
    assert sum(light) > 3 * 200 and theme.applied_theme() == "light"
    theme.apply_theme(qapp, "system")
    assert window_colour(qapp) == native and theme.applied_theme() == "system"


def test_an_unknown_theme_is_refused(qapp):
    with pytest.raises(ValueError, match="Unknown theme"):
        theme.apply_theme(qapp, "sepia")
    with pytest.raises(ValueError, match="no palette"):
        theme.palette_for("system")


def test_the_view_menu_offers_the_themes_and_the_choice_is_remembered(
    window, controller, settings, qapp
):
    submenu = next(a.menu() for a in window.view_menu.actions() if a.menu() is not None)
    assert [a.text() for a in submenu.actions()] == [theme.THEME_TEXT[m] for m in theme.THEMES]
    assert window.actions["theme_system"].isChecked()
    window.actions["theme_dark"].trigger()
    assert theme.applied_theme() == "dark" and window.actions["theme_dark"].isChecked()
    assert not window.actions["theme_system"].isChecked()
    assert settings.value(THEME_KEY) == "dark"

    again = MainWindow(controller, settings=settings)  # a later start
    assert theme.applied_theme() == "dark" and again.actions["theme_dark"].isChecked()
    again.close()


def test_a_theme_that_is_not_one_in_the_settings_means_the_system_theme(controller, settings, qapp):
    settings.setValue(THEME_KEY, "neon")
    win = MainWindow(controller, settings=settings)
    assert win.saved_theme() == "system" and win.actions["theme_system"].isChecked()
    win.close()


def test_resetting_the_layout_does_not_forget_the_theme(window, settings):
    window.actions["theme_light"].trigger()
    window.reset_layout()
    assert settings.value(THEME_KEY) == "light"


def test_the_charts_take_the_new_colours_when_the_theme_changes(window, qapp):
    from evolution_simulator.viewer.panels.charts import ChartsPanel

    charts = window.panels["charts"]
    assert isinstance(charts, ChartsPanel)
    plot = charts.chart_tabs[0].plot
    before = plot.backgroundBrush().color().name()
    window.actions["theme_dark"].trigger()
    qapp.processEvents()
    assert plot.backgroundBrush().color().name() != before
    assert plot.backgroundBrush().color().name() == qapp.palette().window().color().name()
    window.actions["theme_light"].trigger()
    qapp.processEvents()
    assert plot.backgroundBrush().color().name() == qapp.palette().window().color().name()


# --- the shortcuts window ------------------------------------------------------------------------


def test_every_key_of_the_map_has_a_description_and_none_is_stale():
    assert set(help.KEY_TEXT) == set(KEY_MAP)


def test_the_shortcut_rows_list_the_key_map_first_and_then_the_other_actions(window):
    rows = help.shortcut_rows(window.actions)
    labels = [row.label for row in rows]
    assert labels[: len(KEY_MAP)] == [help.KEY_TEXT[name] for name in KEY_MAP]
    play = rows[0]
    assert play.label == "Play or pause" and play.keys == ("Space",)
    assert "Keyboard shortcuts" in labels
    assert all(row.keys for row in rows)


def test_the_rows_follow_the_actions_keys_and_fall_back_to_the_key_map(qapp):
    bound = QAction("Play")
    bound.setShortcuts([QKeySequence("P"), QKeySequence("Ctrl+P")])
    rows = help.shortcut_rows({"play_pause": bound})
    assert rows[0].keys[0] == "P" and len(rows[0].keys) == 2
    assert rows[1].keys == KEY_MAP["step"]  # no action for it: the key map's own keys


def test_a_key_added_to_an_action_shows_up_without_editing_the_window(window):
    extra = QAction("Zoom the world", window)
    extra.setShortcut(QKeySequence("Ctrl+9"))
    window.actions["zoom_the_world"] = extra
    assert "Zoom the world" in [row.label for row in help.shortcut_rows(window.actions)]


def test_the_shortcuts_text_names_the_keys_and_the_mouse(window):
    text = help.shortcuts_html(window.actions)
    assert "<b>Space</b>" in text and "Play or pause" in text
    assert "<b>+</b> or <b>=</b>" in text  # two keys on one action
    assert "Pan" in text and "Zoom around the pointer" in text


def test_f1_and_the_help_menu_open_the_shortcuts_window(window):
    assert window.actions["shortcuts"].shortcut() == QKeySequence(
        QKeySequence.StandardKey.HelpContents
    )
    window.actions["shortcuts"].trigger()
    first = window.shortcuts_dialog
    assert first is not None and first.isVisible()
    assert "Play or pause" in first.browser.toPlainText()
    window.actions["shortcuts"].trigger()  # asking again shows a current list, not a second window
    assert window.shortcuts_dialog is not first
    window.shortcuts_dialog.close()
    titles = [a.text().replace("&", "") for a in window.help_menu.actions()]
    assert titles == ["Keyboard shortcuts", "About"]


# --- the About box -------------------------------------------------------------------------------


def test_the_version_comes_from_the_build_folder_first(tmp_path):
    (tmp_path / "VERSION").write_text("1.2.34\n", encoding="utf-8")
    assert about.program_version(root=tmp_path, folder=tmp_path) == "1.2.34"


def test_a_source_checkout_reports_its_own_version(tmp_path):
    version = about.program_version(folder=tmp_path)  # no VERSION file there
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert version.startswith(f"{_toml_major_minor()}.")


def _toml_major_minor() -> str:
    import tomllib

    data = tomllib.loads((about.SOURCE_ROOT / "version.toml").read_text())
    return f"{data['major']}.{data['minor']}"


def test_with_no_version_file_and_no_checkout_the_installed_version_is_shown(tmp_path):
    assert about.program_version(root=tmp_path, folder=tmp_path) == __version__


def test_the_notices_come_from_the_build_then_the_source_then_a_built_in_list(tmp_path):
    (tmp_path / "THIRD_PARTY_NOTICES.md").write_text("# Mine\n", encoding="utf-8")
    assert about.notices_text(root=tmp_path, folder=tmp_path) == "# Mine\n"
    source = about.notices_text(root=about.SOURCE_ROOT, folder=tmp_path / "nowhere")
    assert "PySide6" in source and "pyqtgraph" in source
    empty = tmp_path / "empty"
    empty.mkdir()
    assert about.notices_text(root=empty, folder=empty) == about.FALLBACK_NOTICES
    assert "LGPL" in about.FALLBACK_NOTICES


def test_the_about_text_has_the_version_the_licence_and_the_source():
    text = about.about_html("9.9.9")
    assert "Version 9.9.9" in text and about.LICENCE_URL in text and about.REPOSITORY_URL in text
    assert "CC0 1.0" in text and "pyqtgraph" in text


def test_the_about_box_shows_the_version_and_opens_the_notices(window):
    window.actions["about"].trigger()
    dialog = window.about_dialog
    assert dialog is not None and dialog.isVisible()
    assert "Version" in dialog.browser.toPlainText() and "CC0" in dialog.browser.toPlainText()
    dialog.notices_button.click()
    assert dialog.notices is not None and dialog.notices.isVisible()
    assert "PySide6" in dialog.notices.browser.toPlainText()
    window.actions["about"].trigger()  # the same dialog again
    assert window.about_dialog is dialog
    dialog.notices.close()
    dialog.close()


# --- status messages and tooltips ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "tidy"),
    [
        ("saved the preset 'a'", "Saved the preset 'a'."),
        ("Already at the fastest", "Already at the fastest."),
        ("Cannot start: seed is not a number.", "Cannot start: seed is not a number."),
        ("  spaced   out  ", "Spaced out."),
        ("Really?", "Really?"),
        ("", ""),
    ],
)
def test_messages_are_sentences(text, tidy):
    assert tidy_message(text) == tidy


def test_the_window_and_its_panels_say_things_as_sentences(window):
    window.show_message("wrote 12 rows")
    assert window.statusBar().currentMessage() == "Wrote 12 rows."
    window.panels["controls"].context.show_message("nothing to do")
    assert window.statusBar().currentMessage() == "Nothing to do."


def test_every_menu_action_explains_itself_on_the_status_bar(window):
    docks = {dock.toggleViewAction() for dock in window.docks.values()}  # Qt's own, named by title
    missing = []
    for menu in (window.file_menu, window.run_menu, window.view_menu, window.help_menu):
        for action in menu.actions():
            if action.isSeparator() or action.menu() is not None or action in docks:
                continue
            if not action.statusTip():
                missing.append(action.text())
    assert missing == []
    for label in window.status_labels.values():
        assert label.toolTip()


# --- the parenting rule ------------------------------------------------------------------------------

WIDGETS = {
    "QWidget",
    "QLabel",
    "QPushButton",
    "QToolButton",
    "QCheckBox",
    "QRadioButton",
    "QComboBox",
    "QLineEdit",
    "QPlainTextEdit",
    "QTextEdit",
    "QTextBrowser",
    "QSpinBox",
    "QDoubleSpinBox",
    "QSlider",
    "QFrame",
    "QGroupBox",
    "QScrollArea",
    "QTabWidget",
    "QStackedWidget",
    "QTableWidget",
    "QListWidget",
    "QTreeWidget",
    "QSplitter",
    "QProgressBar",
    "QDockWidget",
    "QDialog",
    "QMenu",
}
TEXT_FIRST = {
    "QLabel",
    "QPushButton",
    "QToolButton",
    "QCheckBox",
    "QRadioButton",
    "QLineEdit",
    "QPlainTextEdit",
    "QTextEdit",
    "QGroupBox",
    "QDockWidget",
    "QMenu",
}
"""Widgets whose first argument may be the text, so one argument alone is not a parent."""


TEXT_LIKE = re.compile(
    r"(text|label|title|name|tip|message|msg|caption|legend|note)$", re.IGNORECASE
)


def _is_text(node: ast.expr) -> bool:
    """Whether a lone argument is the widget's text and not its parent (``QLabel(label)``)."""
    ident = node.id if isinstance(node, ast.Name) else getattr(node, "attr", "")
    return ident.isupper() or bool(TEXT_LIKE.search(ident))


def _is_parent(node: ast.expr) -> bool:
    """Whether an argument looks like a parent widget: a name or an attribute (self.stack), not a
    literal, a string built on the spot or a Qt enum (``Qt.Orientation.Horizontal``)."""
    if isinstance(node, ast.Name):
        return not node.id.isupper()
    if isinstance(node, ast.Attribute):
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        return isinstance(root, ast.Name) and root.id not in {"Qt", "QFrame", "QSizePolicy"}
    return False


def widgets_without_a_parent(source: str) -> list[int]:
    """The line numbers of widgets made with no parent in ``source``."""
    lines = source.splitlines()
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name not in WIDGETS or "no-parent" in lines[node.lineno - 1]:
            continue
        if any(kw.arg == "parent" for kw in node.keywords):
            continue
        args = node.args
        if name in TEXT_FIRST and len(args) == 1:
            ok = _is_parent(args[0]) and not _is_text(args[0])
        else:
            ok = bool(args) and _is_parent(args[-1])
        if not ok:
            found.append(node.lineno)
    return found


def test_the_checker_sees_a_widget_made_without_a_parent():
    bad = "x = QLabel('text')\ny = QCheckBox(label)\nz = QWidget()\nw = QSlider(Qt.Orientation.Horizontal)"
    good = (
        "a = QLabel('text', self)\nb = QWidget(parent)\nc = QLabel(self)\n"
        "d = QSlider(Qt.Orientation.Horizontal, self)\ne = QTableWidget(0, 5, self)\n"
        "f = QLabel('x', parent=self)\ng = QWidget()  # no-parent: a window"
    )
    assert widgets_without_a_parent(bad) == [1, 2, 3, 4]
    assert widgets_without_a_parent(good) == []


@pytest.mark.parametrize(
    "path", sorted(VIEWER.rglob("*.py")), ids=lambda p: p.relative_to(VIEWER).as_posix()
)
def test_every_widget_the_viewer_makes_is_given_its_parent_when_it_is_made(path):
    """The PySide6 rule found in UX.12 (a widget made with no parent and moved later has led to a
    double free): pass the parent to the constructor. A widget that really is a window of its own
    says so with ``# no-parent`` on its line."""
    lines = widgets_without_a_parent(path.read_text(encoding="utf-8"))
    assert not lines, f"{path.name}: widgets made without a parent on lines {lines}"


@pytest.mark.parametrize(
    "path", sorted(VIEWER.rglob("*.py")), ids=lambda p: p.relative_to(VIEWER).as_posix()
)
def test_nothing_reads_an_item_back_from_a_combo_boxs_model(path):
    """``combo.model().item(i)`` crashes some PySide6 builds; keep the data in ``itemData`` and
    set per-item looks through ``setItemData`` instead."""
    assert ".model().item(" not in path.read_text(encoding="utf-8")
