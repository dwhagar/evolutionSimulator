# Roadmap

The plan for the simulator. Major and minor versions track milestones set here; the build number
is bumped automatically on every merge into main (see [versioning](versioning.md)). Work is tracked
as task IDs (`AREA.N`) in [TODO.md](../TODO.md).

## 0.0 — Pre-release (current)

Starting point. The scaffold, docs, versioning, research notes and the first DNA and traits objects
(a port of the owner's prototype) are in place. There is no world or step loop yet, so nothing runs.

Goals for this stage are not set (`DOCS.4`). Add milestones below as they are decided; each new
milestone becomes the next minor version (0.1, 0.2, ...).

### Candidate first milestone

A first runnable simulation: organisms with DNA and traits placed in a world, a step loop that feeds,
ages and reproduces them, and seeded runs that repeat. It needs these decisions first:

- World model, `WORLD.1` ([#10](https://github.com/dwhagar/evolutionSimulator/issues/10)), then the world and step loop, `WORLD.2`.
- Reproduction modes, `REPRO.1` ([#4](https://github.com/dwhagar/evolutionSimulator/issues/4)), and what `fertility` does, `REPRO.2` ([#17](https://github.com/dwhagar/evolutionSimulator/issues/17)).
- Crossover and mutation defaults, `DNA.5` ([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)) and `DNA.6` ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)).
- The longevity cost, `TRAIT.2` ([#16](https://github.com/dwhagar/evolutionSimulator/issues/16)), and then the constants config, `TRAIT.3`.

Open design questions that do not block it: ploidy `DNA.3` ([#3](https://github.com/dwhagar/evolutionSimulator/issues/3)), genome detail `DNA.2` ([#2](https://github.com/dwhagar/evolutionSimulator/issues/2)),
and fixed versus variable genomes `DNA.4` ([#5](https://github.com/dwhagar/evolutionSimulator/issues/5)).

## Later

_Nothing planned yet._
