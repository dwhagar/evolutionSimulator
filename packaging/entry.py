"""The program the Windows build runs (UX.19): ``evolutionSimulator.exe``.

PyInstaller freezes this script. It stays tiny on purpose, because the first thing a frozen program
must do is ``multiprocessing.freeze_support()``: the simulation runs in its own process, started by
``spawn``, and on Windows a frozen program starts that process by running itself again with
special arguments. ``freeze_support()`` notices them and runs the simulation instead of opening a
second window; it does nothing in a normal run.
"""

import multiprocessing
import os
import sys


def quiet_streams() -> None:
    """A windowed program has no console: ``sys.stdout`` and ``sys.stderr`` are ``None`` and
    anything that prints would raise. Point them at the null device."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - lives as long as the program
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def selftest(timeout: float = 60.0) -> int:
    """``evolutionSimulator.exe --selftest``: start the simulation process the way the viewer will,
    wait for its first frame, ask it for five ticks, wait for a frame past tick 0, shut it down. Exit code 0 when
    all of that worked, 1 when not. It opens no window, so the build workflow can run it on a
    machine with no screen; it is what proves the frozen program can start its own second process."""
    import time

    from evolution_simulator.session import FakeSpec, ProcessClient, Step

    client = ProcessClient(FakeSpec(animals=10, plants=20))
    try:
        deadline = time.monotonic() + timeout
        ready = moved = False
        while time.monotonic() < deadline and not moved:
            inbox = client.poll()
            if inbox.crash is not None:
                return 1
            if inbox.ready and not ready:
                ready = True
                client.send(Step(5))
            if ready and inbox.frame is not None and inbox.frame.tick > 0:
                moved = True
            time.sleep(0.02)
        return 0 if moved else 1
    finally:
        client.close()


def run(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    quiet_streams()
    args = sys.argv[1:] if argv is None else argv
    if args == ["--selftest"]:
        return selftest()
    from evolution_simulator.viewer.app import main

    return main(args)


if __name__ == "__main__":
    sys.exit(run())
