"""Fit the seeded first-generation brain to the reference rule (BRAIN.9).

Offline tool, not part of the package: it needs numpy, which the simulator itself does not. It starts
from a network designed by hand (one neuron per idea, weights chosen from the genome's 16 levels, with
the brain's dead zone so a weight of -0.4 to 0.4 is off), moves single levels while the agreement with
``seed_brain.reference_rule`` rises, and writes the result into ``src/evolution_simulator/seed_brain.py``.
Training a network by gradient descent and rounding it does not work here: the 16 levels and the dead
zone throw away too much (97% before rounding, 45% after).

    python -m evolution_tools.fit_seed_brain --warm --seconds 600     # print the result
    python -m evolution_tools.fit_seed_brain --warm --write           # and rewrite the table
    python -m evolution_tools.fit_seed_brain --report-only            # how sturdy is the table

Rerun it when the inputs, the rule or the brain block change.

Sturdiness (BRAIN.25). A founder is the seed with a few weights or biases moved one level
(``seeded_dna``), so the search maximises the agreement less ``--robust`` times the *fragility*: the
mean, over every single one-level mutation, of the agreement lost beyond ``SMALL_LOSS``
(``mutation_losses`` computes the whole set in a few batched passes), less ``--sparsity`` per weight
that is switched on. After the greedy sweeps, ``--anneal SECONDS`` runs simulated annealing whose
kicks go to the parameters whose mutation costs most and move related weights with them (the
cliffs are sums of terms that cancel). The report prints, on held-out data, the share of single
mutations and of simulated founders that lose more than 10% and 25% of their agreement.
"""

from __future__ import annotations

import argparse
import ast
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
    """Which samples agree; ``out`` may have extra leading axes after the sample one (mutations),
    ``t`` is then broadcast against it."""
    steering = np.abs(t[..., 0]) > sb.STEERING
    turn = np.where(
        steering, out[..., 0] * t[..., 0] > 0, np.abs(out[..., 0] - t[..., 0]) <= sb.STEER_SLACK
    )
    ok = turn & (
        (speed_class(out[..., 1]) == speed_class(t[..., 1]))
        | (np.abs(out[..., 1] - t[..., 1]) <= sb.SPEED_SLACK)
    )
    for k in range(2, 6):
        ok &= (out[..., k] > ACTION_THRESHOLD) == (t[..., k] > ACTION_THRESHOLD)
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
    """The table now in ``seed_brain.py`` as a ``Net`` of ``SEED_HIDDEN`` neurons. When the table has
    fewer neurons than ``SEED_HIDDEN`` the new ones are added with the prey wiring: prey pulls the
    steering neuron and the walk neuron like a plant, and the last neurons detect prey in reach,
    which eats."""
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
    return net


def _outputs(z):
    """The six outputs from the output sums ``z`` (any leading shape)."""
    out = sigmoid(z)
    out[..., 0] = np.tanh(z[..., 0])
    return out


