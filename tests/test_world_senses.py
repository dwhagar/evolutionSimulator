"""WorldSenses (SENSE.12): the world's neighbour search and classifier feeding the sensing step."""

import math
import random
from dataclasses import replace
from types import SimpleNamespace

import pytest
from world_support import animal_dna, plant_dna

from evolution_simulator.brain_adapter import Percepts
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT
from evolution_simulator.learning import LearningRules
from evolution_simulator.sensing import (
    Neighbour,
    SensingConditions,
    SensingRules,
    organs_from_traits,
    sense,
)
from evolution_simulator.traits import AnimalTraits
from evolution_simulator.world import Bounds, DayCycle, Vec, World, WorldConfig, WorldSenses
from evolution_simulator.world.senses import (
    classify,
    loudness,
    relative_direction,
    wrap_angle,
)

HERE = Vec.of(500, 500)
BLIND_DEAF = {"hearing": "0000", "smell": "0000"}
NARROW = {"sight_range": "3333", "sight_fov": "0000", "touch": "0000", **BLIND_DEAF}
WIDE = {"sight_range": "3333", "sight_fov": "3333", "touch": "0000", **BLIND_DEAF}  # 33 units
NOSE = {"sight_range": "0000", "hearing": "0000", "smell": "3333", "touch": "0000"}  # 100 units
EARS = {"sight_range": "0000", "hearing": "3333", "smell": "0000", "touch": "0000"}  # 85 units
MASS_1, MASS_2, MASS_4 = "0000", "1111", "3333"
EXACT = SensingRules()
SHORT_DAY = DayCycle(length_seconds=100.0 * 3600.0)  # noon at tick 0, night from tick 33 to 67


def seen_by(world, animal, rules=EXACT):
    return WorldSenses(rules, noisy=False).perceive(world, animal)


def surface(a, b):
    return a.position.distance_to(b.position) - a.radius - b.radius


# --- the helpers ----------------------------------------------------------------------------


def test_wrap_angle_and_relative_direction():
    assert abs(wrap_angle(3 * math.pi)) == pytest.approx(math.pi)
    assert wrap_angle(2.5 * math.pi) == pytest.approx(0.5 * math.pi)
    assert relative_direction(0.0, HERE, Vec.of(600, 500)) == pytest.approx(0.0)
    assert relative_direction(0.0, HERE, Vec.of(500, 600)) == pytest.approx(-0.5)  # to the left
    assert relative_direction(0.0, HERE, Vec.of(500, 400)) == pytest.approx(0.5)  # to the right
    assert abs(relative_direction(0.0, HERE, Vec.of(400, 500))) == pytest.approx(1.0)  # behind


def test_classes_follow_mass_and_what_the_animals_can_digest():
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2), HERE)
    light = world.add_animal(animal_dna(size=MASS_1), HERE)
    heavy = world.add_animal(animal_dna(size=MASS_4), HERE)
    same = world.add_animal(animal_dna(size=MASS_2), HERE)
    assert [classify(me, o) for o in (light, heavy, same)] == ["prey", "threat", "mate"]
    # A plant eater has no use for a lighter animal, and a heavy plant eater is no danger.
    grazer = world.add_animal(animal_dna(size=MASS_2, carnivore_eff="0000"), HERE)
    gentle = world.add_animal(animal_dna(size=MASS_4, carnivore_eff="0000"), HERE)
    assert classify(grazer, light) == "other"
    assert classify(grazer, heavy) == "threat"
    assert classify(me, gentle) == "other"
    assert classify(me, same) == "mate"


def test_loudness_is_quiet_when_still_or_asleep_and_full_at_top_speed():
    still = SimpleNamespace(asleep=False, last_decision=None)
    asleep = SimpleNamespace(asleep=True, last_decision=SimpleNamespace(speed=1.0))
    half = SimpleNamespace(asleep=False, last_decision=SimpleNamespace(speed=0.5))
    full = SimpleNamespace(asleep=False, last_decision=SimpleNamespace(speed=1.0))
    assert loudness(still) == pytest.approx(0.1)
    assert loudness(asleep) == pytest.approx(0.1)
    assert loudness(half) == pytest.approx(0.55)
    assert loudness(full) == pytest.approx(1.0)


# --- seeing plants --------------------------------------------------------------------------


