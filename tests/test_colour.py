"""The shared colour module (TRAIT.20 note, built early inside UX.43)."""

import pytest

from evolution_simulator import colour


def test_the_line_runs_rust_purple_blue_teal_green_and_clamps():
    for position, anchor in zip(colour.POSITIONS, colour.ANCHORS, strict=True):
        assert colour.rgb(position) == pytest.approx(anchor)
    assert colour.rgb(-1.0) == colour.ANCHORS[0] and colour.rgb(7.0) == colour.ANCHORS[-1]
    assert colour.rgb(float("nan")) == colour.ANCHORS[0]
    middle = colour.rgb(0.125)  # halfway from rust red to purple
    assert middle == pytest.approx([(a + b) / 2 for a, b in zip(*colour.ANCHORS[:2], strict=True)])


def test_chroma_is_the_spread_of_the_channels():
    assert colour.chroma(0.5) == pytest.approx(0.65)  # blue, the most vivid
    assert colour.chroma(0.0) == pytest.approx(0.48)  # rust


def test_diet_colour_puts_meat_eaters_on_red_plant_eaters_on_blue_and_omnivores_between():
    assert colour.diet_colour(1.0, 0.0) == 0.0
    assert colour.diet_colour(0.0, 1.0) == 0.5
    assert colour.diet_colour(1.0, 1.0) == 0.25 == colour.diet_colour(0.3, 0.3)
    assert colour.diet_colour(5.0, 0.0) == 0.0 and colour.diet_colour(0.0, 5.0) == 0.5  # clamped
    assert [colour.share_colour(s) for s in (0.0, 0.5, 1.0)] == [0.5, 0.25, 0.0]
    assert colour.share_colour(2.0) == 0.0 and colour.share_colour(-1.0) == 0.5


def test_the_background_is_ground_blended_toward_foliage_darker_when_tough():
    assert colour.background(0.0) == colour.GROUND
    assert colour.background(1.0) == pytest.approx(colour.PLANT_GREEN)
    assert colour.foliage(1.0) == pytest.approx([c * 0.5 for c in colour.PLANT_GREEN])
    assert colour.background(1.0, 1.0) == pytest.approx(colour.foliage(1.0))


def test_the_design_table_of_contrast_factors_is_reproduced():
    """``contrast = 1 - 0.5 * match`` for an animal that keeps still, by plant cover and coat."""
    table = {
        0.00: [0.69, 0.83, 1.00, 0.94, 0.85],
        0.25: [0.75, 0.86, 1.00, 0.89, 0.77],
        0.50: [0.82, 0.91, 1.00, 0.86, 0.70],
        1.00: [0.97, 1.00, 1.00, 0.84, 0.58],
    }
    for cover, row in table.items():
        background = colour.background(cover)
        found = [1.0 - 0.5 * colour.match(p, background) for p in colour.POSITIONS]
        assert found == pytest.approx(row, abs=0.006)


def test_a_far_coat_gets_no_match_and_a_perfect_one_gets_one():
    assert colour.match(0.5, colour.rgb(0.5)) == 1.0
    assert colour.match(0.5, colour.GROUND) == 0.0
    assert colour.match(0.5, colour.GROUND, radius=10.0) > 0.0
