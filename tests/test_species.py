"""The species tracker (SPECIES.1): synthetic populations for the rules, a real world for the plumbing."""

import gzip
import json
import random

import pytest

from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT
from evolution_simulator.species import (
    SPECIES_FORMAT,
    SpeciesRules,
    SpeciesTracker,
    _Space,
    choose_sample,
    consensus,
    digits_of,
    load_species_data,
    migrate,
    save_species,
)
from evolution_simulator.world import World, WorldConfig

LENGTH = 400


class Nothing:
    """A source with no world: the tests hand genomes in."""

    tick = 0
    simulated_seconds = 0.0
    animals = ()
    plants = ()


def tracker(**rules):
    return SpeciesTracker(Nothing(), SpeciesRules(**rules), attach=False)


def random_digits(rng, length=LENGTH):
    return "".join(rng.choice("0123") for _ in range(length))


def noisy(base, rng, rate):
    """``base`` with about ``rate`` of its digits changed."""
    digits = list(base)
    for i in range(len(digits)):
        if rng.random() < rate:
            digits[i] = rng.choice("0123".replace(digits[i], ""))
    return "".join(digits)


def shifted(base, rng, fraction):
    """``base`` with exactly this fraction of its digits changed (different ones each call)."""
    digits = list(base)
    for i in rng.sample(range(len(digits)), round(fraction * len(digits))):
        digits[i] = rng.choice("0123".replace(digits[i], ""))
    return "".join(digits)


def cloud(centre, size, rng, noise, start):
    return [(start + i, noisy(centre, rng, noise)) for i in range(size)]


def feed(tr, groups, samples, rng, noise=0.01, first_day=0):
    """Take ``samples`` samples of populations drawn around the given centres."""
    for n in range(samples):
        animals, start = [], 0
        for centre, size in groups:
            animals += cloud(centre, size, rng, noise, start)
            start += size
        tr.observe_genomes(first_day + 7.0 * n, animals)


# --- the distance and the consensus -------------------------------------------------


def test_the_integer_distance_matches_dna_distance():
    rng = random.Random(1)
    space = _Space(ANIMAL_LAYOUT.length)
    for _ in range(5):
        a, b = DNA.random(ANIMAL_LAYOUT, rng), DNA.random(ANIMAL_LAYOUT, rng)
        assert space.distance(int(str(a), 4), int(str(b), 4)) == pytest.approx(a.distance(b))
    assert space.distance(int(str(a), 4), int(str(a), 4)) == 0.0


def test_consensus_is_the_digit_wise_mode_with_ties_to_the_lower_digit():
    assert consensus(["0123", "0123", "3210"]) == "0123"
    assert consensus(["00", "33"]) == "00"
    assert consensus(["2031"]) == "2031"
    with pytest.raises(ValueError):
        consensus([])


def test_the_sample_is_bounded_deterministic_and_does_not_depend_on_order():
    ids = list(range(1000))
    chosen = choose_sample(ids, 300, salt=5)
    assert len(chosen) == 300 == len(set(chosen)) and chosen == sorted(chosen)
    assert chosen == choose_sample(ids, 300, salt=5)
    assert chosen != choose_sample(ids, 300, salt=6)
    assert choose_sample(ids[:10], 300, salt=1) == list(range(10))
    # a hash of the id, not of the position: the same organisms are chosen however they are listed
    shuffled = ids[:]
    random.Random(3).shuffle(shuffled)
    again = {shuffled[i] for i in choose_sample(shuffled, 300, salt=5)}
    assert again == {ids[i] for i in chosen}


def test_digits_of_a_diploid_genome_are_both_strands():
    class Strand:
        def __init__(self, text):
            self.text = text

        def __str__(self):
            return self.text

    class Diploid:
        strands = (Strand("0123"), Strand("3210"))

    assert digits_of(Diploid()) == "01233210"
    assert digits_of(Strand("2020")) == "2020"


# --- one population, two populations ------------------------------------------------


def test_one_interbreeding_population_stays_one_species():
    rng = random.Random(2)
    base = random_digits(rng)
    tr = tracker()
    feed(tr, [(base, 300)], 30, rng, noise=0.02)
    live = tr.species("animal", alive=True)
    assert len(live) == 1 and live[0].id == 1 and live[0].parent is None
    assert live[0].size == 300 and live[0].divergence == 0.0
    assert len(tr.species("animal")) == 1 and tr.species("plant") == []