def test_a_plant_ahead_is_in_the_middle_and_closeness_follows_the_gap_between_surfaces():
    world = World()
    animal = world.add_animal(animal_dna(**NARROW), HERE, heading=0.0)
    plant = world.add_plant(plant_dna(), Vec.of(520, 500))
    seen = seen_by(world, animal)
    reach = animal.traits.current_sight_range
    assert seen.plant_direction == pytest.approx(0.0, abs=0.06)
    assert seen.plant_closeness == pytest.approx(1.0 - surface(animal, plant) / reach)


def test_left_is_negative_and_right_is_positive_when_the_view_is_wide():
    for y, expected in ((510, -0.5), (490, 0.5)):
        world = World()
        animal = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
        world.add_plant(plant_dna(), Vec.of(500, y))
        assert seen_by(world, animal).plant_direction == pytest.approx(expected, abs=0.06)


def test_turning_toward_what_it_sees_uses_the_same_sign_as_the_direction():
    # Facing +x with food to the right (direction +): a positive turn reduces the bearing gap.
    world = World()
    animal = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    plant = world.add_plant(plant_dna(), Vec.of(500, 490))
    assert seen_by(world, animal).plant_direction > 0
    animal.heading = wrap_angle(animal.heading - 0.3)  # what turn=+1 does at turn rate 0.3
    assert relative_direction(animal.heading, animal.position, plant.position) < 0.5


def test_things_out_of_range_or_outside_the_field_of_view_are_not_seen():
    world = World()
    animal = world.add_animal(animal_dna(**NARROW), HERE, heading=0.0)
    world.add_plant(plant_dna(), Vec.of(500 + 100, 500))  # beyond 60 units
    world.add_plant(plant_dna(), Vec.of(480, 500))  # behind, outside 40 degrees
    world.add_plant(plant_dna(), Vec.of(510, 540))  # ahead-ish but far off to the side
    assert seen_by(world, animal) == Percepts(daylight=1.0)


def test_a_plant_one_can_stand_on_is_seen_whichever_way_it_faces():
    world = World()
    animal = world.add_animal(animal_dna(**NARROW), HERE, heading=0.0)
    plant = world.add_plant(plant_dna(), Vec.of(500, 500.4))  # overlapping, off to one side
    assert surface(animal, plant) <= 0.0
    assert seen_by(world, animal).plant_closeness == pytest.approx(1.0)


def test_the_nearest_plant_wins():
    world = World()
    animal = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    world.add_plant(plant_dna(), Vec.of(520, 500))
    near = world.add_plant(plant_dna(), Vec.of(505, 505))
    seen = seen_by(world, animal)
    assert seen.plant_closeness == pytest.approx(
        1.0 - surface(animal, near) / animal.traits.current_sight_range
    )


def test_a_plant_is_smelled_in_proportion_to_its_biomass():
    world = World()
    animal = world.add_animal(animal_dna(**NOSE), HERE, heading=0.0)
    plant = world.add_plant(plant_dna(), Vec.of(500, 560))  # about 59 units from the surface
    gap = surface(animal, plant)
    assert 40.0 < gap < 100.0
    plant.traits.current_biomass = 20.0  # scent 0.2: carries 20 units
    assert seen_by(world, animal).plant_closeness == 0.0
    plant.traits.current_biomass = 100.0 * (gap + 1.0) / 100.0  # just reaches
    reaching = seen_by(world, animal)
    assert reaching.plant_closeness > 0.0
    plant.traits.current_biomass = 100.0  # full scent: carries the whole smell range
    full = seen_by(world, animal)
    assert full.plant_closeness == pytest.approx(1.0 - gap / 100.0)


# --- seeing animals -------------------------------------------------------------------------


def test_other_animals_are_prey_threat_or_possible_mate():
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2, **WIDE), HERE, heading=0.0)
    world.add_animal(animal_dna(size=MASS_1), Vec.of(510, 500))  # lighter
    world.add_animal(animal_dna(size=MASS_4), Vec.of(500, 510))  # heavier
    world.add_animal(animal_dna(size=MASS_2), Vec.of(490, 500))  # similar
    seen = seen_by(world, me)
    assert seen.prey_closeness > 0 and seen.prey_direction == pytest.approx(0.0, abs=0.06)
    assert seen.threat_closeness > 0 and seen.threat_direction == pytest.approx(-0.5, abs=0.06)
    assert seen.mate_closeness > 0 and abs(seen.mate_direction) == pytest.approx(1.0, abs=0.06)
    assert seen.crowding == pytest.approx(3 / 8)


