"""``python -m evolution_simulator``: the command line (``UX.22``). See ``runs/headless.py``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from evolution_simulator.runs import RunError, RunStore, RunStoreRules, default_runs_root
from evolution_simulator.runs.headless import RunPlan, describe_runs, execute, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evolution_simulator", description="Run the simulation with no window."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="start a run, or resume one, and save it as it goes")
    run.add_argument(
        "--until",
        required=True,
        metavar="TIME",
        help="simulated time to run to, from the start of the world: 30d, 100y, 5000t",
    )
    run.add_argument(
        "--config",
        metavar="FILE",
        help="world settings as JSON (or a run's run.json or run.sqlite)",
    )
    run.add_argument("--seed", type=int, help="seed of the world (overrides the config's)")
    run.add_argument("--animals", type=int, default=120, help="animals to start with (default 120)")
    run.add_argument("--plants", type=int, default=600, help="plants to start with (default 600)")
    run.add_argument("--name", help="a name for the run")
    run.add_argument(
        "--resume",
        metavar="RUN",
        help="resume this run id (or 'latest'); the run keeps its own settings",
    )
    run.add_argument(
        "--keep-going", action="store_true", help="carry on after the last animal dies"
    )
    run.add_argument(
        "--checkpoint-days",
        type=float,
        default=None,
        help="simulated days between checkpoints (default 10)",
    )
    run.add_argument(
        "--keep-newest",
        type=int,
        default=None,
        help="newest checkpoints to keep besides the yearly ones (default 3)",
    )
    run.add_argument(
        "--min-wall-seconds",
        type=float,
        default=None,
        help="fewest real seconds between checkpoints (default 60)",
    )
    run.add_argument("--quiet", action="store_true", help="print only the last line")

    listing = commands.add_parser("list", help="list the saved runs")

    for sub in (run, listing):
        sub.add_argument(
            "--out", metavar="DIR", help="the runs folder (default: the per-user data folder)"
        )
    return parser


def _store(args: argparse.Namespace) -> RunStore:
    root = Path(args.out) if args.out else Path(str(default_runs_root()))
    given = {
        name: value
        for name, value in (
            ("checkpoint_every_days", getattr(args, "checkpoint_days", None)),
            ("keep_newest", getattr(args, "keep_newest", None)),
            ("min_wall_seconds", getattr(args, "min_wall_seconds", None)),
        )
        if value is not None
    }
    return RunStore(root, RunStoreRules(**given))


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    out = sys.stdout if out is None else out
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        store = _store(args)
        if args.command == "list":
            print("\n".join(describe_runs(store)), file=out)
            return 0
        plan = RunPlan(
            until=args.until,
            config=load_config(args.config) if args.config else None,
            seed=args.seed,
            animals=args.animals,
            plants=args.plants,
            name=args.name,
            resume=args.resume,
            keep_going=args.keep_going,
        )
        result = execute(store, plan, out=None if args.quiet else out)
        if args.quiet:
            print(f"{result.reason}: {result.run.path}", file=out)
        return 130 if result.reason == "interrupted" else 0
    except (RunError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
