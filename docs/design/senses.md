# Senses: what creatures perceive and how it reaches the brain

Design and research note, written 2026-10-14 by the Research 3 thread. Task ID `SENSE.1`. The decisions
it needs from the owner are issues, listed under [Open questions](#open-questions).

**Who this is for.** The owner is new to this area, so each idea is explained in plain terms before it
is used. A reader who only wants the answer can read the [summary](#summary) and the
[open questions](#open-questions). Figures marked *measured* were produced by running small Python
scripts against the code in this repository while writing it; everything else about real animals is
standard textbook material, quoted from memory.

**Reads with.** [brain.md](brain.md) (the network, its 17 inputs and 6 outputs),
[dna-traits-interaction.md](dna-traits-interaction.md) (how genes become traits) and
[../research/basic-traits.md](../research/basic-traits.md) (costs and ranges). It also uses the owner's
answers on the GitHub issues, listed under [What the owner has decided](#what-the-owner-has-decided).

Task IDs and the owner's answers are recorded in [../decisions.md](../decisions.md) and
[TODO.md](../../TODO.md); this note refers to the neighbouring tasks by ID (the day-night cycle and sleep
`WORLD.5`, the evolving brain shape `BRAIN.13`, learning `BRAIN.15`, the random-movement fallback
`BRAIN.16`, mate choice `REPRO.4`, the constants config `TRAIT.3`).

> **Update, 2026-10-14 (`SENSE.14`).** Eight more inputs are built (animal layout version 8): own young
> (bearing and closeness), a mate's likeness, tiredness, the bearing and closeness of the world's edge,
> and the time of day as a sine and a cosine. See the "Inputs 21 to 28" row in [brain.md](brain.md).

> **Update, 2026-10-14 (`SENSE.15`).** The sense channels, the sensing step, the sense genes and
> inputs 18 to 20 are built (`SENSE.8` to `SENSE.11`, `SENSE.9`); `sense_genes.py` now has ranges that
> reach 0, noise that falls with the gene, and cost on the area covered, so parts of
> "What the existing code already does" below describe the code at the time of writing. The owner's
> request for a field-of-vision gene, an acuity gene with a hard trade-off, a gene per sense starting
> mid-range and different starting eyes for predators and prey, and the check of what the world must
> provide for each sense, are in [sense-genes.md](sense-genes.md). Where the two disagree (for example
> "a wider field shortens the range by 45%"), that note is newer.

## Contents

1. [Summary](#summary)
2. [What a sense is, for a simulated creature](#what-a-sense-is-for-a-simulated-creature)
3. [What the owner has decided](#what-the-owner-has-decided)
4. [Real-world senses, scaled down](#real-world-senses-scaled-down)
5. [What the existing code already does, and what the numbers say](#what-the-existing-code-already-does-and-what-the-numbers-say)
6. [Recommended set of senses](#recommended-set-of-senses)
7. [From senses to brain inputs](#from-senses-to-brain-inputs)
8. [Sense range, cost and noise](#sense-range-cost-and-noise)
9. [Evolving and switching senses](#evolving-and-switching-senses)
10. [Running it: what the world has to compute](#running-it-what-the-world-has-to-compute)
11. [Risks](#risks)
12. [Build plan](#build-plan)
13. [Open questions](#open-questions)
14. [Sources](#sources)
15. [Glossary](#glossary)

## Summary

- **A sense is a filter between the world and the brain.** The brain never sees the world. It sees a
  short list of numbers, each between 0 and 1 or between -1 and 1. A sense is the rule that turns "what
  is out there" into some of those numbers, and it decides what is lost on the way (too far, behind the
  creature, too dark, too quiet).
- **Recommended set: four outer senses plus awareness of the creature's own body and the time of day.**
  Vision, hearing, smell and touch (the genes for the first three and for touch already exist; taste
  stays a separate action, as in brain.md), the body senses the brain already has (energy, health,
  vitality, readiness to mate) plus **pain**, and **daylight**, because the owner is adding a day-night
  cycle. Thermal sense, magnetic sense, electric sense, echolocation and balance are left out until the
  world gives them a reason to exist ([table](#real-world-senses-scaled-down)).
- **The brain's inputs are grouped by what is sensed, not by which organ sensed it.** There is one
  "nearest plant" pair of inputs, one "nearest threat" pair, and so on, filled by whichever sense
  noticed the thing best. Sense genes decide how good the report is (range, field of view, noise), not
  which wires exist. This keeps the brain's interface stable while senses evolve, and it matches the
  inputs already built in `brain_adapter.py`.
- **Three inputs should be added to the 17:** pain (damage taken this tick), daylight, and the relative
  size of the nearest other animal. The last one is something the current fixed rule uses
  (`env_target_size_ratio`) that the brain cannot see, so a brain seeded from the rule (`BRAIN.9`) would
  disagree with it. That makes 20 inputs, with another ten optional ones listed for later.
- **A real problem in the current sense costs.** At the same energy cost, smell scans about 25 times the
  area of the best narrow eye and hearing about 18 times (*measured*, [section 5](#what-the-existing-code-already-does-and-what-the-numbers-say)),
  and the minimum ranges mean no creature can ever be blind. If nothing limits what hearing and smell
  can report, every population will evolve a big nose and ignore its eyes. The fix recommended here is
  that each sense can report only some things, imprecisely, then a cost review once there is a world.
- **Evolving senses has three layers:** the strength of each organ (its genes), whether the brain is
  wired to use it (the brain's connections, which the owner has said can evolve), and whether the organ
  exists at all (a gene that can reach zero). New kinds of sense are added by the developers when the
  world needs them, not invented by mutation.

## What a sense is, for a simulated creature

Think of a creature standing in the world. The world knows everything: where every plant, animal and
wall is, how big each is, whether it is moving. The creature's brain knows nothing except the numbers it
is handed each time it decides. Between the two sits the **sensing step**, run by the world loop for each
creature just before the brain thinks:

```
 world (everything)  --sensing step-->  brain inputs (20 numbers)  --brain-->  outputs (6 numbers)
                          ^
                          |  uses the creature's sense genes:
                          |  range, field of view, noise, whether the sense exists
```

Three ideas cover almost everything below.

**1. A sense limits what gets through.** A creature with short-range vision reports "nothing there" for
a plant 50 units away, even though the plant exists. That is the whole mechanism: a missing report is a
zero in the inputs. Evolution can improve the sense (longer range), or improve the brain's use of what
it gets, and both cost energy.

**2. Egocentric and scaled.** Everything is measured from the creature's own position and heading
(direction: -1 hard left, +1 hard right) and squeezed into a fixed range. This is already the contract in
brain.md. It means a brain's numbers mean the same thing whatever the creature's size or position, so
good brains are copyable from parent to child.

**3. Closer means bigger.** A "closeness" input is 1 when something touches the creature and falls to 0
at the edge of what it can sense. A strong input is something important and near, which is what a small
network needs to respond to first.

## What the owner has decided

Collected from the issue answers on 2026-10-14. These are the constraints the design has to meet.

| Decision | Where | What it means for senses |
| --- | --- | --- |
| The world is continuous 2D, with 3D kept possible later; bounds set by the user, default 1000 by 1000 | [#10](https://github.com/dwhagar/evolutionSimulator/issues/10) | Distances are in world units; the creature has an edge it can run into. Directions are one angle now, and a second angle (up or down) must be easy to add later. The answer says "grid" in the last line; this note reads it as 1000 by 1000 *units* of continuous space. |
| One tick is 1 second of real time by default; the time-scale choices (1 second = 1 minute up to 1000 years) change what a tick stands for | [#10](https://github.com/dwhagar/evolutionSimulator/issues/10) | Sensing is done per tick or per decision, so its cost has to be low enough to run at the faster scales. |
| The brain is a neural network (B), "also genetic factors", and it **learns during life**: at night creatures sleep, regain energy and their weights update | [#23](https://github.com/dwhagar/evolutionSimulator/issues/23) | There is a **day-night cycle**, so light is a sense input and sleep changes what the senses do. The inputs a creature met during the day are what the nightly update works from. |
| Memory: none at birth, but the creature gains it over its life through nightly weight changes | [#24](https://github.com/dwhagar/evolutionSimulator/issues/24) | The senses can stay memoryless. Anything the creature needs to "remember" is carried in its weights, not in extra inputs. |
| Thinking costs energy | [#25](https://github.com/dwhagar/evolutionSimulator/issues/25) | Every connection from an input to a hidden neuron costs energy, so an unused sense can be unplugged cheaply. |
| Fall back on random movement when the brain cannot decide, so the senses start providing information | [#27](https://github.com/dwhagar/evolutionSimulator/issues/27) | A creature with all-zero inputs must still be able to move around. This is the world loop's job, not the senses', but it means a creature that senses nothing is not stuck forever. |
| The brain's shape evolves (option C): genes control the network and how it operates; it cannot change after birth. How this fits fixed-length DNA is still to confirm ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 6) | [#28](https://github.com/dwhagar/evolutionSimulator/issues/28) | The list of input channels should be a fixed registry, and which inputs are wired to what is what evolves. A fixed maximum set of inputs with evolvable connections (a weight that can be switched off) fits fixed-length DNA whichever way question 6 goes. |
| Animals reproduce sexually, prefer their own species, can cross-breed; plants are asexual | [#4](https://github.com/dwhagar/evolutionSimulator/issues/4) | "Nearest possible mate" has to take species similarity into account; the brain may need to see how similar the candidate is (optional input below). |
| Three reproduction genes: caregiving, a limit on how often to reproduce, and a drive to reproduce, all affecting behaviour | [#17](https://github.com/dwhagar/evolutionSimulator/issues/17) | Caregiving implies the creature can tell its own young from other animals (optional input below). |

## Real-world senses, scaled down

Each row says what the sense does in real animals, what a small version would be in this simulation, and
a recommendation. "Cost" is the energy the creature pays for having it; every sense in the simulation
must have one, or evolution maximises it (the first rule of the traits research).

| Sense | What it does in animals | Scaled-down version | Recommendation |
| --- | --- | --- | --- |
| **Vision** | Light is focused on a retina; gives direction and distance to many things at once, in colour. Needs light, only covers what is in front (the field of view), and wider fields give shorter useful range. | Range in units, a field of view in degrees, exact direction and distance to the nearest thing of each kind inside the cone. Reduced in the dark and by wear. | **Include.** Already genes (`sight_range`, `sight_fov`). |
| **Hearing** | Pressure waves; works in the dark, around corners and in every direction, but is blurry about direction and only detects things that make noise. | A range in all directions. Detects calls (already signals 0 and 2 in the code) and the noise of moving animals. Noisy direction. | **Include.** Already a gene (`hearing`). |
| **Smell** | Chemicals carried by air or water; works at long range and in the dark, tells "food here" and "animal of this kind passed", but direction is hard (animals compare left and right or follow a gradient). | A range in all directions. Detects plants and mates (and weakly other animals). Only a crude left-right bias, no exact direction. Not reduced by darkness. | **Include.** Already a gene (`smell`). |
| **Touch** | Pressure and contact on the skin; whiskers extend the reach a little. Short range, always accurate, cannot be fooled. | Contact within the tactile range (body radius times 1.1 to 2.6); also tells the creature it has hit the edge of the world. | **Include.** Already a gene (`touch`). |
| **Taste** | Chemical test of food in the mouth, mostly a safety check. | Already an action in the code: `inspect_food` has a chance to detect toxin. Not a continuous input. | **Keep as an action,** as brain.md says. |
| **Interoception** (feeling hunger, tiredness, pain) | Receptors inside the body report energy state, injury and fatigue. | The brain already gets energy ratio, health ratio, vitality and readiness to mate. Add **pain** (health lost this tick) and, once sleep exists, **tiredness**. | **Include.** Pain is new and matters because creatures have no memory: a creature hit by something it cannot see can still flee. |
| **Proprioception** (feeling the body's own movement) | Knowing limb positions and speed. | The creature's current speed as a fraction of its top speed. | Optional later. The brain chooses its own speed, so it can infer this. |
| **Circadian sense** (an inner clock and sensitivity to light) | Light-sensitive cells and a clock synchronise sleep and activity to day and night. | **Daylight** from 0 (night) to 1 (full day), as a fraction of a day cycle, not a number of ticks. Optionally the clock phase as two numbers (sine and cosine of the cycle). | **Include daylight.** The clock phase is optional. |
| **Thermal sense** (warm and cold, infrared in some snakes) | Temperature on the skin, or heat of nearby bodies. | Needs a temperature in the world. The traits research (issue [#11](https://github.com/dwhagar/evolutionSimulator/issues/11)) puts climate out of scope. | **Skip until the world has climate.** |
| **Magnetoreception** | Birds, turtles and others sense the Earth's magnetic field for long-distance navigation. | A compass direction. Only useful in a world with something to navigate between. | **Skip.** |
| **Electroreception** | Sharks and some fish sense the weak electric field of living animals, even buried ones. | A short-range detector of nearby animals, even those out of sight. | **Skip for now.** Interesting later as a "hunter's sense" with a different cost profile. |
| **Echolocation** | Bats and dolphins make sound and listen for echoes. | An active sense with a cost per use, giving distance in the dark. | **Skip for now.** Needs an "emit" output and a world with obstacles. |
| **Balance / acceleration** | Inner ear. | Not meaningful in a flat 2D world. | **Skip.** Becomes relevant if 3D arrives. |
| **Lateral line / vibration** | Water movement or ground vibration. | Overlaps hearing and touch here. | **Skip.** |

The "skip" rows are not forever. They are skipped because a sense that nothing in the world rewards will
evolve to a meaningless value (the same reason the traits research dropped temperature genes). Each
comes back when its matching world feature does.

## What the existing code already does, and what the numbers say

The animal traits already contain the raw material. All of the following is read from
`src/evolution_simulator/trait_defs.py` and `traits.py` at the current commit.

| Gene | Range it maps to | Where it is used |
| --- | --- | --- |
| `sight_range` (cost gene) and `sight_reach` | 0 to 60 units | `effective_sight_range = sight_reach * (0.6 + 0.8 * acuity)` (`SENSE.16`; was `* (1 - 0.45 * sight_fov)`) |
| `sight_fov` and `fov_half_degrees` | 15 to 180 degrees either side, log scale | The field of vision; `fov_degrees` is twice it. A wide field caps the acuity the eye can use |
| `sight_acuity` and `acuity` | 0 to 1 | `acuity = min(sight_acuity, 1 - sight_fov)`; lengthens the reach, shrinks the errors, adds to the eye's cost (`SENSE.16`, [sense-genes.md](sense-genes.md)) |
| `hearing` and `hearing_range` | 15 to 85 units | `current_hearing_range` |
| `smell` and `smell_range` | 20 to 100 units | `smell_range` |
| `touch` and `tactile_factor` | 1.1 to 2.6 times body radius | `tactile_range`; reflex `flag_tactile_evade` when `touch` is above 0.1 |
| `taste` | detection chance | `inspect_food` |
| `encoder_fidelity` | call radius 0 to 60, call cost 1.5 to 7.5 | Calls: signal 0 mating, signal 2 alarm |

Vitality scales sight and hearing between 40% and 100% of their range. The cost of the senses is
`0.08 * (sight_range² + hearing² + smell² + touch² + taste²)`, where each term is the gene value from 0
to 1. Seeing this against the world size (1000 by 1000 units) and the brain, five things stand out.

**1. Smell and hearing buy far more area than sight for the same energy** (*measured* by script from the
ranges above; area is what a sense covers, in square units):

| Sense (gene value 1, cost 0.08 each) | Effective range | Area covered |
| --- | --- | --- |
| Vision, narrowest field (40 degrees) | 60 | 1,257 |
| Vision, widest field (360 degrees) | 33 | 3,421 |
| Hearing | 85 | 22,698 |
| Smell | 100 | 31,416 |

At the middle of the gene range the ratio is similar (smell 11,310 against 1,164 for the widest eye).
So on the current numbers an animal that puts everything into smell can detect many times more than
one that puts it into sight, at the same cost, in every direction, in the dark. The only thing that
stops this is the information each sense is allowed to carry, which the current code does not limit:
the world is told to supply "sight and smell" for each nearest-thing input (brain.md input table).
Section 6 fixes this by giving each sense a restricted job.

**2. The field of view is almost free.** Cost is charged on the `sight_range` gene only. A narrow
field (40 degrees) gets a range of up to 60 and covers 1,257 square units; a wide one (360 degrees) gets
33 and covers 3,421, over 2.7 times as much, at the same cost. In the traits research the point of the
trade was that a wider field gives a shorter range for the same budget, but here the wider field wins on
area. Hunters with narrow eyes only win on distance, so a narrow-vs-wide choice needs more than a range
penalty (see [cost](#sense-range-cost-and-noise)).

**3. No creature can be blind.** The gene maps onto a range starting above zero (sight 10, hearing 15,
smell 20) and the cost of a gene value of 0 is 0. So the minimum sense is free and permanent, and a
creature that would do better with no eyes (a cave animal, a burrower) cannot get there.

**4. Senses are a big share of the energy budget.** Over 500 random animals the senses cost on
average 22% of basal metabolism (1% to 44%, *measured*), a mean of 0.13 energy per tick against a mean
basal budget of 0.61. The brain adds a few percent more (brain.md). So sense costs matter more than
brain costs at present, which is the opposite of what the brain note assumed.

**5. The fixed rule uses an input the brain does not get.** `_update_needs_and_drives` reads
`env_target_size_ratio` (how large the other animal is compared with this one, clamped 0.2 to 2.0).
Brain.md says every one of the 17 inputs is available to the world, and the seeding plan is to fit a
brain that agrees with the rule on 95% of random situations. That cannot work if the brain cannot see
the size ratio. It is one extra input ([below](#inputs)).

Also relevant for the brain: how many things a creature can see at once. With a uniformly spread
population and the ranges above (*computed*):

| Animals in the world | In sight range 35 | In range 60 | In range 100 |
| --- | --- | --- | --- |
| 200 | 0.8 | 2.3 | 6.3 |
| 1,000 | 3.9 | 11 | 31 |
| 5,000 | 19 | 57 | 157 |

A typical sighted animal in a population of a thousand sees a handful of others. That is the right size
for the "nearest of each kind" way of describing the world: it throws away little. In a crowd of
thousands it throws away a lot, which the crowding input partly makes up for.

## Recommended set of senses

### The four outer senses

Each sense is allowed to report some kinds of things, at some precision. They are listed so the
differences are real: no sense is simply better than another.

| Sense | Reports on | Direction | Works in the dark | Covers | Reduced by |
| --- | --- | --- | --- | --- | --- |
| **Vision** | Plants, prey, threats, mates, other animals' relative size, the world edge | Exact, within the field of view | No: range scales with daylight | Cone: `fov_degrees` wide | Daylight, vitality, a wider field (shorter range) |
| **Hearing** | Calls (alarm, mating) with their direction, and moving animals as threats, prey or mates | Noisy, all around | Yes | Circle of `hearing_range` | Vitality; sleep |
| **Smell** | Plants (food), mates, and weakly prey and threats as a presence, not an identity | A left-right bias only, noisy, all around | Yes | Circle of `smell_range` | Sleep |
| **Touch** | Whatever is in contact, and the world edge | Not needed | Yes | Tactile range (about body size) | Nothing |

Plants make no sound, so hearing cannot find them. Smell is the only sense that finds plants in the dark
and from behind. Vision is the only sense that tells exactly where a thing is. A fast-moving animal makes
more noise than a still one, so an ambusher that keeps still is quiet to hearing but not to vision or
smell. These differences give evolution something to choose between: sniffing plants out at night
versus watching for predators in daylight, rather than one sense that does everything.

The values in the table are starting rules, to be calibrated against a running world.

### The body: awareness of oneself

The brain already has energy ratio, health ratio, vitality and readiness to mate. Add:

- **Pain**: how much health was lost this tick, as a fraction of maximum health (clamped 0 to 1; any
  damage of 20% of maximum or more in one tick reads as 1). It is the only way a memoryless brain learns it
  is being attacked by something unseen.
- **Tiredness**, once the sleep mechanic exists: how much of the day has been spent awake. Not specified
  here because sleep is not designed yet.

### The clock: daylight

Because the owner is building a day-night cycle, daylight is the one sense that comes from the world and
not from other creatures: a number from 0 (full night) to 1 (full day), computed from the position in the
cycle. Two things follow.

- Vision range is multiplied by a light factor (starting value `0.25 + 0.75 * daylight`), so a creature
  that relies on vision is almost blind at night. Smell and hearing are unaffected, so a nocturnal niche
  (night-time smellers that avoid daytime predators) can arise.
- The day length is a world setting measured in ticks. The input is a fraction of the cycle, so brains
  do not need to change when the day length does.

### Do plants sense?

No. Plants do not move or decide, so they get no brain (brain.md) and no senses in the first version.
They are **sensed**: a plant can be seen, and smelled with a strength that grows with its biomass, and it
makes no sound, so hearing cannot find it. If plants later respond to light or crowding (growing toward
light, shedding seeds in space), that is part of the plant rules and the day-night cycle (`WORLD.5`), not
a sense gene.

### What is deliberately not an input

Taste (an action), the temperature of the world (no climate), the identity of the other animal's species
beyond whether it counts as a mate (see [below](#optional-inputs-for-later)), and anything the brain can
work out from what it already has (its own speed, whether it is facing a wall it can see).

## From senses to brain inputs

### The encoding rules

These extend the two rules in brain.md ("egocentric and scaled" and "a sense that cannot see a thing
gives 0").

1. **Every input lies in 0 to 1, or -1 to 1.** The hidden neurons use `tanh`, which saturates: `tanh(1)`
   is 0.76, `tanh(2)` is 0.96, and `tanh(3)` is 0.995 (*computed*). Inputs bigger than about 1 would add
   to the pile-up at the edge and make small differences invisible. The adapter already clamps every
   input to its range and rejects anything not finite.
2. **Closeness** is `1 - d / R`, clamped to 0 to 1, where `d` is the distance between the two bodies'
   surfaces (centre distance minus both radii) and `R` is the range of the best sense for that class
   (`R_class`, below). A thing at the range limit reads 0, a thing in contact reads 1.
3. **Direction** is the bearing from the creature's heading, divided by the half field of view for
   vision (so -1 is the left edge of the view and +1 the right edge) and by 180 degrees for senses that
   cover every direction. Left is negative, matching the existing `turn` output. When nothing is sensed
   both closeness and direction are 0.
4. **A class is reported by its nearest member.** For each class (plant, prey, threat, mate) the world
   finds the nearest member that any sense detected. Closeness is measured against `R_class`, the
   largest range among the senses that can report that class. Direction comes from the most precise
   sense that detected it (vision, then hearing, then smell), with that sense's noise added.
5. **Distances are in world units** and all ranges scale with the world size setting, not with the
   default 1000, so a bigger world does not make creatures near-sighted.
6. **Scaling by the creature's own range, not by the world.** Dividing by the creature's own range means
   a child with slightly better eyes than its parent can use its parent's wiring: the meaning of
   "closeness 0.5" is "half way to the edge of what I can sense". The cost is that the brain cannot tell
   absolute distance. It does not need to for steering. It does need to know whether something is within
   biting reach, and touch provides that (input "touching"). The world ignores the eat or attack output
   when nothing is in reach.

### A worked example

A creature faces east. Its vision has a field of view of 120 degrees and an effective range of 40. Its
smell range is 50. A plant lies 20 units ahead and 30 degrees to its left (*computed* by running the
rules above):

| Time of day | Vision reports | Smell reports | Plant inputs (closeness, direction) |
| --- | --- | --- | --- |
| Daylight 1.0 | closeness `1 - 20/40 = 0.5`, direction `-30/60 = -0.5` | closeness `1 - 20/50 = 0.6`, direction `-30/180 = -0.17` before noise | `R_class` is 50 (smell), so closeness is 0.6; direction comes from vision: -0.5 |
| Daylight 0.3 | Light factor `0.25 + 0.75*0.3 = 0.475`, range 19: the plant is out of reach and nothing is reported | as above | closeness 0.6, direction -0.17 plus smell noise |

By day the creature steers accurately toward the plant. At night it still knows the plant is there and
roughly where, because smell is not dimmed, but it steers worse. A brain that works with the noisy
direction is a different (and evolvable) skill from one that works with the exact one.

### Three ways to encode direction

The design question behind inputs 5 to 12 is how a brain should be told where something is. Three
options, for the four classes (plant, prey, threat, mate):

| Option | What the brain gets per class | Inputs for 4 classes (2D / 3D) | For | Against |
| --- | --- | --- | --- | --- |
| **A. Bearing and closeness** (built, recommended for v1) | One signed bearing and one closeness | 8 / 12 | Already built in `brain_adapter.py`; the natural "turn toward it" signal; small | A target directly behind flips between -1 and +1 (a seam, [Risks](#risks)); 3D needs a second angle |
| **B. Closeness-weighted vector** | The unit vector to the target in the creature's own frame (forward, sideways, and up in 3D), multiplied by closeness | 8 / 12 | No seam: behind is simply "forward is negative"; closer is stronger; nothing sensed is 0; the same idea in 3D with one more number | A little harder to read; fleeing from the side is natural, chasing something dead behind needs noise to pick a side |
| **C. Angle sectors** (a "retina" of N slices, each reporting the closeness of the nearest member of a class in that slice) | A closeness per slice | 4 classes × 5 slices = 20 / far more | Looks like real vision and animal "whisker rings"; lets a creature see two things of one kind at once | Many more inputs, so many more weights and more cost; 3D needs cones; resolution is fixed by the slice count |

All three come from the same data: the **vector from the creature to the target**, measured in the
creature's own frame. The recommendation is therefore to compute and pass around **vectors, not angles**,
inside the world and the sensing step, so 3D is a matter of one more component, and to turn them into
bearing and closeness (option A) at the end, in `brain_adapter.py`, for v1. If the seam ever causes
problems (a creature that flees badly from a threat behind it) the change to B is confined to the
adapter and to a layout version bump, with no change to the senses. Option C is the design to reach for
only if one-nearest-object proves too crude for crowded worlds.

### Inputs

The recommended inputs, grouped by where they come from. Items 1 to 17 are the ones built in
`brain_adapter.py` (same order); 18 to 20 are new. Ranges are as in brain.md.

| # | Input | Range | Source |
| --- | --- | --- | --- |
| 1 | Energy ratio | 0 to 1 | Body |
| 2 | Health ratio | 0 to 1 | Body |
| 3 | Vitality | 0 to 1 | Body |
| 4 | Ready to mate | 0 or 1 | Body |
| 5, 6 | Nearest plant: direction, closeness | -1 to 1, 0 to 1 | Vision, smell |
| 7, 8 | Nearest possible prey: direction, closeness | -1 to 1, 0 to 1 | Vision, hearing, smell (weak) |
| 9, 10 | Nearest threat: direction, closeness | -1 to 1, 0 to 1 | Vision, hearing, smell (weak) |
| 11, 12 | Nearest possible mate: direction, closeness | -1 to 1, 0 to 1 | Vision, hearing, smell |
| 13 | Touching something | 0 or 1 | Touch (includes the world edge) |
| 14, 15 | Alarm call heard, mating call heard: strength | 0 to 1 | Hearing |
| 16 | Direction of loudest call | -1 to 1 | Hearing |
| 17 | Crowding | 0 to 1 | Vision, hearing |
| **18** | **Pain** (health lost this tick, fraction of maximum health) | 0 to 1 | Body |
| **19** | **Daylight** | 0 to 1 | Clock |
| **20** | **Relative size** of the nearest animal (prey or threat class, whichever is closer): `log2(mass ratio) / 2`, so a quarter of its size is -1, equal is 0, four times its size is +1 | -1 to 1 | Vision (hearing for sound-only reports, with noise) |

Why the mass ratio is on a log scale: body mass runs from 1 to 4 in the current traits, so the ratio of
two animals is between 0.25 and 4, and the log gives equal steps for "twice as big" and "half as big".
The old rule clamped the ratio to 0.2 to 2.0, which this covers.

The crowding input is the number of other animals within the creature's sense reach divided by a
reference count, clamped to 1. Starting value for the reference is 8, taken from the table above (about
eight animals in range at moderate density).

Going from 17 to 20 inputs adds `3 × 8 = 24` hidden weights (8 hidden neurons) and 48 digits to the
genome, a layout version bump, and a change to `INPUT_NAMES` and `DEFAULT_SHAPE` in the code.

### Optional inputs for later

| Input | Range | When |
| --- | --- | --- |
| Nearest edge of the world (or obstacle): direction, closeness | -1 to 1, 0 to 1 | When creatures are seen to get stuck on walls; touch alone only warns after contact |
| Similarity of the nearest possible mate (genetic similarity, 0 to 1) | 0 to 1 | When species preference for mating is built ([#4](https://github.com/dwhagar/evolutionSimulator/issues/4)); lets the brain decline a poor match |
| Nearest own young: direction, closeness | -1 to 1, 0 to 1 | When the caregiving gene exists ([#17](https://github.com/dwhagar/evolutionSimulator/issues/17)) |
| Tiredness | 0 to 1 | When sleep exists |
| Clock phase as sine and cosine of the day | -1 to 1 | If creatures need to tell dusk from dawn, which daylight alone cannot |
| Own speed as a fraction of top speed | 0 to 1 | Probably never; the brain chose its speed |
| Ahead-or-behind for each direction (the cosine of the bearing) | -1 to 1 | See [Risks](#risks) |
| Elevation (up or down) for each direction | -1 to 1 | If the world becomes 3D |

Each is one row in a registry (see the [build plan](#build-plan)), so adding one is a small change.

## Sense range, cost and noise

### Range and cost together

The existing rule (cost proportional to the square of the gene value, range linear in the gene value)
makes cost grow roughly with the area scanned, which is sound. Two changes are recommended, both for the
reasons found in section 5.

- **Charge for what is covered.** Vision cost should depend on the area of the cone
  (`fov_degrees / 360 * effective_range²`), not just the range gene, so a wide field costs more than a
  narrow one at the same range. Hearing and smell cost the area of their circles. Each sense gets its own
  cost constant, with vision the highest. At the current constants all long-range senses together cost 22%
  of basal on average (measured); the aim is a typical animal paying a sense bill of about 10 to 15% of
  its basal budget, with an extreme specialist (a creature maxing one sense) paying 30 to 40%. These
  numbers are for calibration against a world, in the same config object as the rest of the constants
  (`TRAIT.3`).
- **Give the minimum a price,** or let it reach zero (below). A free permanent sense cannot be traded
  off.

### Noise

A sense that reports the world exactly leaves nothing for evolution to improve besides range. Noise is the
second axis of quality. Starting values for the standard deviation of the error added to the direction
input (in input units, so 0.1 is about 18 degrees on a 360-degree sense):

| Sense | Direction noise at gene 0 | At gene 1 |
| --- | --- | --- |
| Vision | 0.02 | 0.01 |
| Hearing | 0.30 | 0.15 |
| Smell | 0.50 | 0.25 |

Noise falls as the sense gene rises, so better senses are more accurate as well as longer. Closeness
gets a small error too (0.03) so creatures cannot rely on knowing exact distances. A noisy report is
drawn from the world's seeded random generator so runs repeat.

### How the existing genes plug in

| Existing gene | Role in the new scheme | Change needed |
| --- | --- | --- |
| `sight_range`, `sight_fov` | Range and field; light and vitality scale the range | Cost on cone area; light factor |
| `hearing` | Range, noise | Noise; cost on area |
| `smell` | Range, noise | Noise; cost on area; floor of 0 if issue answered yes |
| `touch` | Tactile range, contact | None |
| `taste` | Toxin detection in `inspect_food` | None |
| `encoder_fidelity` | Call range and cost | None (the sender's side of hearing) |

A possible later gene is `sense_acuity`, tier 3 in the traits research, which would set the noise level
directly. Tying noise to the existing sense genes needs no new gene.

## Evolving and switching senses

"Evolving senses" means three things that the design keeps separate.

| Layer | What evolves | How | Cost of changing it |
| --- | --- | --- | --- |
| **Strength of an organ** | Range, field of view, noise | The existing sense genes mutate | The sense cost, which rises with area |
| **Use of an organ** | Whether the brain is wired to its inputs | The brain's connections (the owner has chosen that the brain's shape evolves, [#28](https://github.com/dwhagar/evolutionSimulator/issues/28)); a weight below the threshold counts as unplugged | The per-connection energy cost, which falls when connections are pruned |
| **Existence of an organ** | Whether the sense is there at all | The sense gene can reach a value meaning "off" (a range of 0): no cost, no report, and the world does not compute it | Losing the sense, which is the point |

The order matters. A population that does not need smell first stops wiring it (cheap to do and to
undo), then its smell gene drifts down and the organ cost falls. A population that needs a sense back
can regrow it from the gene. Real evolution works this way: cave fish lose their eyes in stages.

**New kinds of sense are not invented by mutation.** Adding thermal or electric sense means new code in
the world to compute them, new genes, and a new input row. The recommendation is to add them when the
world has a feature that rewards them, as the table above says. Reserving blank genes for unknown
senses would let them drift without purpose and would count against the mutation rate.

**Switching within a life.** The day-night cycle and sleep give two natural switches that need no new
genes, only rules:

- Vision range is multiplied by the light factor.
- While asleep, each sense is multiplied by a sleep factor. Starting values: vision 0, smell 0.5,
  hearing 0.5, touch 1. A loud alarm call at full strength wakes the creature. The idea is that a sleeper
  is vulnerable but not deaf, which is what makes sleeping risky and gives evolution a trade-off to
  tune. These belong to the sleep design (an owner question below).

**Dealing with a creature that senses nothing.** The owner's answer on #27 requires a random-movement
fallback when the brain has nothing to go on. With sensible floors and a seeded brain this is rarely
needed, but with senses able to reach zero it is necessary, and it is what keeps a blind creature in the
population long enough for evolution to work on it.

## Running it: what the world has to compute

Every tick (or every decision tick, `BRAIN.11`) the world does the sensing step for each creature:

1. Find other organisms within the largest sense range the creature has. This is a **neighbour search**.
   A grid of cells about as big as the largest sense range makes it cheap: look in the creature's cell
   and the eight around it.
2. Classify each neighbour for the creature (plant, prey, threat, mate, young, ignore) using the rules the
   world already needs: diet genes, relative size, species similarity.
3. For each sense, decide which neighbours it detects (range, field of view, light, sleep, noise).
4. For each class, keep the nearest detected member and encode it with the rules above.

A plain-Python grid search over 1,000 animals spread across 1000 by 1000 with a cell of 100 took
about 13 ms per tick and looked at about 79 candidates per animal. For 5,000 animals it took about 295
ms (*measured*, the neighbour search alone, no classification). This is the same order as the brain
(about 20 microseconds per decision, 20 ms for 1,000 animals, brain.md) at a thousand animals and much
worse at five thousand, because the candidate count grows with density. Mitigations in order of effort:
size the cells to the actual largest range present rather than the maximum possible; sense every second
or third tick with the brain (`BRAIN.11`); skip senses whose gene is off; use numpy later if populations
grow, as brain.md also suggests.

Because the neighbour search runs once and every sense reads from it, adding another sense does not add
another search, only another filter.

## Risks

| Risk | Why | What to do |
| --- | --- | --- |
| Everyone evolves a big nose | Smell scans many times the area of vision for the same cost, in the dark | Limit what each sense can report; add noise; review costs once a world exists |
| Narrow eyes never win | Wide field covers 2.7 times the area for the same cost | Charge on cone area; keep the narrow eye's advantage as range |
| Direction is ambiguous behind the creature | Direction is one signed number; a target directly behind reads -1 or +1 depending on a tiny change, so turning toward it works but fleeing away from it does not | Accept in v1 (turning either way reaches a target). If creatures flee badly from things behind them, add the "ahead or behind" optional input |
| Brain cannot tell absolute distance | Closeness is scaled by the creature's own range | Acceptable; touch covers reach. If hunting suffers, add an "in reach" input |
| Seeded brain disagrees with the rule | The rule uses the size ratio and the brain did not | Add input 20 before `BRAIN.9` |
| Too many inputs | Every added input adds one weight per hidden neuron, in genome and in cost | Keep optional inputs optional; unused inputs get unplugged by evolution |
| Blind start | A world full of random brains with random senses | Seeded brains (`BRAIN.9`), the random-movement fallback, and senses that cannot all reach zero in the first generation |
| Noise makes tests flaky | Random errors on every report | All noise from the injected seeded generator; tests use a zero-noise setting |
| 3D later | One direction number is not enough in 3D | Direction inputs are a registry row each; adding "elevation" is a second row per class and a layout bump |

## Build plan

The TODO thread assigns the task IDs; the items below are proposed.

1. **A sense-channel registry.** One table (like the trait table) listing every brain input: name,
   range, class, which senses can report it. `INPUT_NAMES`, `Percepts` and `build_inputs` in
   `brain_adapter.py` are generated from it, so adding an input is one row.
2. **The three new inputs** (pain, daylight, relative size) with the brain shape change (17 to 20 inputs;
   layout version bump) and updated tests.
3. **The sensing step** as a pure function, outside the brain: given a creature's position, heading,
   senses and a list of neighbours, return a `Percepts`. Pure so it can be tested without a world and
   with a fixed seed. Includes encoding rules, light and sleep factors and noise.
4. **Sense genes**: floor at zero so a sense can be lost (if the owner agrees), noise as a function of
   the gene, a cost on covered area, all in the constants config (`TRAIT.3`).
5. **World neighbour search** (belongs to `WORLD.2`): the grid and the classifier.
6. **Calibration against a running world:** sense cost share, noise levels, light and sleep factors.
7. **Optional inputs** as the matching features arrive (world edge, mate similarity, young, tiredness).

Items 1 to 4 do not need a world and can start as soon as the owner answers the questions below, or on
the stated defaults.

## Open questions

Tracked as GitHub issues so the owner can answer there, each with a recommended default that will be
assumed until answered.

| Question | Issue | Default |
| --- | --- | --- |
| Can a creature lose a sense completely, or does every creature keep a small minimum? | [#40](https://github.com/dwhagar/evolutionSimulator/issues/40) | Vision, hearing and smell can reach zero; touch always works |
| Should darkness make creatures see less? | [#41](https://github.com/dwhagar/evolutionSimulator/issues/41) | Yes, vision range scales with daylight; smell and hearing do not |
| Should senses be imperfect, with errors in direction and distance? | [#42](https://github.com/dwhagar/evolutionSimulator/issues/42) | Yes: vision nearly exact, hearing and smell noisy, less noisy as the gene rises |
| Does the brain see only the kind of thing nearby (plant, prey, threat, mate), or also its size and species similarity? | [#43](https://github.com/dwhagar/evolutionSimulator/issues/43) | Kind plus relative size now; similarity when mate preference is built |
| Can new kinds of sense appear during a run, or is the list fixed by us? | [#44](https://github.com/dwhagar/evolutionSimulator/issues/44) | Fixed list; new senses are added when the world has a reason |
| While asleep, which senses still work? | [#45](https://github.com/dwhagar/evolutionSimulator/issues/45) | Touch fully, hearing and smell half, vision off; a loud alarm wakes the creature |

Related questions already open: the world model ([#10](https://github.com/dwhagar/evolutionSimulator/issues/10), answered; the size and shape of the
world fix the ranges), mating preference and sexes ([#4](https://github.com/dwhagar/evolutionSimulator/issues/4)), the reproduction genes ([#17](https://github.com/dwhagar/evolutionSimulator/issues/17)) and the
brain's size and learning ([#26](https://github.com/dwhagar/evolutionSimulator/issues/26), [#28](https://github.com/dwhagar/evolutionSimulator/issues/28)).

## Sources

Standard references, cited from memory for orientation. Check any figure before relying on it.

- Braitenberg 1984, *Vehicles: Experiments in Synthetic Psychology*: how very small direct sensor-to-motor
  wiring already produces lifelike steering; the standard introduction to sensors in simple creatures.
- Sims 1994, "Evolving 3D morphology and behavior by competition", *Artificial Life*, and Yaeger 1994,
  PolyWorld: evolved creatures with eyes and neural controllers.
- Nilsson 2009, "Eye evolution: a question of genetic promiscuity" and Land and Nilsson, *Animal Eyes*:
  eyes appear from simple light-sensitive cells in stages, which is the model behind "a sense can grow from
  nothing".
- Aiello and Wheeler 1995, "The expensive-tissue hypothesis", *Current Anthropology*: why neural tissue,
  and with it sensing, costs energy.
- Niven and Laughlin 2008, "Energy limitation as a selective pressure on the evolution of sensory
  systems", *Journal of Experimental Biology*: sense organs and the neural tissue behind them are
  expensive, so animals invest only in the senses they use.
- Stanley and Miikkulainen 2002 (NEAT): how networks of changing shape, including their input wiring, can
  evolve. Relevant to [#28](https://github.com/dwhagar/evolutionSimulator/issues/28).
- This repository: [brain.md](brain.md), [dna-traits-interaction.md](dna-traits-interaction.md),
  [../research/basic-traits.md](../research/basic-traits.md), `src/evolution_simulator/traits.py`,
  `trait_defs.py` and `brain_adapter.py`.

## Glossary

- **Sense:** a rule that turns part of the world into some of the brain's input numbers.
- **Organ (sense organ):** the thing that carries a sense, here represented by its genes and its cost.
- **Field of view:** the angle a creature can see in front of it.
- **Egocentric:** measured from the creature's own position and heading.
- **Class (of target):** the kind of thing a sensed object counts as: plant, prey, threat, mate.
- **Closeness:** an input that is 1 in contact and 0 at the edge of what is sensed.
- **Interoception:** sensing one's own body's state (hunger, pain).
- **Daylight:** the position in the day-night cycle as a number from 0 (night) to 1 (day).
- **Noise:** a small random error added to a report so no sense is perfect.
- **Neighbour search:** finding which other organisms are within a given distance.
