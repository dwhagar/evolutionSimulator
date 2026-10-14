"""The headless run command (UX.22): durations, a run through the store, resume, the command line."""

import io
import json
import subprocess
import sys

import pytest
from world_support import HOURLY

from evolution_simulator.__main__ import main
from evolution_simulator.runs import RunError, RunStore, RunStoreRules
from evolution_simulator.runs.headless import RunPlan, execute, load_config, parse_duration
from evolution_simulator.world import Bounds, WorldConfig, persistence

SMALL = WorldConfig(seed=2, bounds=Bounds((300.0, 300.0))).with_time_scale(HOURLY)


def store_in(tmp_path) -> RunStore:
    return RunStore(
        tmp_path / "runs", RunStoreRules(min_wall_seconds=0.0, checkpoint_every_days=2.0)
    )


def plan(**kwargs) -> RunPlan:
    kwargs.setdefault("config", SMALL)
    kwargs.setdefault("animals", 10)
    kwargs.setdefault("plants", 60)
    return RunPlan(**kwargs)


# --- durations ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("30s", 30.0),
        ("2h", 7200.0),
        ("3d", 3 * 86400.0),
        ("1w", 7 * 86400.0),
        ("100y", 100 * 365.25 * 86400.0),
        ("1.5y", 1.5 * 365.25 * 86400.0),
        ("10 min", 600.0),
        ("5000t", 5000 * 3600.0),
        ("12H", 12 * 3600.0),
    ],
)
def test_parse_duration(text: str, seconds: float) -> None:
    assert parse_duration(text, 3600.0) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["", "100", "y", "5 parsecs", "-3d"])
def test_parse_duration_refuses_nonsense(text: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(text, 3600.0)


# --- a run through the store -------------------------------------------------------------------


def test_run_writes_history_and_checkpoints(tmp_path) -> None:
    store = store_in(tmp_path)
    out = io.StringIO()
    result = execute(store, plan(until="6d", name="demo", progress_seconds=0.0), out=out)
    assert result.reason == "finished"
    assert result.world.tick == 6 * 24
    run = store.open(result.run.id)
    history = run.history()
    assert history is not None
    assert history.latest is not None
    assert history.latest.day >= 5
    ticks = [c.tick for c in run.checkpoints()]
    assert ticks[0] == 0
    assert ticks[-1] == 6 * 24
    assert "Finished" in out.getvalue()
    assert "--resume" in out.getvalue()
    assert store.list_runs()[0].tick == 6 * 24


def test_resume_matches_a_straight_run(tmp_path) -> None:
    straight = execute(store_in(tmp_path / "a"), plan(until="8d"))
    store = store_in(tmp_path / "b")
    first = execute(store, plan(until="3d"))
    second = execute(store, plan(until="8d", resume=first.run.id))
    assert second.run.id == first.run.id
    assert second.world.tick == straight.world.tick
    assert second.world.state_digest() == straight.world.state_digest()
    assert straight.run.history() == second.run.history()
    latest = execute(store, plan(until="9d", resume="latest"))
    assert latest.run.id == first.run.id
    assert latest.world.tick == 9 * 24


def test_stops_when_every_animal_has_died(tmp_path) -> None:
    store = store_in(tmp_path)
    result = execute(store, plan(until="2y", animals=0, plants=30))
    assert result.reason == "extinct"
    assert result.world.tick < 2 * 365 * 24
    kept = execute(store, plan(until="3d", animals=0, plants=30, keep_going=True))
    assert kept.reason == "finished"
    assert kept.world.tick == 3 * 24


def test_stop_request_saves_and_can_be_resumed(tmp_path) -> None:
    store = store_in(tmp_path)
    calls = iter([False, False, True])
    result = execute(store, plan(until="30d"), should_stop=lambda: next(calls))
    assert result.reason == "interrupted"
    assert result.world.tick == 2 * 24
    assert result.run.checkpoints()[-1].tick == 2 * 24
    done = execute(store, plan(until="3d", resume=result.run.id))
    assert done.world.tick == 3 * 24


def test_seed_overrides_config(tmp_path) -> None:
    result = execute(store_in(tmp_path), plan(until="1d", seed=99))
    assert result.run.manifest["seed"] == 99
    assert result.world.config.seed == 99


def test_resume_of_missing_run(tmp_path) -> None:
    with pytest.raises(RunError):
        execute(store_in(tmp_path), plan(until="1d", resume="nope"))
    with pytest.raises(RunError):
        execute(store_in(tmp_path), plan(until="1d", resume="latest"))


# --- config files and the command line ---------------------------------------------------------


def test_load_config_from_config_or_manifest(tmp_path) -> None:
    data = persistence.config_to_dict(SMALL)
    plain = tmp_path / "c.json"
    plain.write_text(json.dumps(data))
    assert load_config(plain) == SMALL
    manifest = tmp_path / "run.json"
    manifest.write_text(json.dumps({"format": 1, "kind": "run", "config": data}))
    assert load_config(manifest) == SMALL
    partial = tmp_path / "p.json"
    partial.write_text(json.dumps({"seed": 5}))
    assert load_config(partial).seed == 5
    bad = tmp_path / "bad.json"
    bad.write_text("[")
    with pytest.raises(RunError):
        load_config(bad)
    unknown = tmp_path / "u.json"
    unknown.write_text(json.dumps({"colour": "red"}))
    with pytest.raises(RunError):
        load_config(unknown)


def test_command_run_list_and_resume(tmp_path) -> None:
    config = tmp_path / "c.json"
    config.write_text(json.dumps(persistence.config_to_dict(SMALL)))
    runs = str(tmp_path / "runs")
    out = io.StringIO()
    args = ["run", "--config", str(config), "--animals", "8", "--plants", "40", "--until", "2d"]
    assert main([*args, "--out", runs, "--name", "cli", "--min-wall-seconds", "0"], out) == 0
    assert "Finished" in out.getvalue()
    listing = io.StringIO()
    assert main(["list", "--out", runs], listing) == 0
    assert "cli" in listing.getvalue()
    resumed = io.StringIO()
    assert main(["run", "--resume", "latest", "--until", "3d", "--out", runs], resumed) == 0
    assert "Resuming" in resumed.getvalue()
    quiet = io.StringIO()
    assert (
        main(["run", "--resume", "latest", "--until", "4d", "--out", runs, "--quiet"], quiet) == 0
    )
    assert quiet.getvalue().startswith("finished:")
    assert RunStore(runs).list_runs()[0].tick == 4 * 24


def test_command_errors_exit_two(tmp_path, capsys) -> None:
    runs = str(tmp_path / "runs")
    assert main(["run", "--until", "soon", "--out", runs]) == 2
    assert main(["run", "--until", "1d", "--resume", "nope", "--out", runs]) == 2
    assert (
        main(["run", "--until", "1d", "--config", str(tmp_path / "none.json"), "--out", runs]) == 2
    )
    assert "error:" in capsys.readouterr().err


def test_python_dash_m_runs(tmp_path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "evolution_simulator", "list", "--out", str(tmp_path / "r")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0
    assert "no runs" in done.stdout
