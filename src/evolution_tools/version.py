"""Compute the project version as MAJOR.minor.build from git history.

The build number is the number of first-parent commits reachable from HEAD but not from the
`base` commit in version.toml. On main that is one per merge (squash, merge commit or fast-forward
of a single commit), with no manual step. Run `python -m evolution_tools.version` to print the current version.
"""

import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build_number(base: str) -> int:
    """First-parent commits since `base`, or 0 when git history is unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-list", "--first-parent", "--count", f"{base}..HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return int(out.strip())
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def get_version() -> str:
    config = tomllib.loads((ROOT / "version.toml").read_text())
    return f"{config['major']}.{config['minor']}.{build_number(config['base'])}"


if __name__ == "__main__":
    print(get_version())
