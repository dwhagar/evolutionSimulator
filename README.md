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
