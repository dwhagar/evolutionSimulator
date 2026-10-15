# evolutionSimulator

An evolution simulator written in Python.

## Getting started

Requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`pip install -e ".[dev]"` also brings in the tools for testing faster and measuring (`pytest-xdist`,
`hypothesis`, `pyinstrument`, `pytest-benchmark`); none of them ship to players. Add `-n auto` to run
the tests on every core, and see [docs/testing.md](docs/testing.md) for profiling and benchmarks.

## Running without a window

```bash
python -m evolution_simulator run --until 100y --out runs/       # new run, saved as it goes
python -m evolution_simulator run --resume latest --until 200y --out runs/
python -m evolution_simulator list --out runs/
```

Each run is a folder with its settings, history and checkpoints; see [docs/design/ux.md](docs/design/ux.md).

## The window

```bash
pip install -e ".[gui]"
python -m evolution_simulator.viewer            # the real world, in its own process
python -m evolution_simulator.viewer --fake     # a made-up world, for trying the screens
```

A plain launch opens the newest saved run, or, with none saved, a new world with the default
founders and the New run panel to change them. `--new` (or `--seed`, `--animals`, `--plants`) starts a
new world even when runs are saved, and `--in-process` keeps the simulation in the window's own
process, for debugging. Closing the window on a world that was never saved asks "Save this run?".

## Windows download

A build for Windows is made on request (the "Package Windows" workflow in the Actions tab), as a zip
named `evolutionSimulator-<version>-win64.zip`. Unzip the whole folder and run `evolutionSimulator.exe`;
it opens the real world, the same as a plain launch above.
The program is not signed with a code-signing certificate, which costs money every year, so Windows
SmartScreen may say "Windows protected your PC" the first time: choose "More info", then "Run anyway".
The warning says the publisher is unknown, nothing more, and the source is all here to read. The zip
carries the licence notices for the libraries it includes (see `packaging/THIRD_PARTY_NOTICES.md`).

To build it yourself: `pip install -e ".[gui,package]"` then `python -m evolution_tools.package`.

## Project layout

```
src/evolution_simulator/   package source
tests/                     pytest test suite
benchmarks/                pytest-benchmark measurements (not part of the plain test run)
docs/                      roadmap, design, research, archive
src/evolution_tools/version.py         prints the current MAJOR.minor.build version
src/evolution_tools/package.py         builds the Windows zip (UX.19)
packaging/                 PyInstaller spec, entry point and notices
```

## Versioning

Versions are `MAJOR.minor.build`, and every merge into main bumps the build. See [docs/versioning.md](docs/versioning.md).

## Continuous integration

CI runs once a week, Mondays at 07:00 UTC, on a schedule only. It does not run on pushes or pull requests.

## License

Released into the public domain under [CC0 1.0 Universal](LICENSE).
