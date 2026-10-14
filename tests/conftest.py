"""Shared test fixtures."""

import gc
import os
from dataclasses import replace

import pytest
import world_support

from evolution_simulator.config import DEFAULT_RULES


@pytest.fixture
def sure_conception(monkeypatch):
    """Every mating takes, so a test can follow a pregnancy without depending on a dice roll.
    Worlds made by ``hourly_world`` carry these rules."""
    sure = replace(
        DEFAULT_RULES,
        reproduction=replace(DEFAULT_RULES.reproduction, conception_base=1.0, conception_slope=0.0),
    )
    monkeypatch.setattr(world_support, "TEST_RULES", sure)


@pytest.fixture(autouse=True)
def no_save_prompt(monkeypatch):
    """Closing a window on an unsaved world asks "Save this run?" (UX.37); a test that closes one
    must not wait on a dialog nobody answers, so the answer is Discard unless the test sets its
    own (``panel.ask_to_save = ...``)."""
    try:
        from PySide6.QtWidgets import QMessageBox

        from evolution_simulator.viewer.panels import runs
    except ImportError:  # the gui extra is not installed
        return
    monkeypatch.setattr(
        runs.RunsPanel,
        "ask_to_save",
        lambda self, never_saved: QMessageBox.StandardButton.Discard,
    )


@pytest.fixture(scope="session")
def qapp():
    """The one ``QApplication`` of a test run, on Qt's offscreen platform (no display needed).
    Tests that use it skip when the ``gui`` extra (or a library it needs) is not installed."""
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = widgets.QApplication.instance() or widgets.QApplication(["tests"])
    yield app
    # Windows still alive here sit in reference cycles; free them while the application exists,
    # or the interpreter crashes when it frees them at exit.
    app.closeAllWindows()
    app.processEvents()
    gc.collect()
