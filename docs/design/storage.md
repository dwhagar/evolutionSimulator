# Storing runs in SQLite

Design note for `STORE.1`, the plan for the build `STORE.2` (built; what differs from the plan is in
[ux.md](ux.md), "As built: the SQLite run file"). The owner decided on 2026-10-14 that data
storage is SQLite and not a database server ([decisions.md](../decisions.md)). This note says what goes in
the file, how it is written and read, how old runs come across, and what was measured. The numbers come
from `src/evolution_tools/bench_storage.py`; the schema there is the draft this note describes.

## The short version

- **One file per run: `<runs folder>/<run id>/run.sqlite`, in WAL mode**, opened with the standard
  library `sqlite3`. The core stays free of dependencies. The run keeps its folder, so the `-wal` and
  `-shm` files SQLite makes live beside it, and an export or a preset can sit next to it later.
- **A checkpoint is one transaction.** The world is the compressed JSON of `UX.9` (`save_world`'s bytes,
  no pickle) stored as a blob, with the recorder's state beside it. A crash leaves the last committed
  checkpoint and nothing half-written; this was tried by killing a writer 12 times in the middle of a
  write (below).
- **History is rows that are added as samples are taken**, not a file that is rewritten at each
  checkpoint: a row per value and per statistic of each sample, in the tiers the recorder already has.
  A viewer, or a second program, reads a chart's series while the simulation writes.
- **Retention is deletes**, with `auto_vacuum = INCREMENTAL` giving the space back at once; a full
  `VACUUM` is only for importing and for a "compact" button nobody has asked for yet.
