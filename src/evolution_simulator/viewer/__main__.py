"""``python -m evolution_simulator.viewer``."""

import multiprocessing
import sys

if __name__ == "__main__":
    # First thing: a frozen program starts the simulation process by running itself again, and
    # this call is what sends that second run to the simulation instead of opening a window. The
    # guard matters too: a spawned process imports this module under another name, and must not
    # open a second window.
    multiprocessing.freeze_support()
    from evolution_simulator.viewer.app import main

    sys.exit(main())