def test_two_lines_that_drift_apart_split_on_the_third_clear_sample():
    rng = random.Random(3)
    base = random_digits(rng)
    other = shifted(base, rng, 0.10)  # 10% apart, with 1% noise: far over twice the spread
    tr = tracker()
    for sample in range(1, 6):
        feed(tr, [(base, 200), (other, 100)], 1, rng, first_day=7.0 * sample)
        count = len(tr.species("animal", alive=True))
        assert count == (1 if sample < 3 else 2), sample
    big, small = tr.species("animal", alive=True)
    assert (big.id, big.parent, big.size) == (1, None, 200)
    assert (small.id, small.parent, small.size) == (2, 1, 100)
    assert small.first_day == 21.0  # the day it was first told apart
    assert big.divergence < small.divergence or big.divergence == pytest.approx(0.0, abs=0.01)


def test_the_larger_half_keeps_the_id_whichever_side_it_is():
    rng = random.Random(4)
    base = random_digits(rng)
    other = shifted(base, rng, 0.10)
    tr = tracker()
    feed(tr, [(base, 50)], 1, rng)
    feed(tr, [(base, 60), (other, 140)], 3, rng, first_day=7.0)
    big = tr.get(1)
    assert big.size == 140 and big.parent is None
    assert tr.get(2).parent == 1 and tr.get(2).size == 60


def test_a_gap_must_last_three_samples_in_a_row():
    rng = random.Random(5)
    base = random_digits(rng)
    other = shifted(base, rng, 0.10)
    tr = tracker()
    for sample in range(12):
        two = sample % 3 != 2  # apart for two samples, together for one, and so on
        feed(
            tr,
            [(base, 150), (other, 150)] if two else [(base, 300)],
            1,
            rng,
            first_day=7.0 * sample,
        )
    assert len(tr.species("animal")) == 1


def test_a_gap_under_the_minimum_share_of_digits_is_not_a_species():
    rng = random.Random(6)
    base = random_digits(rng)
    close = shifted(base, rng, 0.03)  # tight groups but only 3% apart: under the 4% floor
    tr = tracker()
    feed(tr, [(base, 150), (close, 150)], 10, rng, noise=0.001)
    assert len(tr.species("animal", alive=True)) == 1
    loose = tracker(min_gap=0.02)  # the floor is a setting
    feed(loose, [(base, 150), (close, 150)], 10, rng, noise=0.001)
    assert len(loose.species("animal", alive=True)) == 2


def test_a_gap_under_twice_the_spread_is_not_a_species():
    rng = random.Random(7)
    base = random_digits(rng)
    other = shifted(base, rng, 0.06)
    tr = tracker()
    feed(tr, [(base, 150), (other, 150)], 10, rng, noise=0.04)  # spread about 4%: needs over 8%
    assert len(tr.species("animal", alive=True)) == 1
    stricter = tracker(separation=1.0)
    feed(stricter, [(base, 150), (other, 150)], 10, rng, noise=0.04)
    assert len(stricter.species("animal", alive=True)) == 2


def test_a_handful_of_oddities_does_not_make_a_species():
    rng = random.Random(8)
    base = random_digits(rng)
    odd = shifted(base, rng, 0.30)
    tr = tracker()
    feed(tr, [(base, 295), (odd, 4)], 10, rng)  # under min_members
    assert len(tr.species("animal", alive=True)) == 1


def test_species_that_grow_back_together_are_merged_into_the_larger():
    rng = random.Random(9)
    base = random_digits(rng)
    places = rng.sample(range(LENGTH), LENGTH)
    values = [rng.choice("0123".replace(base[i], "")) for i in places]

    def at(gap):
        """``base`` moved this far (a share of its digits) along one fixed path."""
        digits = list(base)
        for i, v in zip(places[: round(gap * LENGTH)], values, strict=False):
            digits[i] = v
        return "".join(digits)

    tr = tracker()
    feed(tr, [(base, 200), (at(0.10), 100)], 4, rng)
    assert len(tr.species("animal", alive=True)) == 2
    day = 100.0
    for gap in (
        0.08,
        0.06,
        0.04,
        0.03,
        0.025,
        0.02,
    ):  # the second line drifts back towards the first
        feed(tr, [(base, 200), (at(gap), 100)], 1, rng, first_day=day)
        day += 7.0
        assert len(tr.species("animal", alive=True)) == 2
    feed(tr, [(base, 200), (at(0.015), 100)], 2, rng, first_day=day)
    assert len(tr.species("animal", alive=True)) == 2  # not yet: three samples in a row
    feed(tr, [(base, 200), (at(0.015), 100)], 1, rng, first_day=day + 14.0)
    live = tr.species("animal", alive=True)
    assert [s.id for s in live] == [1] and live[0].size == 300
    gone = tr.get(2)
    assert not gone.alive and gone.merged_into == 1 and gone.parent == 1


