"""The core and the session never import Qt or numpy (UX.6): the base install has no dependencies."""

import ast
import subprocess
import sys
from pathlib import Path

import evolution_simulator

FORBIDDEN = ("numpy", "PySide6", "PyQt5", "PyQt6", "pyqtgraph", "shiboken6")
SOURCE = Path(evolution_simulator.__file__).parent
VIEWER = SOURCE / "viewer"  # UX.11 adds this package behind the "gui" extra, outside the core


def imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_no_core_module_names_a_gui_or_numeric_library():
    offenders = {}
    for path in sorted(SOURCE.rglob("*.py")):
        if VIEWER in path.parents:
            continue
        found = imports(path) & set(FORBIDDEN)
        if found:
            offenders[str(path.relative_to(SOURCE))] = sorted(found)
    assert offenders == {}


def test_importing_the_session_loads_neither_qt_nor_numpy():
    code = (
        "import sys\n"
        "import evolution_simulator.session\n"
        "import evolution_simulator.world\n"
        f"bad = [m for m in sys.modules if m.split('.')[0] in {FORBIDDEN!r}]\n"
        "print(bad)\n"
        "sys.exit(1 if bad else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_package_still_declares_no_dependencies():
    text = (SOURCE.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert "dependencies = []" in text
