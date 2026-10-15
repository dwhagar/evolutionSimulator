"""Saved runs (``UX.10``, ``STORE.2``): a folder per run holding one SQLite file with a manifest,
checkpoints and the recorded history.

``RunStore(folder).create(world, recorder=recorder)`` starts a run, ``run.autosave(world, recorder)``
checkpoints it as it goes, ``store.list_runs()`` lists every run and ``run.resume()`` brings the
newest checkpoint back as a world and recorder that carry on exactly as an uninterrupted run would.
See ``store.py`` and docs/design/storage.md. No window code and no dependencies.
"""

from evolution_simulator.runs.errors import RunError
from evolution_simulator.runs.paths import default_runs_root
from evolution_simulator.runs.store import (
    RUN_FORMAT,
    Autosaver,
    CheckpointInfo,
    Resumed,
    Run,
    RunStore,
    RunStoreRules,
    RunSummary,
)

__all__ = [
    "RUN_FORMAT",
    "Autosaver",
    "CheckpointInfo",
    "Resumed",
    "Run",
    "RunError",
    "RunStore",
    "RunStoreRules",
    "RunSummary",
    "default_runs_root",
]
