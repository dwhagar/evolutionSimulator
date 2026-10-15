"""Feasibility measurements behind docs/design/numpy-core.md (``WORLD.19``). Not engine code.

    python -m evolution_tools.numpy_kernel_check [--repeat 20] [--reach 50]

The design note claims that the expensive parts of a tick (finding neighbours, sensing, thinking,
growing plants, the per-animal bookkeeping) cost a few milliseconds each when written as numpy array
operations on 1,000 animals and 5,000 plants. This script is that claim in runnable form: small
stand-ins for those steps on random worlds, each timed, and the two that choose by distance checked
against a plain loop on a small world first (a fast kernel that is wrong would prove nothing).

The stand-ins are simpler than the real rules (one sense, one class split, a brain of random weights,
a plant growth formula of the right shape), so read the milliseconds as the cost of the *technique*
at the real sizes, not as a forecast of the finished tick; the note adds what the rest will cost.
Needs numpy only. The numbers depend on the computer: compare runs from the same machine.
"""

from __future__ import annotations

import argparse
import math
import time
from functools import partial
from typing import Any

import numpy as np

SIZE = 1000.0
"""Side of the square world, as in ``Bounds``."""
CELL = 50.0
"""Grid cell side. Sense reaches here are 30 to 50 units; the real limits are 84 (sight), 85 (hearing)
and 100 (smell), so the note also times a reach of 100."""
SIGHT_HALF_FOV = math.radians(52.0)


def make_world(animals: int, plants: int, reach: float, seed: int = 1) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    return {
        "rng": rng,
        "ax": rng.uniform(0.0, SIZE, animals),
        "ay": rng.uniform(0.0, SIZE, animals),
        "heading": rng.uniform(-math.pi, math.pi, animals),
        "body": rng.uniform(1.5, 4.0, animals),
        "mass": rng.uniform(0.5, 4.0, animals),
        "reach": rng.uniform(0.6 * reach, reach, animals),
        "px": rng.uniform(0.0, SIZE, plants),
        "py": rng.uniform(0.0, SIZE, plants),
        "canopy": rng.uniform(0.5, 4.0, plants),
    }


