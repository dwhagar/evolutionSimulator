"""The Windows launcher in the repository root (INFRA.10): ``run.ps1`` and ``run.bat``.

PowerShell is not part of the test machine, so most of this is a text check of the steps the
launcher must take. When a PowerShell is on the path (``pwsh``, or ``powershell`` on Windows) the
script is also parsed with PowerShell's own parser and its "no Python" path is run for real. What
only a Windows machine can show (the ``py`` launcher, the Microsoft Store shortcut, a double-click)
is the owner's check in UX.34.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "run.ps1"
BAT = ROOT / "run.bat"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")

needs_powershell = pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell on this machine")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_both_files_sit_in_the_root_and_are_plain_ascii() -> None:
    # Windows PowerShell 5.1 reads a file without a byte-order mark in the system code page, so
    # any character outside ASCII could change meaning there.
    for path in (PS1, BAT):
        assert path.is_file(), f"{path.name} belongs in the repository root"
        path.read_bytes().decode("ascii")


def test_the_batch_file_runs_the_script_with_the_policy_lifted_and_passes_everything_on() -> None:
    lines = [ln for ln in _text(BAT).splitlines() if not ln.lower().startswith("rem ")]
    call = next(ln for ln in lines if "powershell" in ln.lower())
    assert "-ExecutionPolicy Bypass" in call and "-NoProfile" in call
    assert '-File "%~dp0run.ps1"' in call  # next to itself, whatever the folder it is started from
    assert call.rstrip().endswith("%*")  # every argument goes on
    assert any(ln.startswith("exit /b") and "%CODE%" in ln for ln in lines)  # exits with its code


def test_the_script_finds_python_in_the_order_the_task_names() -> None:
    text = _text(PS1)
    order = [text.index(marker) for marker in ('"-3.12"', '"-3"', 'Exe = "python"')]
    assert order == sorted(order)
    assert '[version]"3.12"' in text  # the minimum
    assert "winget install Python" in text and "python.org/downloads/windows" in text


def test_the_script_keeps_the_environment_up_to_date_only_when_the_project_files_change() -> None:
    text = _text(PS1)
    assert '".venv"' in text and "Remove-Item" in text  # built again when it is the wrong Python
    assert "pyproject.toml" in text and "version.toml" in text and "Get-FileHash" in text
    assert "install-stamp.txt" in text  # kept inside .venv, so a new .venv installs again
    assert re.search(r'pip install .*-e "\.\[gui\]"', text)
    install = text.index("pip install")
    assert text.index("Set-Content") > install  # the stamp is written only after the install ran
    assert "$code -ne 0" in text  # ... and only if it worked


def test_the_script_starts_the_viewer_and_exits_with_its_exit_code() -> None:
    text = _text(PS1).rstrip()
    assert text.endswith("exit $LASTEXITCODE")
    assert "-m evolution_simulator.viewer @args" in text.splitlines()[-2]


def test_the_script_stays_in_the_folder_it_was_started_from() -> None:
    # Relative paths in the arguments (--settings, --runs-folder) mean the user's folder.
    text = _text(PS1)
    assert "Set-Location" not in text and "cd " not in text
    assert "Push-Location" in text and "Pop-Location" in text  # only around the install
    assert "$PSScriptRoot" in text  # and it finds its own files from where it lies
    assert "-LiteralPath" in text  # a path with spaces or brackets is a path


def test_the_script_uses_nothing_newer_than_windows_powershell_5_1() -> None:
    code = "\n".join(ln.split("#")[0] for ln in _text(PS1).splitlines())
    newer = {
        "&&": "pipeline chain operators",
        "||": "pipeline chain operators",
        "??": "null coalescing",
        "?.": "null conditional",
        "$IsWindows": "an automatic variable that 5.1 lacks",
        "-Parallel": "ForEach-Object -Parallel",
    }
    found = {what for token, what in newer.items() if token in code}
    assert not found, f"PowerShell 7 only: {sorted(found)}"
    assert not re.search(r"\)\s*\?\s*\S.*:\s*\S", code), "no ternary operator"


def test_the_readme_and_the_docs_explain_how_to_run_it() -> None:
    readme = _text(ROOT / "README.md")
    assert "Run from source" in readme and "run.ps1" in readme and "run.bat" in readme
    assert "ExecutionPolicy" in readme
    docs = _text(ROOT / "docs" / "design" / "ux.md")
    assert "run.ps1" in docs


@needs_powershell
def test_powershell_parses_the_script_without_errors() -> None:
    command = (
        "$errors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{PS1}', [ref]$null, [ref]$errors); "
        "$errors | ForEach-Object { $_.ToString() }; exit $errors.Count"
    )
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


@needs_powershell
@pytest.mark.skipif(os.name == "nt", reason="needs a PATH with no Python on it")
def test_without_a_suitable_python_it_says_how_to_install_one_and_exits_with_1() -> None:
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "a folder with spaces" / "run.ps1"
        copy.parent.mkdir()
        shutil.copy(PS1, copy)
        empty = Path(folder) / "empty"
        empty.mkdir()
        done = subprocess.run(
            [POWERSHELL, "-NoProfile", "-File", str(copy), "--fake"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env={**os.environ, "PATH": str(empty)},
        )
        assert done.returncode == 1, done.stdout + done.stderr
        assert "Python 3.12 or newer was not found" in done.stdout
        assert "winget install Python" in done.stdout
        assert not (copy.parent / ".venv").exists()