def test_a_pair_between_split_and_merge_stays_as_it_is():
    rng = random.Random(10)
    base = random_digits(rng)
    other = shifted(base, rng, 0.10)
    tr = tracker()
    feed(tr, [(base, 150), (other, 150)], 4, rng)
    assert len(tr.species("animal", alive=True)) == 2
    halfway = shifted(base, rng, 0.05)  # over half the needed gap (0.04) yet under the full one
    feed(tr, [(base, 150), (halfway, 150)], 10, rng, first_day=100.0)
    assert len(tr.species("animal", alive=True)) == 2


def test_a_split_off_line_can_split_again_and_the_tree_records_it():
    rng = random.Random(11)
    base = random_digits(rng)
    b = shifted(base, rng, 0.10)
    c = shifted(base, rng, 0.20)
    tr = tracker()
    feed(tr, [(base, 150), (b, 150)], 4, rng)
    feed(tr, [(base, 150), (b, 100), (c, 100)], 4, rng, first_day=100.0)
    live = tr.species("animal", alive=True)
    assert len(live) == 3
    parents = {s.id: s.parent for s in live}
    assert parents[1] is None and parents[2] == 1 and parents[3] in (1, 2)


# --- ranking, divergence and sizes -------------------------------------------------


def test_divergence_is_from_the_founding_consensus_and_grows_as_a_line_drifts():
    rng = random.Random(12)
    base = random_digits(rng)
    tr = tracker()
    feed(tr, [(base, 300)], 1, rng)
    assert tr.founder("animal") == base
    drifting = base
    last = 0.0
    for step in range(1, 6):
        drifting = shifted(drifting, rng, 0.02)
        feed(tr, [(drifting, 300)], 1, rng, first_day=7.0 * step)
        now = tr.species("animal")[0].divergence
        assert now > last
        last = now
    species = tr.species("animal")[0]
    assert species.id == 1 and len(species.points) == 6
    assert [p.divergence for p in species.points] == sorted(p.divergence for p in species.points)
    assert species.points[0].day == 0.0 and species.points[-1].day == 35.0


def test_ranking_by_divergence_relative_divergence_and_size():
    rng = random.Random(13)
    base = random_digits(rng)
    near = shifted(base, rng, 0.08)
    far = shifted(base, rng, 0.30)
    tr = tracker()
    feed(tr, [(base, 300)], 1, rng)
    feed(tr, [(base, 150), (near, 100), (far, 50)], 8, rng, first_day=7.0)
    assert [s.size for s in tr.ranking("animal", "size")] == [150, 100, 50]
    by_divergence = tr.ranking("animal", "divergence")
    assert [s.size for s in by_divergence] == [50, 100, 150]
    assert [s.size for s in tr.ranking("animal", "relative", 2)] == [50, 100]
    assert tr.ranking("animal", "relative")[-1].relative_divergence == 0.0  # the largest
    assert len(tr.ranking("animal", count=1)) == 1
    assert [x.size for x in tr.top("animal")] == [50, 100, 150]
    assert [x.size for x in tracker(top_count=1).top("animal")] == []
    with pytest.raises(ValueError):
        tr.ranking("animal", "colour")


def test_plants_and_animals_are_tracked_separately_with_their_own_founders():
    rng = random.Random(14)
    animals = cloud(random_digits(rng, 400), 100, rng, 0.01, 0)
    plants = cloud(random_digits(rng, 30), 100, rng, 0.02, 1000)
    tr = tracker()
    tr.observe_genomes(0.0, animals, plants)
    assert len(tr.founder("animal")) == 400 and len(tr.founder("plant")) == 30
    assert [s.kind for s in tr.species()] == ["animal", "plant"]
    assert tr.species("plant")[0].id == 2  # ids are unique across kinds


# --- bounded samples and what disappears -------------------------------------------


def test_a_big_population_is_sampled_and_the_sizes_are_scaled_up_to_it():
    rng = random.Random(15)
    base = random_digits(rng)
    other = shifted(base, rng, 0.10)
    tr = tracker()
    animals = cloud(base, 1500, rng, 0.01, 0) + cloud(other, 500, rng, 0.01, 1500)
    for n in range(4):
        tr.observe_genomes(7.0 * n, animals)
    big, small = tr.species("animal", alive=True)
    assert 1400 <= big.size <= 1600 and 400 <= small.size <= 600
    assert big.size + small.size in range(1900, 2101)


