"""Speed benchmark: milliseconds per tick of a full world (``WORLD.19``, docs/design/numpy-core.md).

    python -m evolution_tools.bench_world   (or scripts/bench-world.ps1 or .bat) [--sizes 60/300,300/3000,1000/5000] [--ticks 48]
        [--warmup 20] [--repeat 3] [--seed 3] [--engine object] [--profile]
        [--json out.json] [--compare baseline.json] [--tolerance 0.15] [--target-ms 41.7]

It builds a seeded world of each size (animals/plants at the start), runs ``--warmup`` ticks so the
first plant die-back is over, then times ``--ticks`` single ticks (two simulated days at the hourly
default, so a night, with its sleep and learning spike, is always inside the window) and repeats that
``--repeat`` times from a fresh world. For each size it prints the mean, median, 95th percentile and
slowest tick of the best repeat, the ticks per second that mean allows, the simulated days per real
second at the world's tick length, and the animals and plants alive at the end.

The goal of the numpy core is a full world (1,000 animals, 5,000 plants, hourly ticks) at one simulated
day per real second: 24 ticks a second, 41.7 ms a tick. ``--target-ms`` turns that into a check: the
largest size must be at or under it or the exit status is 1. ``--json`` saves the result and
``--compare`` reads an earlier file and exits 1 if any size got more than ``--tolerance`` slower, so a
change that touches the tick can be checked against the build before it. ``--profile`` profiles one
run of the largest size and prints the project functions that cost the most.

Nothing is written outside ``--json``. The numbers depend on the computer and on what else it is doing:
compare runs from the same machine, and trust a difference of 10% or less no further than the spread
between repeats (printed with ``--repeat`` above 1).

Engines: ``object`` is today's ``World``. ``WORLD.20`` adds ``array`` to ``ENGINES`` below; an engine is
a function ``(animals, plants, seed) -> world`` and the world needs ``step()``, ``dt``, ``animals``
(a sized collection) and ``plant_count``, which the array world keeps.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import platform
import pstats
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_SIZES = "60/300,300/3000,1000/5000"
"""The three worlds of the package research (docs/research/python-packages.md, section 3)."""
TARGET_DAYS_PER_SECOND = 1.0
"""The numpy core's goal for the largest world: one simulated day per real second."""


def _object_world(animals: int, plants: int, seed: int) -> Any:
    from evolution_simulator.world import World, WorldConfig

    world = World(WorldConfig(seed=seed))
    world.populate(animals=animals, plants=plants)
    return world


ENGINES: dict[str, Callable[[int, int, int], Any]] = {"object": _object_world}
"""Name to world factory. ``WORLD.20`` registers the array engine here."""


def parse_sizes(text: str) -> list[tuple[int, int]]:
    sizes = []
    for part in text.split(","):
        animals, _, plants = part.strip().partition("/")
        sizes.append((int(animals), int(plants)))
    return sizes


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def run_once(
    engine: Callable[[int, int, int], Any],
    animals: int,
    plants: int,
    seed: int,
    warmup: int,
    ticks: int,
) -> dict[str, Any]:
    world = engine(animals, plants, seed)
    for _ in range(warmup):
        world.step()
    times: list[float] = []
    for _ in range(ticks):
        start = time.perf_counter()
        world.step()
        times.append((time.perf_counter() - start) * 1000.0)
    mean = statistics.fmean(times)
    return {
        "mean_ms": mean,
        "median_ms": statistics.median(times),
        "p95_ms": percentile(times, 0.95),
        "max_ms": max(times),
        "ticks_per_second": 1000.0 / mean,
        "days_per_second": (1000.0 / mean) * world.dt / 24.0,
        "animals_end": len(world.animals),
        "plants_end": world.plant_count,
    }


def measure(
    engine_name: str, sizes: list[tuple[int, int]], seed: int, warmup: int, ticks: int, repeat: int
) -> list[dict[str, Any]]:
    engine = ENGINES[engine_name]
    results = []
    for animals, plants in sizes:
        runs = [run_once(engine, animals, plants, seed, warmup, ticks) for _ in range(repeat)]
        best = min(runs, key=lambda r: r["mean_ms"])
        results.append(
            {
                "animals": animals,
                "plants": plants,
                **best,
                "spread_ms": max(r["mean_ms"] for r in runs) - min(r["mean_ms"] for r in runs),
            }
        )
    return results


def environment(engine_name: str) -> dict[str, Any]:
    try:
        import numpy

        numpy_version = numpy.__version__
    except ImportError:
        numpy_version = None
    return {
        "engine": engine_name,
        "python": platform.python_version(),
        "numpy": numpy_version,
        "platform": platform.platform(),
        "cpus": os.cpu_count(),
    }