def candidate_pairs(
    ax: np.ndarray, ay: np.ndarray, reach: np.ndarray, px: np.ndarray, py: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Every (animal, thing) pair with the thing in the cells around the animal (a ring of
    ``ceil(reach / CELL)`` cells), grouped by animal. Things are sorted by cell once; the cells of one
    grid row are contiguous in that order, so each animal needs one slice per row of cells, not one
    per cell. Returns ``(animal_index, thing_index)``."""
    side = math.ceil(SIZE / CELL)
    cell = np.minimum((px // CELL).astype(np.int64), side - 1) + side * np.minimum(
        (py // CELL).astype(np.int64), side - 1
    )
    order = np.argsort(cell, kind="stable")
    starts = np.searchsorted(cell[order], np.arange(side * side + 1))
    cx = np.minimum((ax // CELL).astype(np.int64), side - 1)
    cy = np.minimum((ay // CELL).astype(np.int64), side - 1)
    ring = np.maximum(1, np.ceil(reach / CELL).astype(np.int64))
    lows, highs, owners = [], [], []
    for r in range(1, int(ring.max()) + 1):
        who = np.flatnonzero(ring == r)
        if who.size == 0:
            continue
        for dy in range(-r, r + 1):
            row = cy[who] + dy
            inside = (row >= 0) & (row < side)
            who_row, row = who[inside], row[inside]
            x0 = np.maximum(cx[who_row] - r, 0)
            x1 = np.minimum(cx[who_row] + r, side - 1)
            lows.append(starts[row * side + x0])
            highs.append(starts[row * side + x1 + 1])
            owners.append(who_row)
    low, high, owner = np.concatenate(lows), np.concatenate(highs), np.concatenate(owners)
    arrange = np.argsort(owner, kind="stable")
    low, high, owner = low[arrange], high[arrange], owner[arrange]
    count = high - low
    animal_index = np.repeat(owner, count)
    inside_slice = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
    return animal_index, order[np.repeat(low, count) + inside_slice]


def nearest_by(
    group: np.ndarray, key: np.ndarray, ident: np.ndarray, groups: int
) -> tuple[np.ndarray, np.ndarray]:
    """For each group, the smallest ``key`` and, among equal keys, the smallest ``ident`` (inf and -1
    for a group with no members). Pairs may arrive in any order."""
    best = np.full(groups, np.inf)
    np.minimum.at(best, group, key)
    ties = key <= best[group]
    winner = np.full(groups, np.iinfo(np.int64).max, dtype=np.int64)
    np.minimum.at(winner, group[ties], ident[ties])
    winner[winner == np.iinfo(np.int64).max] = -1
    return best, winner


def sense_plants(w: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, int]:
    """Each animal's nearest plant seen within its field of view: surface gap and plant index."""
    ax, ay = w["ax"], w["ay"]
    ai, pj = candidate_pairs(ax, ay, w["reach"], w["px"], w["py"])
    dx, dy = w["px"][pj] - ax[ai], w["py"][pj] - ay[ai]
    dist = np.sqrt(dx * dx + dy * dy)
    surface = dist - w["body"][ai] - w["canopy"][pj]
    heading = w["heading"][ai]
    ahead = dx * np.cos(heading) + dy * np.sin(heading)
    seen = (surface <= w["reach"][ai]) & (ahead >= math.cos(SIGHT_HALF_FOV) * dist)
    keep = np.flatnonzero(seen)
    best, winner = nearest_by(ai[keep], surface[keep], pj[keep], ax.size)
    return best, winner, int(ai.size)


def classify_animals(w: dict[str, Any]) -> tuple[list[np.ndarray], int]:
    """Prey, threats and possible mates by mass ratio, and the nearest of each per animal."""
    ax, ay = w["ax"], w["ay"]
    ai, aj = candidate_pairs(ax, ay, w["reach"], ax, ay)
    other = ai != aj
    ai, aj = ai[other], aj[other]
    dx, dy = ax[aj] - ax[ai], ay[aj] - ay[ai]
    surface = np.sqrt(dx * dx + dy * dy) - w["body"][ai] - w["body"][aj]
    ratio = w["mass"][aj] / w["mass"][ai]
    near = surface <= w["reach"][ai]
    prey, threat = near & (ratio <= 0.8), near & (ratio >= 1.25)
    nearest = []
    for mask in (prey, threat, near & ~prey & ~threat):
        keep = np.flatnonzero(mask)
        nearest.append(nearest_by(ai[keep], surface[keep], aj[keep], ax.size)[0])
    return nearest, int(ai.size)


def make_brains(
    animals: int, rng: np.random.Generator, inputs: int = 28, hidden: int = 16, outputs: int = 6
):
    """Every animal's network at once: the 16 hidden slots of the genome, each switched by a gate."""
    w1 = rng.normal(size=(animals, hidden, inputs))
    b1 = rng.normal(size=(animals, hidden))
    w2 = rng.normal(size=(animals, hidden, outputs))
    b2 = rng.normal(size=(animals, outputs))
    gate = (rng.random((animals, hidden)) < 0.6).astype(float)
    x = rng.uniform(-1.0, 1.0, (animals, inputs))
    signed = np.array([True] * 3 + [False] * 3)

    def decide() -> np.ndarray:
        h = np.tanh(np.einsum("nhi,ni->nh", w1, x) + b1) * gate
        out = np.einsum("nho,nh->no", w2, h) + b2
        return np.where(signed, np.tanh(out), 0.5 * (1.0 + np.tanh(0.5 * out)))

    return decide


def make_plant_step(plants: int, rng: np.random.Generator):
    biomass = rng.uniform(1.0, 50.0, plants)
    biggest = rng.uniform(20.0, 100.0, plants)
    rate = rng.uniform(0.01, 0.1, plants)
    toxin = rng.uniform(0.0, 1.0, plants)
    age = rng.uniform(0.0, 500.0, plants)
    life = rng.uniform(100.0, 1000.0, plants)
    wait = rng.uniform(0.0, 100.0, plants)
    light = rng.uniform(0.2, 1.0, plants)
    soil = rng.uniform(0.2, 1.0, plants)

    def step() -> tuple[np.ndarray, ...]:
        gain = rate * biomass * (1.0 - biomass / biggest) * light * soil
        upkeep = 0.001 * biomass + 0.0005 * toxin**1.5 * biomass
        grown = np.clip(biomass + gain - upkeep, 0.0, biggest)
        older = age + 1.0
        dead = (grown <= 0.0) | (older > life)
        waited = np.maximum(wait - 1.0, 0.0)
        ready = (waited <= 0.0) & ~dead & (grown > 0.5 * biggest)
        return grown, older, dead, ready

    return step


def make_body_step(animals: int, rng: np.random.Generator):
    energy = rng.uniform(50.0, 100.0, animals)
    speed = rng.uniform(0.0, 1.0, animals)
    mass = rng.uniform(0.5, 4.0, animals)
    damage = rng.uniform(0.0, 10.0, animals)
    basal = rng.uniform(0.1, 0.5, animals)
    x, y = rng.uniform(0.0, SIZE, animals), rng.uniform(0.0, SIZE, animals)
    heading = rng.uniform(-3.0, 3.0, animals)
    turn = rng.uniform(-1.0, 1.0, animals)
    top = rng.uniform(1.0, 5.0, animals)

    def step() -> tuple[np.ndarray, ...]:
        vitality = np.maximum(0.0, 1.0 - damage / 100.0)
        current = top * (0.2 + 0.8 * vitality)
        burn = (speed * current / 3.0) ** 2 * 0.01 * mass
        left = energy - basal - burn
        facing = (heading - turn * 0.5 + math.pi) % (2.0 * math.pi) - math.pi
        run = speed * current
        return (
            left,
            facing,
            np.clip(x + np.cos(facing) * run, 0, SIZE),
            np.clip(y + np.sin(facing) * run, 0, SIZE),
            (left <= 0.0) | (vitality <= 0.0),
        )

    return step


def timed(function, repeat: int) -> tuple[float, Any]:
    result = function()
    start = time.perf_counter()
    for _ in range(repeat):
        result = function()
    return (time.perf_counter() - start) / repeat * 1000.0, result


def check_against_loops() -> None:
    """The nearest plant and the nearest prey, kernel against a plain double loop, 60 / 300."""
    w = make_world(60, 300, reach=50.0, seed=7)
    best, winner, _ = sense_plants(w)
    nearest, _ = classify_animals(w)
    for i in range(60):
        want, want_id = math.inf, -1
        for j in range(300):
            dx, dy = w["px"][j] - w["ax"][i], w["py"][j] - w["ay"][i]
            dist = math.hypot(dx, dy)
            surface = dist - w["body"][i] - w["canopy"][j]
            ahead = dx * math.cos(w["heading"][i]) + dy * math.sin(w["heading"][i])
            seen = surface <= w["reach"][i] and ahead >= math.cos(SIGHT_HALF_FOV) * dist
            if seen and (surface, j) < (want, want_id if want_id >= 0 else 10**9):
                want, want_id = surface, j
        assert winner[i] == want_id and (best[i] == want or abs(best[i] - want) < 1e-9), i
        prey = math.inf
        for j in range(60):
            if j == i:
                continue
            surface = (
                math.hypot(w["ax"][j] - w["ax"][i], w["ay"][j] - w["ay"][i])
                - w["body"][i]
                - w["body"][j]
            )
            if surface <= w["reach"][i] and w["mass"][j] / w["mass"][i] <= 0.8:
                prey = min(prey, surface)
        assert nearest[0][i] == prey or abs(nearest[0][i] - prey) < 1e-9, i
    print("kernels agree with a plain loop on 60 animals / 300 plants")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--reach", type=float, default=50.0, help="farthest sense (units)")
    args = parser.parse_args()
    check_against_loops()
    print(f"numpy {np.__version__}, farthest sense up to {args.reach:g}, cell {CELL:g}")
    print(
        f"{'animals/plants':>15} {'plant pairs':>12} {'sense plants':>13} {'animal pairs':>13} "
        f"{'sense animals':>14} {'brains':>8} {'plants':>8} {'bodies':>8}   all ms"
    )
    for animals, plants in ((60, 300), (300, 3000), (1000, 5000)):
        w = make_world(animals, plants, args.reach)
        t_plants, (_, _, plant_pairs) = timed(partial(sense_plants, w), args.repeat)
        t_animals, (_, animal_pairs) = timed(partial(classify_animals, w), args.repeat)
        t_brains, _ = timed(make_brains(animals, w["rng"]), args.repeat)
        t_plant_step, _ = timed(make_plant_step(plants, w["rng"]), args.repeat)
        t_body, _ = timed(make_body_step(animals, w["rng"]), args.repeat)
        total = t_plants + t_animals + t_brains + t_plant_step + t_body
        print(
            f"{animals:>7}/{plants:<7} {plant_pairs:>12} {t_plants:>12.2f}  {animal_pairs:>13} "
            f"{t_animals:>13.2f}  {t_brains:>8.2f} {t_plant_step:>8.2f} {t_body:>8.2f}   {total:>6.2f}"
        )


if __name__ == "__main__":
    main()