def mutation_losses(net, x, t):
    """Agreement lost under every single one-level mutation a founder can get (``seeded_dna``).

    A founder moves ``variation`` weights or biases of the seeded neurons, and the output biases, one
    level up or down (not past the ends of the 16 levels, where the move does nothing). Returns the
    base agreement and an array of shape (parameters, 2) holding, for each parameter and each
    direction (down, up), the agreement lost; parameters run w1 (H, N_IN), b1 (H), w2 (N_OUT, H),
    b2 (N_OUT) in that order, flattened. The sums of the network are updated instead of rebuilt, so
    the whole set costs a few batched passes.
    """
    gain = sb.SEED_GAIN
    n = len(x)
    ew1, ew2 = effective(net.w1), effective(net.w2)
    v1, v2 = values_of(net.b1), values_of(net.b2)
    pre = x @ ew1.T + v1  # (n, H)
    hid = np.tanh(gain * pre)
    z = gain * (hid @ ew2.T + v2)  # (n, N_OUT)
    base = float(agree_mask(_outputs(z), t).mean())
    steps = np.array([-1, 1])

    def moved(levels, to_effective):
        """Change in a value for each parameter and direction, 0 where the level cannot move."""
        new = np.clip(levels[..., None] + steps, 0, sb.LEVELS - 1)
        values = values_of if not to_effective else effective
        return values(new) - values(levels)[..., None]

    d_w1 = moved(net.w1, True)  # (H, N_IN, 2)
    d_b1 = moved(net.b1, False)  # (H, 2)
    d_w2 = moved(net.w2, True)  # (N_OUT, H, 2)
    d_b2 = moved(net.b2, False)  # (N_OUT, 2)
    t3 = t[:, None, :]
    lost_w1 = np.zeros((H, N_IN, 2))
    lost_b1 = np.zeros((H, 2))
    for j in range(H):
        # Hidden neuron j changes: its new activation moves every output sum by gain * dh * w2.
        pre_new = np.concatenate(
            [
                (pre[:, j, None, None] + x[:, :, None] * d_w1[j]).reshape(n, -1),
                pre[:, j, None] + d_b1[j],
            ],
            axis=1,
        )
        dh = np.tanh(gain * pre_new) - hid[:, j, None]  # (n, N_IN * 2 + 2)
        z_new = z[:, None, :] + gain * dh[:, :, None] * ew2[:, j][None, None, :]
        ok = agree_mask(_outputs(z_new), t3).mean(axis=0)
        lost_w1[j] = (base - ok[: N_IN * 2]).reshape(N_IN, 2)
        lost_b1[j] = base - ok[N_IN * 2 :]
    # Output weights: only the sum of the one output changes.
    lost_w2 = np.zeros((N_OUT, H, 2))
    for k in range(N_OUT):
        z_new = np.repeat(z[:, None, :], H * 2, axis=1)
        z_new[:, :, k] += gain * (hid[:, :, None] * d_w2[k][None]).reshape(n, -1)
        lost_w2[k] = (base - agree_mask(_outputs(z_new), t3).mean(axis=0)).reshape(H, 2)
    lost_b2 = np.zeros((N_OUT, 2))
    for k in range(N_OUT):
        z_new = np.repeat(z[:, None, :], 2, axis=1)
        z_new[:, :, k] += gain * d_b2[k][None]
        lost_b2[k] = base - agree_mask(_outputs(z_new), t3).mean(axis=0)
    flat = np.concatenate(
        [lost_w1.reshape(-1, 2), lost_b1, lost_w2.reshape(-1, 2), lost_b2], axis=0
    )
    return base, flat


# What counts as a bad mutation, and how the fit weighs them.
SMALL_LOSS = 0.02
"""A mutation that costs less agreement than this is harmless and is not penalised."""
ROBUST_WEIGHT = 2.0
"""Default weight of the penalty against the agreement itself (both are shares from 0 to 1). The
fragility of the table before BRAIN.25 was 0.0049, so at 2 removing all of it is worth a point of
agreement."""
MAX_COST = 0.01
"""A move that costs more agreement than this is not tried against the (slower) fragility."""


def fragility(losses):
    """The penalty on a network: the average over all single mutations of the loss beyond
    ``SMALL_LOSS``, so a cliff counts for what it costs and a ripple counts for nothing."""
    return float(np.maximum(losses - SMALL_LOSS, 0.0).mean())


def fitness(net, x, t, xr, tr, weight):
    """What the search maximises: the agreement on ``x`` less ``weight`` times the fragility
    measured on the (smaller) set ``xr``."""
    agreement = score(net, x, t)
    if weight == 0.0:
        return agreement
    return agreement - weight * fragility(mutation_losses(net, xr, tr)[1])