def test_a_species_that_vanishes_from_a_complete_sample_is_extinct_at_once():
    rng = random.Random(16)
    base = random_digits(rng)
    other = shifted(base, rng, 0.10)
    tr = tracker()
    feed(tr, [(base, 200), (other, 100)], 4, rng)
    feed(tr, [(base, 200)], 1, rng, first_day=100.0)
    gone = tr.get(2)
    assert not gone.alive and gone.extinct_day == 100.0 and gone.merged_into is None
    assert gone.peak == 100 and tr.get(1).alive


def test_a_species_missing_from_a_partial_sample_must_stay_missing_for_three_samples():
    rng = random.Random(17)
    base = random_digits(rng)
    other = shifted(base, rng, 0.10)
    tr = tracker()
    feed(tr, [(base, 400), (other, 100)], 4, rng)
    assert len(tr.species("animal", alive=True)) == 2
    for n in range(
        1, 4
    ):  # 600 left of the first only: more than the 300 sampled, so not exhaustive
        feed(tr, [(base, 600)], 1, rng, first_day=100.0 + 7.0 * n)
        expect_alive = n < 3
        assert tr.get(2).alive == expect_alive, n
    assert tr.get(1).alive


def test_nothing_alive_ends_every_species_and_a_new_population_starts_over():
    rng = random.Random(18)
    base = random_digits(rng)
    tr = tracker()
    feed(tr, [(base, 100)], 2, rng)
    tr.observe_genomes(100.0, [])
    assert tr.species("animal", alive=True) == [] and not tr.get(1).alive
    feed(tr, [(base, 100)], 1, rng, first_day=107.0)
    assert [s.id for s in tr.species("animal", alive=True)] == [2]
    assert tr.founder("animal") == base  # the founders stay what they were


def test_a_genome_of_another_length_starts_that_kind_over():
    rng = random.Random(19)
    tr = tracker()
    feed(tr, [(random_digits(rng, 100), 50)], 1, rng)
    animals = cloud(random_digits(rng, 120), 50, rng, 0.01, 0)
    tr.observe_genomes(7.0, animals)
    assert len(tr.founder("animal")) == 120
    assert [s.id for s in tr.species("animal", alive=True)] == [2]


def test_what_is_kept_is_bounded():
    rng = random.Random(20)
    base = random_digits(rng, 100)
    tr = tracker(history_points=8, extinct_kept=2)
    feed(tr, [(base, 30)], 40, rng)
    assert len(tr.species("animal")[0].points) <= 8
    kept = tr.species("animal")[0].points
    assert kept[-1].day == 7.0 * 39  # the newest points are whole
    for n in range(6):  # six extinct species one after the other
        tr.observe_genomes(500.0 + n, cloud(random_digits(rng, 100), 30, rng, 0.0, 0))
        tr.observe_genomes(600.0 + n, [])
    assert len(tr.species(alive=False)) <= 2


# --- saving ---------------------------------------------------------------------------


def build_history(tr, rng, base, other, upto):
    for n in range(upto):
        two = n >= 3
        feed(tr, [(base, 150), (other, 150)] if two else [(base, 300)], 1, rng, first_day=7.0 * n)


def test_a_restored_tracker_carries_on_exactly_as_an_uninterrupted_one_would():
    base = random_digits(random.Random(21))
    other = shifted(base, random.Random(22), 0.10)
    whole, rng_a = tracker(), random.Random(23)
    build_history(whole, rng_a, base, other, 8)
    interrupted, rng_b = tracker(), random.Random(23)
    build_history(interrupted, rng_b, base, other, 5)
    data = json.loads(json.dumps(interrupted.to_dict()))  # through real JSON
    resumed = SpeciesTracker.restore(Nothing(), data, attach=False)
    for n in range(5, 8):
        feed(resumed, [(base, 150), (other, 150)], 1, rng_b, first_day=7.0 * n)
    assert resumed.to_dict() == whole.to_dict()
    assert resumed.samples_taken == 8 and resumed.last_day == 49.0


def test_the_file_round_trips_and_is_byte_for_byte_repeatable(tmp_path):
    rng = random.Random(24)
    base = random_digits(rng)
    tr = tracker()
    feed(tr, [(base, 100)], 3, rng)
    first = save_species(tr, tmp_path / "species.json.gz")
    second = save_species(tr, tmp_path / "again.json.gz")
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(gzip.decompress(first.read_bytes()))["format"] == SPECIES_FORMAT
    data = load_species_data(first)
    assert SpeciesTracker.restore(Nothing(), data, attach=False).to_dict() == tr.to_dict()
    plain = save_species(tr, tmp_path / "species.json")
    assert load_species_data(plain) == data
    (tmp_path / "list.json").write_text("[]")
    with pytest.raises(ValueError, match="not a saved species"):
        load_species_data(tmp_path / "list.json")