def test_a_plant_eater_sees_a_small_animal_only_as_company():
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2, carnivore_eff="0000", **WIDE), HERE)
    world.add_animal(animal_dna(size=MASS_1), Vec.of(510, 500))
    seen = seen_by(world, me)
    assert seen.prey_closeness == 0.0
    assert seen.crowding == pytest.approx(1 / 8)


def test_crowding_counts_animals_in_reach_and_tops_out_at_the_reference():
    world = World()
    me = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    for i in range(12):
        world.add_animal(animal_dna(), Vec.of(500 + 2 * i, 505))
    assert seen_by(world, me).crowding == 1.0
    assert seen_by(world, me, SensingRules(crowding_reference=24)).crowding == pytest.approx(0.5)


def test_relative_size_is_that_of_the_nearer_of_prey_and_threat():
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2, **WIDE), HERE, heading=0.0)
    world.add_animal(animal_dna(size=MASS_1), Vec.of(510, 500))  # lighter: half the mass
    world.add_animal(animal_dna(size=MASS_4), Vec.of(500, 520))  # heavier: twice the mass, further
    assert seen_by(world, me).relative_size == pytest.approx(-0.5)  # log2(1/2) / 2
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2, **WIDE), HERE, heading=0.0)
    world.add_animal(animal_dna(size=MASS_1), Vec.of(520, 500))
    world.add_animal(animal_dna(size=MASS_4), Vec.of(500, 510))  # now the nearer one
    assert seen_by(world, me).relative_size == pytest.approx(0.5)  # log2(2) / 2
    world = World()
    alone = world.add_animal(animal_dna(size=MASS_2, **WIDE), HERE, heading=0.0)
    world.add_animal(animal_dna(size=MASS_2), Vec.of(510, 500))  # a possible mate is not sized
    assert seen_by(world, alone).relative_size == 0.0


def test_the_time_of_day_is_reported():
    world = World()
    me = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    assert seen_by(world, me).daylight == 1.0  # no day cycle: always full daylight
    assert seen_by(world, me).senses_nothing  # and that is not a sense


def test_an_animal_does_not_sense_itself():
    world = World()
    me = world.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    seen = seen_by(world, me)
    assert seen == Percepts(daylight=1.0)  # daylight is reported even when nothing else is


def test_a_sleeper_is_quiet_but_not_invisible():
    world = World()
    me = world.add_animal(animal_dna(size=MASS_2, **EARS), HERE, heading=0.0)
    other = world.add_animal(animal_dna(size=MASS_1), Vec.of(540, 500))
    other.last_decision = SimpleNamespace(speed=1.0, calls_alarm=False, calls_for_mate=False)
    assert seen_by(world, me).prey_closeness > 0.0  # running, so heard at 40 units
    other.last_decision = SimpleNamespace(speed=0.0, calls_alarm=False, calls_for_mate=False)
    assert seen_by(world, me).prey_closeness == 0.0  # still, so heard only to about 8 units
    other.position = Vec.of(506, 500)
    assert seen_by(world, me).prey_closeness > 0.0


# --- touch ----------------------------------------------------------------------------------


def test_touch_reaches_a_little_past_the_body():
    world = World()
    wide = {**WIDE, "touch": "3333"}
    numbed = {**WIDE, "touch": "0000"}
    toucher = world.add_animal(animal_dna(**wide), HERE, heading=0.0)
    numb = world.add_animal(animal_dna(**numbed), Vec.of(502, 500), heading=0.0)
    assert seen_by(world, toucher).touching
    assert not seen_by(world, numb).touching
    far = world.add_animal(animal_dna(**wide), Vec.of(900, 100))
    world.add_plant(plant_dna(), Vec.of(600, 600))
    assert not seen_by(world, far).touching


def test_the_wall_is_felt_like_anything_else_in_contact():
    world = World()
    at_wall = world.add_animal(animal_dna(**WIDE), Vec.of(0.2, 500), heading=0.0)
    mid = world.add_animal(animal_dna(**WIDE), Vec.of(500, 300), heading=0.0)
    assert seen_by(world, at_wall).touching
    assert not seen_by(world, mid).touching
    assert world.edge_distance(Vec.of(0.2, 500)) == pytest.approx(0.2)
    assert world.edge_distance(Vec.of(990, 400)) == pytest.approx(10.0)


# --- light and sleep ------------------------------------------------------------------------


