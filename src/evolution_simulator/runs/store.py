"""The run store (``UX.10``): one folder per run, with checkpoints, history and a manifest.

::

    <root>/<run id>/
        run.json                  the manifest: name, seed, versions, config, and a summary
        history.json.gz           the recorded history as of the latest checkpoint (for charts)
        checkpoints/
            checkpoint-000000009600/
                meta.json         tick, simulated time, state digest, population
                world.json.gz     the world (``persistence.save_world``)
                history.json.gz   the recorder's state at that moment (when a recorder is used)

No pickle: every file is JSON (gzip where large), each with a format number, so a run opens after the
classes change. ``run.json`` is the history index: ``RunStore.list_runs`` reads only the manifests to
list every run with its seed, versions, simulated age, last population and last checkpoint, and a short
population series for a small chart, without opening a world.

A checkpoint is a world and the recorder's state taken together, written to a hidden folder and moved
into place, so a crash leaves the previous checkpoint intact. ``Run.resume`` restores the newest one
that reads (falling back to older ones), and a resumed run goes on exactly as an uninterrupted one
would. ``Run.autosave`` writes checkpoints as the run goes: every ``checkpoint_every_days`` simulated
days (and no more often than ``min_wall_seconds`` of real time), keeping the newest ``keep_newest``
plus the first checkpoint of each simulated year. Runs are never deleted unless asked; ``space_warning``
says when the folder holds more than ``warn_bytes``.

Nothing here reads a clock but the one passed in, and there are no dependencies outside the core.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evolution_simulator import __version__
from evolution_simulator.history import Recorder, load_history_data, save_history
from evolution_simulator.history.samples import HistorySamples
from evolution_simulator.runs.paths import default_runs_root
from evolution_simulator.world.persistence import (
    SaveFormatError,
    config_from_dict,
    config_to_dict,
    load_world,
    save_world,
)
from evolution_simulator.world.world import StepReport, World, WorldConfig

RUN_FORMAT = 1
"""The layout of ``run.json`` and a checkpoint's ``meta.json``."""

MANIFEST = "run.json"
HISTORY = "history.json.gz"
WORLD_FILE = "world.json.gz"
CHECKPOINTS = "checkpoints"
CHECKPOINT_PREFIX = "checkpoint-"
POPULATION_POINTS = 60
"""Points of the animal and plant counts kept in the manifest for a run list's small chart."""
GIGABYTE = 1024**3


class RunError(Exception):
    """A run cannot be created, found or resumed."""


@dataclass(frozen=True)
class RunStoreRules:
    checkpoint_every_days: float = 10.0
    """Simulated days between automatic checkpoints."""
    min_wall_seconds: float = 60.0
    """And never more often than this many real seconds, however fast the run goes."""
    keep_newest: int = 3
    """Checkpoints kept besides the yearly ones: the newest this many."""
    keep_yearly: bool = True
    """Also keep the first checkpoint of every simulated year (the first one of all included)."""
    year_days: float = 365.25
    warn_bytes: int = 5 * GIGABYTE
    """``space_warning`` speaks once the store holds more than this."""

    def __post_init__(self) -> None:
        for name in ("checkpoint_every_days", "year_days"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value > 0.0):
                raise ValueError(f"{name} must be above zero, got {value}.")
        if not (math.isfinite(self.min_wall_seconds) and self.min_wall_seconds >= 0.0):
            raise ValueError(f"min_wall_seconds must be zero or more, got {self.min_wall_seconds}.")
        if self.keep_newest < 1:
            raise ValueError("keep_newest must be at least 1.")
        if self.warn_bytes < 0:
            raise ValueError("warn_bytes must not be negative.")


@dataclass(frozen=True, slots=True)
class CheckpointInfo:
    name: str
    path: Path
    tick: int
    simulated_seconds: float
    state_digest: str
    animals: int
    plants: int
    written: str
    has_history: bool


@dataclass(frozen=True, slots=True)
class RunSummary:
    """One line of the run list."""

    id: str
    path: Path
    name: str
    seed: int
    program_version: str
    created: str
    updated: str
    tick: int
    simulated_seconds: float
    elapsed: str
    animals: int
    plants: int
    checkpoints: int
    last_checkpoint: str | None
    animal_history: tuple[float, ...]
    """Up to ``POPULATION_POINTS`` animal counts across the run's recorded history, for a chart."""
    plant_history: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Resumed:
    world: World
    recorder: Recorder | None
    checkpoint: CheckpointInfo


