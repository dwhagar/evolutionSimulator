"""Shared test fixtures."""

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
