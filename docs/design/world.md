# The world and its step loop

Design note for `WORLD.2` (world and step loop), `WORLD.3` (time scale) and `WORLD.4` (bounds). The
code is the `evolution_simulator.world` package. The owner's decisions behind it are in
[decisions.md](../decisions.md) (issue [#10](https://github.com/dwhagar/evolutionSimulator/issues/10));
the open question about edges and ticks is [#36](https://github.com/dwhagar/evolutionSimulator/issues/36)
question 3.

## Using it

```python
from evolution_simulator.world import World, WorldConfig, Bounds, TimeScale

config = WorldConfig(seed=7, bounds=Bounds((1000, 1000))).with_time_scale(TimeScale.from_preset("hour"))
world = World(config)
world.populate(animals=50, plants=300)   # random bodies with the seeded brain, at random places (seeded=False: random brains)
report = world.run(1000)                 # 1000 ticks; the report sums births and deaths
print(world.elapsed, len(world.animals), len(world.plants))
```

To place organisms yourself: `world.add_animal(dna, Vec.of(x, y), heading)` and
`world.add_plant(dna, Vec.of(x, y))`.

## Modules

| Module | What it holds | Task |
| --- | --- | --- |
| `vector.py` | `Vec`, an immutable position for any number of dimensions (only the angle helpers are 2D) | WORLD.2 |
| `bounds.py` | `Bounds`, a box from the origin to `size`, default 1000 by 1000; `clamp` makes the edges walls | WORLD.4 |
| `timescale.py` | `TimeScale` (a view of `traits.time`'s tick length and speed), the speed presets, `Pacer` (real time to whole ticks), `format_duration` | WORLD.3 |
| `spatial.py` | `SpatialIndex`, a grid for "what is near this point" | WORLD.2 |
| `daycycle.py` | re-exports `DayCycle` (`config.py`, `TraitRules.day_cycle`): daylight, night and day number as a function of simulated time | WORLD.5, TRAIT.10 |
| `sleep.py` | the `SleepListener` hook (`SleepRules` is `TraitRules.sleep` in `config.py`) | WORLD.5, TRAIT.10 |
| `organisms.py` | `Animal` and `Plant`: traits plus a place (and heading for animals) | WORLD.2 |
| `senses.py` | the `Senses` interface and `WorldSenses`: neighbour search and classifier feeding the sensing step | SENSE.12 |
| `mating.py` | `may_mate`, `mate_rank`, `choose_mate`: who may mate and who is preferred | REPRO.4 |
| `world.py` | `World`, `WorldConfig`, `StepReport` and the step loop | WORLD.2 |

## One tick

1. Every living animal senses the world as it stands and its brain decides (`AnimalTraits.think`,
   given the world's random generator so the wander fallback is on: an animal that senses nothing,
   or whose outputs are all quiet, turns at random and moves instead of standing still). All
   decisions are made before anyone acts, so the order of animals does not change what they see.
   Before this, the day-night cycle sets the light (plants get it as sunlight) and animals fall
   asleep or wake; a sleeper skips sensing and thinking.
2. In id order each awake animal ages and burns energy (`update_metabolism_and_aging`, with the brain's
   speed output as the movement ratio), turns, moves and, if the brain says "eat" and a plant is
   within reach, grazes it.
3. Animals whose brain says "seek mating" and that can mate (off cooldown, not pregnant) pair off in id
   order, each with the willing animal of the other sex within `mating_reach` (3 units, `TraitRules.world`) whose genome is
   closest (see [Mate choice](#mate-choice)). `AnimalTraits.mate` charges the mating effort and, if it
   takes (chance from both fertilities), makes the bearer pregnant with a litter whose genomes
   (`DNA.reproduce`, default crossover) are fixed now. Then, in id order, each bearer whose gestation
   is up gives birth with `AnimalTraits.give_birth`: both parents pay for the litter and the young
   appear within `birth_scatter` (`TraitRules.world`) of the bearer, as far as the animal cap allows. If a parent cannot
   pay, nobody is charged and she keeps carrying them.
4. Plants grow in id order; a ready plant drops up to `seed_capacity` seeds within its dispersal radius
   and pays each one its `seed_provision` of its own full size. Seeds are mutated clones of the parent
   (`REPRO.3`); a plant seeds only after its cooldown is over and at most `seed_capacity` seeds at once. A
   plant's age and cooldown also run on the reference-tick clock (`TRAIT.8`: it lives `longevity` days, a
   month for a first generation, and can first seed at 6% of that).
5. Corpses rot, every animal that died leaves one, the dead are removed and the tick counter goes up by one.

Aging (plants too), energy burn, healing, the mating cooldown and the pregnancy run per **reference tick** (an hour of
simulated time) and are scaled by `World.dt = seconds_per_tick / 3600`. So are movement (`dt` times the
per-reference-tick distance), turning, the energy spent moving, a bite of a plant (`graze_amount * dt`, `TraitRules.world`) and the
poison in it, a plant's growth and upkeep, and a sleeper's energy regain (`WORLD.7`). Every rate in the code is
per reference tick, whatever the tick: a one-second tick (`TimeScale(seconds_per_tick=1)`) is correct but slow,
an animal then moves 1/3600 of its per-hour distance in a tick. The default tick is one hour, which is what the
numbers were set for, so `dt` is 1 and a default animal lives about 8,765 ticks.

Movement: the `turn` output turns the animal by up to `base_turn_rate` radians (a positive turn goes
right, the same side as a positive direction input, so turning toward a thing and seeing it move to
the middle use one sign). The `speed` output times `current_max_speed` is the distance moved this
tick in world units. Walls stop an animal at the edge; its heading is unchanged.

## Repeatable runs

A run is pure: the same `WorldConfig` (including `seed`), the same organisms added in the same order
and the same calls give the same world. One `random.Random(seed)` feeds everything, organisms are
visited in id order, neighbour searches return ids in order, ties break on id, and no clock or global
state is read. `World.state_digest()` hashes the state that decides what happens next (the random generator, and each organism's place,
energy, health, age, sleep, pregnancy, learned changes and genome; `UX.9` widened it) so a
test or a user can check two runs match.

## Saving and loading (UX.9)

`world/persistence.py` saves a whole world and loads it back so that it runs on exactly as the saved one would
have: `save_world(world, "run.json.gz")` and `load_world("run.json.gz")` (gzip when the name ends in
`.gz`), or `world_to_dict` and `world_from_dict` for the JSON-ready document. It is independent of any window
and is what the run store (`UX.10`) and the save and load screen (`UX.18`) will call.

- **What is written.** The `WorldConfig` tree (every rule, read back by type, so a rule added later takes
  its default from an older save), the clock, the next id, the random generator's state, the largest body
  and canopy seen, this tick's calls, and every animal, plant and corpse: genome, position and the numbers
  that change over a life (energy, health, damage, age, cooldowns), the cached decision and wander turn,
  the learner (the day log, the open decisions and the learned offsets), the learned-brain flag and the
  pregnancy with its litter's genomes and its father. The body itself (traits, brain, costs) is rebuilt from the
  genome, the rules and the tick length by the same constructors that made it, and the spatial indexes
  are rebuilt from positions in id order.
- **Checked on load.** The document names its format and version, the gene-layout versions and the
  `state_digest` taken at save time; a file of another kind, from a newer program, from other gene layouts or
  with a restored state that does not reproduce the digest raises `SaveFormatError` instead of loading
  something almost right.
- **Versioned.** `FORMAT_VERSION` counts changes to the document's layout. When a change keeps old saves
  readable (a field renamed or moved) add a function to `_MIGRATIONS` that turns version `n` into `n + 1`;
  loading runs the chain. A change to a gene layout makes older genomes unreadable, which the layout check reports.
- **Keeping it current.** Whoever adds state to the world, an organism or the learner adds it to
  `persistence.py` (the scalar fields of organisms are name tables, so a new number is one line). The
  test `tests/test_persistence.py` is the guard: it saves a world holding every kind of state at several moments (asleep, mid-day, with litters on the way and
  fathers dead), compares every attribute of the restored world with the original (`tests/persistence_support.py`,
  not only what `state_digest` hashes), and runs both on and against an uninterrupted run.
- **Not saved.** The `Senses` object (a `WorldSenses` is saved by its settings; anything else is passed
  to `load_world(senses=...)`) and sleep listeners beyond the default learning one
  (`load_world(sleep_listeners=...)`). A father who has died and left the world is not kept: a missing father pays nothing at the birth,
  the same as a dead one.

## Time (WORLD.3)

A tick is `seconds_per_tick` of simulated time, one hour by default (`WORLD.7`; it was a second). The speed is how many simulated
seconds pass per real second, set from the presets (1 real second equals 1 minute, 1 hour, 1 day,
7 days, 1 month, 1 year, 10 years, 100 years, 1000 years) or any number. A year is 365.25 days and
a month a twelfth of a year. `TimeScale.ticks_per_real_second` is speed divided by tick length.

`Pacer.advance(real_seconds, max_ticks)` turns real time that has passed into whole ticks to run,
carrying the remainder. The world never reads a clock; whatever drives the run (a user interface, a
script) supplies the elapsed time. The fast presets cannot be met by any computer (a year per second
is about 31.6 million ticks per second), so `max_ticks` drops the excess and the run is slower than
the label. Nothing is queued, so a slow machine does not fall further behind.

`seconds_per_tick` sets the clock and, through `World.dt`, the physics: a longer tick means more
metabolism, ageing, movement, eating and growth per tick (see the reference tick above). At the default
hourly tick the presets need these ticks per real second (`TimeScale.ticks_per_real_second`), and a
default animal's life of about 8,765 ticks takes this long in real time. Measured: 60 animals and 300
plants step in about 4 ms, so about 240 ticks per second:

| Preset | Ticks per second | A life (8,765 ticks) takes | Met? |
| --- | --- | --- | --- |
| real-time | 0.0003 | 1 year | yes |
| minute | 0.017 | 6 days | yes |
| hour | 1 | 2.4 hours | yes |
| day | 24 | 6 minutes | yes |
| week | 168 | 52 seconds | yes |
| month | 730 | 12 seconds | no, about a third of it |
| year | 8,766 | 1 second | no |
| decade and up | 87,660 and up | under a second | no |

With a one-second tick the same presets need 1 (real-time) up to 31.6 million (year) ticks per second, so only
real-time and minute are within reach; that tick is for studying fast things, not for evolving.

## Bounds (WORLD.4)

The world is a box from the origin to `Bounds.size`; the default is 1000 by 1000 world units, set by
the user. Edges are walls for now (the default in [#36](https://github.com/dwhagar/evolutionSimulator/issues/36)
question 3, still open). The rest of the world only calls `clamp` and `contains`, so wrap-around or
open space would be added in `Bounds` alone, though distances in the senses would then also need to
wrap.

## Day, night and sleep (WORLD.5)

`WorldConfig.day_cycle` (a `DayCycle`, or `None` for permanent daylight and no sleep) turns simulated
time into light. A day is 24 simulated hours by default (`WORLD.7`; it was 600 seconds, set for animals
that lived minutes: now they live about a year, so a real day still leaves hundreds of nights to learn in,
`BRAIN.15`). Daylight runs smoothly from 0 at midnight to 1 at noon, `0.5 - 0.5 cos(2 pi phase)`,
and it is night while daylight is below 0.3, which is 37% of the day (about 9 ticks of 24 at the default
hourly tick). The world starts at noon. `World.daylight`, `World.is_night` and `World.day` read it.

- **Plants** get the daylight as their sunlight factor each tick, so they grow by day and only
  burn reserves at night (the traits code floors sunlight at 0.05).
- **Animals** see less in the dark: the sensing step multiplies sight range by
  `SensingRules.light_factor` (0.25 + 0.75 x daylight, the default for issue
  [#41](https://github.com/dwhagar/evolutionSimulator/issues/41)). A sleeper's organs work at the
  `SensingRules` sleep factors (blind, half hearing and smell, full touch).
- **Sleep.** At night every animal with at least 15% of its energy store falls asleep (a hungrier
  one stays awake to feed, the default for "can a creature skip sleep"). A sleeper does not sense,
  think, move, eat or mate. It still ages. It burns 40% of its basal metabolism and regains 0.2% of
  its energy store per reference tick (an hour) at average `recovery` (half to double that for the worst
  and best sleepers). Checked at the 24-hour day (`WORLD.7`): a still animal at average recovery loses
  about 5.7 energy over a whole day with its night (3% of its store) against about 13.7 awake, so sleep
  cuts the daily bill by about 40% and is never free: a night nets zero at the lowest recovery and up to
  half an energy point an hour at the highest. The numbers stay as they were. It wakes when
  the night ends, or earlier if an alarm call wakes it (below). These are starting values in
  `SleepRules`.
- **An alarm wakes a sleeper** (`SENSE.7`). A sleeper whose (sleeping) hearing reaches an alarm
  caller, inside the caller's call radius and at call strength `SleepRules.alarm_wakes_above` (0.2)
  or more, is `disturbed`: it wakes and stays up until the next day. Calls only happen when
  `calls_enabled` (`TraitRules.world`) is on (see [Senses](#senses-are-swappable)).
- **Falling asleep** clears the animal's cached brain decision and its wander turn
  (`AnimalTraits.reset_behaviour`), so it wakes with a fresh start.
- **The hook for learning (`BRAIN.24`).** `World.add_sleep_listener(listener)` registers an object
  with `fell_asleep(world, animal)` and `woke(world, animal)`, called in id order during the step.
  The nightly update can run in either.
- **Vulnerability** (issue [#57](https://github.com/dwhagar/evolutionSimulator/issues/57), default
  partly): sleepers stay in the world, so other animals sense them normally; what they can sense
  themselves follows the sleep factors in the sensing rules once `SENSE.12` wires `sense()` into the
  world. A loud call waking a sleeper needs calls to be heard first, so it is not built.

## Plant balance (WORLD.8)

The finding: with the prototype constants 300 random plants reached the 5000 cap in about 200
ticks, because a plant's growth (0.2 to 1.0 a tick) is several times its upkeep (about 0.1) and
nothing took it away. Plants now limit each other (`PlantRules`, `TraitRules.plant_limits`):

- **Soil.** Within 25 units, the biomass of a plant's neighbours (not its own, `WORLD.11`) adds up. The plant keeps
  `1 - biomass per unit of ground / capacity` of its soil access (`capacity` is 0.015 biomass per
  unit of ground), nothing at or above capacity. It is a logistic limit that does not depend on
  how fast plants grow. The neighbourhood is the same for every plant on purpose: when root radius
  set it, plants evolved the smallest roots and the limit stopped working (measured). Strengths
  that only damped growth (a divisor of 1 + k x load) also failed: with growth ten times upkeep, even
  k = 100 let the population reach the cap.
- **Light.** A heavier neighbour whose canopy covers a plant shades it by `1 / (1 + load)`, where
  the load is `1 - distance / canopy radius`, so tall plants shade seedlings.
- **Refresh.** One plant in ten is recomputed each tick, which keeps the cost low (the speed
  figures above include it).

*Measured* (1000 by 1000 world, 300 random plants, seed 1, the default day cycle, no animals):
the count dips to about 50 in the first night (most random seedlings do not survive it), then
grows slowly and settles on a daily swing between about 1100 (night) and 3400 (day) by tick 6000,
well under the 5000 cap. At capacity 0.01 the population nearly dies out and at 0.02 it peaks near
4800, so 0.015 is the middle. Plants also evolve toward fast growth and small bodies in these runs.
The daily swing comes from seedlings: they start at 15% of their body mass and the traits code
leaves them burning upkeep all night on a floor of 0.05 sunlight, so most die before dawn. That is
a `TRAIT.3` tuning matter (starter reserve or night upkeep), not a world rule. Animals eating plants
will move all of this, so the capacity should be calibrated again once animals survive.

### Seedling survival and founders (WORLD.11)

Two things killed the plants of an hourly world, both measured on 300 random founder plants in a 1000 by 1000
world with no animals, seeds 1 to 3, 3,000 ticks.

- **A plant's own biomass filled its soil limit.** The limit holds `capacity x ground` = 0.015 x 1,963 = 29
  biomass within 25 units, and a plant's growth is about ten times its upkeep, so a plant stalls where the soil
  access falls to a tenth, at about 26 biomass counting itself. A default plant is 80 (up to 200), so it never
  reached the 85% it needs to seed, whatever its neighbours did. Only plants of the smallest body could seed:
  the survivors of every run had a mean full size of 22 (the lowest the gene allows is 20), 50 to 111 plants were
  left after 3,000 ticks, and the daily swing of 1,100 to 3,700 plants seen earlier was the same effect in a
  population with room. Fix: the soil counts the neighbours' biomass only. A lone plant of any size now grows
  to full size and seeds; crowding by neighbours still limits it, and the logistic limit still keeps the
  population off the cap.
- **About 40% of random plants cannot pay their way.** Full-size upkeep over growth (`PlantTraits.upkeep_share`)
  above 0.4 meant every plant died as a seedling (none of 135 in a sparse world lived 500 ticks); below 0.3,
  about 90% lived. Seedlings run at half health, which halves their growth. `World.populate` now redraws a
  founder plant whose `upkeep_share` is above `TraitRules.plant.founder_upkeep_share` (0.3, up to 50 draws). The
  first generation is chosen for viability, as the animals' reproduction genes and brain are (`BRAIN.9`); every
  later generation is left to selection, and sizes still run from 20 to 200 in the founders.

*Result* (same worlds): 300 founders give 840 to 1,770 plants at tick 2,880 with mean full size 33 to 45, and
the day to night swing is about 7% (968 to 1,106 in one run). 40 founders pass 100 plants within 2,000 ticks (30 founders reached 180 to 790 in 3,000 before the founder filter).
With 100 seeded animals and 800 plants the plants no longer collapse (they were down to 25 to 96 plants after
3,000 ticks before, and are 1,800 to 2,300 now), but the animals still die within about 1,000 ticks, so the
food side of `WORLD.15` is not solved by this.

Tried and left out: letting upkeep follow a seedling's current size (a seedling then pays about 40% of a full
plant's upkeep). It lifted first-night survival (295 of 300 against 119, in the older soil rule) but lets thousands of stunted
seedlings sit on the soil floor without dying, because the soil counts biomass and not plants, and one run
reached the 5,000 cap. The starter reserve (15%) and the night upkeep are unchanged. Seedling mortality is still
high (about 9% of a cohort lives 240 ticks, from crowding by the parent's neighbourhood), which is the soil
limit working; it only stopped being a daily pulse.

## Founders and the energy economy (WORLD.15, first reading)

The default founder run (100 seeded animals, 800 plants, 1,000 by 1,000, hourly ticks) still ends in
extinction with no births. This is the first reading of why and of what a change of constants can
and cannot do. Every number below is from `src/evolution_tools/founder_economy.py` (seeds 1 to 3 unless said, a
run of 3,000 ticks is about 80 seconds); nothing in the rules has changed yet.

**Where the energy goes.** Per animal and tick, seed 1, default constants:

| Ticks | Alive | Gained by eating | Lost (all) | of it basal | of it healing | Bites per animal tick |
|---|---|---|---|---|---|---|
| 0 to 100 | 99 | 0.063 | 0.78 | 0.67 | 0.04 | 0.039 |
| 100 to 200 | 96 | 0.042 | 0.76 | 0.67 | 0.03 | 0.028 |
| 200 to 300 | 71 | 0.040 | 0.73 | 0.68 | 0.00 | 0.025 |

A bite is 5 biomass at about 0.4 digestion, so about 2 energy; the store is 100 to 300. The basal
bill alone is 10 to 15 times what the founders eat, so they live about 150 to 300 ticks on the store
and all are dead by tick 1,000. (`TraitRules.sleep.energy_regain`, 0.002 of the store per sleeping
hour, is a free income once the bill is lowered: lowering the burn without lowering it as well makes
sleepers gain energy, so every test below scales the two together.)

**Why they eat so little** (88% of awake animal ticks have a plant within sight, 38% of ticks are
spent asleep):

- A plant is touched once every 15 to 30 awake ticks (0.03 to 0.07 per animal tick; the seeded brain
  asks to eat on about a third of the ticks). A trace of single animals shows why: they walk to
  within 3 to 5 units of a plant, the plant leaves the 100 degree field of view, the pull on the
  animal drops to zero and they wander off or circle, and the average step over all ticks is only 0.67
  units. This is the seeded brain and the eye, not a world constant (see the follow-ups).
- About 30% of the touches are refused by taste (the plant's toxin), and the mean toxicity of founder
  plants is 0.45; an animal that stays by a poisonous plant keeps tasting it and sooner or later eats
  it (poison damage of 0.06 to 0.16 health per animal tick, healing it costs 0.03 energy).
- The founder plants are all seedlings of the same age. 800 plants fall to about 200 to 260 by tick
  500 to 800, as the first cohort dies in one wave (a month-long life, 18 to 52 days) while the
  seedlings that replace it are small (mean radius 2.5 against 6 for the founders). Plants are back
  above 1,500 by tick 3,000, when most animals are gone. Starting the founders grown (70% of full size)
  and at random ages up to half their life does not remove the dip, because 800 grown plants are
  over the soil capacity (0.015 biomass per unit of ground, about 15,000 biomass in all) and thin out
  to about 250 as well.
- A smaller world is worse: 100 animals eat a 500 by 500 world down to 62 plants by tick 1,000 and a
  300 by 300 world to none.

**Levers tried** (animals alive at tick 1,000 and 3,000, births in 3,000 ticks, three seeds; "levels"
is `FOUNDER_LEVELS` fertility 0.3 and parenting 0.1 against 0.75 and 0; bite is `world.graze_amount`,
5 by default; `tox` scales the founder plants' toxicity gene):

| Change | Alive at 1,000 | Alive at 3,000 | Births |
|---|---|---|---|
| default | 0 | 0 | 0 |
| burn x0.25 (sleep regain scaled), with or without levels | about 30 | 0 | 0 |
| bite 20 at full burn | 0 | 0 | 0 |
| burn x0.25 and bite 20, with or without levels or a diet filter | 14 to 20 | 0 to 5 | 0 |
| burn x0.1 and bite 10 to 40, levels | 74 to 81 | 16 to 28 | 0 to 3 |
| burn x0.05 and bite 20, levels | 75 to 80 | 22 to 32 | 0 |
| burn x0.1, bite 20, tox 0.3 | 76 to 81 | 28 to 35 | 0 to 3 |
| burn x0.1, bite 20, tox 0.3, wide eye, touch or smell at 1 | 75 to 82 | 20 to 39 | 0 to 6 |
| burn x0.1, bite 20, tox 0.3, founder plants grown and aged | 80 to 91 | 34 to 38 | 6 in each run |
| the same at burn x0.05, 6,000 ticks | 88 to 91 | 20 to 27 at 6,000 | 9 to 25 |

"Burn" scales the animal's whole upkeep bill (`basal_metabolism`, the sum of the body, gut, organ, brain
and temperament terms; sleeping saves against the same bill). A x0.05 to x0.1 bill is what it takes
for the store to outlast the long wait for a plant. Below x0.25 the moving cost (about 0.08 per animal
tick, 60% of what is left) is the larger part, so the kinetic burn would have to come down with it.
The burn rows were run with a knob in `BodyRules` that the script replaces by scaling the bill when
an animal is made; the two agree to within a few animals (seed 1, burn x0.1, bite 20, tox 0.3,
levels: 81 and 78 alive at tick 1,000). Even at these settings the animals keep eating less
over time (touches per animal tick fall from 0.03 to 0.01 by tick 1,000) and the first litters, which
appear around tick 1,000 to 1,500, mostly starve as newborns (10 of 25 under 300 ticks in the best
runs; parenting 0.3 gave 0 to 12 births in 8,000 ticks).

**So constants alone do not make the founders breed.** The smallest set that gets any litters
(burn x0.05, bite 20, plants 0.3 as poisonous, founder plants grown) is a world where life costs a
twentieth of what the body tables say and still shrinks from 100 to about 20 animals in 6,000 ticks,
with a few births a run. What blocks it is how little the founders eat per hour awake (one plant
touched in 15 to 30 ticks while a plant is in sight 88% of the time), how long the first breeding
takes (the maturity cooldown is about 890 ticks and the population is at its lowest by then), and
that newborns starve; the follow-ups for these went to the TODO thread with the `WORLD.15` row. The script takes these options:
`python -m evolution_tools.founder_economy burn=0.1 sleep.energy_regain=0.0002 world.graze_amount=20 tox=0.3
grown=0.7 agespread=0.5 lvl.fertility=0.3 lvl.parenting=0.1` (add `account=1` for the energy table).

## Speed (WORLD.14, WORLD.17)

A tick at 300 animals and 3,000 plants costs about 35 ms (about 140 ms at 1,000 animals). `WORLD.14`
took the cheap savings (about 8% to 10%: night learning, DNA distance, the input builder, the
per-tick light lookup) and left a flat profile: about 22% spatial queries, 30% sensing and thinking
(about 200 microseconds per awake animal), 9% plants. More than that needs a change in behaviour, so
`WORLD.17` adds two options to `TraitRules.brain` that default to today's behaviour (a run with the
defaults has the same `state_digest` as before):

- **`interval_scale`** (1.0): every animal's decision interval, as its genes give it, is multiplied by this
  when it is made (so an interval of 1 to 4 hours becomes 2 to 8 at 2.0). The brain runs less often and
  the animal repeats its last decision in between; contact and pain still cut the wait short
  (`BRAIN.22`). The brain upkeep follows the interval (a slower thinker is cheaper, as between animals).
- **`idle_interval_factor`** (1.0): an animal whose last look sensed nothing at all (no creature, plant,
  contact, call, crowd or wall: `Percepts.senses_nothing`) waits this many times its interval before it
  looks again. Contact or pain end the wait at once. It saves nothing where animals always sense a
  plant, and a lot where they roam sparse ground.

Measured on the code at the time (seed 1, best of one run, process time; ticks 20 to 120 at 300 animals,
20 to 60 at 1,000):

| Option | 300 animals + 3,000 plants | 1,000 animals + 3,000 plants | 300 animals + 200 plants |
|---|---|---|---|
| default | 35.8 ms | 143.5 ms | 21.2 ms |
| `interval_scale` 2 | 27.6 ms | 116.2 ms | |
| `interval_scale` 3 | 25.8 ms | 88.6 ms | |
| `idle_interval_factor` 4 | 35.0 ms | 143.7 ms | 18.2 ms |
| `idle_interval_factor` 8 | 32.4 ms | 146.8 ms | 14.7 ms |
| scale 2 with idle 4 | 25.4 ms | 98.2 ms | 9.3 ms |

What the options do to a run is not yet known: the default founder run (100 seeded animals, 800 plants,
1,000 by 1,000) still dies out in about 500 ticks with no births (`WORLD.15`) under every setting, so it
cannot tell them apart. Animals alive at tick 250 and 500, three seeds, default against each option, are
within the seed-to-seed spread (76 to 84 and 6 to 15). The comparison that matters (does a population
that breeds still breed, at the same size and with the same genes) has to wait for `WORLD.15`.

## Senses are swappable

The loop calls `world.senses.perceive(world, animal)` and expects the brain's `Percepts`
([brain_adapter.py](../../src/evolution_simulator/brain_adapter.py)). Pass any object with that method
to `World(config, senses=...)`. The world calls it only on ticks when the brain will look (see Speed). The default is `WorldSenses` (`SENSE.12`), the world's half of the
pure sensing step in [sensing.py](../../src/evolution_simulator/sensing.py): the step knows organs and
neighbours, the world finds and classifies the neighbours.

- **Search.** Animals within the animal's longest effective sense reach (plus body sizes), by the
  grid. For plants only the two that matter are handed on: the nearest one the animal detects and the
  nearest one within touch, because the step reports the nearest plant only and touch only needs to
  know that something is there. The grid cell is the longest range any sense can have (100), so a
  search looks at the nine cells around the animal. Distances are between surfaces (centre distance
  less both radii, a plant's radius being its canopy).
- **Classes.** A plant is a plant. An animal at most 0.8 of the viewer's mass is prey if the viewer
  can digest meat (effective carnivore efficiency above 0.1); one at least 1.25 times its mass is a
  threat if that animal can digest meat; one of about its own size is a possible mate; any other
  animal is `other`, sensed and counted in crowding but nothing else.
- **What can be heard and smelled.** Loudness is 0.1 for a still or sleeping animal and rises to 1
  at full speed. A plant makes no sound; its scent is its biomass over 100, capped at 1. Animals
  have full scent. A faint plant is therefore found by smell only close up.
- **Calls.** With `calls_enabled` (`TraitRules.world`) (on by default since `BRAIN.10`), an awake animal
  whose last decision called, and that has a call radius (the encoder gene) and more energy than
  the call costs, pays `call_energy_cost` for each call and is heard this tick (`World.calls`) by
  animals whose hearing reaches it. A call costs about seven times the basal rate, so a brain that
  calls on every tick starves itself and calling pays only for a brain that does it when it
  matters. Seeded founders (`BRAIN.9`) do not call at all; calling is left to evolve. That is the
  whole call rule: the brain decides, the world charges and delivers.
- **Touch** sees the world's edge as well as other bodies (`World.edge_distance`).
- **Family, wall, clock and tiredness** (`SENSE.14`). `classify` calls a viewer's own child *young* while it has lived less
  than the viewer's `dependence_ticks`; for a possible mate `perceive` hands `sense()` a function that compares the two
  genomes (`DNA.distance`, only when the answer is read); `World.edge_vector` gives the unit vector to the nearest wall
  for the edge bearing; `World.day_phase` gives the clock (`None` without a day cycle); `_update_tiredness` counts each
  animal's time awake (`Animal.awake_time`, cleared by sleep) as a share of a day and hands it to its traits.
- **Size and light.** Each animal neighbour carries its mass and the step gets the viewer's mass,
  for the relative-size input (`SENSE.9`); the daylight input is the world's daylight.

`WorldSenses(noisy=False)` is the zero-noise setting: every report is exact and the world's random
stream is not used. First generations get their eyes from `layouts.seed_sense_genes` (`SENSE.16`): the
sense genes start near the middle and the field of vision is tilted by diet, narrow and sharp for meat
eaters and wide and soft for plant eaters.

The sensing step is imported inside `perceive` because `sensing` itself imports from this package.

## Mate choice

`REPRO.4`. Two functions in `world/mating.py` decide everything about pairing, so the step loop does not.
`may_mate(a, b)` says whether two animals can have a child at all: the same layout, the same ploidy and one
of each sex (`DNA.9`: the sex digit modulo 2, 0 impregnates and 1 bears). `choose_mate(a, candidates)` picks the preferred
one among the willing animals in reach: the smallest genetic `distance` (the fraction of differing digits;
for diploid genomes the closer pairing of strands), then the nearer animal, then the lower id.

The closest genome is the same species or the nearest relative, so animals prefer their own kind.
Cross-breeding between distant genomes is allowed but is the last choice: it happens only when nothing closer
is in reach. There is no species label and no hard line between species; "closest" is relative to who is
there. Pairing is greedy in id order, so an animal can lose its first choice to an earlier one.

## Placeholders and limits

- **Births are paid for (`REPRO.5`, `REPRO.8`).** A bearer carries a litter for her gestation; at the
  birth each parent pays for it by its own `parenting` gene and each young starts with the mean (a dead father
  pays nothing). A seed starts with the biomass its parent paid for it (`seed_provision`). Newborns are
  juveniles for 6% of their lifespan, and the founders `populate` creates are juveniles too, so a first
  generation cannot breed until it has lived about three weeks of simulated time; random founders still starve
  before then (`BRAIN.9`).
- **Acting on the brain** (`BRAIN.10`). Turn and speed move the animal. "Eat or attack" above 0.5
  eats the plant the animal overlaps, or, if it overlaps none, bites the nearest animal it touches
  that it counts as prey (`classify`: a meat eater at most 0.8 times its mass; code in
  `world/combat.py`, constants in `AttackRules`, `TraitRules.attack`). A bite does
  `damage` (30) × carnivore efficiency × √(attacker mass / prey mass) × `dt` (damage is per reference tick, like grazing) and wakes a sleeper. What a kill is worth is
  the corpse it leaves (next item).
- **Corpses** (`WORLD.12`, `world/corpses.py`, `CorpseRules`, `TraitRules.corpses`). Every animal that
  dies, by a bite or by starving, leaves a `Corpse` where it fell, with `meat_share` (half) of its
  maximum energy as meat. The meat rots (half-life 72 reference ticks, so three days at the hourly
  tick) and the corpse goes when under 1 is left. An animal that can digest meat and whose brain
  says "eat or attack" with no plant underfoot eats from a corpse it touches (25 meat per
  reference tick, times `dt`, through `feed(..., is_meat=True)`, so its carnivore efficiency decides
  how much it gains); only then does it bite a live animal. For the senses a corpse is prey that
  cannot hide: a meat eater reports it as the nearest prey, seen in its field of view or smelled at
  the full smell range (live prey is smelled weakly), scaled by how much meat is left like a
  plant's scent grows with its biomass. Corpses make no sound, do not crowd and are in
  `state_digest`. The optional scent field (`SENSE.20`) and visibility properties (`SENSE.21`) are
  not built.
  Seek-mating and the two call outputs are acted on as described above. `AnimalTraits` keeps no
  behaviour flags any more (no "wants food", "in fear" or "wants to attack"): the brain is the
  only source of behaviour, and a body only offers `wants_mate` and `mating_energy_threshold` as
  facts the brain's `ready_to_mate` and `energy_ratio` inputs show it.
- **Sex.** One of each sex is needed (`DNA.9`), decided in `may_mate`. The reading of the sex digit (value
  modulo 2, with 2 and 3 changing the drive) is the default for question 1 on
  [#69](https://github.com/dwhagar/evolutionSimulator/issues/69).
- **Time.** See the reference tick above. Everything is scaled by `dt` (`WORLD.7`); the defaults are an hour a
  tick and a 24-hour day. The brain's decision interval (the `reaction_time` gene, 1 to 4
  reference ticks, hours) and the learning rules' `reward_window` (10 reference ticks) are times too
  (`WORLD.16`): the world gives each animal its `dt` and the animal turns them into ticks (at
  least one), so a world with a one-second tick decides every 1 to 4 hours, not every few
  seconds, and brain upkeep per hour does not change with the tick.
- **The hourly default exposes the plant ecology.** Founder plants in an hourly world mostly died before they
  seeded (growth below upkeep at seedling health, and a lone plant's own biomass filling the soil limit
  before 85% of its size): fixed by `WORLD.11` (see "Seedling survival and founders"). Seeded founder animals (`BRAIN.9`) now live about 200 ticks (12 days) in a 1000 by 1000 world
  with 120 plants before they starve; breeding them is `WORLD.15`. In the one-second world these effects were
  hidden because nothing aged or ate in a meaningful time.
- **Sleep** energy numbers are guesses to calibrate (`SENSE.13`).
- **Population caps** (1000 animals, 5000 plants) are a safety net so a run cannot grow without limit; plants now stay under theirs on their own.
- **Speed** (`WORLD.9`). Measured with `cProfile` on 300 animals and 3000 plants: the first version took
  about 62 ms per tick, mostly in the senses (generic vector arithmetic and the neighbour query
  building temporary vectors) and the brain pass. Now about 23 ms per tick (about 3 ms at 60
  animals and 300 plants), the same behaviour up to floating-point rounding (`math.sumprod` sums more exactly). What changed: `Vec` skips its checks for results it builds
  itself and uses `math.dist`; the grid stores plain coordinates and returns distances with the ids
  (`animals_within`, `plants_within`) so the senses do not measure twice; the bearing test uses
  coordinates directly; the brain's dot products use `math.sumprod`. What is left is spread thinly:
  the senses 30%, the brain and input building 35% (`sense_channels.build_inputs` and its
  clamps are the biggest single piece), plant growth 8%. The fast presets still cannot be met at
  this size.
  `SENSE.12` made it slower again: about 75 ms per tick at 300 animals and 3000 plants (6 ms at 60
  and 300), because three senses are now searched and reported instead of one, over a wider reach.
  `WORLD.13` brought it to about 44 ms (5 ms at 60 and 300) with three changes (the first alters only what the learning log
  records, the others nothing an animal perceives):
  - **Sense only when the brain will look.** The brain runs every `decision_interval` ticks (1 to 4 hours,
    that many ticks at the hourly default) and repeats its last decision in between, so the world asks `AnimalTraits.cached_decision`
    first and calls the senses only when it returns nothing. An animal that is logging its day
    (`BRAIN.24`) logs the threat it saw when the brain last looked instead of re-sensing every tick.
  - **Search by surfaces.** The grid stores each item's radius (`SpatialIndex.within_reach`,
    `World.plants_in_reach`, `World.animals_in_reach`), so a search returns exactly the things whose
    surfaces are in reach, unsorted, without the widest-canopy margin, extra lookups or a sort.
  - **One detection pass in `sense()`.** Each neighbour is measured once and its vision, hearing and
    smell detection settled once, instead of once per class and again for crowding.

  What is left: plant growth (about 7 ms for 3000 plants), the brain, and the plant loop in
  `WorldSenses`. The 25 ms of before `SENSE.12` is not quite reached; smell reaching far over many
  faint plants is the part that costs.

## Follow-ups

Sent to the TODO thread rather than built here:

- Whether metabolism, ageing and speed should be per second (so `seconds_per_tick` changes the
  physics) or per tick: answered by `WORLD.7`, they are per reference tick (hour) times `dt`, and the tick is
  an hour by default (rules in [trait-config.md](trait-config.md), `TimeRules`).
- Random first-generation animals starve before they breed, as the brain note predicted
  (`BRAIN.9`, `BRAIN.16`).