def founder_losses(net, x, t, founders=2000, seed=0, variation=3.0):
    """Agreement lost by simulated founders: the net with ``variation`` random one-level moves, as
    ``seeded_dna`` makes them. Returns the base agreement and the loss of each founder."""
    rng = np.random.default_rng(seed)
    base = score(net, x, t)
    names = ("w1", "b1", "w2", "b2")
    sizes = [getattr(net, name).size for name in names]
    losses = []
    for _ in range(founders):
        trial = Net(net.w1.copy(), net.b1.copy(), net.w2.copy(), net.b2.copy())
        for flat in rng.choice(sum(sizes), size=int(variation), replace=False):
            which = int(np.searchsorted(np.cumsum(sizes), flat, side="right"))
            offset = int(flat - sum(sizes[:which]))
            arr = getattr(trial, names[which])
            index = np.unravel_index(offset, arr.shape)
            arr[index] = int(np.clip(arr[index] + rng.choice((-1, 1)), 0, sb.LEVELS - 1))
        losses.append(base - score(trial, x, t))
    return base, np.array(losses)


def report(label, net, x, t, xv, tv):
    """Print how fragile a net is: single mutations and simulated founders, on held-out data."""
    base, flat = mutation_losses(net, xv, tv)
    _, fl = founder_losses(net, xv, tv)
    print(
        f"{label}: agreement {base:.4f}; single mutations losing >2%/>10%/>25%: "
        f"{(flat > 0.02).mean():.1%}/{(flat > 0.10).mean():.1%}/{(flat > 0.25).mean():.1%}, "
        f"worst {flat.max():.3f}; founders (3 moves) losing >10%/>25%: "
        f"{(fl > 0.10).mean():.1%}/{(fl > 0.25).mean():.1%}, mean loss {fl.mean():.3f}, "
        f"worst {fl.max():.3f}",
        flush=True,
    )


def score(net, x, t):
    return agree_mask(net.forward(x)[1], t).mean()


SPARSITY = 2e-5
"""Fitness lost for each weight that is switched on (outside the dead zone). It breaks ties in favour
of a tidy table, so a weight that does nothing useful is left off instead of drifting to a value
that happens to cancel something else. The fit once gave the always-off call outputs a dozen
large weights; each is one more way for a descendant's mutation to start a call."""


def active_weights(net):
    """How many weights are switched on."""
    return int((effective(net.w1) != 0).sum() + (effective(net.w2) != 0).sum())


class Objective:
    """The agreement on the training set, less the weighted fragility when ``weight`` is above 0,
    less ``SPARSITY`` per active weight.

    Moves that lose more than ``max_cost`` of agreement are refused without measuring fragility,
    which is the slow part."""

    def __init__(self, x, t, xr, tr, weight, max_cost=MAX_COST, sparsity=SPARSITY):
        self.x, self.t, self.xr, self.tr = x, t, xr, tr
        self.weight, self.max_cost, self.sparsity = weight, max_cost, sparsity
        self.agreement_floor: float | None = None

    def agreement(self, net):
        return score(net, self.x, self.t)

    def __call__(self, net, floor=None):
        """The fitness; ``None`` if the agreement is below ``floor`` (so it cannot win)."""
        agreement = self.agreement(net)
        if floor is not None and agreement < floor:
            return None
        fit = agreement - self.sparsity * active_weights(net)
        if self.weight == 0.0:
            return fit
        return fit - self.weight * fragility(mutation_losses(net, self.xr, self.tr)[1])


def greedy(net, objective, best, sweeps=4, deadline=None):
    """Move single levels (up to 3 either way) while the fitness rises, until ``deadline``."""
    for sweep in range(sweeps):
        improved = False
        for name in ("w1", "b1", "w2", "b2"):
            arr = getattr(net, name)
            for idx in np.ndindex(arr.shape):
                if deadline is not None and time.time() > deadline:
                    return best
                keep = arr[idx]
                chosen = keep
                for new in (keep - 3, keep - 2, keep - 1, keep + 1, keep + 2, keep + 3):
                    if not 0 <= new < sb.LEVELS:
                        continue
                    arr[idx] = new
                    s = objective(net, objective.agreement_floor)
                    if s is not None and s > best + 1e-9:
                        best, chosen, improved = s, new, True
                        objective.agreement_floor = objective.agreement(net) - objective.max_cost
                arr[idx] = chosen
        print(f"  sweep {sweep + 1}: fitness {best:.4f}", flush=True)
        if not improved:
            break
    return best