def _utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "run"


def _write_json(path: Path, data: Any) -> None:
    scratch = path.with_name(path.name + ".part")
    scratch.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(scratch, path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RunError(f"{path.name} cannot be read: {error}") from error
    if not isinstance(data, dict):
        raise RunError(f"{path.name} is not a run file.")
    return data


def _downsample(values: tuple[float, ...], points: int) -> tuple[float, ...]:
    if len(values) <= points:
        return values
    return tuple(values[round(i * (len(values) - 1) / (points - 1))] for i in range(points))


class RunStore:
    """A folder of runs."""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        rules: RunStoreRules | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root) if root is not None else Path(str(default_runs_root()))
        self.rules = rules if rules is not None else RunStoreRules()
        self.clock = clock

    # ---- creating and finding runs ----------------------------------------------------------

    def create(
        self, world: World, name: str | None = None, recorder: Recorder | None = None
    ) -> Run:
        """Start a run folder for ``world`` (as it stands now) and write its first checkpoint, so
        the run can be resumed at once. Give the recorder to keep its history with the run."""
        label = name or f"seed {world.config.seed}"
        stamp = datetime.fromtimestamp(self.clock(), tz=UTC).strftime("%Y%m%d-%H%M%S")
        base = f"{stamp}-{_slug(label)}"
        run_id, n = base, 1
        while (self.root / run_id).exists():
            n += 1
            run_id = f"{base}-{n}"
        path = self.root / run_id
        (path / CHECKPOINTS).mkdir(parents=True)
        now = _utc(self.clock())
        manifest = {
            "format": RUN_FORMAT,
            "kind": "run",
            "id": run_id,
            "name": label,
            "seed": world.config.seed,
            "program_version": __version__,
            "created": now,
            "updated": now,
            "config": config_to_dict(world.config),
            "summary": {},
        }
        run = Run(self, path, manifest)
        run.checkpoint(world, recorder)
        return run

    def open(self, run_id: str) -> Run:
        path = self.root / run_id
        if not (path / MANIFEST).is_file():
            raise RunError(f"There is no run {run_id!r} in {self.root}.")
        return Run(self, path, self._manifest(path))

    def _manifest(self, path: Path) -> dict[str, Any]:
        manifest = _read_json(path / MANIFEST)
        if manifest.get("kind") != "run" or manifest.get("format") != RUN_FORMAT:
            raise RunError(f"{path.name} is not a run this program can read.")
        return manifest

    def list_runs(self) -> list[RunSummary]:
        """Every run in the folder, the most recently updated first. A folder that is not a readable
        run is left out."""
        if not self.root.is_dir():
            return []
        found: list[RunSummary] = []
        for path in sorted(self.root.iterdir()):
            if not (path / MANIFEST).is_file():
                continue
            try:
                found.append(_summary(path, self._manifest(path)))
            except (RunError, KeyError, TypeError, ValueError):
                continue
        return sorted(found, key=lambda r: (r.updated, r.id), reverse=True)

    def delete(self, run_id: str) -> None:
        """Remove a run and everything in it."""
        path = self.root / run_id
        if not (path / MANIFEST).is_file():
            raise RunError(f"There is no run {run_id!r} in {self.root}.")
        shutil.rmtree(path)

    # ---- space -------------------------------------------------------------------------------

    def total_bytes(self) -> int:
        total = 0
        if self.root.is_dir():
            for folder, _, files in os.walk(self.root):
                for name in files:
                    with contextlib.suppress(OSError):
                        total += (Path(folder) / name).stat().st_size
        return total

    def space_warning(self) -> str | None:
        """A sentence when the runs take more than ``rules.warn_bytes``, else ``None``."""
        used = self.total_bytes()
        if used <= self.rules.warn_bytes:
            return None
        return (
            f"Saved runs use {used / GIGABYTE:.1f} GB in {self.root}; "
            f"more than {self.rules.warn_bytes / GIGABYTE:.1f} GB. Delete runs you no longer need."
        )