def print_table(
    results: list[dict[str, Any]], env: dict[str, Any], args: argparse.Namespace
) -> None:
    print(
        f"engine={env['engine']}  python={env['python']}  numpy={env['numpy']}  "
        f"{env['platform']}  seed={args.seed}  warmup={args.warmup}  ticks={args.ticks}  "
        f"repeat={args.repeat}"
    )
    print(
        f"{'animals/plants':>15} {'mean ms':>9} {'median':>8} {'p95':>8} {'max':>8} "
        f"{'ticks/s':>8} {'days/s':>7} {'end a/p':>12} {'spread':>7}"
    )
    for r in results:
        print(
            f"{r['animals']:>7}/{r['plants']:<7} {r['mean_ms']:>9.1f} {r['median_ms']:>8.1f} "
            f"{r['p95_ms']:>8.1f} {r['max_ms']:>8.1f} {r['ticks_per_second']:>8.1f} "
            f"{r['days_per_second']:>7.2f} {r['animals_end']:>5}/{r['plants_end']:<6} "
            f"{r['spread_ms']:>7.1f}"
        )


def compare(results: list[dict[str, Any]], baseline: dict[str, Any], tolerance: float) -> bool:
    """Print each size against the baseline file; True if none is more than ``tolerance`` slower."""
    before = {(r["animals"], r["plants"]): r for r in baseline["results"]}
    ok = True
    print(f"against {baseline['environment']['engine']} engine, tolerance {tolerance:.0%}:")
    for r in results:
        old = before.get((r["animals"], r["plants"]))
        if old is None:
            continue
        ratio = r["mean_ms"] / old["mean_ms"]
        verdict = "ok"
        if ratio > 1.0 + tolerance:
            verdict, ok = "SLOWER", False
        elif ratio < 1.0 - tolerance:
            verdict = "faster"
        print(
            f"  {r['animals']}/{r['plants']}: {old['mean_ms']:.1f} -> {r['mean_ms']:.1f} ms "
            f"(x{ratio:.2f}) {verdict}"
        )
    return ok


def profile(engine_name: str, size: tuple[int, int], seed: int, warmup: int, ticks: int) -> None:
    world = ENGINES[engine_name](size[0], size[1], seed)
    for _ in range(warmup):
        world.step()
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(ticks):
        world.step()
    profiler.disable()
    print(
        f"\nprofile of {size[0]}/{size[1]} over {ticks} ticks (the profiler itself slows a tick ~2-3x)"
    )
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative").print_stats("evolution_simulator", 25)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sizes", default=DEFAULT_SIZES, help="animals/plants, comma separated")
    parser.add_argument("--ticks", type=int, default=48, help="ticks timed per run")
    parser.add_argument("--warmup", type=int, default=20, help="ticks run before timing")
    parser.add_argument("--repeat", type=int, default=3, help="runs per size, from a fresh world")
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--engine", choices=sorted(ENGINES), default="object")
    parser.add_argument("--profile", action="store_true", help="profile the largest size")
    parser.add_argument("--json", type=Path, help="write the results here")
    parser.add_argument("--compare", type=Path, help="a --json file to compare with")
    parser.add_argument("--tolerance", type=float, default=0.15, help="slower than this fails")
    parser.add_argument(
        "--target-ms",
        type=float,
        help=f"fail if the largest size is slower (the goal is {1000.0 / 24.0 / TARGET_DAYS_PER_SECOND:.1f})",
    )
    args = parser.parse_args()

    sizes = parse_sizes(args.sizes)
    results = measure(args.engine, sizes, args.seed, args.warmup, args.ticks, args.repeat)
    env = environment(args.engine)
    print_table(results, env, args)
    ok = True
    if args.compare is not None:
        ok = compare(results, json.loads(args.compare.read_text()), args.tolerance) and ok
    if args.target_ms is not None:
        largest = max(results, key=lambda r: (r["animals"], r["plants"]))
        met = largest["mean_ms"] <= args.target_ms
        print(
            f"target {args.target_ms:.1f} ms at {largest['animals']}/{largest['plants']}: "
            f"{largest['mean_ms']:.1f} ms -> {'met' if met else 'NOT met'}"
        )
        ok = ok and met
    if args.json is not None:
        args.json.write_text(json.dumps({"environment": env, "results": results}, indent=2) + "\n")
    if args.profile:
        profile(args.engine, max(sizes), args.seed, args.warmup, min(args.ticks, 24))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
