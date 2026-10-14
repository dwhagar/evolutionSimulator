"""Learning during life (BRAIN.24, design note ``docs/design/brain-learning.md``).

By day a creature logs what its brain did and how things turned out; at night (when it falls asleep,
``WORLD.5``) the log is turned into small changes to the brain's output layer, and the log is
emptied. The changes are kept as **offsets** on the creature, never written to its DNA, and are
lost when it dies (owner answer to question 5 of issue 36).

Nothing here knows about the world or the traits: ``Learner`` is told the creature's state each tick
(``State``) and each decision (``record``), and ``nightly_update`` is a pure function. The pieces:

* ``LearningRules``: the log size, the reward window and weights, the cap on one night's change.
  Starting values from the design note to calibrate (``TRAIT.3``, ``WORLD.2``).
* ``reward``: a weighted sum of what happened over the window after a decision (energy gained,
  health lost, matings, a threat falling away), minus the usual level at night.
* ``nightly_update``: ``eta * (reward - usual) * (action - proposal) * hidden`` summed over the
  day's snapshots, each number moved by no more than the cap.
* ``Learner``: one creature's log and offsets.
* ``NightlyLearning``: the sleep listener that runs the update when an animal falls asleep.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evolution_simulator.world.organisms import Animal
    from evolution_simulator.world.world import World


@dataclass(frozen=True)
class LearningRules:
    """The world's settings for learning; move into the constants config with ``TRAIT.3``."""

    log_size: int = 64
    """Decisions kept in the day log; the oldest are dropped when it is full."""
    reward_window: int = 10
    """Ticks after a decision over which its outcome is counted."""
    energy_weight: float = 1.0
    """Reward per unit of energy-store fraction gained (a fall counts against)."""
    health_weight: float = 2.0
    """Penalty per unit of damage-capacity fraction lost."""
    mating_weight: float = 1.0
    """Reward for each mating achieved."""
    safety_weight: float = 0.5
    """Reward per unit that the threat input falls after a threat was sensed."""
    night_cap: float = 0.5
    """The most any one number may change in one night (an eighth of a weight's range)."""
    fade: float = 0.0
    """Share of the learned offsets lost each night (forgetting); off by default."""
    max_offset: float = 2.0
    """The most a number's total learned change may reach, so repeated nights cannot run away."""

    def __post_init__(self) -> None:
        if self.log_size < 1 or self.reward_window < 1:
            raise ValueError("log_size and reward_window must be at least 1.")
        for name in ("energy_weight", "health_weight", "mating_weight", "safety_weight"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be a finite number.")
        for name in ("night_cap", "max_offset"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0.0):
                raise ValueError(f"{name} must be zero or more, got {value}.")
        if not 0.0 <= self.fade <= 1.0:
            raise ValueError(f"fade must be between 0 and 1, got {self.fade}.")


@dataclass(frozen=True)
class State:
    """What reward is made from, sampled once per tick."""

    energy: float
    """Energy as a fraction of the store."""
    damage: float
    """Health lost so far in life, as a fraction of damage capacity (only ever rises)."""
    matings: int
    """Matings achieved so far in life."""
    threat: float
    """The threat-closeness input right now."""


def reward(start: State, end: State, rules: LearningRules) -> float:
    """The outcome of the window from ``start`` to ``end``: outcomes, not actions."""
    safety = max(0.0, start.threat - end.threat)
    return (
        rules.energy_weight * (end.energy - start.energy)
        - rules.health_weight * (end.damage - start.damage)
        + rules.mating_weight * (end.matings - start.matings)
        + rules.safety_weight * safety
    )


@dataclass(frozen=True)
class Snapshot:
    """One logged decision: what the hidden neurons did, what the brain proposed, what was done
    (the proposal plus curiosity noise) and, once known, the reward."""

    hidden: tuple[float, ...]
    proposal: tuple[float, ...]
    action: tuple[float, ...]
    reward: float


Offsets = tuple[tuple[tuple[float, ...], ...], tuple[float, ...]]
"""Learned changes: ``(weights[output][hidden], biases[output])``."""


def zero_offsets(hidden: int, outputs: int) -> Offsets:
    return ((((0.0,) * hidden),) * outputs, (0.0,) * outputs)


def nightly_update(
    offsets: Offsets,
    snapshots: Sequence[Snapshot],
    eta: float,
    rules: LearningRules,
) -> Offsets:
    """The offsets after one night of reward-weighted learning on the output layer.

    The offsets first fade by ``rules.fade``; then for each output weight and bias the night's
    change (``eta`` times reward above the day's average, times how far the action went past the
    proposal, times the hidden activation, summed over the log) is capped at ``rules.night_cap`` and
    added; the total learned change is capped at ``rules.max_offset``. With no snapshots, a zero
    ``eta`` or no curiosity noise in the log, nothing changes (apart from fading).
    """
    weights, biases = offsets
    keep = 1.0 - rules.fade
    new_w = [[w * keep for w in row] for row in weights]
    new_b = [b * keep for b in biases]
    if snapshots and eta > 0.0:
        usual = statistics.fmean(s.reward for s in snapshots)
        dw = [[0.0] * len(row) for row in weights]
        db = [0.0] * len(biases)
        for snap in snapshots:
            for k, (proposed, acted) in enumerate(zip(snap.proposal, snap.action, strict=True)):
                g = eta * (snap.reward - usual) * (acted - proposed)
                if g == 0.0:
                    continue
                db[k] += g
                row = dw[k]
                for j, h in enumerate(snap.hidden):
                    row[j] += g * h
        cap, top = rules.night_cap, rules.max_offset

        def move(old: float, change: float) -> float:
            return max(-top, min(top, old + max(-cap, min(cap, change))))

        new_w = [[move(w, d) for w, d in zip(r, dr, strict=True)] for r, dr in zip(new_w, dw)]
        new_b = [move(b, d) for b, d in zip(new_b, db, strict=True)]
    return tuple(tuple(row) for row in new_w), tuple(new_b)


_Open = tuple[int, State, tuple[float, ...], tuple[float, ...], tuple[float, ...]]
"""A decision whose window is still open: tick, state, hidden, proposal, action."""


class Learner:
    """One creature's day log and learned offsets."""

    def __init__(self, hidden: int, outputs: int, rules: LearningRules) -> None:
        self.rules = rules
        self.offsets: Offsets = zero_offsets(hidden, outputs)
        self._tick = 0
        self._pending: deque[_Open] = deque()
        self._log: deque[Snapshot] = deque(maxlen=rules.log_size)

    @property
    def log(self) -> tuple[Snapshot, ...]:
        """The decisions whose reward is known, oldest first."""
        return tuple(self._log)

    @property
    def open_decisions(self) -> int:
        return len(self._pending)

    def observe(self, state: State) -> None:
        """Note the creature's state at the start of a tick; closes decisions whose window ended."""
        self._tick += 1
        window = self.rules.reward_window
        while self._pending and self._tick - self._pending[0][0] >= window:
            self._close(state)

    def record(
        self,
        state: State,
        hidden: Sequence[float],
        proposal: Sequence[float],
        action: Sequence[float],
    ) -> None:
        """Log a decision made in ``state`` (call after ``observe`` for the same tick)."""
        self._pending.append((self._tick, state, tuple(hidden), tuple(proposal), tuple(action)))

    def _close(self, end: State) -> None:
        _, start, hidden, proposal, action = self._pending.popleft()
        self._log.append(Snapshot(hidden, proposal, action, reward(start, end, self.rules)))

    def sleep(self, state: State, eta: float) -> bool:
        """The nightly step: close the open decisions on what has happened so far, learn from the
        day's log, empty it. Returns whether any offset changed."""
        while self._pending:
            self._close(state)
        before = self.offsets
        self.offsets = nightly_update(self.offsets, self.log, eta, self.rules)
        self._log.clear()
        return self.offsets != before


class NightlyLearning:
    """Sleep listener: an animal that falls asleep learns from its day (``World.add_sleep_listener``)."""

    def fell_asleep(self, world: World, animal: Animal) -> None:
        animal.traits.learn_night()

    def woke(self, world: World, animal: Animal) -> None:
        return None
