"""Python 3.12 or newer, everywhere it is stated (INFRA.11)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import evolution_simulator

ROOT = Path(__file__).resolve().parents[1]
MINIMUM = ".".join(str(n) for n in evolution_simulator.MINIMUM_PYTHON)


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_pyproject_requires_the_minimum_python() -> None:
    assert _pyproject()["project"]["requires-python"] == f">={MINIMUM}"


def test_ruff_targets_the_minimum_python() -> None:
    target = _pyproject()["tool"]["ruff"]["target-version"]
    assert target == "py" + MINIMUM.replace(".", "")


def test_workflows_use_the_minimum_python() -> None:
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        versions = re.findall(r'python-version:\s*"([\d.]+)"', workflow.read_text(encoding="utf-8"))
        assert versions, f"{workflow.name} sets no python-version"
        assert set(versions) == {MINIMUM}, workflow.name


def test_the_readme_states_the_minimum_python() -> None:
    assert f"Python {MINIMUM} or newer" in (ROOT / "README.md").read_text(encoding="utf-8")
