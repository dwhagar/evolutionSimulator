"""A copy of a recorder's history kept somewhere else (``UX.31``).

The simulation process owns the ``Recorder``. It tells the viewer the history once in full and then
sends each new single-period sample as it is taken; ``HistoryMirror`` keeps the viewer's copy by
merging those into the same ring buffers the recorder uses (``push_sample``), so after any number of
samples the mirror's ``history()`` is equal to the recorder's. If a sample is ever missed, a new full
history (``reset``) puts it right.
"""

from __future__ import annotations

from collections.abc import Iterable

from evolution_simulator.history.recorder import RecorderRules, push_sample
from evolution_simulator.history.samples import HistorySamples, Sample, Tier


class HistoryMirror:
    def __init__(self) -> None:
        self._rules: RecorderRules | None = None
        self._tiers: list[list[Sample]] = []

    @property
    def ready(self) -> bool:
        """Whether a full history has been taken in (samples cannot be pushed before that)."""
        return self._rules is not None

    def reset(self, rules: RecorderRules, history: HistorySamples) -> None:
        """Replace everything with a full history taken under ``rules``."""
        if len(history.tiers) != len(rules.tiers):
            raise ValueError("The history's tiers do not match the recorder rules.")
        self._rules = rules
        self._tiers = [list(tier.samples) for tier in history.tiers]

    def push(self, samples: Iterable[Sample]) -> None:
        """Take in new single-period samples, oldest first."""
        if self._rules is None:
            raise ValueError("A mirror needs a full history before it can take new samples.")
        for sample in samples:
            push_sample(self._tiers, self._rules.tiers, 0, sample)

    def history(self) -> HistorySamples:
        """What the mirror holds, as the same immutable value the recorder gives."""
        if self._rules is None:
            raise ValueError("A mirror has no history until it has been given one.")
        return HistorySamples(
            self._rules.period_seconds,
            tuple(
                Tier(rule.name, rule.periods, tuple(samples))
                for rule, samples in zip(self._rules.tiers, self._tiers, strict=True)
            ),
        )
