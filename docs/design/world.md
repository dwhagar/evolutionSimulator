# The world and its step loop

Design note for `WORLD.2` (world and step loop), `WORLD.3` (time scale) and `WORLD.4` (bounds). The
code is the `evolution_simulator.world` package. The owner's decisions behind it are in
[decisions.md](../decisions.md) (issue [#10](https://github.com/dwhagar/evolutionSimulator/issues/10));
the open question about edges and ticks is [#36](https://github.com/dwhagar/evolutionSimulator/issues/36)
question 3.

## Using it

```python
from evolution_simulator.world import World, WorldConfig, Bounds, TimeScale

world = World(WorldConfig(seed=7, bounds=Bounds((1000, 1000)), time_scale=TimeScale.from_preset("hour")))
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
| `timescale.py` | `TimeScale`, the speed presets, `Pacer` (real time to whole ticks), `format_duration` | WORLD.3 |
| `spatial.py` | `SpatialIndex`, a grid for "what is near this point" | WORLD.2 |
| `daycycle.py` | `DayCycle`: daylight, night and day number as a function of simulated time | WORLD.5 |
| `sleep.py` | `SleepRules` and the `SleepListener` hook | WORLD.5 |
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
   order, each with the willing animal of the other sex within `mating_reach` (3 units) whose genome is
   closest (see [Mate choice](#mate-choice)). `AnimalTraits.mate` charges the mating effort and, if it
   takes (chance from both fertilities), makes the bearer pregnant with a litter whose genomes
   (`DNA.reproduce`, default crossover) are fixed now. Then, in id order, each bearer whose gestation
   is up gives birth with `AnimalTraits.give_birth`: both parents pay for the litter and the young
   appear within `birth_scatter` of the bearer, as far as the animal cap allows. If a parent cannot
   pay, nobody is charged and she keeps carrying them.
4. Plants grow in id order; a ready plant drops up to `seed_capacity` seeds within its dispersal radius
   and pays each one its `seed_provision` of its own full size. Seeds are mutated clones of the parent
   (`REPRO.3`); a plant seeds only after its cooldown is over and at most `seed_capacity` seeds at once.
5. The dead are removed and the tick counter goes up by one.

Aging, energy burn, healing, the mating cooldown and the pregnancy run per **reference tick** (an hour of
simulated time) and are scaled by `World.dt = seconds_per_tick / 3600`; movement, grazing and plant growth
are per tick. A one-hour tick (`TimeScale(seconds_per_tick=3600)`) is what the numbers were set for; the
world's default is still a one-second tick until `WORLD.7` switches it, so a default world burns energy
3,600 times slower than its movement suggests.

Movement: the `turn` output turns the animal by up to `base_turn_rate` radians (a positive turn goes
right, the same side as a positive direction input, so turning toward a thing and seeing it move to
the middle use one sign). The `speed` output times `current_max_speed` is the distance moved this
tick in world units. Walls stop an animal at the edge; its heading is unchanged.

## Repeatable runs

A run is pure: the same `WorldConfig` (including `seed`), the same organisms added in the same order
and the same calls give the same world. One `random.Random(seed)` feeds everything, organisms are
visited in id order, neighbour searches return ids in order, ties break on id, and no clock or global
state is read. `World.state_digest()` hashes the whole state (including the random generator) so a
test or a user can check two runs match.

## Time (WORLD.3)

A tick is `seconds_per_tick` of simulated time, 1 second by default. The speed is how many simulated
seconds pass per real second, set from the presets (1 real second equals 1 minute, 1 hour, 1 day,
7 days, 1 month, 1 year, 10 years, 100 years, 1000 years) or any number. A year is 365.25 days and
a month a twelfth of a year. `TimeScale.ticks_per_real_second` is speed divided by tick length.

`Pacer.advance(real_seconds, max_ticks)` turns real time that has passed into whole ticks to run,
carrying the remainder. The world never reads a clock; whatever drives the run (a user interface, a
script) supplies the elapsed time. The fast presets cannot be met by any computer (a year per second
is about 31.6 million ticks per second), so `max_ticks` drops the excess and the run is slower than
the label. Nothing is queued, so a slow machine does not fall further behind.

`seconds_per_tick` changes only the clock. The traits code charges energy and ages animals per
tick, not per second, so a longer tick does not yet mean more metabolism per tick (see
[Follow-ups](#follow-ups)).

## Bounds (WORLD.4)

The world is a box from the origin to `Bounds.size`; the default is 1000 by 1000 world units, set by
the user. Edges are walls for now (the default in [#36](https://github.com/dwhagar/evolutionSimulator/issues/36)
question 3, still open). The rest of the world only calls `clamp` and `contains`, so wrap-around or
open space would be added in `Bounds` alone, though distances in the senses would then also need to
wrap.

## Day, night and sleep (WORLD.5)

`WorldConfig.day_cycle` (a `DayCycle`, or `None` for permanent daylight and no sleep) turns simulated
time into light. A day is 600 simulated seconds by default: animals live from about 22 minutes to
3.3 hours, so a real 24-hour day would leave most of them less than one night in which to learn
(`BRAIN.15`). Daylight runs smoothly from 0 at midnight to 1 at noon, `0.5 - 0.5 cos(2 pi phase)`,
and it is night while daylight is below 0.3, which is 37% of the day (about 221 ticks of 600). The
world starts at noon. `World.daylight`, `World.is_night` and `World.day` read it.

- **Plants** get the daylight as their sunlight factor each tick, so they grow by day and only
  burn reserves at night (the traits code floors sunlight at 0.05).
- **Animals** see less in the dark: the sensing step multiplies sight range by
  `SensingRules.light_factor` (0.25 + 0.75 x daylight, the default for issue
  [#41](https://github.com/dwhagar/evolutionSimulator/issues/41)). A sleeper's organs work at the
  `SensingRules` sleep factors (blind, half hearing and smell, full touch).
- **Sleep.** At night every animal with at least 15% of its energy store falls asleep (a hungrier
  one stays awake to feed, the default for "can a creature skip sleep"). A sleeper does not sense,
  think, move, eat or mate. It still ages. It burns 40% of its basal metabolism and regains 0.2% of
  its energy store per tick, a net gain of roughly a fifth of the store over a night. It wakes when
  the night ends, or earlier if an alarm call wakes it (below). These are starting values in
  `SleepRules`.
- **An alarm wakes a sleeper** (`SENSE.7`). A sleeper whose (sleeping) hearing reaches an alarm
  caller, inside the caller's call radius and at call strength `SleepRules.alarm_wakes_above` (0.2)
  or more, is `disturbed`: it wakes and stays up until the next day. Calls only happen when
  `WorldConfig.calls_enabled` is on (see [Senses](#senses-are-swappable)).
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
nothing took it away. Plants now limit each other (`PlantRules` in `WorldConfig`):

- **Soil.** Within 25 units, a plant's own biomass and its neighbours' add up. The plant keeps
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
- **Calls.** With `WorldConfig.calls_enabled` (off by default), an awake animal whose last decision
  called, and that has a call radius and the energy, pays `call_energy_cost` for each call and is
  heard this tick (`World.calls`) by animals whose hearing reaches it. Off by default because a
  call costs about seven times the basal rate and random founder brains call on most ticks, which
  killed them before they could do anything else; `BRAIN.9` and `BRAIN.10` decide the real rule.
- **Touch** sees the world's edge as well as other bodies (`World.edge_distance`).
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
- **Acting on the brain is partial.** Only turn, speed, eat and seek-mating are used. Attacking
  prey, meat, calls and retiring the fixed rule are `BRAIN.10`. Animals do not eat each other yet.
- **Sex.** One of each sex is needed (`DNA.9`), decided in `may_mate`. The reading of the sex digit (value
  modulo 2, with 2 and 3 changing the drive) is the default for question 1 on
  [#69](https://github.com/dwhagar/evolutionSimulator/issues/69).
- **Time.** See the reference tick above. Movement, grazing and plant growth are not scaled by `dt` yet
  (`WORLD.7`), and the sleep and day numbers are in seconds, so a world with a one-hour tick needs a day
  cycle of `24 * 3600` seconds or longer.
- **Sleep** energy numbers and the 600-second day are guesses to calibrate (`SENSE.13`, `TRAIT.3`).
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
  - **Sense only when the brain will look.** The brain runs every `decision_interval` ticks (1 to
    4) and repeats its last decision in between, so the world asks `AnimalTraits.cached_decision`
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
  physics) or per tick (as now). Needs the `TRAIT.3` config.
- Random first-generation animals starve before they breed, as the brain note predicted
  (`BRAIN.9`, `BRAIN.16`).