def test_the_dark_shortens_sight_and_sleep_closes_the_eyes():
    day = World(WorldConfig(day_cycle=SHORT_DAY))
    me = day.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    day.add_plant(plant_dna(), Vec.of(520, 500))
    noon = seen_by(day, me).plant_closeness
    assert noon > 0.0

    night = World(WorldConfig(day_cycle=SHORT_DAY))
    for _ in range(50):  # midnight
        night.tick += 1
    owl = night.add_animal(animal_dna(**WIDE), HERE, heading=0.0)
    night.add_plant(plant_dna(), Vec.of(520, 500))
    assert night.daylight == pytest.approx(0.0)
    dark = seen_by(night, owl).plant_closeness
    assert 0.0 <= dark < noon  # a quarter of the range at full dark

    owl.asleep = True
    assert seen_by(night, owl).plant_closeness == 0.0


# --- pruning ---------------------------------------------------------------------------------


def brute_force(world, animal, rules, rng):
    """The same sensing step fed with every plant and animal in the world, no search at all."""
    neighbours = []
    for plant in world.plants:
        neighbours.append(
            Neighbour(
                ident=plant.id,
                role="plant",
                position=plant.position,
                radius=plant.traits.canopy_radius,
                loudness=0.0,
                scent=min(1.0, plant.traits.current_biomass / 100.0),
            )
        )
    for other in world.animals:
        if other is animal:
            continue
        alarm, mating = world.calls.get(other.id, (0.0, 0.0))
        neighbours.append(
            Neighbour(
                ident=other.id,
                role=classify(animal, other),
                position=other.position,
                radius=other.radius,
                loudness=loudness(other),
                scent=1.0,
                alarm_call_radius=alarm,
                mating_call_radius=mating,
                mass=other.traits.mass,
            )
        )
    return sense(
        animal.position,
        animal.heading,
        animal.radius,
        organs_from_traits(animal.traits),
        neighbours,
        SensingConditions(daylight=world.daylight, asleep=animal.asleep),
        rules,
        rng,
        edge_distance=world.edge_distance(animal.position) - animal.radius,
        mass=animal.traits.mass,
    )


def test_searching_only_nearby_gives_the_same_answer_as_looking_at_everything():
    rules = SensingRules()
    world = World(WorldConfig(seed=11, day_cycle=SHORT_DAY))
    world.populate(animals=40, plants=300)
    world.run(60)  # night, some asleep, everyone somewhere new
    senses = WorldSenses(rules)
    for animal in world.animals:
        world.rng = random.Random(animal.id)
        found = senses.perceive(world, animal)
        expected = brute_force(world, animal, rules, random.Random(animal.id))
        assert found == expected


def test_perceiving_changes_nothing_but_the_random_stream():
    world = World(
        WorldConfig(seed=3, bounds=Bounds((120, 120)))
    )  # crowded, so everyone senses someone
    world.populate(animals=10, plants=40)
    before = world.state_digest()
    stream = world.rng.getstate()
    for animal in world.animals:
        seen_by(world, animal)
    assert world.state_digest() == before  # a noise-free look leaves even the stream alone
    noisy = WorldSenses()
    for animal in world.animals:
        noisy.perceive(world, animal)
    assert world.rng.getstate() != stream  # the noise came from the world's generator
    world.rng.setstate(stream)
    assert world.state_digest() == before


# --- calls ----------------------------------------------------------------------------------


def add_caller(world):
    """An animal whose brain calls an alarm and for a mate on every tick."""
    brain = {"alarm": 2.0, "call": 2.0, "mate": 2.0}
    return world.add_animal(animal_dna(brain=brain, **WIDE), HERE, heading=0.0)


def calling_world(**config):
    world = World(WorldConfig(calls_enabled=True, **config))
    caller = add_caller(world)
    listener = world.add_animal(animal_dna(**EARS), Vec.of(515, 500), heading=0.0)
    return world, caller, listener


def test_calls_can_be_turned_off():
    world = World(WorldConfig(calls_enabled=False))
    add_caller(world)
    listener = world.add_animal(animal_dna(**EARS), Vec.of(515, 500), heading=0.0)
    world.run(3)
    assert world.calls == {}
    assert seen_by(world, listener).alarm_strength == 0.0


