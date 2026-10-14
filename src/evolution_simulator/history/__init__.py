"""History (``UX.8``): the statistics recorder and the samples it keeps.

``Recorder(world)`` samples a running world once per simulated day into bounded, merging ring
buffers; ``recorder.history()`` is a ``HistorySamples`` that a viewer reads. No window code, no
dependencies. See ``recorder.py``.
"""

from evolution_simulator.history.recorder import (
    DEFAULT_TIERS,
    Observable,
    Recorder,
    RecorderRules,
    TierRule,
    load_history_data,
    save_history,
)
from evolution_simulator.history.samples import (
    HISTORY_FORMAT,
    HistorySamples,
    Sample,
    Stat,
    Tier,
    is_flow,
)

__all__ = [
    "DEFAULT_TIERS",
    "HISTORY_FORMAT",
    "HistorySamples",
    "Observable",
    "Recorder",
    "RecorderRules",
    "Sample",
    "Stat",
    "Tier",
    "TierRule",
    "is_flow",
    "load_history_data",
    "save_history",
]
