"""Timings of the simulation's inner loop (INFRA.7), run on request, not with the test suite:

    pytest benchmarks --benchmark-only

See docs/testing.md. These check nothing about behaviour; they exist so a change that claims to make
the world faster (WORLD.19) can show the before and after with the same measurement.
"""

from evolution_simulator.world import World, WorldConfig


def make_world(animals: int, plants: int) -> World:
    world = World(WorldConfig(seed=1))
    world.populate(animals=animals, plants=plants)
    return world


def run_five_ticks(world: World) -> None:
    world.run(5)


def bench(benchmark, animals: int, plants: int, rounds: int) -> None:
    """Each round times five ticks of a fresh world, so rounds are comparable."""
    benchmark.pedantic(
        run_five_ticks,
        setup=lambda: ((make_world(animals, plants),), {}),
        rounds=rounds,
        warmup_rounds=1,
    )


def test_step_a_small_world(benchmark):
    bench(benchmark, animals=60, plants=300, rounds=15)


def test_step_a_crowded_world(benchmark):
    bench(benchmark, animals=400, plants=1500, rounds=8)
