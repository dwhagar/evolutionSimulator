"""Label colours by category (INFRA.8, INFRA.12): one colour family per area, shades per item."""

from __future__ import annotations

import colorsys

from evolution_tools import sync_labels


def _hue(tag: str) -> float:
    value = sync_labels.colour(tag)
    red, green, blue = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(red, green, blue)[0] * 360


def test_every_area_has_a_family() -> None:
    assert set(sync_labels.FAMILIES) == set(sync_labels.AREAS)


def test_items_of_an_area_are_shades_of_one_colour() -> None:
    colours = [sync_labels.colour(f"TRAIT.{n}") for n in range(1, 7)]
    assert len(set(colours)) == 6  # six shades before it repeats
    assert sync_labels.colour("TRAIT.7") == colours[0]
    hues = {round(_hue(f"TRAIT.{n}")) for n in range(1, 7)}
    assert max(hues) - min(hues) <= 2  # the same hue, only the lightness changes


def test_areas_have_different_colours() -> None:
    first = {area: sync_labels.colour(f"{area}.1") for area in sync_labels.AREAS}
    assert len(set(first.values())) == len(first)


def test_status_labels_are_not_a_tag_colour() -> None:
    assert sync_labels.NEEDS_OWNER[1] == "ff0000"  # bright red
    assert sync_labels.IN_PROGRESS[1] == "4169e1"  # royal blue
    every = {sync_labels.colour(f"{a}.{n}") for a in sync_labels.AREAS for n in range(1, 40)}
    assert sync_labels.NEEDS_OWNER[1] not in every
    assert sync_labels.IN_PROGRESS[1] not in every


def test_every_tag_in_the_sources_gets_a_colour() -> None:
    labels = sync_labels.wanted()
    assert "needs-owner" in labels and "in-progress" in labels
    assert all(len(v) == 6 for v in labels.values())


def test_tags_are_found_in_area_and_number_order() -> None:
    assert sync_labels.tags_in("see UX.2, DOCS.10, DOCS.2 and TRAIT.1 again DOCS.2") == [
        "DOCS.2",
        "DOCS.10",
        "TRAIT.1",
        "UX.2",
    ]
