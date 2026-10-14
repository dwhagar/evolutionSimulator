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
world.populate(animals=50, plants=300)   # random genomes at random places
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
| `organisms.py` | `Animal` and `Plant`: traits plus a place (and heading for animals) | WORLD.2 |
| `senses.py` | the `Senses` interface and `BasicSenses`, a stand-in until `SENSE.1` | WORLD.2 |
| `world.py` | `World`, `WorldConfig`, `StepReport` and the step loop | WORLD.2 |

## One tick

1. Every living animal senses the world as it stands and its brain decides (`AnimalTraits.think`,
   given the world's random generator so the wander fallback is on: an animal that senses nothing,
   or whose outputs are all quiet, turns at random and moves instead of standing still). All
   decisions are made before anyone acts, so the order of animals does not change what they see.
2. In id order each animal ages and burns energy (`update_metabolism_and_aging`, with the brain's
   speed output as the movement ratio), turns, moves and, if the brain says "eat" and a plant is
   within reach, grazes it.
3. Animals whose brain says "seek mating", that are off cooldown and have at least half their energy
   store, pair off with the nearest such animal within `mating_reach` (3 units). Each pair has one
   child (`DNA.reproduce` with `crossover_by_unit`) placed near the parents' midpoint.
4. Plants grow in id order; a ready plant drops `seed_count` seeds within its dispersal radius.
5. The dead are removed and the tick counter goes up by one.

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

## Senses are swappable

The loop calls `world.senses.perceive(world, animal)` and expects the brain's `Percepts`
([brain_adapter.py](../../src/evolution_simulator/brain_adapter.py)). Pass any object with that method
to `World(config, senses=...)` when `SENSE.1` lands. `BasicSenses` is the stand-in: sight within the
animal's range and field of view, touch (if the touch gene is above 0.1) and crowding. A lighter
animal (under 0.8 of its mass) is prey, a heavier one (over 1.25 times) a threat, and anything else
the nearest possible mate. Calls are not heard yet, so those inputs stay 0.

## Placeholders and limits

- **Energy is not conserved at birth.** A child starts at 75% energy and a seed at 15% biomass
  whatever the parents paid (`REPRO.5`). Animals pay the existing mating cost.
- **Acting on the brain is partial.** Only turn, speed, eat and seek-mating are used. Attacking
  prey, meat, calls and retiring the fixed rule are `BRAIN.10`. Animals do not eat each other yet.
- **Mating guard.** The 50% energy rule is a world setting for now; it moves with `TRAIT.5` and
  `TRAIT.3`.
- **Sex and species.** Any two willing animals of the same layout may mate; mate choice by genetic
  closeness is `REPRO.4`.
- **Population caps** (1000 animals, 5000 plants) exist so a run cannot grow without limit.
- **Speed.** Neighbour searches use a grid. Measured on one run: 300 animals and 3000 plants step in
  about 60 ms per tick in plain Python (about 5 ms per tick at 60 animals), so the faster time
  presets cannot be met at that size. Profiling the senses and the brain is a later job.

## Follow-ups

Sent to the TODO thread rather than built here:

- Whether metabolism, ageing and speed should be per second (so `seconds_per_tick` changes the
  physics) or per tick (as now). Needs the `TRAIT.3` config.
- Plant balance: with the prototype's constants a few hundred random plants reach the 5000 cap within
  about 200 ticks, so the plant growth and seeding numbers need tuning against a food limit.
- Speed: about 60 ms per tick at 300 animals and 3000 plants; profile the senses and brain pass.
- Random first-generation animals starve before they breed, as the brain note predicted
  (`BRAIN.9`, `BRAIN.16`).