def _summary(path: Path, manifest: dict[str, Any]) -> RunSummary:
    summary = manifest.get("summary", {})
    return RunSummary(
        id=manifest["id"],
        path=path,
        name=manifest["name"],
        seed=int(manifest["seed"]),
        program_version=manifest["program_version"],
        created=manifest["created"],
        updated=manifest["updated"],
        tick=int(summary.get("tick", 0)),
        simulated_seconds=float(summary.get("simulated_seconds", 0.0)),
        elapsed=str(summary.get("elapsed", "")),
        animals=int(summary.get("animals", 0)),
        plants=int(summary.get("plants", 0)),
        checkpoints=int(summary.get("checkpoints", 0)),
        last_checkpoint=summary.get("last_checkpoint"),
        animal_history=tuple(float(v) for v in summary.get("animal_history", ())),
        plant_history=tuple(float(v) for v in summary.get("plant_history", ())),
    )


class Run:
    """One run folder."""

    def __init__(self, store: RunStore, path: Path, manifest: dict[str, Any]) -> None:
        self.store = store
        self.path = path
        self.manifest = manifest
        self._last_seconds: float | None = None
        self._last_wall: float | None = None

    @property
    def id(self) -> str:
        return str(self.manifest["id"])

    @property
    def name(self) -> str:
        return str(self.manifest["name"])

    @property
    def summary(self) -> RunSummary:
        return _summary(self.path, self.manifest)

    @property
    def config(self) -> WorldConfig:
        """The run's settings, read back from the manifest."""
        return config_from_dict(self.manifest["config"])

    # ---- checkpoints -------------------------------------------------------------------------

    def checkpoints(self) -> list[CheckpointInfo]:
        """The checkpoints that are there, oldest first."""
        folder = self.path / CHECKPOINTS
        found: list[CheckpointInfo] = []
        if not folder.is_dir():
            return found
        for entry in folder.iterdir():
            if not entry.name.startswith(CHECKPOINT_PREFIX) or not entry.is_dir():
                continue
            try:
                found.append(_checkpoint_info(entry))
            except (RunError, KeyError, TypeError, ValueError):
                continue
        return sorted(found, key=lambda c: c.tick)

    def checkpoint(self, world: World, recorder: Recorder | None = None) -> CheckpointInfo:
        """Write a checkpoint of the world (and the recorder, if given) now, update the manifest and
        the run's history file, and drop the checkpoints the retention rules no longer keep."""
        if recorder is not None:
            recorder.observe()  # a sample due at this very tick belongs in this checkpoint
        name = f"{CHECKPOINT_PREFIX}{world.tick:012d}"
        folder = self.path / CHECKPOINTS
        folder.mkdir(parents=True, exist_ok=True)
        scratch = folder / f".writing-{name}"
        if scratch.exists():
            shutil.rmtree(scratch)
        scratch.mkdir()
        now = self.store.clock()
        meta = {
            "format": RUN_FORMAT,
            "kind": "checkpoint",
            "tick": world.tick,
            "simulated_seconds": world.simulated_seconds,
            "state_digest": world.state_digest(),
            "animals": len(world.animals),
            "plants": world.plant_count,
            "written": _utc(now),
            "has_history": recorder is not None,
        }
        save_world(world, scratch / WORLD_FILE)
        if recorder is not None:
            save_history(recorder, scratch / HISTORY)
        _write_json(scratch / "meta.json", meta)
        final = folder / name
        if final.exists():
            shutil.rmtree(final)
        os.replace(scratch, final)
        if recorder is not None:
            save_history(recorder.history(), self.path / HISTORY)
        self._last_seconds = world.simulated_seconds
        self._last_wall = now
        self._prune()
        self._update_manifest(world, recorder, name, now)
        return _checkpoint_info(final)

    def _prune(self) -> None:
        rules = self.store.rules
        found = self.checkpoints()
        keep = {c.name for c in found[-rules.keep_newest :]}
        if rules.keep_yearly:
            year = rules.year_days * 86400.0
            first_of_year: dict[int, CheckpointInfo] = {}
            for c in found:
                first_of_year.setdefault(int(c.simulated_seconds // year), c)
            keep.update(c.name for c in first_of_year.values())
        for c in found:
            if c.name not in keep:
                shutil.rmtree(c.path, ignore_errors=True)

    def _update_manifest(
        self, world: World, recorder: Recorder | None, checkpoint: str, now: float
    ) -> None:
        animals: tuple[float, ...] = ()
        plants: tuple[float, ...] = ()
        if recorder is not None:
            history = recorder.history()
            animals = _downsample(history.series("animals")[1], POPULATION_POINTS)
            plants = _downsample(history.series("plants")[1], POPULATION_POINTS)
        self.manifest["updated"] = _utc(now)
        self.manifest["summary"] = {
            "tick": world.tick,
            "simulated_seconds": world.simulated_seconds,
            "elapsed": world.elapsed,
            "animals": len(world.animals),
            "plants": world.plant_count,
            "corpses": len(world.corpses),
            "checkpoints": len(self.checkpoints()),
            "last_checkpoint": checkpoint,
            "animal_history": list(animals),
            "plant_history": list(plants),
        }
        _write_json(self.path / MANIFEST, self.manifest)

    # ---- resuming and reading ---------------------------------------------------------------

    def resume(self, checkpoint: str | None = None) -> Resumed:
        """Restore the world (and the recorder, if the checkpoint has one). Without a name this is
        the newest checkpoint that reads, trying older ones if the newest is damaged."""
        found = self.checkpoints()
        if checkpoint is not None:
            found = [c for c in found if c.name == checkpoint]
            if not found:
                raise RunError(f"Run {self.id} has no checkpoint {checkpoint!r}.")
        errors: list[str] = []
        for info in reversed(found):
            try:
                world = load_world(info.path / WORLD_FILE)
                recorder = None
                if info.has_history:
                    recorder = Recorder.restore(world, load_history_data(info.path / HISTORY))
                self._last_seconds = world.simulated_seconds
                self._last_wall = self.store.clock()
                return Resumed(world, recorder, info)
            except (SaveFormatError, RunError, OSError, ValueError, KeyError, EOFError) as error:
                errors.append(f"{info.name}: {error}")
        raise RunError(
            f"Run {self.id} has no checkpoint that can be restored. " + "; ".join(errors)
        )

    def history(self) -> HistorySamples | None:
        """The recorded history as of the latest checkpoint, or ``None`` if there is none."""
        file = self.path / HISTORY
        if not file.is_file():
            return None
        data = load_history_data(file)
        return HistorySamples.from_dict(data)

    # ---- autosave ---------------------------------------------------------------------------

    def due(self, world: World) -> bool:
        """Whether an automatic checkpoint is owed: enough simulated days and enough real time have
        passed since the last one."""
        rules = self.store.rules
        if self._last_seconds is None or self._last_wall is None:
            return True
        days = (world.simulated_seconds - self._last_seconds) / 86400.0
        waited = self.store.clock() - self._last_wall
        return days >= rules.checkpoint_every_days and waited >= rules.min_wall_seconds

    def autosave(self, world: World, recorder: Recorder | None = None) -> Autosaver:
        """Write a checkpoint whenever one is due, after each step, until ``close()``."""
        return Autosaver(self, world, recorder)


def _checkpoint_info(folder: Path) -> CheckpointInfo:
    meta = _read_json(folder / "meta.json")
    if meta.get("kind") != "checkpoint" or meta.get("format") != RUN_FORMAT:
        raise RunError(f"{folder.name} is not a checkpoint this program can read.")
    return CheckpointInfo(
        name=folder.name,
        path=folder,
        tick=int(meta["tick"]),
        simulated_seconds=float(meta["simulated_seconds"]),
        state_digest=str(meta["state_digest"]),
        animals=int(meta["animals"]),
        plants=int(meta["plants"]),
        written=str(meta["written"]),
        has_history=bool(meta["has_history"]),
    )


class Autosaver:
    """Listens to the end of every step and checkpoints the run when one is due."""

    def __init__(self, run: Run, world: World, recorder: Recorder | None = None) -> None:
        self.run = run
        self.world = world
        self.recorder = recorder
        self.written = 0
        """Checkpoints this autosaver has written."""
        world.add_step_listener(self._on_step)
        self._closed = False

    def _on_step(self, report: StepReport) -> None:
        if self.run.due(self.world):
            self.run.checkpoint(self.world, self.recorder)
            self.written += 1

    def finish(self) -> CheckpointInfo:
        """Checkpoint now (when a run ends or is stopped) and stop listening."""
        self.close()
        info = self.run.checkpoint(self.world, self.recorder)
        self.written += 1
        return info

    def close(self) -> None:
        if not self._closed:
            self.world.remove_step_listener(self._on_step)
            self._closed = True
