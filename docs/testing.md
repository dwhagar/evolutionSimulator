# Testing, profiling and benchmarks

All of this needs the `dev` extra: `pip install -e ".[dev]"` (add `,gui` for the window and its
tests). It holds `pytest`, `ruff`, `pytest-xdist`, `hypothesis`, `pyinstrument` and
`pytest-benchmark`, with lower bounds only. Nothing in it is a dependency of the program, so none of it
ships to players (the Windows zip is built from the `package` extra).

## Running the tests

```bash
pytest                     # the whole suite, one process
pytest -n auto             # the same, one worker per core
pytest -n 4                # a chosen number of workers
pytest tests/test_combat.py -p no:xdist   # one test, no workers
```

The suite is a little over three minutes serial on a 4-core machine and about a minute with
`-n auto` (INFRA.7 measured 195 s against 66 s, with 1,700 tests either way). The weekly CI uses
`-n auto`.

- `-n auto` is not in `pyproject.toml`'s `addopts`, so a single test run from the editor starts no
  workers; add it when running the whole suite.
- The window tests use Qt's offscreen platform. The `qapp` fixture in `tests/conftest.py` sets
  `QT_QPA_PLATFORM=offscreen` before the first `QApplication` is made, and each xdist worker is its own
  process with its own `QApplication`, so nothing needs setting by hand. On Linux Qt still needs
  `libegl1` and `libxkbcommon0`.
- Tests write only under `tmp_path` and never to the player's runs folder, which is what keeps workers
  from stepping on each other. A test that writes somewhere shared would fail under `-n auto` and
  should be fixed to use `tmp_path`, not skipped. If a failure only shows up with workers, rerun that
  test with `-p no:xdist` to see whether it is the test or the parallel run.
- `ruff check .` and `ruff format --check .` are part of CI too.

### Property tests

`hypothesis` is there for tests that state a rule and let it try many inputs (a round trip through
`to_data` and `from_data`, a counts-stay-in-bounds rule). Use `@given(...)` as usual; a failing case is
saved under `.hypothesis/` (ignored by git) and replayed on the next run. Keep `max_examples` modest
(`@settings(max_examples=50)`) so the suite stays quick.

## Profiling

`pyinstrument` samples the program and prints where the time went, which is the first thing to try
before changing anything for speed.

```bash
# a headless run
pyinstrument -m evolution_simulator run --until 30d --out /tmp/profile-runs
# the same, as a page you can open (flame graph and call tree)
pyinstrument -r html -o profile.html -m evolution_simulator run --until 30d --out /tmp/profile-runs
# one slow test
pyinstrument -m pytest tests/test_combat.py -p no:xdist -x
# a piece of code
python -c "
from pyinstrument import Profiler
from evolution_simulator.world import World, WorldConfig
world = World(WorldConfig(seed=1)); world.populate(animals=300, plants=1000)
with Profiler() as p:
    world.run(200)
p.print()
"
```

Profile with the same seed and counts before and after a change, and keep the numbers in the pull
request. `profile.html` and similar output stay out of git.

## Benchmarks

`pytest-benchmark` times a function over repeated rounds and compares runs. The measurements live in
`benchmarks/`, outside `testpaths`, so the plain `pytest` never runs them:

```bash
pytest benchmarks --benchmark-only                         # time them
pytest benchmarks --benchmark-only --benchmark-save=before # keep the result in .benchmarks/
# ... change the code ...
pytest benchmarks --benchmark-only --benchmark-compare=0001  # against the saved one
```

Run benchmarks serial (xdist turns the benchmark off, with a warning) and on a quiet machine; the
timings are only comparable between runs on the same computer. Add a benchmark by writing a test in
`benchmarks/` that takes the `benchmark` fixture; `benchmarks/test_world_step.py` is the model.
`scripts/bench_storage.py` is a one-off measurement script for the run store (STORE.1), not a
pytest-benchmark file.