def refine(net, objective, seconds=240.0, seed=0):
    """Iterated local search: greedy level moves, then random kicks that are kept if they help."""
    rng = np.random.default_rng(seed)
    objective.agreement_floor = objective.agreement(net) - objective.max_cost
    started = time.time()
    best = greedy(net, objective, objective(net), deadline=started + seconds)
    print(f"  greedy: fitness {best:.4f}, agreement {objective.agreement(net):.4f}", flush=True)
    arrays = [("w1", net.w1), ("b1", net.b1), ("w2", net.w2), ("b2", net.b2)]
    while time.time() - started < seconds:
        trial = Net(net.w1.copy(), net.b1.copy(), net.w2.copy(), net.b2.copy())
        for _ in range(int(rng.integers(2, 6))):
            name, arr = arrays[int(rng.integers(len(arrays)))]
            idx = tuple(int(rng.integers(n)) for n in arr.shape)
            getattr(trial, name)[idx] = int(
                np.clip(getattr(trial, name)[idx] + rng.integers(-4, 5), 0, sb.LEVELS - 1)
            )
        objective.agreement_floor = objective.agreement(trial) - objective.max_cost
        start = objective(trial)
        got = greedy(trial, objective, start, sweeps=3)
        if got > best + 1e-9:
            best = got
            net.w1, net.b1, net.w2, net.b2 = trial.w1, trial.b1, trial.w2, trial.b2
            arrays = [("w1", net.w1), ("b1", net.b1), ("w2", net.w2), ("b2", net.b2)]
            print(
                f"  kick kept: fitness {best:.4f}, agreement {objective.agreement(net):.4f} "
                f"after {time.time() - started:.0f}s",
                flush=True,
            )
    return net


def parameter_list(net):
    """Every weight and bias as (array name, index), in the order ``mutation_losses`` reports."""
    return [
        (name, idx)
        for name in ("w1", "b1", "w2", "b2")
        for idx in np.ndindex(getattr(net, name).shape)
    ]


def related(net, name, idx, params):
    """Parameters that work with ``(name, idx)``: those of the same neuron, the weights into the
    same output and that output's bias. A cliff is usually a sum of a few such terms that cancel,
    so a move that fixes one has to shift another with it."""
    if name in ("w1", "b1"):
        hidden = idx[0]
        return [p for p in params if p[0] in ("w1", "b1") and p[1][0] == hidden] + [
            p for p in params if p[0] == "w2" and p[1][1] == hidden
        ]
    if name == "w2":
        out, hidden = idx
        return (
            [p for p in params if p[0] == "w2" and p[1][0] == out]
            + [("b2", (out,))]
            + [p for p in params if p[0] in ("w1", "b1") and p[1][0] == hidden]
        )
    out = idx[0]
    return [p for p in params if p[0] == "w2" and p[1][0] == out]


