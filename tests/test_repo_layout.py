"""Where code lives (INFRA.9): Python is under ``src/``; ``scripts/`` holds only shell wrappers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = {".ps1", ".bat", ".cmd", ".sh"}
SKIP = {".git", ".venv", "venv", "build", "dist", "node_modules", "__pycache__"}


def _files(folder: Path):
    for path in folder.rglob("*"):
        if path.is_file() and not (SKIP & set(path.relative_to(ROOT).parts)):
            yield path


def test_scripts_holds_only_shell_wrappers() -> None:
    odd = [p.name for p in _files(ROOT / "scripts") if p.suffix not in SHELL | {".md"}]
    assert not odd, f"scripts/ may hold only PowerShell, batch or bash files: {odd}"


def test_python_files_live_under_src_or_in_tests() -> None:
    allowed = {ROOT / "packaging" / "entry.py"}  # the PyInstaller entry shim
    stray = [
        str(p.relative_to(ROOT))
        for p in _files(ROOT)
        if p.suffix == ".py"
        and p not in allowed
        and (ROOT / "src") not in p.parents
        and (ROOT / "tests") not in p.parents
        and (ROOT / "benchmarks") not in p.parents  # benchmark tests (INFRA.7)
    ]
    assert not stray, f"Python source belongs under src/: {stray}"


def test_every_tool_has_a_wrapper_for_powershell_and_batch() -> None:
    tools = [
        p.stem for p in (ROOT / "src" / "evolution_tools").glob("*.py") if p.stem != "__init__"
    ]
    missing = []
    for tool in tools:
        wrapper = tool.replace("_", "-")
        for suffix in (".ps1", ".bat"):
            if not (ROOT / "scripts" / f"{wrapper}{suffix}").is_file():
                missing.append(f"{wrapper}{suffix}")
    assert not missing, f"add a wrapper in scripts/ for: {missing}"
