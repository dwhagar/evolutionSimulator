"""What the About box says (UX.21): the version, the licence and the third-party notices.

No Qt in here, so it can be tested anywhere. The version is the project's own
``MAJOR.minor.build`` (``version.toml`` plus the commits since its base, as ``scripts/version.py``
counts them) when run from a source checkout, the ``VERSION`` file next to the program in the
downloadable build, and the installed package's version otherwise.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from evolution_simulator import __version__

APP_NAME = "Evolution Simulator"
REPOSITORY_URL = "https://github.com/dwhagar/evolutionSimulator"
LICENCE_NAME = "CC0 1.0 Universal"
LICENCE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"

SOURCE_ROOT = Path(__file__).resolve().parents[3]
"""The repository folder when this runs from a source checkout (it has ``version.toml``)."""

FALLBACK_NOTICES = """# Third-party notices

Evolution Simulator itself is released under CC0 1.0. The program also uses software written by
others:

- **Qt for Python (PySide6) and Qt**: GNU Lesser General Public License v3 (LGPL v3).
  <https://www.qt.io/> and <https://www.gnu.org/licenses/lgpl-3.0.html>
- **pyqtgraph**: MIT licence. <https://www.pyqtgraph.org/>
- **NumPy**: BSD 3-clause licence. <https://numpy.org/>
- **Python**: Python Software Foundation licence. <https://www.python.org/>

The full text, with how to replace the Qt libraries, is in `THIRD_PARTY_NOTICES.md` in the
downloadable build and in `packaging/` in the source.
"""
"""Shown when the notices file cannot be found."""


def frozen_folder() -> Path | None:
    """The folder of the downloadable build's program, or ``None`` when run from Python."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def _source_version(root: Path) -> str | None:
    script = root / "scripts" / "version.py"
    if not (root / "version.toml").is_file() or not script.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("evolution_simulator_version_script", script)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return str(module.get_version())
    except Exception:  # noqa: BLE001 - the About box must open whatever is wrong with git
        return None


def program_version(root: Path = SOURCE_ROOT, folder: Path | None = None) -> str:
    """The version to show. ``folder`` is the build's folder (defaults to where the frozen program
    is); ``root`` is the source checkout."""
    folder = frozen_folder() if folder is None else folder
    if folder is not None:
        try:
            text = (folder / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            return text
    return _source_version(root) or __version__


def notices_text(root: Path = SOURCE_ROOT, folder: Path | None = None) -> str:
    """The third-party notices (Markdown): the file shipped with the build or kept in the source,
    or a short built-in list when neither is there."""
    folder = frozen_folder() if folder is None else folder
    candidates = []
    if folder is not None:
        candidates.append(folder / "THIRD_PARTY_NOTICES.md")
    candidates.append(root / "packaging" / "THIRD_PARTY_NOTICES.md")
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if text.strip():
            return text
    return FALLBACK_NOTICES


def about_html(version: str) -> str:
    """The text of the About box."""
    return (
        f"<h3>{APP_NAME}</h3>"
        f"<p>Version {version}</p>"
        "<p>A simulation in which creatures with their own DNA, bodies and brains live, breed and "
        "evolve.</p>"
        f"<p>Released into the public domain under "
        f'<a href="{LICENCE_URL}">{LICENCE_NAME}</a>.<br>'
        f'Source: <a href="{REPOSITORY_URL}">{REPOSITORY_URL}</a></p>'
        "<p>It is built with Qt (PySide6), pyqtgraph and NumPy; their licences are in the "
        "third-party notices.</p>"
    )
