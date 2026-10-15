"""Fit the seeded first-generation brain to the reference rule (BRAIN.9).

Offline tool, not part of the package: it needs numpy, which the simulator itself does not. It starts
from a network designed by hand (one neuron per idea, weights chosen from the genome's 16 levels, with
the brain's dead zone so a weight of -0.4 to 0.4 is off), moves single levels while the agreement with
``seed_brain.reference_rule`` rises, and writes the result into ``src/evolution_simulator/seed_brain.py``.
Training a network by gradient descent and rounding it does not work here: the 16 levels and the dead
zone throw away too much (97% before rounding, 45% after).

    python -m evolution_tools.fit_seed_brain            # print the result
    python -m evolution_tools.fit_seed_brain --write    # and rewrite the table in seed_brain.py

Rerun it when the inputs, the rule or the brain block change.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from evolution_simulator import seed_brain as sb
from evolution_simulator.brain import DEFAULT_SHAPE
from evolution_simulator.brain_adapter import ACTION_THRESHOLD, INPUT_NAMES
from evolution_simulator.config import DEFAULT_RULES

BRAIN_DEAD_ZONE = DEFAULT_RULES.brain.dead_zone

H = sb.SEED_HIDDEN
N_IN = DEFAULT_SHAPE.inputs
N_OUT = DEFAULT_SHAPE.outputs
STEP = 4.0 / (sb.LEVELS - 1)
LOW = -2.0


def values_of(levels: np.ndarray) -> np.ndarray:
    return LOW + levels * STEP


def effective(levels: np.ndarray) -> np.ndarray:
    v = values_of(levels)
    return np.where(np.abs(v) <= BRAIN_DEAD_ZONE, 0.0, v)


def dataset(count: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = random.Random(seed)
    xs, ts = [], []
    for _ in range(count):
        x = sb.sample_inputs(rng)
        xs.append(x)
        ts.append(sb.reference_rule(x))
    return np.array(xs), np.array(ts)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


class Net:
    """The seed as genome levels: w1 (H, N_IN), b1 (H), w2 (N_OUT, H), b2 (N_OUT)."""

    def __init__(self, w1, b1, w2, b2):
        self.w1, self.b1, self.w2, self.b2 = w1, b1, w2, b2

    def forward(self, x):
        gain = sb.SEED_GAIN
        h = np.tanh(gain * (x @ effective(self.w1).T + values_of(self.b1)))
        z = gain * (h @ effective(self.w2).T + values_of(self.b2))
        out = sigmoid(z)
        out[:, 0] = np.tanh(z[:, 0])
        return h, out


def agree_mask(out, t):
    steering = np.abs(t[:, 0]) > sb.STEERING
    turn = np.where(
        steering, out[:, 0] * t[:, 0] > 0, np.abs(out[:, 0] - t[:, 0]) <= sb.STEER_SLACK
    )
    ok = turn & (
        (speed_class(out[:, 1]) == speed_class(t[:, 1]))
        | (np.abs(out[:, 1] - t[:, 1]) <= sb.SPEED_SLACK)
    )
    for k in range(2, 6):
        ok &= (out[:, k] > ACTION_THRESHOLD) == (t[:, k] > ACTION_THRESHOLD)
    return ok


def speed_class(s):
    return np.where(s < sb.STILL_BELOW, 0, np.where(s < sb.RUNNING_FROM, 1, 2))


def snap(p):
    return np.clip(np.rint((p - LOW) / STEP), 0, sb.LEVELS - 1).astype(int)


def level(value):
    """The genome level nearest to a brain value."""
    return int(np.clip(np.rint((value - LOW) / STEP), 0, sb.LEVELS - 1))


def designed_net():
    """A readable starting point: one neuron per idea, with the weights chosen by hand.

    0 steering (pulls from plant and mate, push from a threat), 1 food or a mate sensed, 2 threat
    close, 3 a plant in reach, 4 ready to mate, 5 enough energy, 6 a plant close (slows the walk);
    7 spare. The outputs read them:
    turn from 0, speed from 1 and 2, eat from 3, seek mating from 4 and 5, the calls stay off.
    """
    idx = {name: i for i, name in enumerate(INPUT_NAMES)}
    zero = level(0.0)
    w1 = np.full((H, N_IN), zero)
    b1 = np.full(H, zero)
    w2 = np.full((N_OUT, H), zero)
    b2 = np.full(N_OUT, zero)
    w1[0, idx["plant_direction"]] = w1[0, idx["mate_direction"]] = level(0.667)
    w1[0, idx["threat_direction"]] = level(-2.0)
    w1[1, idx["plant_closeness"]] = w1[1, idx["mate_closeness"]] = level(2.0)
    b1[1] = level(-0.4)
    w1[2, idx["threat_closeness"]] = level(2.0)
    b1[2] = level(-0.133)
    w1[3, idx["plant_closeness"]] = level(1.867)
    b1[3] = level(-0.933)
    w1[4, idx["ready_to_mate"]] = level(1.867)
    b1[4] = level(-0.933)
    w1[5, idx["energy_ratio"]] = level(2.0)
    b1[5] = level(-1.2)
    w2[0, 0] = level(1.2)
    w2[1, 1] = level(0.667)
    w2[1, 2] = level(2.0)
    b2[1] = level(-0.29)
    w1[6, idx["plant_closeness"]] = level(0.667)
    w2[1, 6] = level(-0.667)
    w2[2, 3] = level(2.0)
    w2[3, 4] = w2[3, 5] = level(1.2)
    b2[3] = level(-1.2)
    b2[4] = b2[5] = level(-2.0)
    return Net(w1, b1, w2, b2)


def warm_net():
    """The table now in ``seed_brain.py`` as a ``Net`` of ``SEED_HIDDEN`` neurons, with the prey
    wiring added: prey pulls the steering neuron and the walk neuron like a plant, and the last
    neurons added since the table was fitted detect prey in reach, which eats."""
    idx = {name: i for i, name in enumerate(INPUT_NAMES)}
    zero = level(0.0)
    w1 = np.full((H, N_IN), zero)
    b1 = np.full(H, zero)
    w2 = np.full((N_OUT, H), zero)
    for j, slot in enumerate(sb.SEED_SLOTS):
        b1[j] = slot[0]
        w1[j] = slot[1 : 1 + N_IN]
        w2[:, j] = slot[1 + N_IN :]
    net = Net(w1, b1, w2, np.array(sb.SEED_OUTPUT_BIASES))
    fresh = len(sb.SEED_SLOTS)
    if fresh < H:
        net.w1[0, idx["prey_direction"]] = level(0.667)
        net.w1[1, idx["prey_closeness"]] = level(2.0)
        net.w1[fresh, idx["prey_closeness"]] = level(1.867)
        net.b1[fresh] = level(-0.933)
        net.w2[2, fresh] = level(2.0)
    # SENSE.14: the new inputs start neutral; young pull like a mate, the edge pushes like a threat.
    if net.w1[0, idx["young_direction"]] == zero:
        net.w1[0, idx["young_direction"]] = level(0.667)
        net.w1[1, idx["young_closeness"]] = level(1.733)
        net.w1[0, idx["edge_direction"]] = level(-1.2)
    return net


def score(net, x, t):
    return agree_mask(net.forward(x)[1], t).mean()


def greedy(net, x, t, best, sweeps=4):
    """Move single levels (up to 3 either way) while the agreement on ``x`` rises."""
    for _ in range(sweeps):
        improved = False
        for name in ("w1", "b1", "w2", "b2"):
            arr = getattr(net, name)
            for idx in np.ndindex(arr.shape):
                keep = arr[idx]
                chosen = keep
                for new in (keep - 3, keep - 2, keep - 1, keep + 1, keep + 2, keep + 3):
                    if not 0 <= new < sb.LEVELS:
                        continue
                    arr[idx] = new
                    s = score(net, x, t)
                    if s > best + 1e-9:
                        best, chosen, improved = s, new, True
                arr[idx] = chosen
        if not improved:
            break
    return best


def refine(net, x, t, seconds=240.0, seed=0):
    """Iterated local search: greedy level moves, then random kicks that are kept if they help."""
    rng = np.random.default_rng(seed)
    best = greedy(net, x, t, score(net, x, t))
    print(f"  greedy: agreement {best:.4f}", flush=True)
    started = time.time()
    arrays = [("w1", net.w1), ("b1", net.b1), ("w2", net.w2), ("b2", net.b2)]
    while time.time() - started < seconds:
        trial = Net(net.w1.copy(), net.b1.copy(), net.w2.copy(), net.b2.copy())
        for _ in range(int(rng.integers(2, 6))):
            name, arr = arrays[int(rng.integers(len(arrays)))]
            idx = tuple(int(rng.integers(n)) for n in arr.shape)
            getattr(trial, name)[idx] = int(
                np.clip(getattr(trial, name)[idx] + rng.integers(-4, 5), 0, sb.LEVELS - 1)
            )
        got = greedy(trial, x, t, score(trial, x, t), sweeps=3)
        if got > best + 1e-9:
            best = got
            net.w1, net.b1, net.w2, net.b2 = trial.w1, trial.b1, trial.w2, trial.b2
            arrays = [("w1", net.w1), ("b1", net.b1), ("w2", net.w2), ("b2", net.b2)]
            print(
                f"  kick kept: agreement {best:.4f} after {time.time() - started:.0f}s", flush=True
            )
    return net


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--seconds", type=float, default=240.0, help="search time")
    parser.add_argument("--seed", type=int, default=0, help="seed of the search's random kicks")
    parser.add_argument(
        "--warm",
        action="store_true",
        help="start from the table now in seed_brain.py (padded and given prey) and not from the "
        "hand-designed network",
    )
    args = parser.parse_args()
    x, t = dataset(6000, 1)
    xv, tv = dataset(8000, 2)
    best = warm_net() if args.warm else designed_net()
    print(f"designed: train {score(best, x, t):.4f}, held out {score(best, xv, tv):.4f}")
    best = refine(best, x, t, args.seconds, args.seed)
    print(f"refined: train {score(best, x, t):.4f}, held out {score(best, xv, tv):.4f}")
    slots = tuple(
        tuple(int(v) for v in (best.b1[j], *best.w1[j], *best.w2[:, j])) for j in range(H)
    )
    biases = tuple(int(v) for v in best.b2)
    block = f"SEED_SLOTS: tuple[tuple[int, ...], ...] = {slots!r}\nSEED_OUTPUT_BIASES: tuple[int, ...] = {biases!r}\n"
    print(block)
    if args.write:
        path = ROOT / "src/evolution_simulator/seed_brain.py"
        text = path.read_text()
        text = re.sub(
            r"(# fitted: begin\n).*?(# fitted: end)",
            lambda m: m.group(1) + block + m.group(2),
            text,
            flags=re.DOTALL,
        )
        path.write_text(text)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
