"""What the inspector says about a creature (UX.14): the parts that need no window."""

import random
from array import array
from dataclasses import replace

import pytest

pytest.importorskip("numpy")

from worldview_support import animal, make_frame

from evolution_simulator.brain_adapter import BrainDecision
from evolution_simulator.catalogue import GENES
from evolution_simulator.deaths import DeathCause
from evolution_simulator.history import HistorySamples
from evolution_simulator.history.samples import Sample, Stat, Tier
from evolution_simulator.layouts import ANIMAL_LAYOUT, founder_animal_dna
from evolution_simulator.session import ANIMAL_COLUMNS
from evolution_simulator.session.snapshot import Block
from evolution_simulator.viewer.inspector import describe
from evolution_simulator.world import World, WorldConfig


@pytest.fixture(scope="module")
def detail():
    world = World(WorldConfig(seed=1))
    world.populate(animals=6, plants=20)
    for _ in range(5):
        world.step()
    return world.animal_detail(world.animals[0].id)


def decision(**kw):
    values = {
        "turn": 0.0,
        "speed": 0.0,
        "eat_or_attack": 0.0,
        "seek_mating": 0.0,
        "alarm_call": 0.0,
        "mating_call": 0.0,
    }
    values.update(kw)
    return BrainDecision(**values)


# --- the body ---------------------------------------------------------------------


def test_stages_follow_the_share_of_the_lifespan_used():
    assert [describe.life_stage(r) for r in (0.0, 0.11, 0.12, 0.5, 0.74, 0.75, 1.0)] == [
        "young",
        "young",
        "in its prime",
        "in its prime",
        "in its prime",
        "old",
        "old",
    ]


def test_age_is_said_in_the_unit_that_fits(detail):
    for ticks, tick_seconds, expected in (
        (10, 3600.0, "10 hours old"),
        (24, 3600.0, "1 day old"),
        (72, 3600.0, "3 days old"),
        (24 * 400, 3600.0, "1.1 years old"),
    ):
        text = describe.age_text(replace(detail, age_ticks=ticks, age_ratio=0.3), tick_seconds)
        assert text.startswith(expected), text
        assert "30% of its life" in text
    assert describe.age_text(replace(detail, age_ticks=7), None).startswith("7 ticks old")


def test_the_tick_length_comes_from_the_frame():
    assert describe.seconds_per_tick(None) is None
    assert describe.seconds_per_tick(make_frame(tick=0)) is None
    assert describe.seconds_per_tick(make_frame(tick=10, seconds=36000.0)) == 3600.0


def test_the_decision_is_said_in_words(detail):
    def say(**kw):
        return describe.decision_words(replace(detail, asleep=False, decision=decision(**kw)))

    assert say() == "straight ahead, standing still"
    assert say(turn=0.3, speed=0.5) == "turning left, at a walk"
    assert say(turn=-0.9, speed=0.9) == "turning hard right, fast"
    assert say(speed=0.2, eat_or_attack=0.9) == "straight ahead, slowly, eating or attacking"
    assert say(seek_mating=0.9, alarm_call=0.9, mating_call=0.9).endswith(
        "looking for a mate, calling an alarm, calling for a mate"
    )
    assert "wandering" in say(speed=0.4, wandering=True)
    assert describe.decision_words(replace(detail, asleep=True)) == "asleep"
    assert describe.decision_words(replace(detail, asleep=False, decision=None)) == (
        "nothing decided yet"
    )
    assert describe.decision_words(replace(detail, alive=False)) == "none (dead)"


def test_the_state_lists_sleep_young_and_readiness(detail):
    awake = replace(detail, asleep=False, pregnant=False, ready_to_mate=False)
    assert describe.state_words(awake) == ["awake"]
    busy = replace(awake, asleep=True, pregnant=True, litter=3, ready_to_mate=True)
    assert describe.state_words(busy) == ["asleep", "carrying 3 young", "ready to mate"]
    assert describe.state_words(replace(awake, pregnant=True, litter=1)) == ["carrying 1 young"]


def test_a_death_is_named_by_its_cause(detail):
    dead = replace(detail, alive=False, death_cause=DeathCause.PREDATION)
    assert describe.state_words(dead) == ["dead: was killed by another animal"]
    assert describe.death_text(None) == "cause unknown"
    for cause in DeathCause:
        assert describe.death_text(cause) != str(cause) or cause not in describe.DEATH_WORDS


def test_diet_in_words():
    assert [describe.diet_text(d) for d in (0.0, 0.2, 0.5, 0.8, 1.0)] == [
        "eats plants only",
        "mostly plants",
        "plants and meat",
        "mostly meat",
        "eats meat only",
    ]


# --- traits -----------------------------------------------------------------------


def test_traits_are_grouped_and_the_gene_levels_are_left_to_the_genes_tab(detail):
    groups = describe.trait_groups(detail.traits)
    assert [g.title for g in groups] == ["Senses", "Traits"]
    shown = {row.id for g in groups for row in g.rows}
    assert {"sight_reach", "mass", "cooldown_days"} <= shown
    assert not shown & {"speed", "size", "fear", "sex_strategy"}  # levels and the digit
    senses = [row.id for row in groups[0].rows]
    assert senses == [n for n in describe.SENSE_TRAITS if n in senses]
    reach = next(r for g in groups for r in g.rows if r.id == "sight_reach")
    assert reach.text.endswith("world units") and reach.name == "Sight reach" and reach.meaning


