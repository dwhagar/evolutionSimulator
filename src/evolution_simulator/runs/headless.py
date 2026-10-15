"""The headless run (``UX.22``): run a world with no window and keep it in the run store.

``execute`` makes a new run (or resumes one), steps it until a simulated time, and writes the history
and the checkpoints through ``RunStore``, so the viewer can open the folder afterwards from the run
history. ``evolution_simulator.__main__`` is the command line over it::

    python -m evolution_simulator run --until 100y --out runs/
    python -m evolution_simulator run --config c.json --seed 7 --animals 200 --until 30d
    python -m evolution_simulator run --resume latest --until 200y --out runs/
    python -m evolution_simulator list --out runs/

Nothing here reads a clock or prints except through the arguments it is given.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, TextIO

from evolution_simulator.history import Recorder
from evolution_simulator.runs.database import RunFile
from evolution_simulator.runs.store import Run, RunError, RunStore
from evolution_simulator.world.persistence import SaveFormatError, config_from_dict
from evolution_simulator.world.timescale import DAY, HOUR, MINUTE, MONTH, YEAR, format_duration
from evolution_simulator.world.world import World, WorldConfig

_UNITS: dict[str, float] = {
    "s": 1.0,
    "sec": 1.0,
    "min": MINUTE,
    "h": HOUR,
    "d": DAY,
    "w": 7.0 * DAY,
    "mo": MONTH,
    "y": YEAR,
}
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]+)\s*$")

Reason = Literal["finished", "extinct", "interrupted"]


def parse_duration(text: str, seconds_per_tick: float) -> float:
    """Simulated seconds for ``"100y"``, ``"30d"``, ``"12h"``, ``"1.5y"`` or ``"5000t"`` (ticks).

    Units: ``s``, ``min``, ``h``, ``d``, ``w``, ``mo`` (a twelfth of a year), ``y`` (365.25 days) and
    ``t`` (ticks of this world).
    """
    found = _DURATION.match(text.lower())
    if found is None:
        raise ValueError(f"I cannot read {text!r} as a time; try 30d, 12h, 100y or 5000t.")
    amount, unit = float(found.group(1)), found.group(2)
    if unit == "t":
        return amount * seconds_per_tick
    if unit not in _UNITS:
        raise ValueError(
            f"Unknown time unit {unit!r} in {text!r}; use one of s, min, h, d, w, mo, y, t."
        )
    return amount * _UNITS[unit]


def load_config(path: str | Path) -> WorldConfig:
    """A world config from a JSON file: ``config_to_dict`` output, a run's manifest (``run.json`` of
    the first version), or a run's ``run.sqlite``."""
    source = Path(path)
    if source.suffix == ".sqlite":
        file = RunFile.open(source, readonly=True)
        try:
            data = file.get_meta("config")
        finally:
            file.close()
        if not isinstance(data, dict):
            raise RunError(f"The run file {path} holds no config.")
    else:
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RunError(f"The config file {path} cannot be read: {error}") from error
        if not isinstance(data, dict):
            raise RunError(f"The config file {path} must hold a JSON object.")
        if isinstance(data.get("config"), dict):
            data = data["config"]
    try:
        return config_from_dict(data)
    except SaveFormatError as error:
        raise RunError(f"The config file {path} is not usable: {error}") from error


@dataclass(frozen=True)
class RunPlan:
    until: str
    """How far to run, in simulated time from the start of the world: ``100y``, ``30d``, ``5000t``."""
    config: WorldConfig | None = None
    seed: int | None = None
    animals: int = 120
    plants: int = 600
    name: str | None = None
    resume: str | None = None
    """A run id, or ``"latest"``; the other settings are then ignored, the run keeps its own."""
    keep_going: bool = False
    """Carry on after the last animal dies (otherwise the run stops there)."""
    chunk_days: float = 1.0
    """Simulated days stepped between looks at the clock and the stop request."""
    progress_seconds: float = 5.0
    """Real seconds between progress lines."""


