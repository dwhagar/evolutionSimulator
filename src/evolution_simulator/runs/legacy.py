"""Runs in the folder layout of the first version (``UX.10``, ``UX.31``), imported into SQLite.

::

    <run>/run.json                    the manifest
    <run>/history.json.gz             the history as of the latest checkpoint
    <run>/checkpoints/checkpoint-N/   meta.json, world.json.gz, history.json.gz

``import_run`` builds ``run.sqlite`` from them in one go (the checkpoints' compressed bytes are copied
as they are, no world is decoded) and moves the old files into ``<run>/imported/``, where they stay
until someone deletes them: a run that cannot be imported loses nothing, and an import cut short
leaves the old files where they were (``tidy`` finishes the move). See docs/design/storage.md.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evolution_simulator.history import load_history_data
from evolution_simulator.history.samples import HistorySamples
from evolution_simulator.runs.database import FILE_NAME, CheckpointRow, RunFile
from evolution_simulator.runs.errors import RunError

LEGACY_RUN_FORMAT = 1
MANIFEST = "run.json"
HISTORY = "history.json.gz"
WORLD_FILE = "world.json.gz"
CHECKPOINTS = "checkpoints"
CHECKPOINT_PREFIX = "checkpoint-"
IMPORTED = "imported"
"""Where the old files go after an import."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RunError(f"{path.name} cannot be read: {error}") from error
    if not isinstance(data, dict):
        raise RunError(f"{path.name} is not a run file.")
    return data


def read_manifest(folder: Path) -> dict[str, Any]:
    """The manifest of an old-layout run (for the run list)."""
    manifest = _read_json(folder / MANIFEST)
    if manifest.get("kind") != "run" or manifest.get("format") != LEGACY_RUN_FORMAT:
        raise RunError(f"{folder.name} is not a run this program can read.")
    return manifest


def _checkpoints(folder: Path) -> list[tuple[CheckpointRow, bytes, bytes | None]]:
    found: list[tuple[CheckpointRow, bytes, bytes | None]] = []
    root = folder / CHECKPOINTS
    if not root.is_dir():
        return found
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith(CHECKPOINT_PREFIX) or not entry.is_dir():
            continue
        try:
            meta = _read_json(entry / "meta.json")
            if meta.get("kind") != "checkpoint" or meta.get("format") != LEGACY_RUN_FORMAT:
                continue
            world = (entry / WORLD_FILE).read_bytes()
            has_history = bool(meta["has_history"]) and (entry / HISTORY).is_file()
            recorder = (entry / HISTORY).read_bytes() if has_history else None
            row = CheckpointRow(
                tick=int(meta["tick"]),
                simulated_seconds=float(meta["simulated_seconds"]),
                state_digest=str(meta["state_digest"]),
                animals=int(meta["animals"]),
                plants=int(meta["plants"]),
                written=str(meta["written"]),
                has_history=has_history,
            )
        except (RunError, OSError, KeyError, TypeError, ValueError):
            continue  # a checkpoint that cannot be read is not carried over (the old files stay)
        found.append((row, world, recorder))
    return found


def import_run(folder: Path, clock: Callable[[], float]) -> None:
    """Make ``folder/run.sqlite`` from the old files in ``folder`` and move them to ``imported/``."""
    manifest = read_manifest(folder)
    checkpoints = _checkpoints(folder)
    manifest.update(format=2, imported_from=LEGACY_RUN_FORMAT)
    manifest["imported"] = datetime.fromtimestamp(clock(), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    setup: dict[str, Any] = {"seed": manifest["seed"]}
    if checkpoints and checkpoints[0][0].tick == 0:
        setup.update(animals=checkpoints[0][0].animals, plants=checkpoints[0][0].plants)
    manifest["setup"] = setup
    part_path = folder / (FILE_NAME + ".part")
    part_path.unlink(missing_ok=True)
    part = RunFile.create(part_path, manifest)
    try:
        with part.transaction():
            for row, world, recorder in checkpoints:
                part.add_checkpoint(row, world, recorder)
            history_file = folder / HISTORY
            if history_file.is_file():
                try:
                    history = HistorySamples.from_dict(load_history_data(history_file))
                except (OSError, ValueError, KeyError, EOFError):
                    history = None
                if history is not None:
                    part.history_replace(history)
        final = part.publish(folder / FILE_NAME)
    except BaseException:
        part.close()
        part_path.unlink(missing_ok=True)
        raise
    final.close()
    tidy(folder)


def tidy(folder: Path) -> None:
    """Move the old files of an imported run into ``imported/``."""
    target = folder / IMPORTED
    target.mkdir(exist_ok=True)
    for name in (MANIFEST, HISTORY, CHECKPOINTS):
        source = folder / name
        if source.exists():
            destination = target / name
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination, ignore_errors=True)
                else:
                    destination.unlink(missing_ok=True)
            shutil.move(str(source), str(destination))
