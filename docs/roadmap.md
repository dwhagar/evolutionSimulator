# Roadmap

The plan for the simulator. Major and minor versions track milestones set here; the build number
is bumped automatically on every merge into main (see [versioning](versioning.md)). Work is tracked
as task IDs (`AREA.N`) in [TODO.md](../TODO.md).

## 0.0 — Pre-release (done)

Scaffold, docs, versioning, research notes, and the first DNA and traits objects (a port of the
owner's prototype). No world or step loop yet, so nothing runs.

## 0.1 — Data models for DNA and traits (current)

Goal, set by the owner on 2026-10-14: the data models for traits and DNA are set up, with a document
on how the two interact.

Done:
- DNA and traits objects, `DNA.1` and `TRAIT.1` ([#18](https://github.com/dwhagar/evolutionSimulator/pull/18)).

Still needed:
- The interaction document, `DOCS.5`.
- The owner's answers on crossover `DNA.5` ([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)), mutation size `DNA.6` ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)), longevity cost
  `TRAIT.2` ([#16](https://github.com/dwhagar/evolutionSimulator/issues/16)), `fertility` `REPRO.2` ([#17](https://github.com/dwhagar/evolutionSimulator/issues/17)) and the world model `WORLD.1` ([#10](https://github.com/dwhagar/evolutionSimulator/issues/10)).
- The follow-ups those answers unblock: `DNA.7`, `DNA.8`, `TRAIT.3`, `TRAIT.5`; and `TRAIT.4` (traits as data).

0.1 is finished when every item above is done. Ploidy `DNA.3` ([#3](https://github.com/dwhagar/evolutionSimulator/issues/3)), genome detail `DNA.2` ([#2](https://github.com/dwhagar/evolutionSimulator/issues/2))
and variable-length genomes `DNA.4` ([#5](https://github.com/dwhagar/evolutionSimulator/issues/5)) are open design questions that do not block it.

## Next: brain

A simple neural network that can drive behaviour (`BRAIN.1` research, owner decisions `BRAIN.3` to `BRAIN.8`, then the `BRAIN.2` build). It has not
been given a version yet; the owner sets milestones.

## Later

A first runnable simulation (`WORLD.2`): organisms placed in a world with a step loop that feeds, ages
and reproduces them, with seeded runs that repeat. Needs `WORLD.1`, `REPRO.1` ([#4](https://github.com/dwhagar/evolutionSimulator/issues/4)) and the 0.1 work.
