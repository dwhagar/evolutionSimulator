"""Helpers for tests that reach into a run's file, to damage it or look at what it holds."""

from __future__ import annotations

import sqlite3
from contextlib import closing


def damage_checkpoint(run, tick: int, blob: bytes = b"not a world") -> None:
    """Overwrite the world of the checkpoint at ``tick`` with ``blob``."""
    with closing(sqlite3.connect(run.file_path)) as db, db:
        db.execute(
            "UPDATE checkpoint_data SET world = ? "
            "WHERE id = (SELECT id FROM checkpoints WHERE tick = ?)",
            (blob, tick),
        )


def remove_checkpoints(run) -> None:
    """Take every checkpoint out of the run's file."""
    with closing(sqlite3.connect(run.file_path)) as db, db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM checkpoints")


def table_count(run, table: str) -> int:
    with closing(sqlite3.connect(run.file_path)) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def make_legacy_run(root, world, recorder=None, name: str = "old") -> str:
    """A run in the folder layout of the first version (run.json, history.json.gz and a folder per
    checkpoint with meta.json, world.json.gz, history.json.gz), written the way it wrote them."""
    import json

    from evolution_simulator.history import save_history
    from evolution_simulator.world.persistence import config_to_dict, save_world

    run_id = f"20231114-221320-{name}"
    folder = root / run_id
    checkpoint = folder / "checkpoints" / f"checkpoint-{world.tick:012d}"
    checkpoint.mkdir(parents=True)
    save_world(world, checkpoint / "world.json.gz")
    if recorder is not None:
        recorder.observe()
        save_history(recorder, checkpoint / "history.json.gz")
        save_history(recorder.history(), folder / "history.json.gz")
    (checkpoint / "meta.json").write_text(
        json.dumps(
            {
                "format": 1,
                "kind": "checkpoint",
                "tick": world.tick,
                "simulated_seconds": world.simulated_seconds,
                "state_digest": world.state_digest(),
                "animals": len(world.animals),
                "plants": world.plant_count,
                "written": "2023-11-14T22:13:20Z",
                "has_history": recorder is not None,
            }
        )
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "format": 1,
                "kind": "run",
                "id": run_id,
                "name": name,
                "seed": world.config.seed,
                "program_version": "0.1.0",
                "created": "2023-11-14T22:13:20Z",
                "updated": "2023-11-14T22:13:20Z",
                "config": config_to_dict(world.config),
                "summary": {
                    "tick": world.tick,
                    "simulated_seconds": world.simulated_seconds,
                    "elapsed": world.elapsed,
                    "animals": len(world.animals),
                    "plants": world.plant_count,
                    "checkpoints": 1,
                    "last_checkpoint": checkpoint.name,
                    "animal_history": [],
                    "plant_history": [],
                },
            }
        )
    )
    return run_id


def checkpoint_forever(root: str, marker: str) -> None:
    """The target of a child process: make a run and checkpoint it as fast as it can until killed."""
    from pathlib import Path

    from persistence_support import rich_world

    from evolution_simulator.history import Recorder
    from evolution_simulator.runs import RunStore, RunStoreRules

    store = RunStore(root, RunStoreRules(min_wall_seconds=0.0, keep_newest=2))
    world = rich_world()
    recorder = Recorder(world)
    run = store.create(world, name="crash", recorder=recorder)
    Path(marker).write_text(run.id)
    while True:
        world.step()
        run.checkpoint(world, recorder)


def compact_forever(root: str, run_id: str, marker: str) -> None:
    """The target of a child process: compact a run again and again until killed."""
    from pathlib import Path

    from evolution_simulator.runs import RunStore

    store = RunStore(root)
    Path(marker).write_text("started")
    while True:
        store.compact(run_id)
