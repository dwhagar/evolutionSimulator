"""Colour every TODO tag on GitHub by its category (INFRA.8, revised for INFRA.12).

The tags are the task IDs in TODO.md, CHANGELOG.md and docs/decisions.md (``AREA.N``). Each area has
its own colour family and the items of an area are shades of it, cycling through six lightness
steps, so a glance at the label list shows the category and no two neighbouring items look alike. A
colour is worked out from the tag alone, so a new tag needs no bookkeeping. Two labels are fixed:
``needs-owner`` is bright red (an owner question is open) and ``in-progress`` is royal blue (a thread
is building it). The scheme is described in ``docs/labels.md``.

    python -m evolution_tools.sync_labels            # print the colours that GitHub should have
    python -m evolution_tools.sync_labels --apply    # also create or recolour the labels with gh

Needs only the standard library; ``--apply`` needs ``gh`` logged in with access to the repository.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
"""The task areas, in the order of the table in TODO.md. A new area is added here and in FAMILIES."""

FAMILIES: dict[str, tuple[float, float]] = {
    "DOCS": (0.0, 0.0),  # grey
    "INFRA": (205.0, 0.20),  # slate
    "DNA": (130.0, 0.55),  # green
    "REPRO": (320.0, 0.55),  # magenta
    "TRAIT": (28.0, 0.90),  # orange
    "WORLD": (170.0, 0.60),  # teal
    "BRAIN": (270.0, 0.50),  # purple
    "SENSE": (50.0, 0.85),  # yellow
    "UX": (90.0, 0.60),  # lime
    "SPECIES": (195.0, 0.75),  # cyan
    "STORE": (25.0, 0.40),  # brown
}
"""Hue in degrees and saturation of each area's family. Red and royal blue are kept free for the two
status labels, and the families are spread around the rest of the colour wheel."""

SHADES = (0.30, 0.38, 0.46, 0.54, 0.62, 0.70)
"""The lightness steps an area's items cycle through (item 1 is the darkest)."""

NEEDS_OWNER = ("needs-owner", "ff0000", "An owner question about this item is still open")
IN_PROGRESS = ("in-progress", "4169e1", "A thread is building this item now")

TAG = re.compile(r"\b(" + "|".join(AREAS) + r")\.(\d+)\b")


def tags_in(text: str) -> list[str]:
    """Every task tag in ``text``, in area order and then number order, each once."""
    found = {(AREAS.index(m.group(1)), int(m.group(2))) for m in TAG.finditer(text)}
    return [f"{AREAS[a]}.{n}" for a, n in sorted(found)]


def colour(tag: str) -> str:
    """The six-digit hex colour (no ``#``) of a task tag such as ``TRAIT.13``."""
    area, number = tag.split(".")
    hue, saturation = FAMILIES[area]
    lightness = SHADES[(int(number) - 1) % len(SHADES)]
    red, green, blue = colorsys.hls_to_rgb(hue / 360.0, lightness, saturation)
    return f"{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


def wanted() -> dict[str, str]:
    """Every label GitHub should have for the tags in the sources, with its colour."""
    text = "\n".join(f.read_text(encoding="utf-8") for f in SOURCES)
    labels = {tag: colour(tag) for tag in tags_in(text)}
    labels[NEEDS_OWNER[0]] = NEEDS_OWNER[1]
    labels[IN_PROGRESS[0]] = IN_PROGRESS[1]
    return labels


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=False)


def current() -> dict[str, str]:
    """The colours the repository's labels have now."""
    found: dict[str, str] = {}
    page = 1
    while True:
        done = gh(
            f"repos/{REPO}/labels?per_page=100&page={page}", "--jq", ".[] | [.name, .color] | @tsv"
        )
        rows = [line.split("\t") for line in done.stdout.splitlines() if "\t" in line]
        found.update({name: colour_ for name, colour_ in rows})
        if len(rows) < 100:
            return found
        page += 1


def apply_label(name: str, wanted_colour: str, description: str = "") -> None:
    """Recolour the label if it exists, create it if not."""
    fields = ["-f", f"color={wanted_colour}"]
    if description:
        fields += ["-f", f"description={description}"]
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
    labels = wanted()
    print(f"{len(labels)} labels")
    if not args.apply:
        print(json.dumps(labels, indent=1))
        return 0
    now = current()
    descriptions = {NEEDS_OWNER[0]: NEEDS_OWNER[2], IN_PROGRESS[0]: IN_PROGRESS[2]}
    changed = 0
    for name, wanted_colour in labels.items():
        if now.get(name, "").lower() != wanted_colour:
            apply_label(name, wanted_colour, descriptions.get(name, ""))
            changed += 1
    print(f"{changed} labels created or recoloured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
