"""WORLD.14: values the world keeps per tick or computes in one pass match the plain formulas."""

import itertools
import random

from world_support import HOURLY, hourly_world

from evolution_simulator.world import Bounds, DayCycle, Vec, World, WorldConfig


def test_cached_light_follows_the_tick_and_the_rules() -> None:
    world = hourly_world(day_cycle=DayCycle())
    cycle = world.config.day_cycle
    assert cycle is not None
    for _ in range(60):
        seconds = world.simulated_seconds
        assert world.daylight == cycle.daylight(seconds)
        assert world.day_phase == cycle.phase(seconds)
        assert world.daylight == world.daylight  # a second ask in the same tick
        world.step()
    # A different cycle in the same tick is not served from the old one.
    other = DayCycle(length_seconds=12 * 3600.0, start_phase=0.25)
    world.config = world.config.with_rules(day_cycle=other)
    assert world.day_phase == other.phase(world.simulated_seconds)
    assert world.daylight == other.daylight(world.simulated_seconds)


def test_no_day_cycle_is_full_light() -> None:
    world = hourly_world(day_cycle=None)
    world.step()
    assert (world.daylight, world.day_phase) == (1.0, None)


def test_simulated_seconds_is_ticks_times_the_tick_length() -> None:
    world = World(WorldConfig().with_time_scale(HOURLY))
    world.run(5)
    assert world.simulated_seconds == 5 * 3600.0
    assert world.time_scale.simulated_seconds(world.tick) == world.simulated_seconds


def test_edge_state_matches_edge_distance_and_vector() -> None:
    world = World(WorldConfig(bounds=Bounds((120.0, 80.0))))
    rng = random.Random(3)
    spots = [Vec.of(rng.uniform(0, 120), rng.uniform(0, 80)) for _ in range(200)]
    spots += [Vec.of(x, y) for x, y in itertools.product((0.0, 60.0, 120.0), (0.0, 40.0, 80.0))]
    spots.append(Vec.of(40.0, 40.0))  # the nearest wall is a tie between two axes
    for spot in spots:
        assert world.edge_state(spot) == (world.edge_distance(spot), world.edge_vector(spot))
