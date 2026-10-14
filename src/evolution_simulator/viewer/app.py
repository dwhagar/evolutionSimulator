"""The command line and ``main`` (UX.11).

``evolution-simulator-gui`` (or ``python -m evolution_simulator.viewer``) opens the window. Until the
process host (UX.7) and the setup screen (UX.17) exist the simulation runs in this process, and by
default it is the made-up ``FakeSimulation``; ``--world`` runs the real one.
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
        help="run the real simulation, in this process (default: the made-up FakeSimulation)",
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

    backend = LocalBackend(Session(build_simulation(args)))
    controller = ViewerController(backend)
    settings = QSettings(args.settings, QSettings.Format.IniFormat) if args.settings else None
    label = f"{'world' if args.world else 'fake'}, seed {args.seed}"
    window = MainWindow(controller, run_label=label, settings=settings)
    controller.start()
    window.show()
    if args.quit_after is not None:
        QTimer.singleShot(args.quit_after, window.close)
    code = app.exec()
    backend.close()
    return code
