# Sense genes: field of vision, acuity, and what the world must provide

Design note for `SENSE.15`, written 2026-10-14 by the Research 3 thread. It extends
[senses.md](senses.md) (`SENSE.1`) with the owner's request of the same day, and it ends with build lists
for `SENSE.16` (the genes) and `WORLD.12` (the world properties the senses need). The owner questions it
raises are issues #88 to #92 (`SENSE.17` to `SENSE.21`), listed under [Questions for the owner](#questions-for-the-owner).

**Who this is for.** The owner is new to this area, so the ideas are explained in plain terms first and
the exact numbers come after. A reader who only wants the decisions can read the [summary](#summary),
[the vision trade-off](#the-vision-trade-off-field-against-acuity) and the
[questions](#questions-for-the-owner). Figures marked *measured* or *computed* came from small Python
scripts run against the code on `main` while writing this note.

**Reads with.** [senses.md](senses.md) for why the senses are what they are, `src/evolution_simulator/sensing.py`
(the sensing step), `sense_genes.py` (ranges, noise and costs), `sense_channels.py` (the brain's inputs)
and `world/senses.py` (the stand-in the world uses today).

## Contents

1. [Summary](#summary)
2. [What the owner asked for](#what-the-owner-asked-for)
3. [What is on main today](#what-is-on-main-today)
4. [The genes](#the-genes)
5. [The vision trade-off: field against acuity](#the-vision-trade-off-field-against-acuity)
6. [Predators and prey: different starting eyes](#predators-and-prey-different-starting-eyes)
7. [A gene for each sense](#a-gene-for-each-sense)
8. [What the world must provide](#what-the-world-must-provide)
9. [Risks](#risks)
10. [What to build](#what-to-build)
11. [Constants for the TRAIT.3 config](#constants-for-the-trait3-config)
12. [Questions for the owner](#questions-for-the-owner)

## Summary

- **One new gene, one changed gene.** `sight_acuity` is new: how sharply a creature sees. `sight_fov`
  keeps its place in the genome but now means the **half-angle** of the field of vision, 15 to 180
  degrees either side of the direction of movement (so 30 to 360 degrees across), on a log scale. The
  other sense genes (`sight_range`, `hearing`, `smell`, `touch`, `taste`) already are "how well this
  sense works"; they keep their meaning and the first generation starts them in the middle.
- **The trade-off is hard and simple.** With the field gene `f` and the acuity gene `a`, each from 0
  to 1, a creature's *working* acuity is `min(a, 1 - f)`. A wide field (`f` high) caps how sharp the
  eye can be; a narrow field (`f` low) allows a sharp one. Because the field is on a log scale, this is
  the real-world rule that resolution falls in proportion to how much you try to cover. A creature that
  carries a high acuity gene with a wide field just does not get to use it.
- **Acuity does three things:** it lengthens the range the eye reaches (by 0.6 to 1.4 times), it shrinks
  the errors in direction, closeness and relative size, and it adds to the cost of the eye. Costs are set
  so the whole frontier costs about the same (0.0074 to 0.0099 energy per tick for a mid-range eye,
  *computed*): you choose *what* to see, not how much to pay. Acuity replaces the old rule that a wider
  field shortens the range by up to 45%.
- **Predators and prey start different.** The first generation's eyes are tilted by diet: an animal that
  eats more meat than plants starts with a narrower field and sharper eyes (about 49 degrees across, reach
  37 at mid vision gene), one that eats mostly plants with a wider field and softer eyes (about 219
  degrees across, reach 23). It is only a starting point, so evolution is free to move anywhere on the
  frontier.
- **The world needs more than it has.** Vision is nearly covered. Hearing has nothing to hear (animals
  do not emit calls or movement noise yet), smell works only from point sources with no trails, touch is
  never told where the world's edge is, and the sensing step is not yet what the world calls (it still
  uses the stand-in). The [world table](#what-the-world-must-provide) lists each gap and what fills it.
- **One risk to watch.** Until predators can hurt prey (`BRAIN.10`), nothing punishes narrow vision,
  and a narrow sharp eye sees farther for less energy than a wide one. The wide-and-soft end only pays
  once there are threats to see from the side. Calibrate after attacks exist (`SENSE.13`).

## What the owner asked for

From the project thread on 2026-10-14, in the owner's words condensed:

1. A **field of vision** gene: how many degrees from the direction of movement, in either direction.
2. An **acuity** gene: how accurately a creature sees.
3. **A gene for each sense and how well it works**, every one starting middle-of-the-road.
4. **Predators:** narrow, high-acuity vision. **Prey:** lower acuity, wider field.
5. **A trade-off:** lower acuity goes with a wider field, higher acuity with a narrower one.
6. Evaluate **what properties the world needs** so that each sense can work.

## What is on main today

All of this is read from the repository at commit `6b84306`.

**Genes** (`layouts.py`, animal layout version 4): `sight_range`, `sight_fov`, `hearing`, `smell`, `touch`,
`taste`, each one gene of four base-4 digits (256 levels), plus `encoder_fidelity` for calls. There is no
acuity gene.

**What each gene becomes** (`sense_genes.py`, `trait_defs.py`):

| Gene | Becomes | Range | Notes |
| --- | --- | --- | --- |
| `sight_range` | `sight_reach` | 0 to 60 units | 0 is blind; cost is charged on the area covered |
| `sight_fov` | `fov_degrees` | 40 to 360 across | and the reach is multiplied by `1 - 0.45 * sight_fov` |
| `hearing` | `hearing_range` | 0 to 85 units | noise 0.30 down to 0.15 as the gene rises |
| `smell` | `smell_range` | 0 to 100 units | noise 0.50 down to 0.25 |
| `touch` | `tactile_factor` | 1.1 to 2.6 times body radius | always on; the gene only sets the reach |
| `taste` | detection chance in `inspect_food` | `toxicity * (0.2 + 0.8 * taste)` | an action, not an input |

**The sensing step** (`sensing.py`, `SENSE.10`) is a pure function `sense()`: it takes a creature's
position, heading, `SenseOrgans` and already-classified `Neighbour` objects and returns `Percepts`. It
already does the following: scales vision by daylight and every organ by sleep, measures distances
between body surfaces, lets each organ report only its classes, takes the field of view as a **total**
angle (`vision_fov_degrees`, halved inside), adds seeded noise that falls as the gene rises, and reports
touch, calls and crowding. It is **not called by the world yet**: `World.senses` is `BasicSenses`, a
stand-in that uses sight only, a mass rule for prey, threat and mate, and the old reach-times-field
formula. `SENSE.12` (wiring `sense()` in, in progress) replaces it.

**The world** (`world/`): a continuous 2D box (1000 by 1000 by default, hard walls), a grid index for
neighbours (`animals_within`, `plants_within`), a day-night cycle (`World.daylight`, 600 simulated
seconds per day), sleep, and an `Animal` with a position, a heading, `asleep` and `last_decision`. Animals
can overlap; nothing blocks them.

**Measured on the current genes.** An animal with every sense gene at 0.5 pays about 14% of its basal
budget for its senses (mean over 400 random bodies; 11% to 19% for the middle 80%, *measured*). Touch and
taste each cost 0.02 energy per tick at that setting, twice what the mid-range eye costs (0.0098), because
they still use the old gene-squared rule (`SENSE.13` already notes this).

## The genes

| Gene | Status | Digits | Expressed as | Range | First generation |
| --- | --- | --- | --- | --- | --- |
| `sight_range` | existing | 4 | vision level: base reach before acuity | 0 to 60 units (0 is blind) | 0.5, so a base reach of 30 |
| `sight_fov` | existing, **meaning changes** | 4 | half-angle of the field, either side of the direction of movement; `15° * 12^f` | 15° to 180° (30° to 360° across) | 0.5 for most; tilted by diet |
| `sight_acuity` | **new** | 4 | sharpness; working value `min(a, 1 - f)` | 0 to 1 | 0.5 for most; tilted by diet |
| `hearing` | existing | 4 | hearing level: range and accuracy | 0 to 85 units | 0.5, so 42.5 units |
| `smell` | existing | 4 | smell level: range and accuracy | 0 to 100 units | 0.5, so 50 units |
| `touch` | existing | 4 | touch level: reach beyond the body | 1.1 to 2.6 times body radius | 0.5 |
| `taste` | existing | 4 | taste level: chance to detect a toxin | `toxicity * (0.2 + 0.8 * taste)` | 0.5 |

"The first generation" means the genomes `World.populate` and the seeding code create. Every sense gene
starts at 0.5 with a little spread (a draw within about 0.07 of the middle, so the population is not a
set of clones). Evolution moves them from there. At layout level this is one new gene, so the animal
layout version goes to 6 (4 is the brain work, 5 is `REPRO.8`, which has not landed).

Everything else about the senses stays as in [senses.md](senses.md): daylight multiplies vision, sleep
multiplies every organ, vitality shrinks sight and hearing, and noise comes from the injected random
generator.

## The vision trade-off: field against acuity

### What the two genes mean

Think of an eye as having a fixed number of light-sensing cells. Spread them over a wide field and each
patch of the view gets few cells: a blurry, panoramic view (a rabbit, a pigeon). Pack them into a narrow
field and each patch gets many: a sharp, tunnel-like view (a hawk, a cat). The number of cells does not
change; the split does.

- The **field gene** `f` (0 to 1) sets the half-angle `h = 15° × 12^f`. The log scale matters: each equal
  step in `f` multiplies the angle by the same factor, so the middle of the gene range is 52°
  (104° across), not 97°, and there is as much room to be narrow as to be wide.
- The **acuity gene** `a` (0 to 1) says how sharp the eye is *trying* to be.
- The **working acuity** is `a_eff = min(a, 1 - f)`.

So the best possible acuity is `1 - f`: a narrow field (`f` near 0) allows acuity near 1, a wide field
(`f` near 1) allows only acuity near 0, and the middle allows 0.5. Doubling the field halves what the
eye can resolve, which is what the real rule is. Both genes can mutate freely, and evolution can move a
creature along the frontier by changing them both.

### What acuity does

| Effect | Formula (working acuity `a_eff`, vision level `L` = `sight_range` gene) | At `a_eff` 0 / 0.5 / 1 |
| --- | --- | --- |
| Reach of the eye | `60 × L × (0.6 + 0.8 × a_eff)` units | 0.6 / 1.0 / 1.4 times the base |
| Direction error (standard deviation, input units) | `0.02 - 0.015 × a_eff` | 0.020 / 0.0125 / 0.005 |
| Closeness error | `0.05 - 0.04 × a_eff` | 0.05 / 0.03 / 0.01 |
| Relative-size error | same as the direction error | 0.020 / 0.0125 / 0.005 |
| Cost of the eye | `8e-6 × (1 + a_eff) × area covered` per tick | |

The reach rule replaces `1 - 0.45 × sight_fov`, which tied range to the field directly. Now the field
changes the range only through the acuity ceiling, so a creature can be wide-eyed *and* sharp only by
paying for it elsewhere (a high vision level `L`). The three error rules replace the fixed closeness error
of 0.03 and the exact relative size that vision reports today. The mid-range values (0.0125 and 0.03)
are close to the current ones at the middle of the gene (0.015 and 0.03), so a mid-range creature
behaves much as it did.

### Where it lands

Computed for vision level 0.5 (`L`), with `a = 1 - f` so the creature uses its full ceiling:

| `f` | `a` | Half-angle | Across | Reach | Area covered | Eye cost per tick |
| --- | --- | --- | --- | --- | --- | --- |
| 0.00 | 1.00 | 15° | 30° | 42.0 | 462 | 0.0074 |
| 0.20 | 0.80 | 25° | 49° | 37.2 | 596 | 0.0086 |
| 0.35 | 0.65 | 36° | 72° | 33.6 | 705 | 0.0093 |
| **0.50** | **0.50** | **52°** | **104°** | **30.0** | **816** | **0.0098** |
| 0.65 | 0.35 | 75° | 151° | 26.4 | 918 | 0.0099 |
| 0.80 | 0.20 | 110° | 219° | 22.8 | 994 | 0.0095 |
| 1.00 | 0.00 | 180° | 360° | 18.0 | 1,018 | 0.0081 |

Along the frontier the reach falls from 42 to 18 units (2.3 times) while the area covered grows 2.2
times, and the eye cost stays within 0.0074 to 0.0099. That is the intended shape: neither end is
cheaper in a way that decides the outcome. A narrow sharp eye sees far and sees little; a wide soft eye
sees close and sees much; the creature pays about the same. What it does with the picture is for the
brain and for its enemies to decide.

Away from the frontier (*computed*): a creature with `f = 0.5` and `a = 1.0` uses `a_eff = 0.5`, so it
gets the same eye as the mid-range one and the extra acuity is unused. One with `f = 0.1` and
`a = 0.1` has a narrow field and a soft eye, with reach 20 and an area of only 140 for 0.0017: a cheap,
poor eye. The vision level `L` multiplies reach and (through the square) area: at `a_eff` 0.5, `L` of
0.25, 0.5, 0.75 and 1 gives reaches of 15, 30, 45 and 60 and costs of 0.0024, 0.0098, 0.0220 and 0.0392.

### The unused part of a gene

Half of all random pairs of genes have more acuity than the frontier allows (*computed*: 50% of uniform
random `a` and `f` give `a > 1 - f`). That unused part does nothing, costs nothing and does not harm; if
the field later narrows, it comes back into use. Real genomes work the same way. Starting the first
generation on the frontier keeps this from happening at the start.

### Other ways to build the trade-off

| Option | How it works | For | Against |
| --- | --- | --- | --- |
| **A. Ceiling (recommended)** | Two genes; working acuity is `min(a, 1 - f)` | Two real genes as the owner asked; a hard limit that is easy to state and test | Part of the acuity gene can be unused |
| B. One dial | A single "focus" gene that sets both field and acuity along the frontier | No unused genes; every mutation moves along the frontier | Not two genes; the field and acuity cannot be separated, so no "wide and sharp but very expensive" creature |
| C. Soft penalty | Each gene is free, but working acuity is `a × (1 - 0.5 × f)` or similar | Every gene always matters | Not a hard trade-off: a creature can have both a wide field and decent acuity if it accepts a small penalty |

The default is A, as the owner wrote "trades off" and "comes with". Issue `SENSE.17` asks.

## Predators and prey: different starting eyes

**What the owner wants:** predators start with narrow, high-acuity vision; prey with lower acuity and a
wider field. Neither is a permanent rule; it is where each begins.

**How it is set.** Each animal in the first generation (and any later seeded animal) gets a diet tilt
from its two diet genes: `tilt = carnivore_eff - herbivore_eff`, from -1 (all plants) to +1 (all meat).
Its starting vision genes are then:

```
f = 0.5 - 0.3 * tilt        (+ a small spread, kept inside 0 to 1)
a = 1 - f                   (so it starts on the frontier)
```

| Animal | Tilt | `f` | `a` | Half-angle | Across | Reach at `L` = 0.5 |
| --- | --- | --- | --- | --- | --- | --- |
| Pure predator | +1 | 0.20 | 0.80 | 25° | 49° | 37.2 |
| Mild predator | +0.5 | 0.35 | 0.65 | 36° | 72° | 33.6 |
| Generalist | 0 | 0.50 | 0.50 | 52° | 104° | 30.0 |
| Mild herbivore | -0.5 | 0.65 | 0.35 | 75° | 151° | 26.4 |
| Pure herbivore | -1 | 0.80 | 0.20 | 110° | 219° | 22.8 |

The other sense genes start at 0.5 for everyone, so the difference at the start is only in the eye. The
diet tilt uses the diet genes as they are in the first genome, and after that the diet genes and the eye
genes evolve independently. If the owner wants the link to be permanent (a herbivore that turns
carnivore also drifts toward a narrow eye), that is a gene cluster (`DNA.14`) and is a separate change;
issue `SENSE.19` asks.

**What this means in play.** A predator sees a thin slice far ahead, so it must turn toward prey and can
be flanked. Prey sees almost all around but only close up, so it notices a threat from any side but late.
Both ends of the frontier cost about the same, so neither is a free win; whether the predator's reach
beats the prey's fear is up to the world, the brain and the attack rules (`BRAIN.10`).

## A gene for each sense

Every sense gene already is the answer to "how well does this sense work", and each sets what that sense
means to the creature. At 0.5 (the first generation) the senses look like this:

| Sense | Gene | What the level sets | At 0.5 | Cost per tick at 0.5 |
| --- | --- | --- | --- | --- |
| Vision | `sight_range` (level), with `sight_fov` and `sight_acuity` | base reach; with the field and acuity, the actual reach, errors and cost | reach 30 at acuity 0.5 (a 104° cone) | 0.0098 |
| Hearing | `hearing` | range (0 to 85) and direction error (0.30 to 0.15) | 42.5 units, error 0.225 | 0.0142 |
| Smell | `smell` | range (0 to 100) and direction error (0.50 to 0.25) | 50 units, error 0.375 | 0.0196 |
| Touch | `touch` | how far past its body it feels (1.1 to 2.6 times the radius) | about 1.85 radii | 0.0200 |
| Taste | `taste` | chance to detect a toxin before eating | 0.6 times the toxicity | 0.0200 |

Total about 0.084 energy per tick, 14% of an average basal budget. Two notes.

- **Hearing and smell do not get their own acuity gene.** For them the one gene sets both range and
  accuracy, as `sense_genes.py` already does, so a good nose is long-ranged and precise together.
  Vision has a separate acuity because it is where the owner wants the trade-off. Issue `SENSE.18` asks
  whether hearing and smell should also split level from acuity.
- **Touch and taste are twice as dear as the eye at the middle.** They still use the old
  gene-squared rule (0.08 times the level squared). That makes the senses that do the least cost the
  most; moving them onto a cost that follows what they do is `SENSE.13`.

Predators and prey could also differ in other genes' starting points (a predator with sharper smell, a
prey animal with sharper hearing), but the owner asked only about vision, and this note does not tilt
the others.

## What the world must provide

For each sense: what the world has to supply, what `main` already supplies, and what is missing. "Gap"
means no code does it yet.

### Vision

| Needs | On main | Gap |
| --- | --- | --- |
| Positions and headings of everyone | Yes: `Animal.position`, `heading`; plants have positions | |
| Body size, to measure between surfaces | Yes: `Animal.radius` (0.5 to 0.79), `Plant.radius` (canopy) | |
| A fast "who is nearby" query | Yes: `SpatialIndex`, `animals_within`, `plants_within` | Cell size must come from the real maximum reach (`SENSE.12`) |
| Light level | Yes: `World.daylight`, 0 to 1, with `DayCycle` | |
| Who counts as plant, prey, threat or mate | A mass rule in `BasicSenses`; genome closeness in `world/mating.py` | The real classifier (diet, size, similarity) is `SENSE.12` |
| The field as a half-angle | `sense()` takes `vision_fov_degrees` as a total and halves it | Pass the half-angle instead and read the new genes |
| Acuity effects | Noise only comes from the range gene | Reach, closeness error and size error from `a_eff` |
| Shade under a canopy | `Plant.shade` exists for plant competition | Optional: dim vision under a heavy canopy (not used by senses yet) |
| How visible a thing is (size, movement, camouflage) | No | Optional: see [Questions](#questions-for-the-owner) (`SENSE.21`) |
| Objects that block the view | No (open field) | Not planned; there are no obstacles |

### Hearing

| Needs | On main | Gap |
| --- | --- | --- |
| Something that makes sound | No: the brain's alarm and mating call outputs are not acted on (`BRAIN.10`); animals do not emit calls | Per-animal call state (which call, its radius) and the code that sets it |
| Footsteps and movement noise | `Neighbour.loudness` exists | Animals have no stored speed; `last_decision.speed × current_max_speed` gives it. Loudness = speed fraction × size, 0 when asleep |
| Sleepers silent | `Animal.asleep` exists | Use it to set loudness 0 |
| Sound that fades with distance | Yes in `sense()`: range limits and call radius | |
| A sleeper waking to a loud call | Not built | Belongs to the sleep code, not the pure sensing step (`SENSE.7`, `SENSE.12`) |
| Walls and wind | None | Not planned |

### Smell

| Needs | On main | Gap |
| --- | --- | --- |
| Things that smell | `Neighbour.scent` (0 to 1) exists | The world must supply it: plants from biomass (available in `PlantTraits`), animals from mass |
| A decay or drift of scent over time and space (trails) | No | A scent field with decay if trails are wanted (`SENSE.20`) |
| Dead bodies as a scent source | No: the dead are removed at once | Needs corpses; part of the predation work |
| Wind or water currents | No | Not planned |

### Touch

| Needs | On main | Gap |
| --- | --- | --- |
| Contact between bodies | Yes: surface distance | |
| The world's edge | `sense()` takes `edge_distance` | The world must pass the distance to the nearest wall (`Bounds` knows it) |
| Bodies that block each other | No: animals can overlap | Not needed; "touching" is information, not collision |
| Harm on contact | No: attacks are not built (`BRAIN.10`) | Pain currently comes only from other health loss |

### Taste, body senses and the clock

| Sense | On main | Gap |
| --- | --- | --- |
| Taste | `inspect_food` called when grazing; plants have `toxicity` | Nothing for animals as food until predation |
| Pain, energy, health, vitality | Yes: the brain's body inputs (`SENSE.9`) | |
| Daylight | Yes: `World.daylight` and the `daylight` input | |
| Sleep factors | Yes: `SensingRules` scales each organ while asleep, and the world puts animals to sleep | Waking on a loud call (see Hearing) |

### Properties each organism must carry

| Property | Used by | On main |
| --- | --- | --- |
| Position and heading | all | Yes |
| Radius | vision, touch, surface distance | Yes |
| Mass | relative size, scent of animals | Yes |
| Current speed | hearing (loudness) | Derivable, not stored |
| Loudness (0 to 1) | hearing | No |
| Scent strength (0 to 1) | smell | No |
| Call state and radius | hearing (calls) | Radius is a trait; "is calling" is not stored |
| Asleep | hearing, smell, vision (sleeper is silent) | Yes |
| Genetic similarity | mate class | Yes (`mating.py`) |
| Visibility (size, camouflage) | vision | No; optional |

### What the world needs, in order

1. **Wire `sense()` in** (`SENSE.12`), with the real classifier. Without this none of the genes changes
   behaviour.
2. **Supply loudness, scent and the edge distance** to `Neighbour` and `sense()`: speed-based loudness,
   mass or biomass-based scent, the wall distance.
3. **Emit calls.** The alarm and mating calls need the world to act on those two brain outputs
   (`BRAIN.10`); until then hearing only has movement noise.
4. **Attacks and pain.** The trade-off in vision pays only once there are threats. This is `BRAIN.10`
   and the predation rules.
5. **Optional later:** a scent field for trails (`SENSE.20`), visibility properties (`SENSE.21`), canopy
   shade for vision.

## Risks

| Risk | Why | What to do |
| --- | --- | --- |
| Narrow vision wins before predators exist | A narrow sharp eye sees farther at the same cost, and nothing yet threatens a creature from the side | Calibrate only after attacks exist (`SENSE.13`); keep both ends of the frontier cheap |
| Acuity gene drifts unused | Half of random pairs have more acuity than the field allows | Start on the frontier; test that working acuity never exceeds `1 - f` |
| Random founders ignore the defaults | `World.populate` makes random genomes | Seed the sense genes (the build list does this) |
| Layout version collisions | Three tasks change the animal layout | `SENSE.16` takes version 6 and builds after `REPRO.8`, or renumbers at merge |
| Blind or near-blind founders | The sense genes can be anywhere from 0 to 1 | The first generation starts at 0.5; a lost sense is possible only by evolution (`SENSE.2`) |
| The brain cannot use the field | Narrow-field creatures see nothing at their side; the brain input says "nothing" | Wander fallback exists (`BRAIN.16`); turn-to-scan behaviour must evolve |
| Touch and taste dominate the sense bill | Old cost rule | `SENSE.13` |
| Sensing slows the world | Wide fields and more neighbours | Cell size from the real maximum reach; sense at the decision interval (`BRAIN.11`) |

## What to build

Two builds, in this order. The first is the gene change and does not need the world; the second is the
world's side. Each can be one change.

### `SENSE.16`: the genes

Written against the code at `6b84306`. Builds after `SENSE.12` lands if possible, because both touch
`sense()` and the stand-in.

1. `layouts.py`: add `GeneSpec("sight_acuity")` to the senses block of `ANIMAL_LAYOUT`, directly after
   `sight_fov`; bump `ANIMAL_LAYOUT.version` to 6 (or the next free number if `REPRO.8` has not landed:
   4 is the brain, 5 is `REPRO.8`).
2. `sense_genes.py`:
   - replace `FOV_DEGREES` with a half-angle range `FOV_HALF_DEGREES = (15.0, 180.0)` and a function
     `half_angle(f)` returning `15 * 12**f` (log scale; `TraitDef` already supports `Scale.LOG`);
   - add `working_acuity(f, a) = min(a, 1 - f)`;
   - delete `FOV_RANGE_PENALTY`; add `vision_reach(L, a_eff) = 60 * L * (0.6 + 0.8 * a_eff)`;
   - `direction_noise("vision", ...)` becomes a function of `a_eff`, not of the range gene; add
     `closeness_noise(a_eff)` and `size_noise(a_eff)`;
   - `COST_PER_AREA["vision"]` becomes `8e-6` and is multiplied by `(1 + a_eff)`; `cone_area` takes the
     total angle `2 * half_angle`.
3. `trait_defs.py`: `sight_fov` row becomes the half-angle (`Scale.LOG`, 15 to 180); a `sight_acuity`
   level row and a derived `acuity` using `working_acuity`.
4. `traits.py`: `effective_sight_range` uses `vision_reach`; keep `fov_degrees` as the total
   (`2 * half_angle`) for code that already reads it; expose `fov_half_degrees`, `acuity`, and the three
   noise values.
5. `sensing.py`: `SenseOrgans` takes the half-angle (or keeps the total and the caller passes
   `2 * half_angle`); closeness noise and relative-size noise come from the organs (the closeness error
   rule 0.03 moves out of `SensingRules` or becomes its default).
6. Founders: a function `seed_sense_genes(dna, rng, tilt)` in a new module (or on the world's seeding
   path, with `BRAIN.9`) that sets all six sense genes and `sight_acuity` for first-generation genomes:
   `0.5` plus a draw within 0.07, then the diet tilt on `sight_fov` and `sight_acuity` as above, keeping
   `a <= 1 - f`. `DNA.replaced` and a helper to encode a level into four digits do it (`BlockSpec.encode`
   exists for blocks). `World.populate` calls it. Diploid genomes set both strands.
7. Tests:
   - working acuity never exceeds `1 - f` over a grid of `(f, a)`; and equals `a` when below;
   - half-angle is 15° at `f = 0`, 52° at 0.5, 180° at 1 (log scale checks);
   - reach, noise and cost at the table points above;
   - the cost across the frontier stays within the stated band;
   - seeded founders: mean near 0.5, pure carnivore starts narrow and sharp, pure herbivore wide and
     soft, all on the frontier;
   - `sense()` with a narrow cone misses a target to the side that a wide cone reports; with the same
     seed, equal reports; zero noise gives exact reports;
   - mid setting: closeness error 0.03 as before, direction error 0.0125 (was 0.015).
8. Constants go in the `TRAIT.3` config with the names below.

### `WORLD.12`: the world properties

Depends on `SENSE.12` (the wiring) being in place.

1. `Animal` stores `speed` (distance moved last tick) and `calling` (None, alarm or mating) so the
   sensing step can read them.
2. A `neighbour_for(world, animal, other)` function builds `Neighbour` with role from the classifier,
   `loudness` (speed fraction times size, 0 when asleep), `scent` (plants: biomass fraction; animals:
   mass fraction), the call radius it is emitting, `mass` and `radius`.
3. Pass `edge_distance` (distance from the animal's surface to the nearest wall; `Bounds` knows it).
4. Cell size of the spatial index from the real maximum sense reach among living animals, updated when
   it changes.
5. Act on the brain's alarm and mating call outputs (the `BRAIN.10` part for calls): set `calling` for
   one tick, charge `call_energy_cost`; a sleeper hears at its sleep factor; a call above a threshold
   wakes a sleeper (`SENSE.7`).
6. Optional, behind a world setting: a scent field with decay (`SENSE.20`) and visibility properties
   (`SENSE.21`); not part of the first change.
7. Tests: a still animal is quieter than a moving one; a sleeper reports no loudness; a plant's scent
   grows with biomass; an animal at a wall feels it by touch; a call is heard inside both the listener's
   hearing range and the caller's call radius; a creature facing away does not see something behind it
   but does hear it; same seed, same world.

## Constants for the TRAIT.3 config

| Name | Value | Used in |
| --- | --- | --- |
| `FOV_HALF_DEGREES` | 15 to 180, log: `15 * 12**f` | `sight_fov` |
| `ACUITY_CEILING` | `1 - f` | working acuity |
| `SIGHT_REACH_BASE` | 60 | vision reach |
| `ACUITY_REACH` | `0.6 + 0.8 * a_eff` | vision reach |
| `ACUITY_DIRECTION_NOISE` | `0.02 - 0.015 * a_eff` | `sense()` |
| `ACUITY_CLOSENESS_NOISE` | `0.05 - 0.04 * a_eff` | `sense()` |
| `ACUITY_SIZE_NOISE` | same as direction noise | `sense()` |
| `VISION_COST_PER_AREA` | `8e-6 * (1 + a_eff)` | `sense_cost` |
| `FOUNDER_SENSE_SPREAD` | 0.07 around 0.5 | seeding |
| `FOUNDER_DIET_TILT` | 0.3 (field `0.5 - 0.3 * tilt`) | seeding |

## Questions for the owner

Filed as GitHub issues, each with a recommended default that the build assumes until answered.

| Question | Issue and task | Default |
| --- | --- | --- |
| What shape is the field-against-acuity trade-off: a hard ceiling, one linked dial, or a soft penalty? | [#88](https://github.com/dwhagar/evolutionSimulator/issues/88) `SENSE.17` | Hard ceiling: working acuity is the smaller of the acuity gene and one minus the field gene |
| Do hearing and smell also get a separate acuity gene, or does one gene set both their range and accuracy? | [#89](https://github.com/dwhagar/evolutionSimulator/issues/89) `SENSE.18` | One gene each for now |
| Is the predator and prey difference only the first generation's starting point, or permanently linked to diet? | [#90](https://github.com/dwhagar/evolutionSimulator/issues/90) `SENSE.19` | Starting point only; evolution is free |
| Should smell leave trails that fade (a scent field), or only come from the things themselves? | [#91](https://github.com/dwhagar/evolutionSimulator/issues/91) `SENSE.20` | From the things themselves; trails later if wanted |
| Should things be harder or easier to see (size, movement, camouflage), or is everything equally visible? | [#92](https://github.com/dwhagar/evolutionSimulator/issues/92) `SENSE.21` | Equally visible within range, apart from size through the surface distance |
