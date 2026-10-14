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

## Running without a window

```bash
python -m evolution_simulator run --until 100y --out runs/       # new run, saved as it goes
python -m evolution_simulator run --resume latest --until 200y --out runs/
python -m evolution_simulator list --out runs/
```

Each run is a folder with its settings, history and checkpoints; see [docs/design/ux.md](docs/design/ux.md).

## Project layout

```
src/evolution_simulator/   package source
tests/                     pytest test suite
docs/                      roadmap, design, research, archive
scripts/version.py         prints the current MAJOR.minor.build version
```

## Versioning

Versions are `MAJOR.minor.build`, and every merge into main bumps the build. See [docs/versioning.md](docs/versioning.md).

## Continuous integration

CI runs once a week, Mondays at 07:00 UTC, on a schedule only. It does not run on pushes or pull requests.

## License

Released into the public domain under [CC0 1.0 Universal](LICENSE).