def anneal(net, objective, seconds, seed=0, start_temperature=0.002):
    """Simulated annealing on the fitness, with kicks aimed at the cliffs.

    Each step picks a parameter whose one-level mutation costs the most agreement (chosen in
    proportion to the square of that cost), moves it by 1 to 3 levels, usually moves one or two
    related parameters with it, and keeps the result if the fitness rose or, with the chance the
    temperature allows, if it fell a little. The temperature falls to zero over the time given. The
    best net seen is returned."""
    rng = np.random.default_rng(seed)
    params = parameter_list(net)
    started = time.time()
    current = Net(net.w1.copy(), net.b1.copy(), net.w2.copy(), net.b2.copy())
    fit = objective(current)
    best_net, best_fit = current, fit
    refresh_at, weights, steps, kept = 0, None, 0, 0
    while time.time() - started < seconds:
        if steps >= refresh_at:
            losses = mutation_losses(current, objective.xr, objective.tr)[1].max(axis=1)
            weights = losses**2 + 1e-4
            weights = weights / weights.sum()
            refresh_at = steps + 25
        steps += 1
        temperature = start_temperature * (1.0 - (time.time() - started) / seconds)
        trial = Net(current.w1.copy(), current.b1.copy(), current.w2.copy(), current.b2.copy())
        pivot = params[int(rng.choice(len(params), p=weights))]
        chosen = [pivot]
        pool = related(trial, *pivot, params)
        for _ in range(int(rng.integers(0, 3))):
            chosen.append(pool[int(rng.integers(len(pool)))])
        for name, idx in chosen:
            arr = getattr(trial, name)
            delta = int(rng.choice((-3, -2, -1, 1, 2, 3)))
            arr[idx] = int(np.clip(arr[idx] + delta, 0, sb.LEVELS - 1))
        floor = objective.agreement(current) - objective.max_cost
        new = objective(trial, floor)
        if new is None:
            continue
        if new > fit or rng.random() < np.exp((new - fit) / max(temperature, 1e-9)):
            current, fit, kept = trial, new, kept + 1
            if fit > best_fit + 1e-9:
                best_net, best_fit = current, fit
                print(
                    f"  anneal: fitness {best_fit:.4f}, agreement "
                    f"{objective.agreement(best_net):.4f} after {time.time() - started:.0f}s "
                    f"({steps} steps)",
                    flush=True,
                )
    print(f"  anneal: {steps} steps, {kept} kept", flush=True)
    net.w1, net.b1, net.w2, net.b2 = best_net.w1, best_net.b1, best_net.w2, best_net.b2
    return net


def table_net(path):
    """A ``Net`` read from the ``SEED_SLOTS`` and ``SEED_OUTPUT_BIASES`` lines in a text file (the
    output of an earlier run, or ``seed_brain.py``)."""
    text = Path(path).read_text()
    slots = ast.literal_eval(re.search(r"SEED_SLOTS: [^=]*= (\(.*\))\n", text).group(1))
    biases = ast.literal_eval(re.search(r"SEED_OUTPUT_BIASES: [^=]*= (\(.*\))\n", text).group(1))
    w1 = np.array([slot[1 : 1 + N_IN] for slot in slots])
    b1 = np.array([slot[0] for slot in slots])
    w2 = np.array([slot[1 + N_IN :] for slot in slots]).T
    return Net(w1, b1, w2, np.array(biases))


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
    parser.add_argument(
        "--robust",
        type=float,
        default=ROBUST_WEIGHT,
        help="weight of the fragility penalty (BRAIN.25); 0 fits the agreement alone",
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        default=MAX_COST,
        help="a move losing more agreement than this is not weighed against the fragility",
    )
    parser.add_argument(
        "--anneal",
        type=float,
        default=0.0,
        help="seconds of simulated annealing with kicks aimed at the cliffs, after the greedy "
        "sweeps (BRAIN.25)",
    )
    parser.add_argument(
        "--sparsity",
        type=float,
        default=SPARSITY,
        help="fitness lost for each weight that is switched on",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.002,
        help="starting temperature of the annealing, in fitness (a worse net is kept with "
        "chance exp(-loss / temperature))",
    )
    parser.add_argument(
        "--start", help="start from the table in this file (an earlier run's output)"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="only report how fragile the table in seed_brain.py is, and exit",
    )
    args = parser.parse_args()
    x, t = dataset(6000, 1)
    xv, tv = dataset(8000, 2)
    xr, tr = dataset(1500, 3)
    best = warm_net() if args.warm or args.report_only else designed_net()
    if args.start:
        best = table_net(args.start)
    if args.report_only:
        report("table", best, x, t, xv, tv)
        return
    print(f"designed: train {score(best, x, t):.4f}, held out {score(best, xv, tv):.4f}")
    report("start", best, x, t, xv, tv)
    objective = Objective(x, t, xr, tr, args.robust, args.max_cost, args.sparsity)
    if args.seconds > 0:
        best = refine(best, objective, args.seconds, args.seed)
    if args.anneal > 0:
        best = anneal(best, objective, args.anneal, args.seed, args.temperature)
    print(f"refined: train {score(best, x, t):.4f}, held out {score(best, xv, tv):.4f}")
    report("refined", best, x, t, xv, tv)
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
