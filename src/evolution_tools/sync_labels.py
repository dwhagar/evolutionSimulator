"""Give every TODO tag its own GitHub label colour, rotating through a palette (INFRA.8).

The tags are the task IDs in TODO.md, CHANGELOG.md and docs/decisions.md (``AREA.N``). Each one gets the next colour of ``PALETTE`` the
first time it is seen, and the choice is kept in ``.github/label-colours.json`` so a tag keeps its
colour and a new tag simply continues the rotation. ``needs-owner`` is the one fixed label: it marks
an item or issue with an owner question that is still open, and is removed when the question is
answered. The scheme is described in ``docs/labels.md``.

    python -m evolution_tools.sync_labels            # update label-colours.json and print what would change
    python -m evolution_tools.sync_labels --apply    # also create or recolour the labels with the gh CLI

Needs only the standard library; ``--apply`` needs ``gh`` logged in with access to the repository.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COLOURS_FILE = ROOT / ".github" / "label-colours.json"
SOURCES = (ROOT / "TODO.md", ROOT / "CHANGELOG.md", ROOT / "docs" / "decisions.md")
REPO = "dwhagar/evolutionSimulator"

AREAS = (
    "DOCS",
    "INFRA",
    "DNA",
    "REPRO",
    "TRAIT",
    "WORLD",
    "BRAIN",
    "SENSE",
    "UX",
    "SPECIES",
    "STORE",
)
"""The task areas, in the order of the table in TODO.md. A new area is added here and there."""

PALETTE = (
    "1d76db",  # blue
    "0e8a16",  # green
    "fbca04",  # yellow
    "5319e7",  # purple
    "ff7619",  # orange
    "006b75",  # teal
    "e99695",  # pink
    "bfd4f2",  # light blue
    "c2e0c6",  # light green
    "d4c5f9",  # lavender
    "f9d0c4",  # peach
    "8b6f47",  # brown
)
"""Twelve distinct colours that stay readable with the text colour GitHub picks. Red is kept for
``needs-owner`` and the default grey (ededed) is what an unassigned tag looks like."""

NEEDS_OWNER = ("needs-owner", "b60205", "An owner question about this item is still open")

TAG = re.compile(r"\b(" + "|".join(AREAS) + r")\.(\d+)\b")


def tags_in(text: str) -> list[str]:
    """Every task tag in ``text``, in area order and then number order, each once."""
    found = {(AREAS.index(m.group(1)), int(m.group(2))) for m in TAG.finditer(text)}
    return [f"{AREAS[a]}.{n}" for a, n in sorted(found)]


def assign(tags: list[str], state: dict) -> dict:
    """Give each tag without a colour the next one of the rotation. Existing choices never change."""
    colours = state.setdefault("colours", {})
    for tag in tags:
        if tag not in colours:
            colours[tag] = PALETTE[state.get("next", 0) % len(PALETTE)]
            state["next"] = state.get("next", 0) + 1
    return state


def load() -> dict:
    if COLOURS_FILE.exists():
        return json.loads(COLOURS_FILE.read_text(encoding="utf-8"))
    return {"next": 0, "colours": {}}


def save(state: dict) -> None:
    """Write the choices, tags in area and number order."""

    def order(tag: str) -> tuple[int, int]:
        area, number = tag.split(".")
        return AREAS.index(area), int(number)

    state["colours"] = {t: state["colours"][t] for t in sorted(state["colours"], key=order)}
    COLOURS_FILE.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=False)


def apply_label(name: str, colour: str, description: str = "") -> None:
    """Recolour the label if it exists, create it if not."""
    fields = ["-f", f"color={colour}"] + (
        ["-f", f"description={description}"] if description else []
    )
    done = gh("-X", "PATCH", f"repos/{REPO}/labels/{name}", *fields)
    if done.returncode != 0:
        done = gh("-X", "POST", f"repos/{REPO}/labels", "-f", f"name={name}", *fields)
    if done.returncode != 0:
        print(f"failed: {name}: {done.stderr.strip()}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="create or recolour the labels on GitHub"
    )
    args = parser.parse_args()
    state = assign(tags_in("\n".join(f.read_text(encoding="utf-8") for f in SOURCES)), load())
    save(state)
    print(f"{len(state['colours'])} tags, next colour index {state['next'] % len(PALETTE)}")
    if args.apply:
        apply_label(*NEEDS_OWNER)
        for tag, colour in state["colours"].items():
            apply_label(tag, colour)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
