# The graphical interface

Design note for `UX.1`. It answers the owner's question (2026-10-14): "I want a graphical
interface, should we do it web? native Windows?" and plans the builds `UX.6` to `UX.21` in
[TODO.md](../../TODO.md). The owner's questions are
[#123](https://github.com/dwhagar/evolutionSimulator/issues/123) (native or web),
[#124](https://github.com/dwhagar/evolutionSimulator/issues/124) (which computers),
[#125](https://github.com/dwhagar/evolutionSimulator/issues/125) (watch only or change things) and
[#126](https://github.com/dwhagar/evolutionSimulator/issues/126) (save, resume, run without a window);
the ones this note adds are listed at the end. Until they are answered, this note builds on the defaults
written in those issues.

## The short version

- **Build a native desktop program with Qt (PySide6), Windows first.** Charts use pyqtgraph. Nothing
  here needs a web server, and Python is the only language.
- **Keep the simulation and the window apart.** The simulation is the "core" that already exists
  (`World` and the rest, no screen code). The window is a separate layer that draws what the core
  reports. The two talk through a small, fixed set of messages, so the window can be replaced or a
  second one (for example a web page) added later without touching the simulation.
- **Run the simulation in its own process.** One tick of a mid-sized world takes about 44 ms (measured
  below). If the window shared a process with the simulation it would freeze while a tick runs. In
  its own process, the window always answers, however slow or fast the simulation is.
- **Draw from snapshots.** The simulation sends a compact picture of the world (about 54 KB for 300
  animals and 3,000 plants) up to 30 times a second; the window draws the plants once into a
  picture and redraws only the animals each frame. Measured: 1,000 animals and 5,000 plants take
  under 10 ms a frame.
- **Be honest about speed.** Most of the fast time presets cannot be reached with a world this size
  (see [Speed](#speed-and-what-the-window-shows)). The window shows the speed it is really getting.
- **Ship a Windows folder you can unzip and run** (PyInstaller), built by a workflow you start by
  hand, so the weekly-only CI rule stays.

## Native or web

Both work. The question is which one costs less to build well and suits how the simulator will be used:
a long run watched on one computer, with a lot of drawing and a lot of charts.

| | Native desktop (Qt / PySide6) | Local web page (server plus browser) |
| --- | --- | --- |
| Languages | Python only | Python for the simulation, plus HTML, CSS and JavaScript for the page |
| Drawing thousands of creatures | Direct drawing on the CPU (measured below), a GPU path exists if needed | Canvas or WebGL in the browser; as fast or faster, but every frame of data crosses a network connection first |
| Charts and panels | pyqtgraph and ready-made widgets (tables, trees, docks) | Many good libraries (Plotly, uPlot); more of it to assemble |
| Responsiveness at fast speeds | Window and simulation are separate processes; data goes over a local pipe | Same split, plus a server, a socket and a browser tab that may throttle when not in front |
| Watching from another computer or a phone | No (only the machine it runs on) | Yes, this is the real advantage |
| Packaging for Windows | One folder with an `.exe` (a PyInstaller build, about 100 MB) | A Python install and a browser, or the same `.exe` that starts a server and opens a tab |
| Look and polish | Native look, fewer fashion options | Full freedom, easy to restyle |
| Testing | Qt runs without a screen (`QT_QPA_PLATFORM=offscreen`), so windows can be tested | Needs a browser driver (Playwright) for the page, a second test stack |
| Two things to keep in step | One viewer | The page, the server and the simulation |
| Licence | PySide6 is LGPL; pyqtgraph is MIT; the project is CC0 and only depends on them, see below | JavaScript libraries are mostly MIT |

**Recommendation: native (`UX.2` default).** The deciding points: one language, nothing to host, fast
drawing without a network hop, and a Windows `.exe`. The cost is that nobody else can watch over a
network. If that ever matters, the process split makes a web viewer an addition (below), not a rewrite.

**When web would win.** If the owner wants to leave a run on a server and watch from a phone, or to
share a link with others, web is the better first choice. That is the reason the question stays open
in [#123](https://github.com/dwhagar/evolutionSimulator/issues/123).

**Other ways to build a native window, and why not.**

| Option | Verdict |
| --- | --- |
| Tkinter (in the standard library) | Nothing to install, but slow drawing, no good charts, dated look |
| pygame or arcade | Fast drawing, but every button, table and chart would have to be built by hand |
| Dear PyGui | Fast, tool-like, good for dashboards; fewer precedents for packaging, a less familiar look |
| wxPython, Kivy | Workable, smaller communities, weaker chart support than Qt |
| PyQt6 | Same Qt, but GPL: it would pull the whole project's licence. PySide6 is LGPL |
| Streamlit, Dash, NiceGUI (Python web) | Built for forms and reports; their redraw model is a poor fit for a moving world |
| A web page inside a native window (pywebview) | Needs the whole web stack as well, so both costs, little gain |

**Licence note.** The project is released under CC0 and depends on PySide6 (LGPL v3). Depending on it is
fine. A Windows build that ships PySide6's libraries must include its licence text and keep them as
separate, replaceable files, which a PyInstaller *folder* build does and a single-file build does not
as cleanly. `UX.19` carries this.

## Layers and the process split

```mermaid
flowchart LR
    subgraph sim["Simulation process (no window code)"]
        world["World (existing)"] --> session["Session: pacing, commands, snapshots"]
        session --> stats["Statistics recorder"]
        session --> store["Run store: saves and history"]
    end
    subgraph app["Viewer process (Qt)"]
        client["SimClient"] --> views["World view, controls,<br/>inspector, charts, dialogs"]
    end
    session -- "frames, details, history, events" --> client
    client -- "commands" --> session
    headless["Headless run command"] --> session
    web["Web viewer (later, optional)"] -.-> session
```

Three layers, each importable without the one above it:

1. **Core** (`evolution_simulator`, as now): `World`, the traits, the brain. No Qt and no numpy;
   `pyproject.toml` still has `dependencies = []`.
2. **Session** (new, still no Qt): wraps one `World` and runs it at the requested speed, takes commands,
   and produces snapshots. It runs in the simulation process, or directly in the calling process for
   tests and for the headless command.
3. **Viewer** (new, `evolution_simulator.viewer`, needs the `gui` extra: PySide6-Essentials, pyqtgraph,
   numpy): talks to the session only through `SimClient`.

**Why a second process.** Python runs one thread of ordinary code at a time (the "GIL"), so a thread in
the same process would still make the window stutter. A `multiprocessing` process started with
`spawn` (the only mode Windows has) runs on its own core. The cost is that the two cannot share
objects, only messages, and that discipline is also what makes the interface clean.

**How the two talk.** `SimClient` hides the transport. The first version uses a `multiprocessing.Pipe`
carrying small Python objects and `bytes` blocks. A later one can use a local socket or named pipe
(`multiprocessing.connection`) so a headless run can be watched from a window opened afterwards, or a
tiny web server can relay the same messages. The screens never see the difference. The same `SimClient`
interface is also implemented by an in-process version and by a `FakeSimulation` that makes up
a world (random creatures, a scripted population curve). The fake lets every screen be built and
tested before the real host exists, and without waiting for a simulation.

## What the viewer and the simulation exchange

### Commands (viewer to simulation)

One small command set; every future intervention (issue #125) is a new command, not a new channel.

| Command | Meaning | Item |
| --- | --- | --- |
| `new_run(config, seed)` | Build a world from a `WorldConfig` (and the rules tree), populate it, start paused | `UX.17` |
| `play` / `pause` / `step(n)` | Run, stop, or run exactly `n` ticks | `UX.13` |
| `set_speed(preset or seconds-per-second)` | How many simulated seconds per real second | `UX.13` |
| `select(id)` / `deselect` | Send details of this creature (the viewer picks from the snapshot it already has) | `UX.14` |
| `set_snapshot_rate(hz)` / `want(layers)` | The viewer says how often and which parts it needs, so a minimised window costs nothing | `UX.7` |
| `save(name)` / `load(path)` | Write or restore a run | `UX.9`, `UX.18` |
| `shutdown` | Stop cleanly | `UX.7` |
| later: `add_animal`, `remove`, `set_rule`, `edit_genes` | Only if the owner picks "also change things" in [#125](https://github.com/dwhagar/evolutionSimulator/issues/125) | `UX.20` |

### What the simulation publishes

The simulation never waits for the window. It keeps running and offers the newest of each kind.

| Message | Content | Rate |
| --- | --- | --- |
| **Frame** | tick, simulated time and day, daylight, speed asked and speed achieved, and arrays for animals, plants and corpses (below) | up to 30 a second, sooner than that only if something changed |
| **Plants** (part of a frame, sent less often) | position, canopy radius and fullness of every plant | 2 a second, or when the viewer asks |
| **Creature details** | one animal's traits, energy, health, age, sex, pregnancy, last decision, the brain's inputs, hidden values and outputs, the genome, parents | 10 a second while one is selected |
| **History samples** | counts, births, deaths, trait means and spreads, gene histograms (see [Charts](#charts-and-history)) | once per simulated day, sent in batches |
| **Events** | born, died (with the cause), ate, mated, saved, error | as they happen, capped per second |
| **Status** | running, paused, finished loading, crashed (with the error text) | on change |

**The arrays.** A frame is a few packed blocks of `float32` numbers, one block per kind, one row per
creature, so the viewer reads them with `numpy.frombuffer` without a loop. Rows:

| Kind | Fields |
| --- | --- |
| Animal | id, x, y, heading, body radius, energy ratio, health ratio, age ratio (age over lifespan), flags (asleep, pregnant, ready to mate, wandering, sex), diet (meat share of what it can digest), a "family colour" key (distance of its genome from the population's centre) |
| Plant | id, x, y, canopy radius, biomass ratio, flags (ready to seed) |
| Corpse | id, x, y, meat left ratio |

Sizes, measured here on the real world (`World.populate(300, 3000)`, a Python loop writing an `array('f')`):
**54 KB per frame and 1.7 ms to pack**. Scaled to the population caps (1,000 animals, 5,000
plants) that is about 100 KB and at most about 6 ms. At 30 frames a second that is 3 MB a second through a
pipe, which is nothing. The cost to watch is the packing, which happens in the simulation process
between ticks; plants change slowly, which is why they go out less often.

**Frame pacing.** The session loop is: read commands; ask the `Pacer` how many ticks real time owes
(`Pacer` in `world/timescale.py`, already built); run them, but stop early after about 30 ms so commands are
heard; if 33 ms have passed since the last frame, pack and send one. The window acknowledges each
frame; with two frames unacknowledged the simulation drops the frames it would have sent (and says
so in the status). A slow window therefore slows nothing but itself.

**What the core still has to provide.** The existing `World` is enough to read positions, but a viewer
that reaches into `world.animals[i].traits...` would tie the screens to the internals. These pieces are
missing or implicit today, and are the content of the first builds (`UX.6` to `UX.9`):

| Need | Today | What to add |
| --- | --- | --- |
| Read-only views of the world | The viewer would read private-ish attributes | A `snapshot.py` that builds frames, details and statistics from public attributes only, with a version number on the format |
| Events with causes | `StepReport` has only four counts; a death has no cause | An optional listener list (like `add_sleep_listener`): `born`, `died(cause)`, `ate`, `mated`. Off unless something listens, so a headless run pays nothing |
| The brain's last inputs and hidden values | `Brain.decide_with_hidden` exists but the animal does not keep the numbers | Keep them for the selected animal only (the host asks for it), so the inspector can show them live |
| Whole-world save and load | `state_digest()` hashes the world; nothing writes it out | See [Saving](#saving-loading-and-run-history) |
| History | Nothing records the population over time | A statistics recorder driven by the day counter |
| Names for display | Gene ids and brain input and output names exist (`INPUT_NAMES`, `OUTPUT_NAMES`, the layout's gene ids and clusters) | A small catalogue of display names and units, so the inspector does not print `base_fear_weight` |

### As built: the session (`UX.6`)

`evolution_simulator.session` is the contract the screens and the process host build on. It has no
dependencies (a test checks that no core module names Qt or numpy).

- **Core gaps filled.** `World.animal_views()`, `plant_views()`, `corpse_views()` and
  `animal_detail(id)` return immutable values from `world/views.py` (read these, never an organism's
  traits). `World.add_event_listener()` delivers `Born`, `Died` (with a `DeathCause` and the
  killer's id for a bite) and `Mated` events from `world/events.py`; they are built only while
  someone listens, and listening changes nothing about a run. `World.trace_brain(id)` keeps the
  inputs, hidden values and outputs of that animal's last brain run (`AnimalDetail.brain`, filled
  in once its brain has run since).
- **Session.** `Session(simulation)` takes `handle(command)` (`Play`, `Pause`, `Step(n)`,
  `SetSpeed(preset | seconds per second | "max")`, `Select(id)`, `Deselect`; a bad one raises
  `CommandError`) and `update()`, which runs the ticks real time owes (inside a work budget; the rest
  are dropped and counted) and returns an `Update` with a `Frame` when one is due and the selected
  animal's `AnimalDetail`. `subscribe(callback)` hears the world's events and `StatusChanged`.
  It takes a clock, so tests are exact, and starts paused.
- **Frame.** Three packed `Block`s (animals, corpses, plants): a `uint32` id array, a `float32`
  matrix and a flag byte per row, with the column names in the block, so a viewer reads them with
  `numpy.frombuffer`. About 11 KB for 300 animals; 74 KB when the 3,000 plants ride along, which
  they do only every half second and when the session settles (paused, steps done), so a paused
  world is exact. `FRAME_FORMAT` versions the layout. The family colour key of the first sketch is
  not in the frame yet (it needs a cheap genome distance; it is UX.12's to ask for).
- **FakeSimulation** has the same face as `World` for the session and the screens, with a scripted
  population curve and events; the session tests run every case against both.

## Speed and what the window shows

At the hourly default tick a tick is one simulated hour (`WORLD.7`), so the speed presets need these
ticks per real second: hour 1, day 24, week 168, month 730, year 8,766 and more above that. Measured
on this sandbox's CPU (one core, pure Python): **44 ms per tick at 300 animals and 3,000 plants**,
about 23 ticks a second, and about 5 ms per tick at 60 animals and 300 plants, about 200 a second.
So with a mid-sized world the presets up to "day" are met, "week" and above are not, and with a very small
world "week" is met. My estimate for the caps (1,000 animals, 5,000 plants) is 100 to 200 ms a tick,
about 5 to 10 ticks a second, which is just short of "day". The real figures depend on the computer.

What this means for the window:

- **Show the achieved speed next to the requested one**, for example "week/s asked, 3.1 days/s got". The
  `TimeScale` and `Pacer` code already drops the excess instead of queueing it.
- **Offer "as fast as the computer can" as a preset** next to the fixed ones.
- **Below about 3 frames a second of ticks, nothing visibly moves between ticks,** and with an hourly
  tick that is every preset below "hour": the picture is still for a minute at a time. Fix: **draw
  one tick behind and slide each creature from where it was to where it is** over the real time the
  tick takes. At "hour" that is a creature gliding over a second; at "real-time" it is a glide over an
  hour, which looks still, as it should. When paused, show the exact current state. Above about 10
  ticks a second this is not needed. (Question 2 under [Questions this note adds](#questions-this-note-adds), [#130](https://github.com/dwhagar/evolutionSimulator/issues/130): hide the presets below "hour"?)
- **Past what the eye can follow** (a decade a second and up, which the simulation cannot reach
  anyway), frames are only a blur. The view lowers its own frame rate and the charts become the thing to
  watch. A "hide the world while fast-forwarding" switch frees the simulation from packing frames.
- **Make quitting and pausing instant.** `pause` is only checked between ticks, so the longest wait is
  one tick (up to a few tenths of a second at the caps). The session says "pausing…" until it stops.

## The screens

One main window with dockable panels (they can be dragged, closed and put back), a menu bar and a
status bar. A sketch of the default layout:

```
+--------------------------------------------------------------------------------------+
| File  Run  View  Help                                                                |
+--------------------------------------------------------------------------------------+
| [Play] [Pause] [Step]   Speed: [1h][1d][1w][1mo][1y][10y][max]   asked 1w  got 3.1d  |
+--------------------------------------+-----------------------------------------------+
|                                      |  Creature #412        [Body|Genes|Brain|Family]|
|                                      |  Female, 3 months old (12% of a life)         |
|        WORLD VIEW                    |  Energy  ######----  61%    Health ######### |
|     (pan: drag, zoom: wheel,         |  Asleep: no   Pregnant: yes (litter of 2)     |
|      click a creature to select)     |  Doing:   turning left, eating                |
|                                      |  ...                                          |
|                                      +-----------------------------------------------+
|                                      |  Charts   [Population|Genes|Births/Deaths]    |
|                                      |   /\    /\                                    |
|                                      |  /  \__/  \__                                 |
+--------------------------------------+-----------------------------------------------+
| Day 41, night  |  Tick 1,000  |  Animals 118  Plants 2,310  |  Seed 7  |  saved 2 min |
+--------------------------------------------------------------------------------------+
```

### World view (`UX.12`)

Top-down view of the box. Drag to pan, wheel to zoom, double-click to fit. The edge is a visible wall.
Day and night tint the ground, matching `World.daylight`. A scale bar in world units (the simulation
has no metres). Layers that can be switched: plants, corpses, animals, a grid, the selected creature's
senses (a wedge for vision using its field of view, circles for hearing and smell, a ring for touch),
and its trail. **Colour by:** diet (default: meat eaters warm, plant eaters cool), sex, energy,
age, or family colour (so species and lineages show up as groups). Animals are small triangles
pointing along their heading; sleeping ones are dimmed and drawn with a mark; pregnant ones have a
dot. A small overview map appears when zoomed in. Colours come from a colour-blind-safe palette, and
no meaning rests on colour alone (shape or marks also differ).

### Controls and status (`UX.13`)

Play, pause, single step and "step a day"; the speed presets from `TimeScale`, a custom value, and
"as fast as possible"; the requested versus achieved speed; the simulated clock ("year 2, day 41, 03:00"),
day or night, the tick, the counts, the seed, and the run name. Keyboard: space to play or pause, the
arrow keys to step, `+`/`-` for speed, `F` to follow the selected creature.

### Creature inspector (`UX.14`, brain tab `UX.15`)

Click a creature (or pick it from a list) and a panel shows tabs:

- **Body:** age and life stage, sex, energy, health, size, the sleep and pregnancy state, the current
  decision in words ("turning left, fast, eating"), the senses' ranges and the traits with their
  units.
- **Genes:** the genome as the named genes grouped by their clusters (see
  [gene-clusters.md](gene-clusters.md)), each as a bar from low to high, next to the population's average so
  that unusual genes stand out. A toggle shows the raw digits.
- **Brain:** the network drawn as three columns (the 20 named inputs, the hidden neurons, the six
  outputs) with the live value on each and the weights as line thickness and colour; a second view
  lists only the inputs and outputs as bars. Dormant neurons are greyed
  ([brain-shape.md](brain-shape.md)). It shows what the creature "sees" and decides, tick by tick.
- **Family:** parents, children, the closest relatives alive, and a "select" link on each.

### Charts and history (`UX.16`)

pyqtgraph line charts that update live and can be zoomed, with a time axis in simulated days or years:

- Population of animals, plants and corpses.
- Births and deaths per period, deaths split by cause once the events exist.
- Mean and spread (a band from the 10th to the 90th percentile) of any chosen gene or trait, with a
  picker; and a **gene distribution** as a histogram that can be scrubbed through time.
- Average energy, age at death, and the number of lineages.

**What is recorded.** The statistics recorder takes one sample per simulated day (not per tick, so a
run of a thousand years stays small) and stores, for each sample, the counts and, for each gene and each
trait, the mean, spread, minimum and maximum; every thirtieth sample also stores a 20-bin histogram per
gene. Old samples are merged by averaging into weeks, then months, then years, so the series never
holds more than a few thousand points per chart. One sample is a few hundred numbers (a few KB), so a
hundred simulated years is a few MB before merging. The recorder is in the core, and
runs with or without a window.

### New run and settings (`UX.17`)

A dialog with a short form on top and an "Advanced" section below:

- **Short:** world size (the box), starting animals and plants, the seed (a "random" button and a field,
  always shown in the title bar and saved with the run), the speed to start at, and a preset list
  ("small test world", "the default", "big and slow").
- **Advanced:** the whole rules tree (`TraitRules`, the world's sleep, attack, corpse, plant and learning rules
  and the day cycle) as a tree of labelled fields with units, a "reset" next to each changed
  value, and "load from file" and "save as preset". These rule classes are frozen dataclasses, so the
  form can be made *from the classes themselves*: a new rule shows up in the dialog without anyone
  editing the dialog. Each rule keeps a one-line description, which the form shows as help text.
- **Preferences** (separate): theme (follows the system), the quality of drawing, the folder for saved
  runs, and the default colour mode.

### Saving, loading and run history (`UX.9`, `UX.10`, `UX.18`)

See the next section. The screens are: File, Save / Save as / Open; an autosave notice in the status bar;
and a **Run history** window listing every run with its name, seed, program version, simulated age,
last population, last save and a small chart of its population; buttons to open, continue, copy with a new
seed, export the history as CSV and delete.

## Saving, loading and run history

Today a world can be rebuilt from its config and seed only by running it again from the start;
`state_digest()` proves two runs are the same, but nothing writes the state out. Saving "the
creatures, plants and world" ([#126](https://github.com/dwhagar/evolutionSimulator/issues/126) question 1)
needs a new piece in the core.

- **What a save holds.** The config (as data, from the dataclass tree), the seed, the program version,
  the tick, the random generator's state, every animal, plant and corpse with its position, its genome
  string and the state that is not in the genome (energy, health, age, pregnancy, cooldowns, what it has
  learned), plus the run's history. A genome is about 1,000 digits for an animal and 33 for a plant,
  so a thousand animals and five thousand plants are about a megabyte before compression, and they
  compress well.
- **The format.** A *folder* per run, with a readable `run.json` (name, seed, program and format version,
  config), a history file, and checkpoint files (`checkpoint-<tick>.json.gz`). **No pickle:** it can run
  code from a file and breaks when classes change. Each file carries a format number; a loader for an
  older number can be added when a change needs it.
- **Proof it works.** A test saves a world, loads it, runs both for the same number of ticks and
  checks `state_digest()` matches. If the digest hides something that a save loses (it hashes the
  genome and the body state but not, say, the pregnancies or the learned values), the same item
  extends the digest.
- **Autosave.** A checkpoint every few simulated days (and at a minimum wall-clock interval), keeping the newest
  few plus one a simulated year, so a crash loses little and the folder does not grow forever.
- **Headless runs** (`UX.22`). A command (`python -m evolution_simulator run --config c.json --until "100y" --out runs/`)
  uses the same session without a window, writing the same run folder. The viewer opens it afterwards
  from Run history. Watching a headless run live is possible later through the socket form of
  `SimClient`, but is not needed first.
- **Replays.** The same seed, config and program version give the same run, but only for that
  version; checkpoints, not seeds, are what survive code changes.
- **Where.** `%LOCALAPPDATA%\evolutionSimulator\runs` by default on Windows, changeable.

## Drawing thousands of creatures

The rule: **draw each kind in the cheapest way that still reads.**

| Layer | How | Cost (measured) |
| --- | --- | --- |
| Ground, day and night, edge | A filled rectangle and an alpha tint | Nothing |
| **Plants** (up to 5,000) | Drawn once into an off-screen picture (`QPixmap`) and reused; rebuilt only when the plants frame arrives (2 a second), or on zoom or pan | 11 ms for 3,000, 20 ms for 5,000 to rebuild, then a single blit per frame |
| **Corpses** | Few; drawn directly | Nothing |
| **Animals** (up to 1,000) | Redrawn every frame, only those inside the view; triangles with a heading when zoomed in, plain dots when each would be a few pixels | 300 animals: 3 ms; 1,000: 8 ms as triangles, 3 ms as dots; 5,000: 39 ms and 13 ms |
| Selection, senses, labels, minimap | Drawn on top, only for the selected creature | Nothing |

Measured on this sandbox: Qt's software raster painter on a 1600 by 900 image, with Python building each
triangle (so a real build with numpy may do better, and a GPU view still better). Frame time at the caps is therefore a few
milliseconds, the 33 ms of 30 frames a second leaves most of the time free, and the screen is not the
limit; the simulation is.

Other rules that keep it fast:

- Draw from the `numpy` arrays directly; no one object per creature in the viewer.
- Do not use Qt's `QGraphicsView` item scene for creatures: it creates one object per creature and
  gets slow in the thousands. A single custom widget that paints is simpler and faster.
- Find the creature under a click with a distance test on the frame arrays, not by asking the
  simulation.
- Move and zoom the camera in the viewer only; a pan does not cost the simulation anything.
- If the caps are ever raised past about 5,000 animals, switch the one widget to `QOpenGLWidget`
  (same painting code, drawn by the graphics card) or draw points through pyqtgraph's `ScatterPlotItem`.
  Nothing else changes, because only the world view draws.
- Optional: a "performance" mode that draws every animal as a dot and skips shading.

## Packaging for Windows (`UX.19`)

- **Run from source** (`pip install -e ".[gui]"` then `python -m evolution_simulator.viewer`) for
  anyone with Python. The `gui` extra holds PySide6-Essentials, pyqtgraph and numpy; the core stays at
  zero dependencies.
- **A program to hand to anyone:** PyInstaller in *folder* mode, zipped (`evolutionSimulator-<version>-win64.zip`).
  Unzip, run `evolutionSimulator.exe`. Expect about 100 MB (Qt is most of it; `PySide6-Essentials` leaves out
  the unneeded modules). Folder mode starts fast and avoids most false alarms from antivirus programs
  that single-file builds trigger.
- **An installer** (Inno Setup, a free script that makes `Setup.exe`) can wrap the same folder later: start menu entry,
  uninstall. The owner decides ([question](#questions-this-note-adds)).
- **Building.** A workflow that runs on a Windows runner *only when started by hand* (`workflow_dispatch`),
  so the weekly-only CI rule is kept, uploading the zip as a release asset or artifact. The version
  comes from `scripts/version.py`, and the window's About box and title show it.
- **Three things to get right:** `multiprocessing.freeze_support()` at the start of the program (the
  simulation process is started by `spawn`, which a frozen program needs told); the licence texts for
  PySide6 in the folder; the data files (palettes, the display-name catalogue) listed so PyInstaller
  includes them.
- **Not signed.** An unsigned `.exe` makes Windows SmartScreen say "unknown publisher" the first
  time. A code-signing certificate costs money each year; for a hobby tool, accept the warning and
  say so in the README.
- **Other systems.** Qt runs on macOS and Linux. Nothing in this design is Windows-only except the
  package, so those need only a build step and testing ([#124](https://github.com/dwhagar/evolutionSimulator/issues/124)).

## Testing

- The core stays tested as now (`pytest`, no GUI). A small test checks that the core modules never import
  Qt or numpy, so the zero-dependency rule cannot slip.
- Snapshot packing and unpacking, the command set, the pacing and the fake simulation are tested
  without a window.
- Viewer tests use `pytest.importorskip("PySide6")` with `QT_QPA_PLATFORM=offscreen`: build
  the main window on a `FakeSimulation`, send a frame, `widget.grab()` the result and check a few pixels
  and the text. They are skipped where PySide6 is not installed, so the base suite stays quick.
  This was tried here: offscreen Qt draws and measures fine on Linux once `libEGL` is installed.
- Because CI runs weekly only, each build thread runs `ruff` and `pytest` locally, as it does now.

## Build order

The builds in [TODO.md](../../TODO.md) are `UX.6` to `UX.21`. They share one main window, one wire format and
one process, so the safest order has one small foundation that everything else waits for, then
items that can be built at the same time.

**Wave 1: the contract (one thread; small, everything waits for it).**
`UX.6`, the session: snapshot types, command set, events hook, `FakeSimulation`, all in process with no
window. The headless run command is `UX.22`, which needs only `UX.6` and `UX.9`. Building the session first fixes the interface the screens are written
against. `UX.9` (world save and load) has no dependency and can start at once, beside it.

**Wave 2: in parallel, each in its own files.**

| Item | What | Needs |
| --- | --- | --- |
| `UX.7` | The simulation process, `SimClient` over a pipe, frame pacing and drop-when-behind, crash report | `UX.6` |
| `UX.8` | Statistics recorder: daily samples, merging, histograms, in the core | `UX.6` |
| `UX.9` | Serialise and restore a whole world; the digest round-trip test (extend the digest if it hides pregnancies or learned values); JSON and gzip, no pickle | none |
| `UX.11` | App shell: `gui` extra, `evolution_simulator.viewer`, the empty main window with dock slots, menu, status bar, theme and the offscreen test harness. Each later screen is a module that fills one dock slot, so the screens do not edit the same file | `UX.7` (it can start against the fake) |
| `UX.10` | Run store on top of `UX.9` | `UX.9`, `UX.5` |

**Wave 3: the screens, in parallel (each against `FakeSimulation`, then the real host).**
`UX.12` world view, `UX.13` controls, `UX.14` inspector (body and genes) then `UX.15` brain and senses
view with the overlays, `UX.16` charts (needs `UX.8`), `UX.17` setup screen (its first step is the
form generator that reads the frozen config dataclasses).

**Wave 4.**
`UX.18` save, load and run-history screens (needs `UX.10`); `UX.19` Windows packaging once the controls
exist, then re-run on every release; `UX.21` polish last.

**Parked.**
Interventions `UX.20` ([#125](https://github.com/dwhagar/evolutionSimulator/issues/125)); a web viewer
([#123](https://github.com/dwhagar/evolutionSimulator/issues/123)); comparing two runs on one chart;
video or GIF export; a family tree view
([#134](https://github.com/dwhagar/evolutionSimulator/issues/134)). The first two depend on the owner's
answers; the others add screens, not new foundations.

Rough sizes: `UX.6`, `UX.8` and `UX.13` small to medium; `UX.7`, `UX.9`, `UX.10`, `UX.11`, `UX.12`, `UX.14`, `UX.16`,
`UX.17`: medium; `UX.15` and `UX.18`: medium; `UX.19`: small to medium (mostly trial and error on
Windows). The window cannot be run on a Linux machine like this sandbox beyond the offscreen tests,
so the Windows packaging and the first look at the real window need the owner's eyes; each screen
thread should attach a screenshot from the offscreen renderer to its PR.

## Questions this note adds

Filed as issues, each with a default so nothing waits. The earlier four are
[#123](https://github.com/dwhagar/evolutionSimulator/issues/123) to
[#126](https://github.com/dwhagar/evolutionSimulator/issues/126).

1. [#129](https://github.com/dwhagar/evolutionSimulator/issues/129) **Look of the creatures** (`UX.23`, feeds `UX.12`): colour by what by default, and the shape. Default: triangles by heading,
   colour by diet, switchable.
2. [#130](https://github.com/dwhagar/evolutionSimulator/issues/130) **Slow and impossible speeds** (`UX.24`, feeds `UX.13`): the lowest presets (real time, a minute a second) move almost nothing
   with an hourly tick, and the fastest cannot be reached. Default: keep all presets, glide between ticks,
   show achieved speed, and add "as fast as possible".
3. [#133](https://github.com/dwhagar/evolutionSimulator/issues/133) **What to see of the brain** (`UX.27`, feeds `UX.15`): the network drawing with live values, or only bars. Default: both,
   bars first.
4. [#131](https://github.com/dwhagar/evolutionSimulator/issues/131) **Where runs are kept and how much space** (`UX.25`, feeds `UX.10`). Default: `%LOCALAPPDATA%\evolutionSimulator\runs`, keep
   all, warn at 5 GB.
5. [#132](https://github.com/dwhagar/evolutionSimulator/issues/132) **How the program is handed over** (`UX.26`, feeds `UX.19`): a zip to unzip or an installer; whether to pay for signing.
   Default: zip first, unsigned.
6. [#134](https://github.com/dwhagar/evolutionSimulator/issues/134) **Extras** (`UX.28`): compare two runs, video export, a family tree view, watching a headless run live, several runs at once.
   Default: not now, ask again after the first window works.

## Limits of this note

The speeds and frame times are measured in a Linux sandbox with no graphics card, one core, Python 3.13, and
PySide6 6.12 in offscreen mode. Windows machines will differ (usually faster for drawing). Nothing here has been
built or run on Windows. The package size is an estimate until `UX.19` builds one. Neither the
web alternative nor the OpenGL path was built, only reasoned about.
