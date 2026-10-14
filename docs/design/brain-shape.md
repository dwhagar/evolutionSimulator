# Brain shape that evolves

Design note for `BRAIN.13`. Written 2026-10-14 by the Research 1 thread. It builds on
[brain.md](brain.md) (what the brain is and how it is built today), on the owner's answer in
[#28](https://github.com/dwhagar/evolutionSimulator/issues/28) (the brain's shape can evolve; genes control the
network and how it operates; a creature cannot change its network after birth) and on
[#5](https://github.com/dwhagar/evolutionSimulator/issues/5) (the genome stays a fixed length).

**Who this is for.** The owner, who is new to neural networks, and the thread that builds this. The
first sections explain the idea in plain terms; the later ones say exactly what changes in the code.

**Status.** Draft design, nothing built. Figures marked *measured* come from small scripts run against the
merged `DNA`, `BlockSpec`, `Brain` and `AnimalTraits` code while writing this note.

## Contents

1. [Summary](#summary)
2. [The problem](#the-problem)
3. [The idea: a maximum brain with switches](#the-idea-a-maximum-brain-with-switches)
4. [What the genes control](#what-the-genes-control)
5. [Recommended layout](#recommended-layout)
6. [How it fits the DNA code](#how-it-fits-the-dna-code)
7. [Mutation](#mutation)
8. [The energy cost link](#the-energy-cost-link)
9. [Speed](#speed)
10. [What changes in the code](#what-changes-in-the-code)
11. [Risks and tests](#risks-and-tests)
12. [Open questions](#open-questions)
13. [Sources](#sources)

## Summary

- **The owner's two requirements fit together.** The DNA keeps one fixed length, and the shape of each
  creature's brain still evolves, if the genome holds a **maximum-size brain** and genes that **switch
  parts of it on or off**. The switches are set at birth by the genome and never change in a life, which is
  what the owner asked for.
- **Recommendation.** Keep the existing network design and add three kinds of gene:
  1. **A gate per hidden neuron.** A neuron whose gate is off does not exist for that creature: it does not
     think and does not cost energy. The slot stays in the DNA as unused code that can wake up later.
  2. **Connections switched off by weight size.** A connection whose weight is close to zero counts as
     missing, for both its effect and its energy cost. This needs no new genes and also solves `BRAIN.12`
     (a way to switch a connection off completely).
  3. **A few "how it operates" genes**: how sharp decisions are (gain), how often the brain runs (reaction
     time), how much it explores (curiosity) and how fast it learns (learning rate, `BRAIN.15`).
- **Size.** A maximum of **16 hidden neurons** (the first brain has 8) makes the animal genome **877 digits**
  (65 body, 812 brain), against 461 now (*measured*). About 8 neurons start switched on.
- **How fast the shape changes.** At the planned one brain mutation per child, about **1.3 in 100 children**
  have a neuron switched on or off (*measured*). That is a deliberately slow rate that can be raised.
- **Energy keeps it honest.** Each extra fully wired hidden neuron costs about **0.45% of an average animal's
  resting energy** (*measured* from the current constants), so a bigger brain has to earn its keep.
- **One bug to fix first.** Today the cost of thinking counts only connections above a threshold (0.25), but
  the network uses every weight. About one random weight in eight acts for free. One threshold for both
  fixes it ([The energy cost link](#the-energy-cost-link)).

## The problem

The merged brain has a fixed shape: 17 inputs, 8 hidden neurons, 6 outputs, 198 numbers, stored as 396
digits. Evolution can change the numbers, which changes what the brain does, but not how big it is. The
owner wants more: the shape itself should be able to evolve, so one species can end up with a tiny
brain and another with a large one. The usual method (called NEAT, see [Sources](#sources)) grows a network by adding
neurons and connections, which needs genomes of different lengths. The owner has chosen a fixed-length
genome ([#5](https://github.com/dwhagar/evolutionSimulator/issues/5)), so the shape has to evolve *inside* a fixed-size
container.

## The idea: a maximum brain with switches

Picture a rack with 16 slots, each able to hold one hidden neuron with all its wiring. Every creature's DNA
describes all 16 slots, plus a gate for each slot. At birth the creature reads the DNA and builds a brain
from the slots whose gate is on. A creature with 5 gates on has a 5-neuron brain, one with 12 on has a
12-neuron brain, and both have DNA of exactly the same length.

This is not an invention for the simulator. Real nervous systems also produce more connections than they keep
and then remove the unused ones (the standard name is *synaptic pruning*), and real genomes carry
switched-off genes that can be reactivated, which is how many new functions arise. A switched-off slot is
the same thing: a spare part that costs nothing to run and may come in handy later.

The switch is decided only by the DNA, once, at birth. During life the shape is fixed, as the owner asked.
(What changes during life is the numbers inside the shape, through nightly learning:
[brain-learning.md](brain-learning.md).)

## What the genes control

The owner said genes control "the network and how it operates". These are the options, with a recommendation
for each.

| What | How | Recommendation |
| --- | --- | --- |
| Which hidden neurons exist | A gate value per slot; on when it is above zero | **Yes.** The main shape gene. |
| A different way: how many hidden neurons exist | One count gene (`n`), neurons `0..n-1` used | Not recommended. A count gene changes by jumps, loses all later neurons at once, and cannot keep a good neuron 5 while dropping neuron 3. Per-neuron gates evolve more smoothly. |
| Which connections exist | A weight inside a "dead zone" around zero counts as no connection | **Yes.** No new genes; one threshold shared by effect and cost. |
| Which senses the brain listens to | Covered by the dead zone: an input whose weights to every hidden neuron are in the dead zone is ignored and costs nothing | Yes, nothing extra to build. |
| How sharp decisions are | One *gain* value multiplying a neuron's input sum before `tanh` (high gain gives near on/off decisions, low gain gives gradual ones) | **Yes**, one gene for the whole brain. A gain per neuron would add 16 values for little extra. |
| How often it thinks | Decision interval in ticks (the existing item `BRAIN.11`) | **Yes**, one gene. A creature that thinks every tick pays more energy and reacts faster. |
| How much it explores | A *curiosity* value: the size of random noise added to the outputs (needed for learning, see [brain-learning.md](brain-learning.md)) | **Yes**, one gene. |
| How fast it learns | A *learning rate* | **Yes**, one gene (`BRAIN.15`). |
| How much it sleeps | A sleep-need value (belongs with the day-night cycle, `WORLD.5`) | Decide when `WORLD.5` is designed; one more gene of the same kind. |
| The kind of neuron | A choice of curve per neuron (smooth, step, linear) | Not now. It makes the network harder to understand and test for no clear benefit at this size. |
| Brain structure changing during life | Switching gates after birth | **No**, by the owner's decision. |

The four "operates" values are ordinary single genes with a range, like `speed` or `fear`. They belong in the
body segment and the trait table (`trait_defs.py`), with a range and a mutation step, so the brain
code receives them as plain numbers and still knows nothing about DNA. That is 4 genes of 4 digits, 16 more
digits (about 893 in total).

## Recommended layout

### The slots

- **Maximum brain:** 17 inputs (unchanged for now; `SENSE.1` may change them), up to **16 hidden neurons**,
  6 outputs.
- **One group per slot** of 25 values: **the gate**, the bias, the 17 incoming weights and the 6 outgoing
  weights. After the 16 groups come the 6 output biases. That is `16 × 25 + 6 = 406` values, two digits each,
  **812 digits** (*measured* with the real `BlockSpec`), and **877 digits** in the animal genome with the 65
  body digits.
- **The gate is the first value of each group**, written with the same two-digit encoding as the weights
  (16 levels from -2 to 2). The neuron exists when its gate is above zero. Keeping the gate *inside* the
  group means it travels with its own weights when whole neurons are crossed over, and nothing in `DNA` has to
  change to hold it.
- **First brain.** Seeded creatures start with 8 slots on and 8 off. The 8 off slots start with weights near
  zero, so waking one up later changes little at first.

Larger maxima cost genome length: *measured* genome sizes are 477 digits for a maximum of 8, 677 for 12,
**877 for 16** and 1,277 for 24. Sixteen is twice the starting size, so brains can double. If the owner wants
a higher ceiling it is a number, not a redesign.

### The dead zone

A weight is **off** when its absolute value is below a threshold. With the two-digit weights (levels
-2, -1.73, ... -0.13, +0.13, ... +2) the share of random weights that are off is, *measured*:

| Threshold | Share of random weights off |
| --- | --- |
| 0.25 | 12.5% |
| 0.5 | 24.9% |
| 1.0 | 50.0% |

The threshold is a setting. A larger dead zone gives sparser brains from the start but more evolutionary
work to wire anything up. A starting value of 0.5 (about a quarter off at random) is a reasonable middle; the
real choice is to use **one threshold both in `Brain.decide` and in the cost**.

This is also the answer to `BRAIN.12`. The item asks for an exact zero because the two-digit encoding has none
(the nearest levels are plus and minus 0.133). A dead zone gives the same ability to switch a connection
off completely, with no change to the encoding and no new gene.

### The brain object

A brain is built from the genome values with the gates and dead zone applied:

1. Drop every hidden neuron whose gate is not above zero (and its row of outgoing weights).
2. Set every remaining weight inside the dead zone to exactly zero.
3. The result is an ordinary `Brain` with `hidden` equal to the number of neurons that exist.

`BrainShape` today describes one fixed network. The cleanest change is a second small description for the
*genome* side (`max_hidden`, `inputs`, `outputs`) and a function that turns genome values into the realized
`BrainShape` and `Brain`. The `Brain` class itself needs only one new input, the gain, and no knowledge of
DNA.

## How it fits the DNA code

Everything uses what already exists in `dna.py` and `layouts.py`.

| Piece | What happens |
| --- | --- |
| `BlockSpec` | The brain block changes from `count=198` and groups of 24 to `count=406` and groups of 25, with the last group the 6 output biases. Same two digits per value, same range. `groups` is already `DEFAULT_SHAPE.group_sizes`, so the group sizes follow the shape. |
| Layout version | The animal layout goes from version 2 to 3 because genes are resized. Saved genomes refuse to load into a different version, so old saves are not silently misread. |
| Segments | Unchanged: `body` and `brain`. The gate and weights are one segment. The four operating genes are body genes. |
| Crossover | `crossover_by_unit` already takes whole groups from either parent, so it takes **whole slots with their gates**. A child never gets a gate from one parent and the matching weights from the other. |
| Per-segment mutation | The brain segment's 1.0 expected change per child is spread over 812 digits instead of 396 (0.0012 per digit instead of 0.0025). |
| Traits | The trait table gains four rows (gain, reaction time, curiosity, learning rate) with ranges and mutation steps. `unread_genes()` already ignores blocks. |
| Seeding (`BRAIN.9`) | The fitted seed brain has 8 neurons, so the seed is encoded into the first 8 slots with gates on and the rest with gates off. `BlockSpec.encode` and `DNA.replaced` already do this. |

One caution about unit crossover. Slot 3 in one parent and slot 3 in the other were never related: they are just
the third positions in two unrelated brains. Taking whole slots keeps each slot's own wiring intact, which is
the best that can be done without a method for matching neurons across parents (NEAT's solution,
which needs variable-length genomes).

## Mutation

### Sizes and rates

| Change | How it happens | Measured effect (rate of one brain mutation per child, 16 slots) |
| --- | --- | --- |
| A gate flips | A mutation hits one of a gate's two digits and moves its value across zero | 1.35% of children get a gate flip, a third of the hits on gate digits |
| A weight changes | A mutation hits one of 780 weight and bias digits | Most mutations; the first digit of a weight moves it by about 0.4 of its range on average, the second by about 0.1 (see [#15](https://github.com/dwhagar/evolutionSimulator/issues/15) and `DNA.8`) |
| A weight crosses the dead zone | The same weight mutation takes a weight between on and off | A side effect of the above |
| An operating gene changes | Body-segment mutation (about 0.65 changes per child over 65 digits) | Same rules as every other body gene |

At the planned rate a population of 500 sees about 7 neurons switched on or off per generation, so shape
changes are possible but not constant. If shape needs to evolve faster, the clean fix is a **per-entry
mutation multiplier inside a group** (for example gates mutated five times more often than weights), which
is the same mechanism as the per-position weight in `DNA.8`. Without it the gate rate can only be raised by
raising the whole brain segment's rate, which also speeds up weight changes. The alternative, putting the
gates in their own segment, would allow a separate rate but would separate each gate from its neuron during
crossover, so it is not recommended.

### Spare slots

A slot that is off is not under selection: its weights mutate freely and drift to random values. When a
mutation switches it on, it arrives with random wiring that is usually harmful at first, like a new
random neuron appearing in a working brain. Two things make that tolerable. Waking a neuron is rare (the
rate above), and most of the time an unhelpful neuron is quickly selected out. Starting spare slots near zero (the seed
does this) helps only for the first generations, because drift then randomises them. If the cost of this
turns out high in practice the options are a softer gate (neuron strength rises smoothly from 0 to 1 as the
gate goes from 0 to 1, instead of switching at 0) or a lower weight-mutation rate on spare slots. Neither is needed at
the start.

## The energy cost link

`BRAIN.5` (thinking costs energy) is approved. The cost already exists as constants in `traits.py`:
`BRAIN_NEURON_COST` 0.0005 per hidden or output neuron per tick, `BRAIN_CONNECTION_COST` 0.0001 per active
connection, and `BRAIN_ACTIVE_THRESHOLD` 0.25. With the gates and the dead zone, the cost is computed from the
**realized** brain (neurons that exist and connections that are on), so a creature pays only for the brain it
has.

*Measured* with the current constants, against a mean basal metabolism of 0.624 per tick for random animals:

| Brain | Upkeep per tick | Share of mean basal |
| --- | --- | --- |
| 4 hidden, all connections on | 0.0142 | 2.3% |
| 8 hidden, all on (the current shape) | 0.0254 | 4.1% |
| 16 hidden, all on | 0.0478 | 7.7% |
| 16 hidden, half of connections on | 0.0294 | 4.7% |
| Average random animal today | 0.0231 | 3.7% |

One more fully wired hidden neuron costs `0.0005 + 23 × 0.0001 = 0.0028`, or **0.45% of mean basal**, and
more neurons only pay off if they improve decisions by more than that. The same cost makes
pruning pay: switching off half of a 16-neuron brain's connections saves about 3 percentage points of basal.
That is the pressure that makes shape evolution meaningful, and the constants belong in the `TRAIT.3` config
so they can be tuned together with the world.

**An inconsistency to fix.** The cost counts connections with `|w| > 0.25`, but `Brain.decide` uses every
weight. At the two-digit encoding the levels plus and minus 0.133 are the only ones in between, which is 12.5%
of random weights: connections that change what the creature does and cost nothing. The dead zone removes
this by making the same rule apply to effect and cost. (The `TRAIT.3` config item should hold the one
threshold.)

## Speed

Pure Python, standard library only, *measured* per decision: 4 hidden neurons 9.6 microseconds, 8 hidden 16.2,
12 hidden 24.1, 16 hidden 28.7. A brain with fewer neurons is faster, so creatures that evolve small brains
also run faster. A full 16-neuron brain is about 1.8 times the cost of today's. Dropping neurons and
zeroing dead-zone weights *before* building the brain at birth means the decision loop only does work for what
exists. Pre-computing the realized brain once at birth is enough; nothing is rebuilt per tick.

## What changes in the code

A checklist for the build thread, in order:

1. **Add the gate and the dead zone to the brain description.** A genome-side description (max hidden,
   inputs, outputs), and `Brain` built from genome values with gates and dead zone applied; the gain becomes
   an argument. Keep `Brain` free of DNA.
2. **Change the brain block** in `layouts.py`: count 406, groups of 25 plus the output-bias group; layout
   version to 3.
3. **Add four operating genes** (gain, reaction time, curiosity, learning rate) to the animal layout and
   the trait table, with ranges and mutation steps.
4. **Use one active-connection threshold** in `Brain.decide` and in `AnimalTraits` upkeep, taken from the
   `TRAIT.3` config; count only realized neurons and connections.
5. **Seed** (`BRAIN.9`): encode the fitted 8-neuron brain into the first 8 slots, gates on; leave the rest
   off.
6. **Optional, later:** a per-entry mutation multiplier inside a block group, to set the gate rate on its
   own.

## Risks and tests

| Risk | Why | Mitigation |
| --- | --- | --- |
| Brains grow to the maximum | Free thinking | The energy cost, with the constants in the config |
| Brains shrink to nothing | Cost beats benefit in an easy world | A floor of one hidden neuron; a world that rewards thinking (`WORLD.2`) |
| Spare slots become harmful when woken | Drift randomises them | Rare switching; softer gate if needed |
| Dead zone makes brains too sparse | Large threshold | Tunable setting; test the share of live connections in seeded brains |
| Shape changes too slowly or too fast | One shared brain mutation rate | Measure per generation; per-entry multiplier |
| A saved genome loads into the wrong layout | Resized block | Layout version bump, already enforced |

Tests worth writing: a genome with all gates off still builds a valid brain (the one-neuron floor); a
gate flip changes the neuron count by exactly one; the energy cost equals the formula on the realized
neurons and connections; unit crossover never splits a slot from its gate; the same seed gives the same
shape; a genome with all gates on and no dead zone gives the same outputs as the equivalent fixed-shape
brain; the seeded 8-neuron brain is unchanged by the 8 spare slots.

## Open questions

Decisions the owner should make, raised as issues so they can be answered there. Each has a default the
build will use until then.

| Question | Issue | Default |
| --- | --- | --- |
| How large may a brain grow (maximum hidden neurons), and may unused neurons stay in the DNA? | [#52](https://github.com/dwhagar/evolutionSimulator/issues/52) (`BRAIN.17`) | 16 hidden neurons, unused slots allowed |
| Which "how it operates" settings should be genes: sharpness (gain), reaction time, curiosity, learning rate? | [#54](https://github.com/dwhagar/evolutionSimulator/issues/54) (`BRAIN.18`) | All four |

Already asked: whether a fixed-length genome with on/off switches is acceptable
([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 6, default yes), and the shape decision itself
([#28](https://github.com/dwhagar/evolutionSimulator/issues/28)).

## Sources

Standard references, cited from memory. Check any detail before relying on it.

- Stanley and Miikkulainen 2002, "Evolving neural networks through augmenting topologies", *Evolutionary
  Computation*: NEAT, networks that grow, and the matching problem for crossover. The approach this note
  avoids because it needs genomes of different lengths.
- Wagner 2005, *Robustness and Evolvability in Living Systems*: neutral changes and why switched-off or
  redundant parts help later innovation.
- Huttenlocher 1979, "Synaptic density in human frontal cortex": the classic study of connections being
  overproduced and then pruned in a developing brain.
- This repository: [brain.md](brain.md), [brain-learning.md](brain-learning.md),
  [dna-traits-interaction.md](dna-traits-interaction.md), `src/evolution_simulator/dna.py`,
  `layouts.py`, `brain.py` and `traits.py`.
