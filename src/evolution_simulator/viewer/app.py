"""The command line and ``main`` (UX.11, UX.33, UX.36).

``evolution-simulator-gui`` (or ``python -m evolution_simulator.viewer``) opens the window on a real
world that runs in its own process, so the window stays responsive however fast the simulation runs.
A plain launch opens the newest saved run if there is one (File > Open run lists the others), and
otherwise starts a new world with the default founders and shows the New run panel (UX.17) to change
them. ``--new``, or any of ``--seed``, ``--animals`` and ``--plants``, starts a new world instead of
opening a run. ``--fake`` shows the made-up ``FakeSimulation`` (for building screens), ``--in-process``
keeps the real world in the window's process (tests and debugging) and ``--process`` puts the made-up
one in a process too (to try that path).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

MISSING_QT = 'The viewer needs PySide6. Install it with:  pip install "evolution-simulator[gui]"\n'


DEFAULT_ANIMALS = 120
DEFAULT_PLANTS = 600
DEFAULT_SEED = 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evolution-simulator-gui", description="Open the Evolution Simulator window."
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="show the made-up FakeSimulation, in this process, instead of the real world",
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help="start a new world instead of opening the newest saved run",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="run the simulation in the window's process instead of its own (for debugging)",
    )
    parser.add_argument(
        "--process",
        action="store_true",
        help="with --fake, run the made-up simulation in its own process too (to try that path)",
    )
    parser.add_argument("--world", action="store_true", help=argparse.SUPPRESS)  # the old default
    parser.add_argument(
        "--seed", type=int, help=f"seed of a new world (default {DEFAULT_SEED}); implies --new"
    )
    parser.add_argument(
        "--animals",
        type=int,
        help=f"animals to start a new world with (default {DEFAULT_ANIMALS}); implies --new",
    )
    parser.add_argument(
        "--plants",
        type=int,
        help=f"plants to start a new world with (default {DEFAULT_PLANTS}); implies --new",
    )
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


def founders(args: argparse.Namespace) -> tuple[int, int, int]:
    """Seed, animals and plants of a new world: what was asked for, else the defaults."""
    seed = DEFAULT_SEED if args.seed is None else args.seed
    animals = DEFAULT_ANIMALS if args.animals is None else args.animals
    plants = DEFAULT_PLANTS if args.plants is None else args.plants
    return seed, animals, plants


def wants_new_world(args: argparse.Namespace) -> bool:
    """A new world was asked for, so the newest saved run is left alone."""
    given = (args.seed, args.animals, args.plants)
    return args.new or args.fake or args.in_process or any(v is not None for v in given)


def uses_process(args: argparse.Namespace) -> bool:
    """The simulation runs in its own process: always, unless it is the made-up world (which needs
    ``--process``) or ``--in-process`` was asked for."""
    if args.fake:
        return args.process
    return not args.in_process


def build_simulation(args: argparse.Namespace):
    """The simulation to show in this process: the real world, or the fake one."""
    seed, animals, plants = founders(args)
    if not args.fake:
        from evolution_simulator.world import World, WorldConfig

        world = World(WorldConfig(seed=seed))
        world.populate(animals=animals, plants=plants)
        return world
    from evolution_simulator.session import FakeSimulation

    return FakeSimulation(animals, plants, seed=seed)


def build_recipe(args: argparse.Namespace):
    """The picklable recipe the simulation process builds a new world from."""
    from evolution_simulator.session import FakeSpec, WorldSpec
    from evolution_simulator.world import WorldConfig

    seed, animals, plants = founders(args)
    if args.fake:
        return FakeSpec(animals, plants, seed=seed)
    return WorldSpec(WorldConfig(seed=seed), animals, plants)


def newest_run(store):
    """The newest saved run that has a checkpoint to open, or ``None``."""
    from evolution_simulator.runs import RunError

    try:
        for summary in store.list_runs():
            if summary.checkpoints > 0:
                return store.open(summary.id)
    except (RunError, OSError):
        return None
    return None


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

    from evolution_simulator.runs import RunStore
    from evolution_simulator.viewer.run_manager import RunManager

    store = RunStore(args.runs_folder)
    resumed = None
    if uses_process(args):
        from evolution_simulator.session import ResumeSpec
        from evolution_simulator.viewer.process_backend import ProcessBackend

        resumed = None if wants_new_world(args) else newest_run(store)
        if resumed is not None:
            backend = ProcessBackend(ResumeSpec(str(store.root), resumed.id))
        else:
            backend = ProcessBackend(build_recipe(args))
    else:
        backend = LocalBackend(Session(build_simulation(args)))
    controller = ViewerController(backend)
    manager = RunManager.install(controller, store)
    if resumed is not None:
        manager.adopt(resumed)
        label = manager.label
    else:
        label = f"{'fake' if args.fake else 'world'}, seed {founders(args)[0]}"
    settings = QSettings(args.settings, QSettings.Format.IniFormat) if args.settings else None
    window = MainWindow(controller, run_label=label, settings=settings)
    controller.start()
    window.show()
    setup = window.panels.get("setup")
    if setup is not None and resumed is None and not wants_new_world(args):
        setup.reveal()  # nothing saved yet: offer the founders to choose
    if args.quit_after is not None:
        QTimer.singleShot(args.quit_after, window.close)
    code = app.exec()
    controller.backend.close()  # not `backend`: a resumed run may have replaced it
    return code