def test_a_calling_animal_is_heard_by_a_listener_within_its_call_radius():
    world, caller, listener = calling_world()
    energy = caller.traits.current_energy
    world.run(2)  # tick 1 decides; tick 2 calls
    assert caller.id in world.calls
    alarm, mating = world.calls[caller.id]
    assert alarm == mating == caller.traits.call_radius > 0.0
    assert caller.traits.current_energy < energy
    heard = seen_by(world, listener)
    gap = surface(caller, listener)
    assert heard.alarm_strength == pytest.approx(1.0 - gap / alarm, abs=0.05)
    assert heard.mating_call_strength == pytest.approx(heard.alarm_strength, abs=0.05)
    assert heard.call_direction != 0.0 or listener.position.coords[1] == caller.position.coords[1]
    # Out of the call radius, nothing.
    listener.position = Vec.of(500, 560)
    assert seen_by(world, listener).alarm_strength == 0.0


def test_a_caller_without_the_energy_stays_quiet():
    world, caller, _ = calling_world()
    world.run(1)
    caller.traits.current_energy = caller.traits.call_energy_cost / 2
    world.step()
    assert caller.id not in world.calls


# --- an alarm wakes a sleeper ---------------------------------------------------------------


def night_with_alarm(listener_at, ticks=3):
    """A listener asleep at night, then a wakeful caller turns up and calls."""
    world = World(WorldConfig(calls_enabled=True, day_cycle=SHORT_DAY))
    listener = world.add_animal(animal_dna(brain={}, **EARS), HERE, heading=0.0)
    world.run(34)  # into the night
    assert listener.asleep
    listener.position = listener_at
    caller = add_caller(world)
    caller.disturbed = True  # keeps watch instead of sleeping
    world.run(ticks)  # one tick to decide, one to call
    assert not caller.asleep
    return world, listener


def test_an_alarm_call_wakes_a_sleeper_who_hears_it():
    world, listener = night_with_alarm(Vec.of(508, 500))
    assert world.is_night
    assert not listener.asleep
    assert listener.disturbed


def test_a_disturbed_animal_stays_up_all_night_and_sleeps_again_the_next():
    world, listener = night_with_alarm(Vec.of(508, 500))
    world.config = replace(world.config, calls_enabled=False)  # the caller falls silent
    world.run(20)
    assert world.is_night and not listener.asleep
    world.run(40)  # day
    assert not world.is_night
    assert not listener.disturbed
    world.run(40)  # the next night
    assert world.is_night and listener.asleep


def test_a_sleeper_too_far_away_is_not_woken():
    # The caller is only heard within its own call radius, 20 units.
    _, listener = night_with_alarm(Vec.of(560, 500))
    assert listener.asleep
    assert not listener.disturbed


# --- swapping the senses --------------------------------------------------------------------


def test_the_world_senses_only_when_the_brain_will_look():
    class Counting(WorldSenses):
        def __init__(self):
            super().__init__()
            self.asked = []

        def perceive(self, world, animal):
            self.asked.append(world.tick)
            return super().perceive(world, animal)

    senses = Counting()
    world = World(WorldConfig(day_cycle=None, learning=None), senses=senses)
    animal = world.add_animal(animal_dna(brain={}), HERE, heading=0.0)
    animal.traits.decision_interval = 3
    world.run(9)
    assert senses.asked == [0, 3, 6]  # between brain runs the last decision is repeated
    assert animal.last_decision is not None


def test_cached_decision_repeats_the_last_one_and_keeps_the_log_going():
    traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(3)), decision_interval=3)
    traits.curiosity = 0.3
    traits.learning_rate = 1.0
    traits.learning_rules = LearningRules()
    rng = random.Random(1)
    assert traits.cached_decision(rng) is None  # nothing to repeat yet
    decided = traits.think(Percepts(threat_closeness=0.7), rng)
    seen = []
    traits.learner.observe = lambda state: seen.append(state.threat)
    assert traits.cached_decision(rng) is decided
    assert traits.cached_decision(rng) is decided
    assert seen == [0.7, 0.7]  # the threat from when the brain last looked
    assert traits.cached_decision(rng) is None  # time to look again


def test_the_step_loop_uses_whatever_senses_it_is_given():
    class AlwaysFoodAhead:
        def __init__(self):
            self.asked = []

        def perceive(self, world, animal):
            self.asked.append(animal.id)
            return Percepts(plant_closeness=0.7)

    senses = AlwaysFoodAhead()
    world = World(WorldConfig(), senses=senses)
    first = world.add_animal(animal_dna(), HERE, heading=0.0)
    second = world.add_animal(animal_dna(), Vec.of(100, 100), heading=1.0)
    world.step()
    assert senses.asked == [first.id, second.id]
    assert first.last_decision is not None