@dataclass(frozen=True)
class RunResult:
    run: Run
    world: World
    reason: Reason
    checkpoints_written: int


def execute(
    store: RunStore,
    plan: RunPlan,
    out: TextIO | None = None,
    should_stop: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """Run the plan and leave a final checkpoint. ``should_stop`` is asked between chunks."""
    say = (lambda text: print(text, file=out, flush=True)) if out is not None else (lambda _: None)

    recorder: Recorder | None
    if plan.resume is not None:
        run = _find_run(store, plan.resume)
        resumed = run.resume()
        world, recorder = resumed.world, resumed.recorder
        say(f"Resuming {run.id} from checkpoint {resumed.checkpoint.name} ({world.elapsed}).")
        if recorder is None:
            recorder = Recorder(world)
    else:
        config = plan.config if plan.config is not None else WorldConfig()
        if plan.seed is not None:
            config = replace(config, seed=plan.seed)
        world = World(config)
        world.populate(animals=plan.animals, plants=plan.plants)
        recorder = Recorder(world)
        run = store.create(
            world,
            name=plan.name,
            recorder=recorder,
            setup={"animals": plan.animals, "plants": plan.plants, "seeded": True},
        )
        say(f"Started {run.id} in {run.path}.")

    target_seconds = parse_duration(plan.until, world.time_scale.seconds_per_tick)
    target_tick = math.ceil(target_seconds / world.time_scale.seconds_per_tick)
    chunk = max(1, round(plan.chunk_days * DAY / world.time_scale.seconds_per_tick))

    saver = run.autosave(world, recorder)
    reason: Reason = "finished"
    started, last_report, started_tick = clock(), clock(), world.tick
    try:
        while world.tick < target_tick:
            if should_stop():
                reason = "interrupted"
                break
            world.run(min(chunk, target_tick - world.tick))
            if not world.animals and not plan.keep_going:
                reason = "extinct"
                break
            now = clock()
            if now - last_report >= plan.progress_seconds:
                last_report = now
                rate = (world.tick - started_tick) / max(now - started, 1e-9)
                say(_progress(world, target_tick, rate))
    except KeyboardInterrupt:
        reason = "interrupted"
    finally:
        info = saver.finish()
    say(_ending(reason, world, info.name, run))
    return RunResult(run, world, reason, saver.written)


def _find_run(store: RunStore, ident: str) -> Run:
    if ident == "latest":
        runs = store.list_runs()
        if not runs:
            raise RunError(f"There are no runs in {store.root} to resume.")
        ident = runs[0].id
    return store.open(ident)


def _progress(world: World, target_tick: int, rate: float) -> str:
    done = min(100.0, 100.0 * world.tick / target_tick) if target_tick else 100.0
    return (
        f"{world.elapsed}  tick {world.tick}  {done:.0f}%  animals {len(world.animals)}  "
        f"plants {world.plant_count}  {rate:,.0f} ticks/s"
    )


def _ending(reason: Reason, world: World, checkpoint: str, run: Run) -> str:
    verb = {
        "finished": "Finished",
        "extinct": "Stopped: every animal has died",
        "interrupted": "Interrupted",
    }[reason]
    return (
        f"{verb} at {format_duration(world.simulated_seconds)} (tick {world.tick}); "
        f"animals {len(world.animals)}, plants {world.plant_count}. "
        f"Saved {checkpoint} in {run.path}. Resume with: --resume {run.id}"
    )


def describe_runs(store: RunStore) -> list[str]:
    """One line per run, newest first, for the ``list`` command."""
    rows: list[Any] = store.list_runs()
    lines = [f"{'id':<44} {'age':<18} {'animals':>7} {'plants':>7}  checkpoints  name"]
    for r in rows:
        lines.append(
            f"{r.id:<44} {r.elapsed:<18} {r.animals:>7} {r.plants:>7}  {r.checkpoints:>11}  {r.name}"
        )
    if not rows:
        lines.append(f"(no runs in {store.root})")
    warning = store.space_warning()
    if warning:
        lines.append(warning)
    return lines
