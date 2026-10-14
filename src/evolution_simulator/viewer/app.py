"""The command line and ``main`` (UX.11).

``evolution-simulator-gui`` (or ``python -m evolution_simulator.viewer``) opens the window. By
default it shows the made-up ``FakeSimulation`` in this process, which needs nothing to start;
``--world`` runs the real one in its own process (UX.33), so the window stays responsive however fast
the simulation runs. ``--in-process`` keeps the real world in this process (for debugging) and
``--process`` puts the made-up one in a process too (to try the path without waiting for a world).
File > New run (the setup screen, UX.17) replaces either with a real world of the user's choosing.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

MISSING_QT = 'The viewer needs PySide6. Install it with:  pip install "evolution-simulator[gui]"\n'


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evolution-simulator-gui", description="Open the Evolution Simulator window."
    )
    parser.add_argument(
        "--world",
        action="store_true",
        help="run the real simulation, in its own process (default: the made-up FakeSimulation)",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="run the simulation in the window's process instead of its own (for debugging)",
    )
    parser.add_argument(
        "--process",
        action="store_true",
        help="run the made-up simulation in its own process too (to try that path)",
    )
    parser.add_argument("--seed", type=int, default=0, help="seed of the world (default 0)")
    parser.add_argument("--animals", type=int, default=120, help="animals to start with")
    parser.add_argument("--plants", type=int, default=600, help="plants to start with")
    parser.add_argument(
        "--settings",
        metavar="FILE",
        help="keep the window layout in this .ini file instead of the user's settings",
    )
    parser.add_argument(
        "--runs-folder",
        metavar="DIR",
        help="where saved runs live (default: the per-user folder, see evolution_simulator.runs)",
    )
    parser.add_argument(
        "--quit-after",
        type=int,
        metavar="MS",
        help="close the window after this many milliseconds (for smoke tests)",
    )
    return parser.parse_args(argv)


def build_simulation(args: argparse.Namespace):
    """The simulation to show: the real world, or the fake one."""
    if args.world:
        from evolution_simulator.world import World, WorldConfig

        world = World(WorldConfig(seed=args.seed))
        world.populate(animals=args.animals, plants=args.plants)
        return world
    from evolution_simulator.session import FakeSimulation

    return FakeSimulation(args.animals, args.plants, seed=args.seed)


def build_recipe(args: argparse.Namespace):
    """The picklable recipe the simulation process builds its world from (``--world`` or
    ``--process``)."""
    from evolution_simulator.session import FakeSpec, WorldSpec
    from evolution_simulator.world import WorldConfig

    if args.world:
        return WorldSpec(WorldConfig(seed=args.seed), args.animals, args.plants)
    return FakeSpec(args.animals, args.plants, seed=args.seed)


def uses_process(args: argparse.Namespace) -> bool:
    return (args.world and not args.in_process) or args.process


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        sys.stderr.write(MISSING_QT)
        return 2

    from evolution_simulator.session import Session
    from evolution_simulator.viewer.backend import LocalBackend
    from evolution_simulator.viewer.controller import ViewerController
    from evolution_simulator.viewer.window import APP_NAME, MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("evolutionSimulator")

    if uses_process(args):
        from evolution_simulator.viewer.process_backend import ProcessBackend

        backend = ProcessBackend(build_recipe(args))
    else:
        backend = LocalBackend(Session(build_simulation(args)))
    controller = ViewerController(backend)
    from evolution_simulator.runs import RunStore
    from evolution_simulator.viewer.run_manager import RunManager

    RunManager.install(controller, RunStore(args.runs_folder) if args.runs_folder else None)
    settings = QSettings(args.settings, QSettings.Format.IniFormat) if args.settings else None
    label = f"{'world' if args.world else 'fake'}, seed {args.seed}"
    window = MainWindow(controller, run_label=label, settings=settings)
    controller.start()
    window.show()
    if args.quit_after is not None:
        QTimer.singleShot(args.quit_after, window.close)
    code = app.exec()
    controller.backend.close()  # not `backend`: a resumed run may have replaced it
    return code