def test_the_format_checks():
    good = tracker().to_dict()
    assert migrate(dict(good))["format"] == SPECIES_FORMAT
    with pytest.raises(ValueError, match="not a saved species"):
        migrate({"kind": "recorder", "format": 1})
    with pytest.raises(ValueError, match="newer"):
        migrate({**good, "format": SPECIES_FORMAT + 1})
    with pytest.raises(ValueError, match="usable format"):
        migrate({**good, "format": "one"})
    with pytest.raises(ValueError, match="usable format"):
        migrate({**good, "format": 0})
    with pytest.raises(ValueError, match="usable format"):
        migrate({**good, "format": True})


def test_an_old_format_is_migrated_by_the_chain(monkeypatch):
    from evolution_simulator import species

    monkeypatch.setattr(species, "SPECIES_FORMAT", 2)
    monkeypatch.setitem(species._MIGRATIONS, 1, lambda data: {**data, "extra": True})
    out = species.migrate({**tracker().to_dict(), "format": 1})
    assert out["format"] == 2 and out["extra"] is True


def test_the_rules_are_checked_and_round_trip():
    rules = SpeciesRules(period_days=3.0, separation=1.5, min_gap=0.02, seed=4)
    assert SpeciesRules.from_dict(json.loads(json.dumps(rules.to_dict()))) == rules
    assert SpeciesRules().period_seconds == 7 * 86400.0
    for bad in (
        {"period_days": 0.0},
        {"min_gap": 1.0},
        {"merge_ratio": 1.0},
        {"sample_size": 5},
        {"confirm": 0},
        {"history_points": 2},
        {"top_count": 0},
        {"separation": float("nan")},
    ):
        with pytest.raises(ValueError):
            SpeciesRules(**bad)


# --- a real world --------------------------------------------------------------------


def make_world(seed=1):
    world = World(WorldConfig(seed=seed))
    world.populate(animals=40, plants=120)
    return world


def test_the_tracker_samples_the_first_step_and_then_every_period():
    world = make_world()
    tr = SpeciesTracker(world, SpeciesRules(period_days=2.0))
    days = []
    tr.add_sample_listener(lambda t: days.append(t.last_day))
    world.run(24 * 7)  # a simulated week of hourly ticks
    assert tr.samples_taken == len(days) and days[0] <= 0.1
    assert days[1:] == [pytest.approx(2.0 * n, abs=0.1) for n in range(1, len(days))]
    assert len(days) in (4, 5)
    live_animals = tr.species("animal", alive=True)
    live_plants = tr.species("plant", alive=True)
    assert len(live_animals) >= 1 and len(live_plants) >= 1
    assert sum(s.size for s in live_animals) == pytest.approx(len(world.animals), abs=3)
    tr.close()


def test_the_tracker_does_not_change_the_world():
    plain, watched = make_world(2), make_world(2)
    tracker_ = SpeciesTracker(watched, SpeciesRules(period_days=1.0))
    plain.run(24 * 5)
    watched.run(24 * 5)
    assert tracker_.samples_taken >= 5
    assert watched.state_digest() == plain.state_digest()
    assert watched.rng.getstate() == plain.rng.getstate()


def test_a_tracker_restored_beside_a_world_goes_on_with_it():
    one, other = make_world(3), make_world(3)
    whole = SpeciesTracker(one, SpeciesRules(period_days=1.0))
    first = SpeciesTracker(other, SpeciesRules(period_days=1.0))
    one.run(24 * 6)
    other.run(24 * 3)
    data = json.loads(json.dumps(first.to_dict()))
    first.close()
    resumed = SpeciesTracker.restore(other, data)
    other.run(24 * 3)
    assert resumed.to_dict() == whole.to_dict()


def test_closing_stops_the_listening():
    world = make_world()
    tr = SpeciesTracker(world, SpeciesRules(period_days=1.0))
    world.run(2)
    taken = tr.samples_taken
    tr.close()
    tr.close()
    world.run(24 * 3)
    assert tr.samples_taken == taken
    tr.attach()
    tr.attach()
    world.run(24 * 2)
    assert tr.samples_taken > taken
