# Research: Python packages that could help the simulator

Status: first full pass, written by a Research thread on 2026-10-14 at the owner's request ("what python packages might help this, search through math, science, graphics, biological, everything that might possibly help, find all possibilities, evaluate"). Research only: nothing here has been added to `pyproject.toml`.

Scope: about 150 packages in every field the simulator touches, each checked against the constraints in [section 4](#4-the-constraints-that-decide-most-verdicts), and a handful measured against the real code. What already exists is not re-recommended (see [section 9](#9-what-the-project-already-has)).

## 1. The short version

- **Nothing on the list is worth adding to the core right now.** The core is dependency-free on purpose (`dependencies = []`), a test keeps Qt and numpy out of it, and saved worlds are checked against a `state_digest` that a differently-rounding fast path would break. The measured gains from the obvious candidates (SciPy's KD-tree, numpy, numba) are real but small against that cost, because the time in a tick is spread over sensing, brains, plants and bookkeeping, not in one loop ([section 3](#3-where-a-tick-spends-its-time)).
- **Two changes need no package at all and are the best returns found:**
  1. *Genome distance as one big integer.* Python's `int(text, 4)` reads a base-4 genome in 1.8 microseconds, and `((a ^ b) | ((a ^ b) >> 1)) & mask` followed by `int.bit_count()` counts differing digits in C. All 45,000 pairs among 300 genomes take **19 ms instead of 1,101 ms (58 times faster)**, with identical answers. That is the expensive step of the species tracker (`SPECIES.1`).
  2. *Lower the gzip level.* Saves use `compresslevel=6` (`world/persistence.py:666`, `history/recorder.py:386`). Level 1 is 4 times faster for a file 18% larger (measured on a 1,000-animal world).
- **The viewer already has what it needs.** PySide6 and pyqtgraph cover the species charts (`UX.41`) and the family tree (`UX.39`); no graph-layout, dendrogram or colour package is needed, and the GPL-licensed tree libraries would be a problem to ship anyway.
- **A few dev-only packages are worth adding to the `dev` extra:** `hypothesis` (properties of DNA and crossover), `pyinstrument` (profiling), `pytest-xdist` (the local suite takes 111 s serially and 47 s on 4 cores, which matters because CI runs weekly), and, for calibration runs, `optuna`.
- **The one real fork is speed, and it is the owner's call** (decision 1 in [section 7](#7-decisions-for-the-owner)). At the world caps (1,000 animals, 5,000 plants) a tick takes about 175 ms, which is a quarter of a simulated day per real second. No drop-in package gets the 4 times needed to reach a day per second; that takes a structural change to arrays (numpy, possibly numba) and its price is the core losing its zero-dependency, bit-for-bit property.
- **Licences to keep out of anything that ships:** GPL/AGPL (`ete3`, `ete4`, `python-igraph`, `graph-tool`, `simuPOP`, `msprime`, `python-Levenshtein`, `toytree`, `grandalf`, `pingouin`, `Nuitka` per its PyPI entry) and LGPL libraries that add nothing (`pykdtree`, `DEAP`). They are fine for the owner's own offline analysis in a separate environment, never as imports of the app.

## 2. How this was done

- **Repo first.** Read `pyproject.toml`, `docs/design/ux.md`, `world.md`, `docs/decisions.md`, TODO.md, and the code for the spatial index, brain, DNA, lineage, persistence, run store and recorder, so that nothing already built is recommended.
- **Metadata from PyPI on 2026-10-14** for every package named below: latest version, licence, `requires_python`, and whether a Windows (win_amd64) or pure-Python wheel exists for Python 3.12 and 3.13. "Windows wheel" below means a wheel is published, so `pip install` needs no compiler. Sizes are the largest Windows wheel.
- **Measurements on this sandbox** (CPython 3.13, one thread used, 4 cores, Linux; Windows numbers will differ, ratios should hold) with the project's own `World`, `DNA`, `Brain` and `persistence` code. Method and results are in the [appendix](#10-appendix-measurements).
- **Not checked:** how the packages behave inside a PyInstaller build on Windows, PyPy (the download host was unreachable from here), and anything on the owner's own machine. Statements from memory about third-party features are marked "from memory".

## 3. Where a tick spends its time

`cProfile` on 300 animals and 3,000 plants (the profiler inflates everything about 2 times, so read the shares, not the seconds). Plain timings without the profiler are in the second table.

| Part of the tick | Share of the tick | Notes |
| --- | --- | --- |
| Sensing (`world/senses.perceive`, `sensing.sense`) | about 40% | Builds each animal's inputs from neighbours |
| of which neighbour search (`SpatialIndex.within_reach`, `query_with_distance`) | about 25% | Pure-Python grid; `math.dist` called 2.4 million times in 60 ticks |
| Brain (`Brain.decide_with_hidden`) | about 5% | 6 microseconds per decision |
| Competition and grazing bookkeeping | about 13% | `_refresh_competition`, `_graze` |
| Plant growth (`update_growth_and_metabolism`, `set_environmental_conditions`) | about 6% | Called per plant per tick (143,940 calls in 60 ticks) |
| Sleep, learning, metabolism and the rest | the remainder | |

| World | Time per tick | Ticks per second | Simulated time per real second at the hourly tick |
| --- | --- | --- | --- |
| 60 animals, 300 plants | 4.3 ms | about 230 | about 9 days |
| 300 animals, 3,000 plants | 38 to 46 ms | about 24 | about 1 day |
| 1,000 animals, 5,000 plants | 170 to 178 ms | about 5.8 | about a quarter of a day |

These agree with `docs/design/ux.md` ("44 ms per tick at 300 animals and 3,000 plants"). The consequence for package choice: the work is *wide* (many small steps for many creatures), not *deep*. Replacing the neighbour search with a C library would save at most a quarter of a tick, and replacing the brain a twentieth.

## 4. The constraints that decide most verdicts

1. **The core has no dependencies, and a test enforces it.** `pyproject.toml` has `dependencies = []`; `ux.md` says "No Qt and no numpy". Any package below that the *core* would import breaks that rule. The `gui` extra (PySide6-Essentials, numpy, pyqtgraph) is where packages are allowed to live today.
2. **Runs must repeat exactly.** One seeded `random.Random` feeds everything, organisms are visited in id order, and `World.state_digest()` is verified when a save is loaded (`SaveFormatError` if the restored state does not reproduce it). Consequences found by measurement or from the documentation:
   - A numpy batched brain differs from the pure-Python `Brain.decide` in the last bits (largest difference 8.7e-16 in my test). A world saved by one path and loaded under the other would fail the digest check, or drift apart over many ticks. Any accelerated path must be the *only* path, or be proven bit-identical.
   - numpy's `Generator` does not promise the same stream across numpy versions (from memory of its compatibility policy; only the legacy `RandomState` is frozen). The standard library's `random.Random` is the safer source for anything saved.
   - numba compiles `math.tanh` through LLVM, not the C library the interpreter uses, so equal results are not guaranteed either.
3. **Windows first, Python 3.12+.** Every verdict below says whether a Windows wheel exists for 3.12 and 3.13. Source-only packages need a C compiler on the owner's machine and are treated as a "no".
4. **CC0 project, bundled Windows zip.** The code can depend on anything, but the zip (`UX.19`, PyInstaller folder build) ships the dependencies, so their licences bind the *distribution*. Permissive (MIT, BSD, Apache, PSF) is fine. LGPL (PySide6) is accepted already, handled by shipping a folder build. GPL and AGPL are not acceptable in the shipped app.
5. **CI is weekly.** Heavy local tooling costs the owner time directly, and anything that needs a compiler in CI (Cython, mypyc builds) needs a build workflow the owner starts by hand.
6. **Size.** A 40 MB wheel is only a cost for the zip. SciPy (37 MB) would be the biggest addition to a build that already carries 82 MB of Qt.

## 5. Findings by field

Verdict key: **Use** (already in or no downside), **Adopt when** (a named task triggers it), **Dev** (development tools, not shipped), **Watch** (plausible later, not now), **Skip** (with reason).

### 5.1 Math and numerics

| Package | Version, licence, Windows | What it would do here | Verdict |
| --- | --- | --- | --- |
| `numpy` | 2.5.4, BSD-3 (bundled parts permissive), 12.9 MB wheel, 3.12 to 3.14 | Frame blocks, charts, offline fits (already in `gui`). In the core: batched brains, array sensing | **Use** in the viewer; core is decision 1 |
| `scipy` | 1.18.1, BSD, 37.4 MB | `cKDTree` neighbour search, `pdist`, `linkage`/`fcluster`/`dendrogram`, `ndimage` for a scent field | **Adopt when** decision 1 allows numpy in the core, or for viewer-side analysis |
| `numba` | 0.68.0, BSD, 2.8 MB + `llvmlite`, 3.12 to 3.14 | JIT-compiles loops. Measured: 1,000 brains in 0.45 ms against 6.1 ms pure Python (13 times) and 0.20 ms for numpy's `einsum` (30 times) | **Watch.** Brains are 5% of a tick; a start-up compile cost, a cache folder problem in a frozen app, a larger PyInstaller bundle, and the float-equality issue in section 4 |
| `Cython` | 3.3.0, Apache-2.0, Windows wheel | Compile hot modules to C | **Skip.** Needs MSVC for any build; the owner's weekly-CI rule makes a build pipeline a project of its own |
| `mypyc` (ships with `mypy` 2.4.0, MIT) | Windows wheel for mypy | Compiles annotated Python unchanged. **Tried:** `world/spatial.py` compiled in 6 s with identical digests and *no measurable speed-up* (38.4 against 41.1 ms and 174.9 against 169.9 ms per tick, within noise). Compiling `vector.py` too failed twice (`__rmul__ = __mul__` aliasing and `object.__new__`), so `Vec` would need edits | **Skip** |
| `pythran` | 0.19.0 | Numpy-kernel compiler | **Skip.** Needs a C++ compiler |
| `jax` | 0.11.2, Apache-2.0 | Whole-world array programming on CPU/GPU | **Skip.** Means rewriting the simulator as arrays; the design is per-creature objects with variable genome decoding, learning and events |
| `torch` | 2.14.1, 124 MB wheel | Neural nets | **Skip.** 124 MB for a 20-8-6 network |
| `warp-lang`, `taichi` | Apache-2.0; taichi last released 2025-07, 83 MB | GPU/CPU kernels | **Skip.** Same rewrite reason; taichi looks unmaintained |
| `numexpr`, `bottleneck` | MIT, BSD-2 | Faster array expressions | **Skip.** Nothing array-shaped in the core to speed up |
| `pint` | 0.26.1, BSD | Units | **Skip.** The simulation deliberately has no real-world units |

### 5.2 Spatial indexing and geometry

| Package | Version, licence, Windows | Measured or reasoned | Verdict |
| --- | --- | --- | --- |
| `scipy.spatial.cKDTree` | see SciPy | 1,000 animals each querying 60 units over 1,000 animals and 5,000 plants: **41 ms with the current grid, 9.3 ms with two KD-trees** (build plus one batched `query_ball_point`), identical 65,862 hits. Rebuilding the animal tree costs 0.12 ms, the plant tree 1.0 ms. About 4 times on the neighbour search, so at best 25% of a whole tick. It returns unordered lists, so the "ids in order" rule needs a sort | **Adopt when** decision 1 is yes |
| `pykdtree` | 1.4.3, **LGPL-3.0+**, Windows | A faster KD-tree but only nearest-neighbour style queries | **Skip** |
| `shapely` | 2.2.0, BSD-3, 1.9 MB | `STRtree`, polygons, intersections | **Watch.** Only if walls become polygons, lakes or obstacles |
| `rtree` | 1.4.1, MIT, Windows wheel | Dynamic R-tree (libspatialindex) | **Skip.** A grid is simpler and better for points |
| `freud-analysis` | 3.6.1, BSD-3 | Fast cell lists, periodic boxes | **Skip.** The world has walls, not wrap-around |
| `scikit-learn` `BallTree`/`KDTree` | see 5.5 | | **Skip.** `cKDTree` is lighter |
| `hnswlib`, `annoy`, `faiss-cpu` | no Windows wheel (hnswlib, annoy); faiss MIT, 16.6 MB | Approximate nearest neighbour for high dimensions | **Skip.** Genomes are compared in samples of a few hundred; exact is cheap |
| Tuning the existing grid (no package) | | The grid stores tuples per entry and calls `math.dist` once per candidate. Cheaper cells, fewer candidate rings and reusing the query one animal made for plants and animals are the cheap lever | See recommendation 2 |

### 5.3 Biology, genetics and phylogeny

Genomes are fixed-layout (the layout, not alignment, says what each digit means), with no insertions or deletions. That makes Hamming distance the right measure and sequence-alignment tools the wrong shape.

| Package | Version, licence, Windows | Verdict and reason |
| --- | --- | --- |
| *Big-integer Hamming (stdlib)* | `int(str(dna), 4)` then XOR, fold, `bit_count()` | **Use** (recommendation 1). 19 ms for all pairs of 300 genomes against 1,101 ms now; the packed int can be cached on the immutable `DNA` |
| `rapidfuzz` | 3.14.6, MIT, 1.8 MB | `process.cdist` with `Hamming`: 13 ms for the same 300 × 300. Not needed beside the big-int trick; useful only for a one-off analysis over thousands of genomes with `workers=-1`. **Skip** |
| `scipy.spatial.distance.pdist` | | 25 ms for the same job; only if SciPy is in anyway |
| `editdistance`, `python-Levenshtein`, `bitarray` | MIT; **GPL-2+**; PSF-2.0 | Edit distance and bit arrays. **Skip** (no indels; Levenshtein is GPL; bitarray adds nothing over `int`) |
| `biopython` | 1.88, Biopython licence (permissive), Windows | Alignments, trees (`Bio.Phylo`), Newick I/O. **Skip** for the app. Handy for the owner's own work on exported trees |
| `scikit-bio` | 0.7.4, BSD-3, 7 MB but many dependencies | Neighbour-joining and UPGMA trees, diversity measures. **Watch** offline. Shannon and Simpson diversity are five lines each; UPGMA on 300 leaves is about 60 lines |
| `dendropy` | 5.1.1, BSD, pure Python | Tree objects, Newick and NEXUS I/O, tree balance and diversity statistics, birth-death tree simulation. **Watch** as an offline tool, e.g. to read a species tree exported as Newick (Newick is trivial to write by hand) |
| `tskit` | 1.0.3, MIT, 0.5 MB, Windows wheel | Tree-sequence ancestry store: records every birth as parents plus recombination points and `simplify()` discards everything with no living descendant. Fits "who descends from whom" at millions of births in a few bytes each, and gives most-recent-common-ancestor queries. Costs a new concept (genome coordinates, nodes, edges) and hooks into every crossover. **Watch.** The upgrade path if the bounded lineage record planned in `UX.39` is not enough |
| `msprime`, `simuPOP`, `ete3`, `ete4`, `toytree` | **GPL** (all five); ete3/ete4/simuPOP no Windows wheel | **Skip** (licence) |
| `pyslim` | 1.1.1, MIT | Bridge to SLiM, a separate program. **Skip** |
| `networkx` | 3.7, BSD-3, pure Python | Ancestor/descendant, DAG tools. **Measured:** 200,000 individuals with two parents: build 1.95 s, all ancestors of one animal 268 ms. A plain list of parent tuples answers "ancestors up to depth 8" in 0.13 ms. **Watch** for offline analysis of exported lineages |
| `rustworkx` | 0.18.1, Apache-2.0, Windows | Same job, build 0.73 s, all ancestors 28 ms. **Skip** unless lineage analysis ever runs inside the app |
| `python-igraph`, `graph-tool` | **GPL**; graph-tool has no Windows build | **Skip** |

### 5.4 Evolution, agents and simulation frameworks

The simulator's selection is emergent (creatures live, breed and die in a world), not a loop that scores a population against a fitness function. Almost every evolutionary-computation library owns that loop, so they do not fit.

| Package | Version, licence | Verdict and reason |
| --- | --- | --- |
| `DEAP` | 1.4.4, **LGPL** | **Skip.** Its operators are bitstring or list generic; ours are layout- and block-aware (`crossover_by_unit` keeps a neuron's wiring together) |
| `neat-python` | 2.0.0, BSD-3 | **Skip.** NEAT grows topology; the brain is a fixed maximum shape with on/off genes (`BRAIN.23`). Worth reading for *prior art on speciation*: NEAT's compatibility distance with a threshold is the classic species definition, which `SPECIES.1` improves on with a spread-aware gap |
| `PyGAD`, `pymoo`, `evotorch`, `evosax`, `pyribs`, `inspyred` | various permissive | **Skip.** Same reason |
| `cma` | 4.5.0, BSD-3 | CMA-ES parameter search. **Adopt when** calibrating world constants offline (see `optuna`) |
| `optuna` | 5.0.0, MIT (from memory; the PyPI licence field is empty), pure Python | Parameter search with parallel trials and an SQLite store. The use: find energy, plant and birth constants that keep a founder population alive (the `WORLD.15` and `WORLD.17` problem), each trial a short headless run. **Dev** (with `ProcessPoolExecutor` from the standard library, `concurrent.futures`, for the parallel runs) |
| `nevergrad` | 1.0.12, MIT | Same job, 139 dependencies listed. **Skip** |
| `mesa` | 3.5.1, Apache-2.0, 3.12+, pure Python | Agent-based modelling framework with its own scheduler, space and web viewer. **Skip.** The core already exists and the viewer is decided native |
| `agentpy`, `gymnasium` | last release 2021; MIT | **Skip** |
| `pymunk` | 7.3.1, MIT, Windows | Rigid-body physics (Chipmunk2D). **Watch.** The world has no collisions between bodies today; this is the package if that is ever wanted |
| Open-ended-evolution measures (evolutionary activity, novelty) | | No maintained package found. Anything wanted here would be written, from the literature |

### 5.5 Statistics, data analysis and clustering

For *species* (`SPECIES.1`) the clustering step per sample is small: at most 300 genomes. Measured on three drifted lines of 100 genomes each:

| Tool | Time for 300 genomes | Result |
| --- | --- | --- |
| scipy `linkage` (average) then `fcluster` at 0.10 | 27 ms | 3 clusters |
| scikit-learn `DBSCAN`, precomputed distances | 5.8 ms | 3 clusters |
| scikit-learn `HDBSCAN`, precomputed distances | 6.1 ms | 3 clusters |
| scikit-learn `PCA` to 2 dimensions (for a "genome map") | 13.6 ms | |

These libraries cluster *one sample*. What `SPECIES.1` needs beyond that (stable species ids across samples, the "separated for 3 samples in a row" rule, splitting, merging, parent species) is bookkeeping none of them provide, so the library would replace only the 20 lines that cut the sample into groups. With the big-int distance, a pure-Python single-linkage cut over 300 genomes is quick enough to stay in the core.

| Package | Version, licence, Windows | Verdict |
| --- | --- | --- |
| `scikit-learn` | 1.9.1, BSD-3, 8.7 MB + SciPy | **Watch.** Clustering and PCA for a viewer "genome map" scatter (colour by species) would be a nice extra; add it only with that feature |
| `hdbscan`, `fastcluster`, `umap-learn`, `openTSNE`, `pacmap` | BSD-ish; umap pulls numba | **Skip.** sklearn's `HDBSCAN` and PCA cover this; UMAP/t-SNE are heavy and their maps change run to run |
| `statsmodels` | 0.15.0, BSD-3, 11.6 MB | **Skip** in the app. Time-series tools for the owner's offline work |
| `pandas`, `polars` | 3.0.6 BSD; 2.0.0 MIT | **Skip** in the app (pandas is a 10 MB wheel with dependencies). Provide CSV export (standard `csv`) so the owner can use either in a notebook |
| `pingouin` | 0.7.0, **GPL-3** | **Skip** |
| `duckdb` | 1.5.6, MIT, 13.7 MB | **Watch** as an owner-side tool: reads CSV, Parquet and SQLite and answers questions about a history in SQL. Not a dependency |

### 5.6 Graphics, charts and the viewer

| Package | Version, licence, Windows | Verdict |
| --- | --- | --- |
| `PySide6-Essentials` | 6.12.0, LGPL-3 / GPL, abi3 wheels, 82 MB | **Use** (already). `PySide6-Addons` (40.5 MB) holds Qt Charts, Qt Multimedia and others (from memory of Qt's wheel split) if ever needed |
| `pyqtgraph` | 0.14.0, MIT, pure Python | **Use** (already). Time series (`PlotCurveItem` with downsampling), `ScatterPlotItem` (genome map), `GraphItem` (trees), `ImageItem` (heat maps, scent field), exporters (PNG/SVG). Its docs say colormaps load from matplotlib or colorcet if installed (from memory), but it bundles its own |
| `matplotlib` | 3.11.2, PSF-based | **Skip** in the app: slower to redraw than pyqtgraph and a 9.6 MB wheel with dependencies. Fine for figures in docs |
| `vispy`, `moderngl`, `pyopengl` | BSD-3, MIT, BSD | **Watch.** The software raster path draws 1,000 animals in 8 ms (`ux.md`); a GPU scatter only pays off past roughly 10,000 drawn creatures |
| `pyglet`, `arcade`, `pygame-ce`, `dearpygui` | MIT, MIT, **LGPL**, MIT | **Skip.** Already weighed in `ux.md` |
| `plotly`, `bokeh`, `holoviews`, `datashader`, `seaborn` | web and notebook tools | **Skip.** The owner chose native only ([#123](https://github.com/dwhagar/evolutionSimulator/issues/123)) |
| `distinctipy`, `colorcet`, `cmcrameri` | MIT, **CC-BY-4.0**, MIT | **Skip.** A stable colour per species id is ten lines (golden-angle hue steps, fixed lightness, or the Okabe-Ito palette for the first eight); `colorcet` needs attribution |
| `pygraphviz`, `graphviz` | BSD-3 (Windows wheel), MIT | **Skip.** A second renderer plus Graphviz binaries. A family tree has natural layers (generation), so rows by generation with a barycentre ordering is a short function; a tree of species is a handful of nodes |
| `scipy.cluster.hierarchy.dendrogram(no_plot=True)` | | Returns line coordinates (from memory) that pyqtgraph can draw, if a genetic-distance dendrogram is ever wanted. **Watch** |
| `Pillow` | 12.3.0, MIT-CMU, 7.2 MB | **Adopt when** UX.40 video export starts, for GIF and PNG sequences |
| `PyAV`, `imageio-ffmpeg`, `opencv-python`, `moviepy` | BSD-3, BSD, Apache-2.0, MIT; 29, 31, 44 and 58 MB | **Watch** for MP4 export (`UX.40`). Check the licence of the FFmpeg build each bundles before shipping (builds with x264 are GPL; from memory, not verified) |
| `skia-python` | 144.0, BSD | **Skip** |

### 5.7 Data storage and serialisation

The brief says storage is SQLite. The run store today is JSON and gzip files (`runs/store.py`: `run.json`, `world.json.gz`, `history.json.gz`), and I found no SQLite in the code or docs, so both are covered. Standard `sqlite3` does everything needed (100,000 history rows insert in 87 ms in memory), so no wrapper package is recommended.

| Package | Version, licence, Windows | Measured or reasoned | Verdict |
| --- | --- | --- | --- |
| `sqlite3` (standard library) | | Enough for history, species and lineage tables | **Use** |
| `apsw`, `SQLAlchemy`, `peewee`, `sqlite-utils` | 3.54 (OSI), 2.1.4 MIT, MIT-ish, Apache-2.0 | | **Skip.** The schema is a few tables; an ORM adds weight and a second way to write the same SQL |
| `orjson` | 3.13.0, MPL-2.0 AND (Apache-2.0 OR MIT), 0.1 MB | `dumps` of a 1,000-animal, 2,700-plant world (10.4 MB of JSON): **38 ms against 219 ms**. Loading was no faster in my run (162 against 128 ms, noisy) | **Watch.** Dumping is not the biggest part of a save (`world_to_dict` itself takes 364 ms) |
| `msgspec` | 0.22.0, BSD-3 | msgpack encode 11 ms and 6.7 MB (a third smaller than JSON). Binary, so saves stop being readable | **Skip** (the saves are deliberately plain JSON) |
| `msgpack`, `ormsgpack`, `cbor2`, `ujson` | | | **Skip** |
| `zstandard` | 0.25.0, BSD-3, 0.5 MB | level 3: 60 ms, 2.94 MB; level 9: 309 ms, 2.74 MB; against gzip level 6: 486 ms, 2.84 MB | **Watch.** Python 3.14 has `compression.zstd` in the standard library, and the project allows 3.12 and 3.13 |
| `lz4`, `blosc2` | BSD | | **Skip** |
| `h5py`, `tables`, `zarr`, `lmdb` | BSD, BSD, MIT, OpenLDAP | Array stores | **Skip.** The data is small and row-shaped |
| `pyarrow` | 26.0.0, Apache-2.0, 29 MB | Parquet export | **Skip** as a dependency |
| `pydantic`, `attrs`, `cattrs` | MIT | Validation and structuring | **Skip.** Frozen dataclasses with a version field already do it |
| `PyYAML`, `ruamel.yaml`, `tomli-w`, `jsonschema` | MIT | Config formats. Reading TOML is in the standard library (`tomllib`) | **Skip** unless presets move off JSON |

Gzip, measured on the same world: level 1: 119 ms, 3.35 MB; level 6 (current): 486 ms, 2.84 MB. Levels do not change what is stored.

### 5.8 Performance, parallelism and profiling

| Package | Version, licence, Windows | Verdict |
| --- | --- | --- |
| `multiprocessing` / `concurrent.futures` (standard library) | | **Use.** Already the process host. A `ProcessPoolExecutor` with `spawn` runs many independent seeds or parameter sets at once, the right tool for calibration and for "does a pattern emerge" experiments |
| `joblib`, `dask`, `ray` | BSD-3, BSD-3, Apache-2.0 (285 dependencies listed) | **Skip** |
| Free-threaded CPython (3.14t) | numpy, SciPy and numba publish `cp314t` wheels, but PySide6 publishes `abi3` wheels only | **Skip.** The viewer cannot use it, and the simulation is not written to be threaded |
| PyPy | not checked | **Not assessed.** The core is pure Python and might run faster there, but PySide6 and the 3.12+ requirement make it a headless-only option; worth a one-hour test by whoever has PyPy for 3.12 |
| `pyinstrument` | 5.1.3, BSD, Windows wheel | **Dev.** Low-overhead sampling profiler with readable output (the standard `cProfile` used here slows runs 2 times) |
| `py-spy`, `scalene`, `line-profiler`, `snakeviz`, `memray` | MIT, Apache-2.0, BSD, BSD; memray has no Windows build | **Dev, optional.** `py-spy` attaches to a running viewer process; `memray` is Linux and macOS only |
| `pytest-benchmark` | 5.3.0, BSD-2 | **Dev.** Budgets for the numbers in section 3 (a tick at a fixed world must not slow by more than X%) |
| `psutil` | 7.2.2, BSD-3, 0.1 MB | **Watch.** Memory and CPU in the status bar; the run store already warns on disk size |
| `platformdirs` | 4.13.0, MIT | **Skip.** `runs/paths.py` already does the Windows, macOS and Linux data folders |

### 5.9 Testing, quality and build tools

| Package | Version, licence | Verdict and reason |
| --- | --- | --- |
| `hypothesis` | 6.169.2, MPL-2.0 (dev only) | **Dev, recommended.** Property tests suit the DNA code: any crossover of two compatible genomes has only parent digits where the operator promises it, `mutated` at rate 0 is the identity, `DNA.distance` is symmetric and 0 only for equal genomes, `from_dict(to_dict(x)) == x` |
| `pytest-xdist` | 3.8.0, MIT | **Dev, recommended.** The whole suite (1,238 tests; viewer tests skipped without PySide6) took **111 s serially and 47 s with `-n 4`** here. CI is weekly, so the owner's local runs are the CI |
| `pytest-qt` | 4.5.0, MIT | **Watch.** The project has its own offscreen `qapp` fixture; `qtbot` would add signal waits and simulated clicks |
| `pytest-cov`, `mutmut` | MIT, BSD-3 | **Skip** for now |
| `mypy` / `pyright` / `ty` | 2.4.0 MIT; 1.1.414 MIT; 0.0.87 MIT | **Watch.** The code is fully annotated; a type pass would catch drift between the session messages and the viewer. Not needed for packages, only for quality |
| `ruff` | 0.17.0, MIT | **Use** (already) |
| `uv` | 0.13.1, MIT or Apache-2.0 | **Watch.** Fast installs for the owner's Windows environment |
| `pre-commit`, `nox` | MIT, Apache-2.0 | **Skip.** A weekly CI makes local hooks plausible, but one command (`ruff` and `pytest -n 4`) is simpler |
| `PyInstaller` | 6.22.3, GPL-2 with the bootloader exception, which allows any licence for the built program | **Use** (already, `package` extra) |
| `Nuitka` | 4.3, AGPL-3+ per its PyPI entry (the compiled program is not covered, but read the terms first) | **Skip.** Faster start and a harder-to-read binary; no need |
| `briefcase`, `cx-Freeze` | BSD-3, PSF | **Skip.** PyInstaller works |

### 5.10 Odds and ends

| Package | Verdict and reason |
| --- | --- |
| `opensimplex`, `perlin-noise`, `noise` | **Watch.** Terrain, resource patches or climate maps. `noise` was last released in 2015 and `perlin-noise` caps Python at below 3.13; `opensimplex` (MIT, pure Python) is the usable one. Not needed while the world is a flat plane |
| Scent field (`SENSE.20`) | A grid that decays and spreads is a handful of lines in numpy (`scipy.ndimage.gaussian_filter` for the spread) and, in pure Python, a sparse dict of cells updated only where scent exists. Cost decides: at 1000 × 1000 units with 10-unit cells that is 10,000 cells, trivial either way. No package needed, but numpy makes the diffusion step 50 to 100 times quicker if it is allowed (decision 1) |
| `rich`, `tqdm`, `typer`, `click` | **Skip.** `argparse` covers the headless command; progress output is a print |
| `structlog` | **Skip** |
| `sortedcontainers` | Apache-2.0, pure Python. **Skip** until some structure needs a sorted order kept as it changes |

## 6. Recommendations, in order

1. **Genome distance with big integers (no dependency).** Give `DNA` a cached packed form (`int(str(dna), 4)`; 1.8 µs per 1,260-digit genome) and a `distance` that uses XOR, fold the two bits, and `bit_count()`. Verify equal to the current `sum(map(ne, ...)) / length`, with a `hypothesis` test over random genomes. `DNA.distance` is also called on the hot path by `world/senses.similarity` (about 3,800 calls and 2% of the tick in the profile) and by `mating.py` mate ranking, so every caller gains. Expected: all pairs among 300 genomes in about 20 ms instead of 1.1 s, and a single comparison from about 24 µs to about 0.5 µs once the packed forms are cached.
2. **Profile-led tuning of sensing before any new library.** The neighbour search (a quarter of a tick) and `perceive` (a third) are pure-Python and allocate heavily. Candidate fixes need no dependency: cell entries kept as parallel lists instead of tuples, one cell walk shared by the animal and plant queries of the same animal, and skipping the plant search when nothing in range can matter. Gate each with the existing digest tests and measure with `pyinstrument` against the three worlds in section 3.
3. **Add a small `dev` extra:** `hypothesis`, `pytest-xdist`, `pyinstrument`, `pytest-benchmark`. Dev-only, MPL-2.0 / MIT / BSD licences, none shipped.
4. **Lower the gzip level** in `persistence.py` and `recorder.py` to 1 to 3 (autosave write is 4 times quicker for 18% more disk). Check the run-store size warning thresholds once.
5. **Species and family tree: build with what is there.** Pure-Python clustering over the big-int distances (`SPECIES.1`), pyqtgraph for charts (`UX.41`), a Qt scene with rows by generation for the tree (`UX.39`), a plain Newick writer for export. No new runtime package.
6. **Calibration tooling (`optuna`, or `cma`) as a dev tool** only when the world constants are next tuned; each trial is a short headless run in a process pool. Not needed to build `SPECIES` or `UX.39`.
7. **Revisit later, only on a named trigger:** `tskit` if the bounded lineage record is outgrown; `scipy` or `numba` if decision 1 goes the speed way; `pyav`/`Pillow` when `UX.40` video export starts; `pymunk` if bodies ever collide; `shapely` if the world gets polygon obstacles; `vispy` past about 10,000 drawn creatures.

## 7. Decisions for the owner

1. **Speed ambition, and with it whether the core may depend on numpy.** Today a world at the caps (1,000 animals, 5,000 plants) runs at about a quarter of a simulated day per real second; 300 animals and 3,000 plants runs at about a day per second. Which target do you want at the caps?
   - *A. Keep the core pure Python (recommended).* Tune it (recommendation 2), accept a quarter-day to half-day per second at the caps, keep exact saves and replays everywhere.
   - *B. Allow numpy (and SciPy) in the core as the only code path.* Rewrite sensing and movement as array code; my estimate, not measured: a 3 to 5 times gain is plausible for sensing and 1.5 to 2 times for the whole tick (the rest stays Python unless it is rewritten too). Costs: a big rewrite, a larger install, old saves no longer replay bit-for-bit, and the `no numpy in the core` test goes.
   - *C. Optional fast path.* Two code paths that must give the same bits; double the testing. Not recommended.
2. **May a `dev` extra with `hypothesis`, `pytest-xdist`, `pyinstrument` and `pytest-benchmark` be added?** Recommended yes: nothing ships and it cuts the local test run to about 40% of its time.
3. *(Later, not blocking.)* When video export (`UX.40`) is started: GIF and PNG sequences only (no licence worries), or MP4 with a bundled FFmpeg (which has licence terms to read first)?

## 8. Suggested tasks (for the TODO thread to turn into items)

- Big-integer `DNA.distance` with cached packed form and property test (recommendation 1). Small; unblocks `SPECIES.1` speed.
- Sensing performance pass with before-and-after timings (recommendation 2). Medium.
- `dev` extra and a `pytest-benchmark` budget for the three reference worlds (recommendations 3 and 2).
- gzip level change (recommendation 4). Small.
- Owner question for decision 1 (speed target and numpy in the core).
- Calibration run harness using a process pool and `optuna` (recommendation 6), after the `WORLD.15`/`WORLD.17` work lands.

## 9. What the project already has

So these are not recommended again: PySide6 and pyqtgraph viewer behind the `gui` extra; numpy in `gui`; PyInstaller in `package`; ruff and pytest in `dev`; multiprocessing process host with a pipe; JSON and gzip saves with versions and migrations (`persistence.py`, `runs/store.py`); a statistics recorder with tiered history (`history/`); a spatial grid index (`world/spatial.py`); `family_key` colouring (`lineage.py`); per-user data folders (`runs/paths.py`); a feed-forward `Brain`; layout-aware crossover and mutation (`dna.py`); a vector class (`world/vector.py`).

## 10. Appendix: measurements

Machine: the cloud sandbox, 4 cores, CPython 3.13, packages from PyPI as listed. All benchmarks used the project's own classes and the seeds shown; times are wall clock, best of the repeats noted, and vary by about 10% between runs.

| What | Setup | Result |
| --- | --- | --- |
| Tick time | `World(WorldConfig(seed=3))`, `populate(...)`, 20 ticks warm-up, 40 timed | 60/300: 4.3 ms; 300/3,000: 38 to 46 ms; 1,000/5,000: 171 to 178 ms |
| Profile | `cProfile`, 300/3,000, 60 ticks | shares in section 3 |
| Genome distance, all pairs | 300 living genomes of length 1,260, 45,000 pairs | current `sum(map(ne, a, b))`: 1,101 ms; big-int XOR + `bit_count`: 19 ms; `scipy pdist("hamming")`: 25 ms; `rapidfuzz.process.cdist` with `Hamming`: 13 ms; numpy broadcast: 497 ms. Packing one genome: `int(s, 4)` 1.8 µs, digit-shift loop 134 µs |
| Neighbour search | 1,000 animals and 5,000 plants uniform in 1,000 × 1,000, each animal queries radius 60 in both | current grid: 41 ms; `cKDTree` build plus batch query: 9.3 ms; same 65,862 hits; moving all 1,000 animals in the current grid: 2.3 ms |
| Brain | 20-8-6 network (222 numbers), 1,000 random brains and inputs | pure Python `decide`: 6.1 ms; numpy `einsum`: 0.20 ms (max difference 8.7e-16); numba `njit`: 0.45 ms after compile (first-call compile of a trivial function: 31 ms) |
| World save | 997 animals, 2,729 plants after 30 ticks | `world_to_dict` 364 ms; `json.dumps` 219 ms, 10.4 MB; `orjson.dumps` 38 ms; gzip level 6: 486 ms, 2.84 MB; level 1: 119 ms, 3.35 MB; zstd level 3: 60 ms, 2.94 MB; level 9: 309 ms, 2.74 MB; msgpack via msgspec 11 ms, 6.7 MB. Decompress and parse: gzip plus `json.loads` about 360 ms |
| SQLite | in-memory table, `executemany` | 100,000 rows in 87 ms |
| Clustering | three lines of 100 genomes, 12% apart, 2% noise | see section 5.5 |
| Lineage graph | 200,000 individuals, two parents each from the 5,000 before | plain list of parent tuples, ancestors to depth 8: 0.13 ms; networkx build 1.95 s, `ancestors` 268 ms; rustworkx build 0.73 s, `ancestors` 28 ms |
| mypyc | `spatial.py` compiled unchanged | 6 s build, identical `state_digest`, no measurable speed-up; with `vector.py`: `KeyError: '__mul__'` then `TypeError: object.__new__(Vec) is not safe` |
| Test suite | `pytest -q` in a venv without PySide6 | 1,238 passed, 10 skipped: 111 s serial, 47 s with `pytest-xdist -n 4` |

Numbers for the shape of a result are trustworthy; do not read the milliseconds as a promise for the owner's computer. Re-measure on Windows before acting on a close call.
