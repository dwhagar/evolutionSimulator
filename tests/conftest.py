"""Shared test fixtures."""

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


@pytest.fixture(scope="session")
def qapp():
    """The one ``QApplication`` of a test run, on Qt's offscreen platform (no display needed).
    Tests that use it skip when the ``gui`` extra (or a library it needs) is not installed."""
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return widgets.QApplication.instance() or widgets.QApplication(["tests"])
