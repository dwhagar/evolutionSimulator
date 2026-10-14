"""Shared test fixtures."""

import pytest

from evolution_simulator import traits as traits_module


@pytest.fixture
def sure_conception(monkeypatch):
    """Every mating takes, so a test can follow a pregnancy without depending on a dice roll."""
    monkeypatch.setattr(traits_module, "FERTILITY_CONCEPTION_BASE", 1.0)
    monkeypatch.setattr(traits_module, "FERTILITY_CONCEPTION_SLOPE", 0.0)
