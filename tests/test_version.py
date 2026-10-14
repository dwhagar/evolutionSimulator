import importlib.util
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("version_script", ROOT / "scripts" / "version.py")
version_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version_script)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_get_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version_script.get_version())


def test_build_number_counts_commits_since_base():
    head_parent = git("rev-parse", "HEAD~1")
    assert version_script.build_number(head_parent) == 1


def test_build_number_unknown_base_is_zero():
    assert version_script.build_number("0" * 40) == 0
