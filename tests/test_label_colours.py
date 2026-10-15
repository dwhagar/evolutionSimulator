"""The TODO tags and their label colours (INFRA.8): every tag has one, and the rotation is kept."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sync_labels", ROOT / "src" / "evolution_tools" / "sync_labels.py"
)
assert spec is not None and spec.loader is not None
sync_labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_labels)


def _state() -> dict:
    return json.loads((ROOT / ".github" / "label-colours.json").read_text(encoding="utf-8"))


def test_every_tag_in_the_todo_has_a_colour() -> None:
    text = "\n".join(f.read_text(encoding="utf-8") for f in sync_labels.SOURCES)
    missing = [t for t in sync_labels.tags_in(text) if t not in _state()["colours"]]
    assert not missing, f"run src/evolution_tools/sync_labels.py to colour: {missing}"


def test_colours_come_from_the_palette_and_follow_the_rotation() -> None:
    state = _state()
    assert set(state["colours"].values()) <= set(sync_labels.PALETTE)
    assert state["next"] == len(state["colours"])


def test_a_new_tag_continues_the_rotation() -> None:
    state = {"next": 5, "colours": {"DOCS.1": sync_labels.PALETTE[4]}}
    sync_labels.assign(["DOCS.1", "DOCS.2", "DOCS.3"], state)
    assert state["colours"]["DOCS.1"] == sync_labels.PALETTE[4]  # unchanged
    assert state["colours"]["DOCS.2"] == sync_labels.PALETTE[5]
    assert state["colours"]["DOCS.3"] == sync_labels.PALETTE[6]
    assert state["next"] == 7


def test_tags_are_found_in_area_and_number_order() -> None:
    assert sync_labels.tags_in("see UX.2, DOCS.10, DOCS.2 and TRAIT.1 again DOCS.2") == [
        "DOCS.2",
        "DOCS.10",
        "TRAIT.1",
        "UX.2",
    ]
