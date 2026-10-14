"""Where saved runs live by default (``UX.10``, owner question ``UX.25``).

The default is a per-user data folder: ``%LOCALAPPDATA%\\evolutionSimulator\\runs`` on Windows,
``~/Library/Application Support/evolutionSimulator/runs`` on macOS and
``$XDG_DATA_HOME/evolutionSimulator/runs`` (``~/.local/share`` if unset) elsewhere. Everything that
writes runs takes the folder as an argument, so tests and scripts use a temporary one; this function
only supplies the default and reads nothing but what it is passed.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

APP_FOLDER = "evolutionSimulator"


def default_runs_root(
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> PurePath:
    """The folder saved runs go in unless the user picks another.

    ``platform`` is a ``sys.platform`` value; ``environ`` and ``home`` default to the real ones.
    """
    if environ is None:
        import os

        environ = os.environ
    platform = sys.platform if platform is None else platform
    home_dir = Path.home() if home is None else home
    if platform.startswith("win"):
        base = environ.get("LOCALAPPDATA")
        folder = PureWindowsPath(base) if base else PureWindowsPath(home_dir) / "AppData" / "Local"
        return folder / APP_FOLDER / "runs"
    if platform == "darwin":
        return PurePosixPath(home_dir) / "Library" / "Application Support" / APP_FOLDER / "runs"
    data = environ.get("XDG_DATA_HOME")
    folder_posix = PurePosixPath(data) if data else PurePosixPath(home_dir) / ".local" / "share"
    return folder_posix / APP_FOLDER / "runs"