- **Settings and presets stay JSON files** (the setup presets and `UX.35`'s shareable preset files): they are
  small, people edit and share them, and they are not run data.
- `RunStore` and `Run` keep their public API. Nothing outside `evolution_simulator/runs` and
  `evolution_simulator/history` needs to change for `STORE.2`, apart from a few tests and the places that
  name `run.json` (below).

## Why this and not the folder

The folder of `UX.10` works, and the measurements say the speed is not the reason. The reasons are what
the folder cannot do:

- **Appending history.** `history.json.gz` is rewritten whole at every checkpoint, so a chart is only as
  fresh as the last checkpoint, and nothing can read a run's history while a headless run writes it
  without racing the rewrite. Rows are appended once.
- **Reading while writing.** WAL gives a reader the last committed state without waiting for the writer
  (measured: a read with a writer's transaction open takes 0.1 ms and does not see the uncommitted row).
  This is what `UX.40`'s "watch a headless run" needs.
- **One thing to copy, delete or move.** A run is one file plus its two short-lived companions, not a
  tree of directories whose renames are not atomic together.
- **Queries.** "One series across the whole run", "the checkpoint nearest tick T", and for `SPECIES.2`
  and `UX.39` "the species alive on day D" and "the children of animal N" are indexed lookups.

It also costs something: one writer at a time per file (the simulation process, which is how it is
already), and a file that must stay on a local disk (below).

## What is in the file

```sql
PRAGMA application_id = 0x45565331;   -- "EVS1": this is an Evolution Simulator run
PRAGMA user_version   = 1;            -- the schema number; migrations run in order from here
PRAGMA journal_mode   = WAL;
PRAGMA synchronous    = NORMAL;       -- safe in WAL: a power cut can lose the last commits, not corrupt
PRAGMA auto_vacuum    = INCREMENTAL;  -- set before the first table exists
PRAGMA foreign_keys   = ON;
PRAGMA journal_size_limit = 8388608;  -- a WAL that grew for a checkpoint shrinks back

-- The manifest (what run.json holds now): one row per key, text values (JSON for structured ones).
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
--   format, kind='run', id, name, seed, program_version, created, updated,
--   config (config_to_dict JSON), setup (the starting animals, plants, seeded-founders choice and
--   seed as JSON, written when the run is created), summary (the run-list line as JSON),
--   writer (see below)

CREATE TABLE checkpoints (            -- what the Saved runs dock lists: small rows, no blobs
    id INTEGER PRIMARY KEY, tick INTEGER NOT NULL UNIQUE, simulated_seconds REAL NOT NULL,
    state_digest TEXT NOT NULL, animals INTEGER NOT NULL, plants INTEGER NOT NULL,
    written TEXT NOT NULL, has_history INTEGER NOT NULL,
    world_format INTEGER,             -- persistence.FORMAT_VERSION of the world blob (NULL: imported)
    encoding TEXT NOT NULL DEFAULT 'json+gzip');  -- how the two blobs are written
CREATE TABLE checkpoint_data (        -- the big part, read only to resume
    id INTEGER PRIMARY KEY REFERENCES checkpoints(id) ON DELETE CASCADE,
    world BLOB NOT NULL,              -- gzip of the world_to_dict JSON: the bytes world.json.gz holds
    recorder BLOB,                    -- gzip of Recorder.to_dict(): the bytes history.json.gz holds
    species BLOB);                    -- gzip of SpeciesTracker.to_dict(), NULL without a tracker

-- The history. A series name is stored once; the rows say which sample and which name.
CREATE TABLE names   (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE samples (tier INTEGER, day INTEGER, span INTEGER NOT NULL, tick INTEGER NOT NULL,
                      PRIMARY KEY (tier, day)) WITHOUT ROWID;        -- day = period the stretch ends at
CREATE TABLE level   (tier INTEGER, day INTEGER, name INTEGER, value REAL NOT NULL,
                      PRIMARY KEY (tier, day, name)) WITHOUT ROWID;  -- levels and flows (Sample.values)
CREATE TABLE stat    (tier INTEGER, day INTEGER, name INTEGER, n INTEGER NOT NULL, mean REAL NOT NULL,
                      std REAL NOT NULL, lo REAL NOT NULL, hi REAL NOT NULL, p10 REAL, p90 REAL,
                      PRIMARY KEY (tier, day, name)) WITHOUT ROWID;  -- Sample.stats
CREATE TABLE histogram (tier INTEGER, day INTEGER, name INTEGER, bins BLOB NOT NULL,
                      PRIMARY KEY (tier, day, name)) WITHOUT ROWID;  -- gene histograms (JSON list)
```

Reasons for the choices that are not obvious:

- **`meta.setup` is the starting setup**, written once by `RunStore.create` (through `Host._new_run`,
  `RunManager.save_now` and the other callers, which give it the `RunSetup` they started from). The
  folder manifest never recorded it, so "Copy with new seed" (`UX.35`, which found this) had to guess
  the counts from the tick-0 checkpoint or the first history sample, and both can be gone after
  pruning. An imported run has no `setup`; the import fills it from its oldest checkpoint when that
  still exists and leaves it out otherwise.
- **The world is the JSON of `UX.9`, as bytes.** The save format has its own version and migrations
  (`persistence.py`), and a run must open after the classes change; a database column per field would
  tie the file to the classes. The blob is exactly what `world.json.gz` holds, so importing an old run
  copies bytes without decoding a world.
- **`checkpoints` and `checkpoint_data` are two tables** so listing checkpoints never touches the
  blobs' pages, and deleting one is a cascade.
- **Each checkpoint keeps the recorder's whole state (tiers included) in its blob**, as now, and the
  history tables are the *live* copy. Resuming from an older checkpoint has to bring back the history
  as it was then, and the coarser tiers cannot be taken apart again once merged. So the rule is: the
  checkpoint is the authority. **On resume the history tables are emptied and refilled from the chosen
  checkpoint's recorder**, which also means samples written after the last checkpoint of a run that
  crashed are cut off, to match the world that comes back. The recorder state without its tiers is the
  births and deaths since the last sample, the lineage roots and the counters; the tiers add about
  10 KB, so nothing is saved by leaving them out.
- **History is rows per value and per statistic**, as the owner asked, because it keeps every later
  series free of schema changes: `UX.32` (percentile bands, lineage counts: already `stat.p10`/`p90`
  and `level` names `lineages.*`) and `SPECIES.2` (a level per species, named like
  `species.animal.<species id>`, with an "others" series) only add names. Reading one series is a scan
  of one tier's rows by name (0.6 ms for 296 points); the whole history reads in 41 ms.
- **`names` are small integers in the rows** (113 names in the benchmark) so a row is a few bytes.
- **The tiers in the tables are the recorder's ring buffers.** Each daily sample is applied as a short
  list of changes: add the new day to the finest tier, and when a tier is over capacity, remove its
  oldest sample and merge it into the next tier (delete the sample it merges with, add the merged one).
  The merge itself is still `Sample.merge`, so a loaded history is exactly what the recorder would
  hold. The cost is 0.9 ms a day on average (0.5 ms median, 28 ms at worst when a merge cascades
  through every tier), and the history tables stay about 2.4 MB however long the run: 296 samples
  after 100 simulated years.

### Later tables (not built by `STORE.2`)

Each is added by a migration (`user_version` 2, 3 ...), so an older program refuses a newer file with a
clear message and a newer one upgrades an older file in one transaction.

- `species(kind, id, parent, first_day, last_day, ...)` for `SPECIES.2`'s descriptive rows (id, age,
  parent, divergence); the series themselves are `level` rows. **Built by `SPECIES.2` as schema 2**
  (see `docs/design/species.md`, Recording); the series are named `species.<kind>.<id>`.
- `lineage(kind, id, mother, father, born, died, family)` for `UX.39`, written as births and deaths
  happen (a listener that batches a day at a time). It can grow without bound in a long run (every
  birth is a row), so it must be bounded, for example by dropping dead rows with no living descendant
  once they are more than a number of generations back; that rule is `UX.39`'s to choose.

## Writing

- **Who writes:** the simulation: the host process (`UX.31`) or the headless command. One at a time per
  run, as now. The writer sets `meta.writer` (`{"pid": ..., "started": ...}`) when it attaches a run and
  clears it when it closes. This is advisory, to tell a viewer the run is live and refuse a second
  writer on the same run (`UX.40`'s watching); a `writer` whose process is gone is a leftover from a
  crash and is taken over.
- **A checkpoint** is `BEGIN IMMEDIATE`; insert `checkpoints` and `checkpoint_data`; update `meta`
  (`updated`, `summary`); apply retention (below); `COMMIT`; then `PRAGMA wal_checkpoint(TRUNCATE)` so the
  WAL does not stay the size of a checkpoint. Serialising the world is by far the larger cost and is the
  same as before; it happens before the transaction starts.
- **The first checkpoint of a new run** writes `run.sqlite.part`'s schema, `meta` and the checkpoint,
  then moves the file into place, so a run folder either has a complete first checkpoint or no
  `run.sqlite` (the same guarantee `RunStore.create` gives now).
- **History** is appended by a sample listener the `Run` adds to the recorder it is given (the recorder
  already has `add_sample_listener`; `STORE.2` adds one for the tier changes). A transaction per sample.
- **Retention** (every 10 days, newest 3 plus the first of each simulated year, unchanged) is a `DELETE`
  of the checkpoints no longer kept, in the same transaction as the new checkpoint, followed by
  `PRAGMA incremental_vacuum` so the file shrinks at once. Without it the file settles at the size of
  the most checkpoints ever held at once (the new one is written before the oldest goes): 10.2 MB for
  three kept of 2.8 MB each, against 8.0 MB with it. A full `VACUUM` rewrites the whole file and is
  kept for the import and for a future "compact" action.
- **Threads.** The host steps the world and answers commands (`SaveNow`, `StartRun`) on one thread; its
  sender thread never touches a run. A `Run` still keeps one connection behind a lock with
  `check_same_thread=False`, so a viewer that saves from its own thread (the local backend) is safe.
- **Timeouts.** `busy_timeout` of 5 s on every connection; a reader never waits on the writer in WAL.

## Reading

- **The run list** (`RunStore.list_runs`) opens each `run.sqlite` read-only (`file:...?mode=ro`) and
  reads `meta` only. That is a few hundred microseconds a run, with no world touched, and works while a
  run is being written. A folder with neither `run.sqlite` nor an old `run.json` is skipped as now.
- **Charts and the History window** read the history tables: the whole thing builds a `HistorySamples`
  in about 40 ms, or one series by name. `Run.history()` returns the live history, so a chart on a
  headless run is current to the day, not to the last checkpoint.
- **Resume** reads one `checkpoint_data` row (10 ms to read and decompress 0.5 MB of gzip into 5.4 MB of JSON) and then loads the
  world as before; `load_world` itself takes about a second at 1,000 animals and 5,000 plants, and that
  is the same in either layout.
- **Opening for watching** (`UX.40`) uses a read-only connection and never writes, not even the `-shm`
  bookkeeping that WAL needs, where it can.

## Crash safety

SQLite commits a transaction atomically, so a kill, a power cut or a full disk during a checkpoint
leaves the previous state: the WAL is replayed or discarded at the next open. In the benchmark a writer
inserting 2 MB checkpoints in a loop was killed with `SIGKILL` at a different moment each of 12 times;
every file opened, passed `PRAGMA integrity_check`, and had every checkpoint it listed readable end to
end. `STORE.2` turns this into a test (kill a real child process mid-checkpoint; the run resumes from the
last good one) and one for the cases that need no process: an error between the inserts rolls back, and
a file with a damaged newest checkpoint falls back to an older one as `Run.resume` does now.

What SQLite does not promise is a disk that lies about `fsync`, or two machines on one file. `synchronous
= NORMAL` in WAL can lose the last few commits on a power cut but never corrupts; the cost of a lost
history row is a gap that the next resume cuts off anyway.

## Old runs

A folder run (`run.json`, `history.json.gz`, `checkpoints/checkpoint-*/`) is imported the first time it
is **opened** (resumed, its history shown, its checkpoints listed). Listing alone does not import: the
run list reads an old `run.json` the way it does now, so the list stays quick and read-only.

The import builds `run.sqlite.part` in one transaction and moves it into place:

- `meta` from `run.json` (id, name, seed, versions, config, summary) plus `imported_from` and its date;
- each checkpoint folder becomes a `checkpoints` row from its `meta.json` and a `checkpoint_data` row
  with the **bytes** of `world.json.gz` and `history.json.gz` unchanged (no world is decoded);
- the live history tables are filled from the newest checkpoint's recorder state.

Then the old files are moved into `<run>/imported/` rather than deleted, so a failed or doubtful import
loses nothing and the original can be restored by hand; the run list ignores the folder, and the 5 GB
warning counts it. Deleting `imported/` is left to the owner (default; asked as an open question
below). The same import covers the runs the process host made with `UX.31`, which use this layout.

## Windows and the package

- **`sqlite3` is part of the Python the package is built with** (`_sqlite3` and `sqlite3.dll` on
  Windows). PyInstaller finds it because the core imports it; `STORE.2` also names it in `hiddenimports`
  and has `--selftest` open an in-memory database and write a checkpoint, so the Windows package check
  (`UX.34`) covers it.
- **Local disks only.** WAL needs shared memory between processes on one machine. A runs folder on a
  network share or inside a cloud-sync folder (OneDrive, Dropbox) can corrupt or lock. The default
  runs folder is under the user's profile; the Saved runs dock warns once when the folder is a network path
  (`\\server\share`), and the README says so.
- **Deleting a run** closes the `Run`'s connection first: Windows will not delete an open file, and the
  `-wal` and `-shm` files go with the folder.
- **Antivirus** scanning a large growing file can slow a checkpoint; a checkpoint is one append, not a
  rewrite of the file, which is no worse than the folder.

## Measured

`python -m evolution_tools.bench_storage` on this machine (4 cores, SQLite 3.45.1, Python 3.13), a world of
1,000 animals and 5,000 plants stepped two days (990 animals and about 3,000 plants by then: the plants
thin out quickly in the default world). The same checkpoints were stored both ways.

| | folder (`UX.10`) | SQLite |
|---|---|---|
| a checkpoint, in all | 0.91 s mean (worst 1.22 s) | about 0.79 s (0.77 + 0.014) |
| serialising the world and recorder (the same bytes in both) | part of the 0.91 s | 0.77 s |
| storing it | the rest of the 0.91 s: two history files, a manifest, a directory move | 14 ms (worst 21 ms), WAL checkpoint included |
| a checkpoint's bytes | `world.json.gz` + `history.json.gz` | the same two, as blobs: 2.81 MB + 0.01 MB |
| file with three kept | | 10.2 MB at the high-water mark; 8.0 MB with `incremental_vacuum` |
| the WAL | | 5.1 MB left behind unless truncated, 0 with `wal_checkpoint(TRUNCATE)` |

(The two columns were taken on worlds a few ticks apart, so sizes are not compared.)

At the start of a run, with all 1,000 animals and 5,000 plants alive, the world is 5.4 MB of JSON and
0.49 MB gzipped, serialising takes 0.35 s, storing it 5 ms, and loading it back (`load_world`) 1.1 s.
So **a checkpoint is dominated by turning the world into JSON, not by storage**, and storage in SQLite
is not slower than the folder (it is faster by the cost of the folder's extra files).

| history, 100 simulated years of daily samples | |
|---|---|
| a daily append | mean 0.9 ms, median 0.5 ms, worst 28 ms |
| rows at the end | 296 samples, 8,880 levels, 24,568 stats, 5,915 histograms |
| file size | 2.4 MB, constant after the first few years (the tiers are bounded) |
| the whole history, read | 41 ms |
| one series, read | 0.6 ms |
| a read while a write transaction is open | 0.1 ms, last committed state |

A world takes about 0.13 s a tick at this size, so the worst history append (28 ms) is a fifth of one
step, and a typical one (0.5 ms) is nothing against the 3 s of stepping a day takes.

## What `STORE.2` builds

1. `runs/sqlite.py` (or inside `store.py`): the connection (pragmas above), the schema and migrations,
   the checkpoint transaction, retention, `incremental_vacuum`, the writer lease.
2. `RunStore` / `Run` over it with the same public API: `create`, `open`, `list_runs`, `delete`,
   `total_bytes`, `space_warning`, `Run.checkpoints`, `checkpoint`, `resume`, `history`, `due`,
   `autosave`, `config`, `summary`, `Autosaver`. What changes: `CheckpointInfo.path` (a folder before)
   becomes the run's file; nothing outside the runs package reads it. New: `Run.close()` (release the
   connection; the store closes it on `delete`), and `RunStore.open(run_id, readonly=True)`.
3. History: the recorder reports tier changes, the `Run` applies them as rows (one transaction a
   sample), `Run.history()` reads the tables, and resume refills them from the checkpoint. **The
   recorder's own saved format does not change** (`HISTORY_FORMAT` stays 2): it is the blob in a
   checkpoint, as before. `UX.32` and `SPECIES.2` add names to `level`/`stat` and, for `SPECIES.2`, one
   migration for `species`; nothing else changes.
4. The import of old folder runs on open (above; it reads history formats 1 and 2, the way
   `Recorder.restore` does, and writes format 2), and the places that name the old files:
   `__main__`'s and `headless`'s "`--config` can be a run's `run.json`" now also reads `run.sqlite`'s
   `meta`; `docs/design/ux.md` and `world.md` mention the folder layout; the packaging selftest.
5. Tests: the existing `test_runstore.py` and `test_headless.py` pass over the new store (they are the
   API contract), plus: a kill during a checkpoint (a real child process) leaves the last good one; an
   error mid-transaction rolls back; a damaged newest checkpoint falls back to an older one; history
   appended incrementally equals the recorder's own `history()` at every day for 3 simulated years; a
   resume from an older checkpoint restores the history of that moment; a reader opened while a writer
   is mid-transaction sees the last commit; the import of a folder run gives the same checkpoints,
   digest and history and leaves `imported/`; a newer `user_version` is refused; a second writer is
   refused while the first lives and allowed after it is gone.
6. `src/evolution_tools/bench_storage.py` stays, so the numbers can be taken again.

## Questions this note adds

None of these block the build; the defaults below are what `STORE.2` uses.

1. **Keep the old files after an import?** Default: yes, in `<run>/imported/`, until the owner deletes
   them. They double that run's size until then.
2. **A "compact" action** for the full `VACUUM`? Default: not built; `incremental_vacuum` already keeps
   the file tight.
3. **Network drives:** warn (default), or refuse to create a run there?

## Limits of this note

The figures are from one machine and a Linux filesystem; Windows file I/O and antivirus can change the
store times (not the serialising), and `UX.34`'s real-machine check should repeat the benchmark there.
The lineage table's growth is a guess until `UX.39` has decided what it records. Nothing here was built
into the run store: the schema in `src/evolution_tools/bench_storage.py` is a draft, and `STORE.2` is free to improve
it while keeping what this note commits to (one file per run, WAL, the checkpoint as one transaction,
rows appended for history, JSON for settings, the old runs imported and kept).