def test_a_trait_the_catalogue_does_not_know_is_still_shown():
    (group,) = describe.trait_groups({"new_thing": 2.5})
    assert group.rows[0].name == "New thing" and group.rows[0].text == "2.5"


def test_numbers_are_short():
    assert [describe.number_text(v) for v in (0.0, 0.00123, 0.4567, 12.345, 123.4, 12345.6)] == [
        "0",
        "0.0012",
        "0.457",
        "12.3",
        "123",
        "12,346",
    ]


# --- genes ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def genome():
    return str(founder_animal_dna(random.Random(4)))


def test_the_genome_is_read_as_the_layouts_named_genes_by_cluster(genome):
    genes = describe.read_genes(genome)
    assert genes is not None
    by_cluster = {g.cluster: [r.id for r in g.rows] for g in genes.groups}
    for cluster, ids in ANIMAL_LAYOUT.clusters.items():
        assert by_cluster[cluster] == list(ids)
    assert [g.title for g in genes.groups][:2] == ["Frame", "Repair"]
    assert genes.groups[-1].title == "Other genes"
    assert "touch" in by_cluster[""] and "brain" not in by_cluster[""]
    assert len(genes.brain_digits) == ANIMAL_LAYOUT.gene("brain").length
    every = {r.id for g in genes.groups for r in g.rows}
    assert every == set(ANIMAL_LAYOUT.gene_ids) - {"brain"} and every <= set(GENES)


def test_a_gene_row_carries_its_level_and_digits(genome):
    genes = describe.read_genes(genome)
    row = next(r for g in genes.groups for r in g.rows if r.id == "size")
    gene = ANIMAL_LAYOUT.gene("size")
    assert row.digits == genome[gene.start : gene.end]
    assert 0.0 <= row.level <= 1.0 and row.name == "Size" and row.population is None
    strategy = next(r for g in genes.groups for r in g.rows if r.id == "sex_strategy")
    assert strategy.text == strategy.digits and len(strategy.digits) == 1


def test_a_gene_far_from_the_population_is_marked_unusual(genome):
    plain = describe.read_genes(genome)
    level = next(r for g in plain.groups for r in g.rows if r.id == "size").level
    near = describe.read_genes(genome, {"size": (level, 0.1)})
    far = describe.read_genes(genome, {"size": (level + 0.5, 0.1)})
    flat = describe.read_genes(genome, {"size": (level + 0.5, 0.0)})

    def size(genes):
        return next(r for g in genes.groups for r in g.rows if r.id == "size")

    assert not size(near).unusual and size(near).population == level
    assert size(far).unusual and size(far).population == pytest.approx(level + 0.5)
    assert not size(flat).unusual  # no spread, nothing to be far from


def test_a_genome_of_another_layout_is_not_read():
    assert describe.read_genes("0123" * 8) is None
    assert describe.read_genes("") is None
    assert describe.read_genes("9" * ANIMAL_LAYOUT.length) is None


def test_the_populations_genes_come_from_the_newest_sample():
    assert describe.population_genes(None) == {}
    empty = HistorySamples(86400.0, ())
    assert describe.population_genes(empty) == {}
    stats = {
        "animal.gene.size": Stat(10, 0.4, 0.1, 0.1, 0.9),
        "animal.trait.mass": Stat(10, 2.0, 0.1, 1.0, 3.0),
        "plant.gene.longevity": Stat(10, 0.5, 0.1, 0.1, 0.9),
    }
    history = HistorySamples(86400.0, (Tier("days", 1, (Sample(1, 1, 24, stats=stats),)),))
    assert describe.population_genes(history) == {"size": (0.4, 0.1)}


# --- family -----------------------------------------------------------------------


def family_frame():
    return make_frame(
        [
            animal(1, family_a=0.10, family_b=0.50, sex=0, age_ratio=0.5),
            animal(2, family_a=0.11, family_b=0.51, sex=1, age_ratio=0.05),
            animal(3, family_a=0.90, family_b=0.05),
            animal(4, family_a=0.12, family_b=0.52),
        ]
    )


def test_the_closest_relatives_are_the_nearest_family_keys():
    found = describe.closest_relatives(family_frame(), 1, limit=3)
    assert [r.id for r in found] == [2, 4, 3]
    assert found[0].sex == 1 and found[0].age_ratio == pytest.approx(0.05)
    assert found[0].distance < found[1].distance < found[2].distance
    assert [r.id for r in describe.closest_relatives(family_frame(), 1, limit=1)] == [2]
    assert describe.relative_text(found[0]) == "#2: female, young"


def test_no_relatives_without_the_animal_or_the_key():
    assert describe.closest_relatives(None, 1) is None
    assert describe.closest_relatives(family_frame(), 99) is None
    block = Block(
        ANIMAL_COLUMNS[:8],
        array("I", [1]).tobytes(),
        array("f", [1, 1, 0, 1, 0.5, 1, 0.2, 0.5]).tobytes(),
        bytes(1),
    )
    old = replace(make_frame([animal(1)]), animals=block)  # a frame from before UX.30
    assert describe.closest_relatives(old, 1) is None
    alone = make_frame([animal(1)])
    assert describe.closest_relatives(alone, 1) == []


def test_the_living_ids_of_a_frame():
    assert describe.animal_ids(None) == frozenset()
    assert describe.animal_ids(family_frame()) == {1, 2, 3, 4}
    assert describe.ids_text([]) == "none" and describe.ids_text([4, 9]) == "#4, #9"
