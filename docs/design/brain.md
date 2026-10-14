# Brain: a small neural network for the creatures

Design and research note for the creature "brain". Written 2026-10-14 by the Research 1 thread.
Task ID `BRAIN.1`. The decisions it needs from the owner are issues, listed under
[Open questions](#open-questions).

**Who this is for.** The owner has said they know very little about neural networks, so the first
half explains the ideas in plain terms and uses no maths beyond multiplying and adding. The second
half is the design: what goes in, what comes out, how the brain is stored in the DNA, what it costs,
and how it would be built. A reader who only wants the decision can read the
[summary](#summary) and the [open questions](#open-questions).

**Status.** Draft for review. The first building blocks are built (`BRAIN.2`, `DNA.11`, `DNA.12`; see
[As built](#as-built)); the world loop, seeding and the behaviour flags are not. All figures marked *measured* were
produced by running small Python scripts while writing it; the others are standard figures from the
literature, quoted from memory (see [Sources](#sources)).

## Contents

1. [Summary](#summary)
2. [What a neural network is](#what-a-neural-network-is)
3. [How a creature's brain would be "trained": evolution, not teaching](#how-a-creatures-brain-would-be-trained-evolution-not-teaching)
4. [Options](#options)
5. [Recommended design](#recommended-design)
6. [Inputs and outputs](#inputs-and-outputs)
7. [Storing the brain in the DNA](#storing-the-brain-in-the-dna)
8. [What thinking costs](#what-thinking-costs)
9. [Getting evolution started](#getting-evolution-started)
10. [How it connects to the DNA and traits objects](#how-it-connects-to-the-dna-and-traits-objects)
11. [As built](#as-built)
12. [Speed](#speed)
13. [Risks and how to see them early](#risks-and-how-to-see-them-early)
14. [Open questions](#open-questions)
15. [Sources](#sources)
16. [Glossary](#glossary)

## Summary

- **What the brain does today.** Animal behaviour is a fixed hand-written rule in
  `AnimalTraits._update_needs_and_drives`: it reads hunger, fear, aggression and nearby threats and
  sets flags such as "wants food", "in fear" and "wants to attack". Evolution can only change two
  numbers in it (the `aggression` and `fear` genes). Nothing decides *where to move*; the rule has
  no steering.
- **Recommendation.** Replace the fixed rule with a **small feedforward neural network** (about 17
  inputs, 8 hidden neurons, 6 outputs, so 198 adjustable numbers). Its numbers (the *weights*) are
  stored in the creature's DNA, are copied to children, and are mixed and mutated with the same
  operators as the body genes. Nothing is "taught": creatures whose weights make them feed,
  flee and breed well leave more children, so good weights spread.
- **Why this and not something bigger.** It is the simplest design in which evolution can discover
  behaviour no one wrote down (steering toward food, circling, learning to avoid a bigger animal),
  it is small enough to run in plain Python (about 20 microseconds per decision, *measured*), and it
  fits the current DNA design with one new kind of gene. More advanced options (a network that
  remembers, networks whose shape evolves) are listed so they can be added later without redoing the
  first one.
- **What it costs us.** Genomes become much longer (about 460 digits for an animal instead of 65),
  so the mutation rate needs to be set per genome and not per digit, the first generation of random
  brains is useless unless we start from sensible ones, and thinking must cost energy or every
  population will evolve the biggest brain it can.
- **Decisions needed** from the owner are listed under [Open questions](#open-questions), one issue
  each, with a recommended default so work can start before they are answered.

## What a neural network is

A neural network is a way of turning a list of numbers (what the creature senses) into another list
of numbers (what the creature does) using a fixed recipe whose details are a set of adjustable
numbers. Everything else in the field is a variation on three ideas.

**1. A neuron is a weighted vote.** A neuron takes several input numbers. It multiplies each by its
own *weight* (a number saying how much that input matters, and whether it pushes up or down), adds
the results together with a constant called the *bias*, and then squashes the total into a fixed
range with a smooth S-shaped function (here `tanh`, which maps any number into -1 to +1). A large
positive weight means "when this input is high, I get excited". A negative weight means "when this
input is high, I get quieter".

**2. Neurons are stacked in layers.** The inputs feed a middle layer of neurons (the *hidden*
layer), and the hidden neurons' outputs feed an *output* layer. The hidden layer is where
combinations form: one hidden neuron might come to mean "I am hungry and food is close", another
"something big is on my right". The output neurons turn those combinations into actions. Because
information only moves forward, this is called a *feedforward* network, and a creature's decision is
one pass through it.

**3. The weights are the program.** The structure is fixed. All of the behaviour is in the weights,
and a different set of weights gives a different creature with the same body.

### A worked example

Three inputs, two hidden neurons and two outputs. Inputs: how close the nearest food is (0 to 1),
how full the creature's energy store is (0 to 1), and which side the food is on (-1 left, +1 right).
The creature currently senses `[0.9, 0.3, -0.5]`: food is close, energy is low, food is to the left.

- Hidden neuron 1 has weights `[+1.0, -1.5, 0]` and bias -0.2. It adds `1.0 × 0.9 + (-1.5) × 0.3 +
  0 × (-0.5) - 0.2 = 0.25` and squashes it to `tanh(0.25) = 0.245`. It reads as "food is near and
  I am hungry", because the negative weight on energy makes low energy raise it.
- Hidden neuron 2 has weights `[0, 0, +1.0]` and bias 0. It gives `tanh(-0.5) = -0.462`, which reads as
  "food is on the left".
- Output "speed" has weights `[+1.5, 0]`: `1.5 × 0.245 = 0.367`, squashed to the range 0 to 1 gives
  0.59, so about 59% of full speed.
- Output "turn" has weights `[0, +2.0]`: `2.0 × (-0.462) = -0.924`, which `tanh` turns into -0.73, so
  turn left, fairly hard.

Four numbers got a sensible reaction out of nine weights. A real creature has 198 weights and 17
inputs, but the arithmetic is exactly this repeated. In Python the whole pass is a few lines:

```python
import math


def forward(net, x):
    w1, b1, w2, b2 = net  # hidden weights and biases, output weights and biases
    hidden = [math.tanh(sum(w * xi for w, xi in zip(row, x)) + b) for row, b in zip(w1, b1)]
    return [math.tanh(sum(w * hi for w, hi in zip(row, hidden)) + b) for row, b in zip(w2, b2)]
```

### What a network cannot do on its own

It has no goals, no memory and no sense of the world beyond the numbers fed in. If something is not in
the inputs, the creature cannot react to it, and if two situations give the same inputs, the creature
treats them the same. So **choosing the inputs is the real design work** (see
[Inputs and outputs](#inputs-and-outputs)), and a creature has no idea what happened a moment ago unless
we add memory ([Options](#options)).

## How a creature's brain would be "trained": evolution, not teaching

The usual way to make a network good at a task is to show it thousands of examples and nudge the
weights after each mistake (*backpropagation*). That needs a list of right answers, and we do not have
one: nobody knows the right way for a simulated animal to behave. We have something better for this
project: **survival and reproduction are the test**.

- Each creature's weights come from its parents, mixed and slightly mutated, exactly like its body
  genes.
- A creature with weights that happen to steer toward food, avoid larger animals and find mates
  eats more, lives longer and has more children.
- Those children inherit its weights. Over many generations, populations drift to weight sets that
  work. This is called **neuroevolution** and is a mainstream, well-studied technique (Floreano and
  colleagues 2008 is a standard review).

Two consequences matter for the design. There is **no training step**: the simulation itself is the
training, and "a good brain" is whatever survives in this particular world. And behaviour is only as
smart as the **world allows**. A boring world with plentiful food and no predators will not produce
interesting brains, because there is nothing a brain can do better than another brain. Brain
research and the world model (`WORLD.1`, [#10](https://github.com/dwhagar/evolutionSimulator/issues/10)) are linked for that reason.

A second kind of change, *learning during life* (a creature adjusts its own weights from experience
and, usually, does not pass the changes on), is possible and is discussed under [Options](#options). It
is not needed to start.

## Options

The options form a ladder. Each step is more capable and more work than the one below.

| Level | What it is | Evolution can discover | Cost and risk |
| --- | --- | --- | --- |
| 0. Fixed rules (today) | A hand-written if-this-then-that decision with two genes (`aggression`, `fear`) tuning it | Only the values of two numbers | Cheapest; behaviour is exactly what we wrote; no steering, no surprises |
| 1. Weighted rules | Same rules but with more genes as weights ("how much does hunger outweigh fear?") | A better balance between rules we wrote | Cheap and easy to read; still cannot invent new behaviour |
| 2. Small feedforward network (**recommended**) | The network above, weights in DNA | Reactions we did not write: steering, using the sense inputs, avoiding bigger animals | Longer genomes, needs a good start (see [Getting evolution started](#getting-evolution-started)), harder to read than rules |
| 3. Network with memory | A feedforward network plus a few extra neurons that carry over from one tick to the next (a *recurrent* connection, as in an Elman network) | Remembering that food was over there a moment ago, finishing a chase, alarm that lasts | Roughly 25 to 50% more weights; behaviour depends on history, so tests and debugging get harder |
| 4. Evolving the network's shape (NEAT and similar) | Neurons and connections are added or removed by mutation, starting from the smallest network | New brain structure appearing over time | The most research-like; needs a way to line up two parents' different networks (Stanley and Miikkulainen 2002 solve this) and a new genome type that is not fixed length |
| 5. Learning during life | Weights also change with experience (reward signals or Hebbian rules, "neurons that fire together wire together") | Creatures that learn their local world quickly | Needs a reward definition; whether learning is inherited is a big design choice (see the Baldwin effect, Hinton and Nowlan 1987) |

Other ideas considered and not recommended:

- **Behaviour trees or decision trees** (a tree of questions) are readable and cheap but need hand
  design and are awkward to mutate and recombine; evolving them is a research area of its own.
- **Spiking networks** model the timing of electrical pulses. Far more realistic, far harder to run
  and tune, and no benefit at this scale.
- **Big neural networks and reinforcement learning** (the technology behind modern game-playing
  systems) need heavy machinery and a reward function; they replace evolution as the engine rather
  than add to it, and the project's point is evolution.

**Recommendation: level 2 for the first brain**, designed so that levels 3 and 5 can be added later
without throwing it away (extra inputs and extra neurons, not a new system).

## Recommended design

A fixed-shape feedforward network, one per animal. Plants do not get a brain: they cannot move, so
their behaviour stays the simple rule `PlantTraits` already has.

- **Shape.** 17 inputs, 8 hidden neurons, 6 outputs ([Inputs and outputs](#inputs-and-outputs)).
- **Number of adjustable values.** `17 × 8` hidden weights plus 8 hidden biases plus `8 × 6` output
  weights plus 6 output biases, which is 198 (*measured* by script; the same counting rule gives 294
  weights for 12 hidden neurons and 502 for 16 hidden and 24 inputs).
- **Activation.** `tanh` for hidden neurons. Outputs are `tanh` (range -1 to 1) for steering and
  `tanh` or a logistic curve rescaled to 0 to 1 for the rest.
- **Same shape for every animal.** A herbivore and a carnivore have the same network; they differ
  in weights (and in the body genes that decide what food is useful to them).
- **Evaluated once per tick, or every few ticks.** A decision interval of one to four ticks is a
  tunable setting. Between decisions the creature keeps its last outputs.
- **Hidden neuron count is a setting, not a gene** in the first version (see
  [Open questions](#open-questions) on whether it should be able to evolve).

## Inputs and outputs

The inputs and outputs are the contract between the brain, the senses and the actions. Two rules
keep it simple and let the same brain work in a grid or a continuous world (`WORLD.1` is still open):

1. **Everything is egocentric and scaled.** Directions are measured relative to which way the
   creature is facing (-1 hard left, +1 hard right), distances are scaled by the creature's own
   sense range so that 1 means "touching" and 0 means "not sensed", and states are fractions between
   0 and 1.
2. **A sense that cannot see a thing gives 0 for that thing.** Sight range, field of view, hearing
   and smell are already evolvable genes in `AnimalTraits`; they decide what the world is allowed to
   put into the brain's inputs. A creature with poor senses has a brain with many zeros, which is the
   point.

### Inputs (17)

| # | Input | Range | Source in the current code |
| --- | --- | --- | --- |
| 1 | Energy ratio | 0 to 1 | `current_energy / max_energy` |
| 2 | Health ratio | 0 to 1 | `current_health / max_damage_capacity` |
| 3 | Vitality | 0 to 1 | `vitality` (age and wear) |
| 4 | Ready to mate | 0 or 1 | `mating_cooldown == 0` |
| 5 | Nearest plant: direction | -1 to 1 | sight and smell, world supplies |
| 6 | Nearest plant: closeness | 0 to 1 | sight range gene scales it |
| 7 | Nearest possible prey: direction | -1 to 1 | |
| 8 | Nearest possible prey: closeness | 0 to 1 | |
| 9 | Nearest threat (larger animal): direction | -1 to 1 | `env_threat_detected`, `env_target_size_ratio` |
| 10 | Nearest threat: closeness | 0 to 1 | |
| 11 | Nearest possible mate: direction | -1 to 1 | |
| 12 | Nearest possible mate: closeness | 0 to 1 | |
| 13 | Touching something | 0 or 1 | `env_tactile_collision`, needs touch gene above 0.1 |
| 14 | Alarm call heard: strength | 0 to 1 | hearing range gene, signal 2 |
| 15 | Mating call heard: strength | 0 to 1 | hearing range gene, signal 0 |
| 16 | Direction of loudest call | -1 to 1 | |
| 17 | Crowding | 0 to 1 | `env_local_density` |

Notes. "Nearest possible mate" means the nearest animal the simulation would allow it to mate with;
who may mate is decided by the simulation ([DNA research](../research/dna-and-reproduction.md)).
Taste and toxicity are not inputs: `inspect_food` is an action with a chance of detection, not a
sense that is always on. Every input is already available to the simulation in some form; the world
loop only has to compute the nearest of each kind, which a world needs for movement anyway.

### Outputs (6)

| # | Output | Range | What the simulation does with it |
| --- | --- | --- | --- |
| 1 | Turn | -1 to 1 | Turns by up to `base_turn_rate` this tick |
| 2 | Speed | 0 to 1 | Becomes `movement_speed_ratio`, scales `current_max_speed` and the kinetic energy cost |
| 3 | Eat or attack | 0 to 1 | Above 0.5 and in reach: `feed` on a plant or an attack on prey |
| 4 | Seek or accept mating | 0 to 1 | Above 0.5 and ready: sets `flag_wants_mate` |
| 5 | Alarm call | 0 to 1 | Above 0.5: emit signal 2 (costs `call_energy_cost`) |
| 6 | Mating call | 0 to 1 | Above 0.5: emit signal 0 |

In the first version the brain would supply the outputs the existing rule currently supplies as
flags (`flag_wants_to_attack`, `flag_wants_mate`, `flag_ready_to_signal`, `signal_to_emit`) and the
two things the rule never decided, direction and speed. Hunger-based target choice (`flag_wants_food`,
`flag_target_is_plant`, `flag_target_is_prey`) is no longer needed because the brain steers toward
whichever food input it is paying attention to. The existing flags can stay as "what the brain
decided" so the rest of the simulation does not change.

## Storing the brain in the DNA

The weights have to live in the genome so they are inherited. The DNA object works in base-4 digits
and decodes runs of digits to a number between 0 and 1. Two ways to store a weight were considered.

| Way | How | For | Against |
| --- | --- | --- | --- |
| A. Weights as digit genes (**recommended**) | Each weight is 2 digits (16 levels), decoded to the range -2 to +2 | One genome, one `reproduce()`, one set of operators; fits the existing `Gene` design | Coarse (steps of about 0.27); first-digit-matters-most problem ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)) |
| B. A separate list of real numbers | Floats alongside the digit genome, mutated by adding a small random nudge (typical neuroevolution) | Fine steps, standard technique | Second genome type, second set of operators, breaks "DNA is digits" |

Coarse weights are not a problem: neuroevolution results with a few bits per weight are standard, and
the benefit of one inheritance path is large. With 2 digits per weight the brain is 198 weights ×
2 = **396 digits**, so an animal genome becomes about 461 digits (65 body digits plus 396).

Three things follow for the DNA design, and they are the main work for the foundation thread:

1. **A new gene-block descriptor.** `Gene()` is one value per line; 198 lines is not workable. A
   block descriptor that declares "N weights of width 2" and returns them as a list is needed, and the
   brain is built from it once at birth (the same pattern as the body traits).
2. **Mutation must be set per genome.** The default of 0.01 per digit would give about 4 changes per
   child in the brain alone and about 4.6 over the whole animal genome (461 × 0.01), where the DNA
   research recommends at most about 1 per organism. The settings should be expected changes per
   genome and per segment (body, brain), for example 1.0 in the brain, which is about 0.0025 per brain
   digit. This is the same recommendation as `DNA.8` (expected changes per genome) and `DNA.6`
   ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)).
3. **First digit dominates.** With two digits per weight the first digit is worth 12 of the 15 steps
   of the range, so one change there moves a weight by about 0.4 of its full range on average
   (*computed* from the existing encoding: mean change per mutation 0.42 of the range at the first
   digit and 0.1 at the second). Two ways to soften it: a Gray code (a numbering in which neighbouring values differ in one digit, which is
   the "Gray code" option already in [#15](https://github.com/dwhagar/evolutionSimulator/issues/15)) or the per-position mutation weight already proposed there. Either is
   cheap for a brain block because it is one place. The brain makes #15 matter more: a brain is hit
   by many more mutations than the body.

**Crossover for brains.** Crossing over inside a neuron's weights produces blends no parent had, and
a whole network from one parent plus a whole network from another usually works worse than either,
because neuron number 3 in one parent does not mean the same thing as neuron number 3 in the other
(*the competing conventions problem*). The safest default is **per-neuron blocks**: keep each hidden
neuron's incoming weights together, take whole neurons from either parent, and keep the output
weights attached to the neuron they read. This is the same recommendation as gene-level crossover
([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)); a brain simply makes the reason stronger. Fully avoiding the problem is what NEAT
(level 4 above) is for, and is not needed at this size.

## What thinking costs

Real brains are expensive: the human brain uses about a fifth of the body's resting energy while
being about 2% of its mass (*the expensive tissue hypothesis*, Aiello and Wheeler 1995, is the
standard reference). If the simulation lets creatures think for free, every population evolves the
largest, fastest brain available and nothing interesting stops it. The existing trait code already
charges for senses (`sensory_overhead`, 0.08 times the sum of squared sense genes) and for the gut,
so a brain cost fits the model.

Suggested cost, added to `basal_metabolism`:

```
brain_upkeep = k_neuron * (hidden neurons + outputs)
             + k_synapse * (number of weights with |w| above a small threshold)
```

where `k_*` are tunable constants placed in the same config object as the rest of the tuning numbers
(`TRAIT.3`). Counting only active connections means pruning useless weights saves energy, which gives
evolution a reason to switch off wasted wiring; counting every weight would charge for a fixed-shape
network whatever it does. If the brain has a fixed shape for every animal, the first term is a
constant for all creatures and only the second varies. Starting values are a calibration job for the
first runs; the aim is that a typical brain costs a few percent of the basal budget and a heavily
wired one costs noticeably more.

How often the brain runs can also be a cost: a creature that decides every tick pays more than one
that decides every fourth tick but reacts more slowly. That is a possible later gene (reaction time),
not needed first.

## Getting evolution started

A population of random brains behaves randomly: it walks in circles, ignores food and dies. If every
member dies before reproducing, evolution never starts. Three ways to avoid this:

1. **Seed with sensible brains** (**recommended**). Build starting weights that reproduce what the
   current fixed rule does (eat when hungry, flee larger animals, mate when fed), then let evolution
   improve on it. The rule produces thousands of labelled examples (inputs and the flags it would
   set), and a network can be fitted to them offline with a simple search, so no external machine
   learning library is needed. A natural test is that the seeded brain agrees with the rule on at
   least 95% of random situations. This also means the first brain-driven simulation behaves like
   today's, which is the right baseline to compare against.
2. **Generous start.** Plenty of food, no predators, safe early generations, so random brains
   survive long enough to reproduce. Works but is world-dependent and slow.
3. **Curriculum.** Start with a world that only needs one skill (find food), then add skills
   (avoid predators) as the population improves. A good later tool, a lot of extra machinery now.

Seeded brains should be varied slightly (small random changes to the seed weights) so the starting
population is not clones.

## How it connects to the DNA and traits objects

The current objects are `AnimalDNA` (65 digits, genes read by name) and `AnimalTraits` (reads genes
once at birth to set the body, then tracks energy, health and flags). The brain is a third piece:

- **`AnimalDNA` gains one brain segment**: a block of weight genes, after the existing body genes.
  Body genes and their positions do not change, so saved genomes and the existing tests are
  unaffected if the brain segment is added as a separate class or a separate segment. A decision for
  the foundation thread is whether this is one genome of 461 digits or two linked ones; one genome is
  recommended because `reproduce()` then needs no change.
- **`AnimalTraits` is unchanged in what it computes** and gains a `brain` made at birth from the
  weight block. Body genes still fix mass, speed, sense ranges and costs. The brain decides what to
  do with that body.
- **A new `Brain` object** holds the decoded weights and has one method, `decide(inputs) -> outputs`.
  It knows nothing about the world, the DNA layout or the traits; it is a pure function of its
  weights and its inputs, so it is simple to test.
- **The sense and drive code feeds the brain**. The world loop (`WORLD.2`) computes the 17 inputs
  from what each creature can sense, calls `brain.decide`, and passes the outputs to the existing
  actions (`movement_speed_ratio`, `feed`, `AnimalTraits.give_birth`, `trigger_signal_emission`). The
  fixed rule stays as the fallback and as the reference the seeded brain imitates.
- **The traits-and-DNA contract still holds.** DNA does not know what a weight means, traits do not
  read weights, and the brain only reads decoded numbers.

One point to watch: because the brain steers, the existing behaviour flags stop being a description
of the whole decision. `flag_wants_food` and the like should be set from the brain's outputs (or
removed) rather than computed independently, so there is one source of truth.

## As built

Built by the Foundations 2 thread (`BRAIN.2`, `DNA.11`, `DNA.12`) with the design above as the default for
every open question ([#23](https://github.com/dwhagar/evolutionSimulator/issues/23): neural network).
Anything the owner answers differently is a change to one constant or one table row.

| Piece | Where | What it does |
| --- | --- | --- |
| `Brain`, `BrainShape` | `brain.py` | The network. Pure: `decide(inputs) -> outputs` from weights alone, no DNA, traits or world. `DEFAULT_SHAPE` is 17 inputs, 8 hidden, 6 outputs, 198 numbers. Hidden neurons use `tanh`; output 0 (turn) is `tanh` and the other five are logistic (0 to 1), as in the worked example. |
| `Percepts`, `build_inputs`, `BrainDecision`, `decode_outputs` | `brain_adapter.py` | The world side. The world fills in a `Percepts` (13 of the 17 inputs: nearest plant, prey, threat and mate, touch, calls, crowding); the animal adds its own energy, health, vitality and readiness to mate; the six outputs come back named, with the action outputs counting as "do it" above 0.5. Inputs are clamped to their ranges and must be finite. When `WORLD.1` settles how the world measures things, only this module changes. |
| `BlockSpec` | `dna.py` | `DNA.11`. A gene that is an array of values: `count` values of `digits_per_value` digits decoded onto `low`..`high`, in `groups` that recombination keeps together. The brain is one block of 198 two-digit values over -2 to 2 (16 levels, steps of 0.267, no exact zero) in segment `brain`. `dna.values("brain")` reads it; `BlockSpec.encode` is the other way, for seeding. |
| Segments and `crossover_by_unit` | `dna.py` | `DNA.12`. Mutation can be set as expected changes per segment, and crossover can take whole neurons from either parent. See [dna-and-traits.md](dna-and-traits.md). |
| `Wanderer`, `WanderPolicy` | `brain_adapter.py` | `BRAIN.16`, the owner's answer to [#27](https://github.com/dwhagar/evolutionSimulator/issues/27): with no memory, a creature that cannot decide moves in a random direction so its senses start giving it information. A creature is undecided when the world reports nothing at all (`Percepts.senses_nothing`) or when its own outputs are all quiet (turn and speed under 0.1 and no action output above 0.5). Then its turn is replaced by a random one in -1 to 1 (kept for several ticks, with a 25% chance per tick of a new one, so the path bends instead of jittering) and its speed is raised to at least 0.4; the action outputs are left alone and the returned decision has `wandering` set. All numbers are on the policy, either reason can be switched off, and all randomness comes from the `random.Random` passed in. |
| `Temperament` | `brain_adapter.py` | `BRAIN.14`, the owner's "behaviour comes from genetic factors as well as the network" ([#23](https://github.com/dwhagar/evolutionSimulator/issues/23)). The `aggression` and `fear` genes bend what the brain perceives: aggression scales the prey-closeness input and fear the threat-closeness input, by a factor from 0.4 to 1.6 (0.5 is neutral, `TEMPERAMENT_STRENGTH` sets the spread). `think` passes the animal's *current* aggression (after hunger, crowding, size and sex adjustment) and its effective fear (stronger when worn down), the same numbers the fixed rule uses. A thing that is not sensed stays unsensed. **Why modifiers and not extra inputs:** two more inputs would change the brain's shape and so the genome layout, which `BRAIN.13` (an evolving shape) and `SENSE.1` (new senses) are about to rework; a modifier lives in the adapter, needs no layout change and gives a guaranteed genetic effect, where a brain input only matters once evolution has wired it up. The reproduction genes from `REPRO.5` become more fields on `Temperament`. |
| Decision interval | `traits.py` | `BRAIN.11`. `AnimalTraits(dna, decision_interval=n)` (default `DECISION_INTERVAL = 1`) runs the brain every n-th call to `think` and returns the last decision, wander turn included, on the calls in between, so the world loop calls `think` once per tick and does not need to know. Thinking costs are charged per tick divided by n, so a slower thinker is cheaper and reacts later (the trade-off in [What thinking costs](#what-thinking-costs)). The interval is a constructor argument for now; it moves to the `TRAIT.3` config and could later become a gene (reaction time). |
| Sense-channel table | `sense_channels.py` | `SENSE.8`. One table, `INPUT_CHANNELS`, with a row per brain input: name, range, whether the body or the world supplies it, its role (level, flag, bearing, closeness), which senses can report it, which target it concerns, and whether temperament scales it. `INPUT_NAMES`, the `Percepts` fields and `build_inputs` in `brain_adapter.py` are all generated from it, so adding a sense input is one row (plus the brain shape and layout, which is `SENSE.9`). `build_inputs` now takes the body values by keyword and checks that all of them are given. The table is checked when the module loads (unique names, a closeness always has its bearing, a target only on bearing and closeness rows). |
| Sensing step | `sensing.py` | `SENSE.10`. `sense(position, heading, radius, organs, neighbours, conditions, rules, rng, edge_distance) -> Percepts`, a pure function that follows the rules in [senses.md](senses.md) (the worked example is a test). The caller gives already-classified `Neighbour`s (plant, prey, threat, mate or other, with a radius, loudness, scent and call radii); `SenseOrgans` holds the effective range, field of view and direction noise of each organ, which `SENSE.11` fills from the genes; `SensingConditions` holds daylight and sleep; `SensingRules` holds every constant (light floor 0.25, sleep factors 0, 0.5, 0.5, 1, weak smell, crowding reference 8, closeness noise 0.03) for the `TRAIT.3` config. Distances are between surfaces, each class reports its nearest detected member scaled by the best range that can report that class, and the bearing comes from the most precise organ that found it. With no `rng` every report is exact, and the draws are in a fixed order, so a seed repeats. It is 2D only for now; positions are vectors and the creature's frame is built from vectors, so 3D adds components. The world's neighbour search and classifier (`SENSE.12`) is what will call it, replacing `BasicSenses`. |
| Sense genes | `sense_genes.py`, `trait_defs.py`, `traits.py` | `SENSE.11`, with the owner's defaults for [#40](https://github.com/dwhagar/evolutionSimulator/issues/40) and [#42](https://github.com/dwhagar/evolutionSimulator/issues/42). Sight reach, hearing range and smell range now start at 0 (10, 15 and 20 before), so a sense can be lost; touch is always on. The direction error of each organ falls linearly with its gene (vision 0.02 to 0.01, hearing 0.30 to 0.15, smell 0.50 to 0.25) and sits on the animal as `vision_noise`, `hearing_noise` and `smell_noise`. The sense cost is `COST_PER_AREA` times the area covered (the cone of vision, the circles of hearing and smell) plus the old 0.08 times the gene squared for touch and taste. `organs_from_traits(traits)` in `sensing.py` turns an animal into the `SenseOrgans` the sensing step reads. No gene was added, so the genome layout is unchanged. All the numbers are module constants for the `TRAIT.3` config. The cost constants are placeholders: a random animal's sense bill is about 19% of basal metabolism (22% before), a smell specialist's 28%, a hearing one's 22%, a wide-eyed one's 17% and a narrow-eyed one's 7%. |
| Dead zone | `brain.py`, `traits.py` | `BRAIN.21`. `Brain.from_values(shape, values, dead_zone=0.0)`: a weight (never a bias) whose absolute value is at or below the dead zone is off. It does nothing in `decide` and `active_connections()` does not count it, so a connection pays energy exactly when it acts; before, `decide` used every weight while the cost counted only those above 0.25, so small weights acted for free. `to_values` still returns the numbers as given, and equality includes the dead zone. `AnimalTraits` builds its brain with `BRAIN_ACTIVE_THRESHOLD` (0.25) as the dead zone, which switches off the weights at about +-0.133 (one level in eight; the next level, 0.4, stays on). `BRAIN.23` replaces this with its own dead zone of about 0.5. |
| `AnimalTraits.brain`, `.brain_upkeep`, `.think(percepts)` | `traits.py` | The hookup. The brain is built from the genome at birth; `think` adds the animal's own state to the percepts, runs the brain and returns the decision; pass an `rng` to enable the wander fallback. |

**Genome.** `ANIMAL_LAYOUT` is now 466 digits at layout version 3: the 70 body digits (the prototype's 65, with
the three reproduction genes of `REPRO.5` in place of `fertility`), then the 396 brain digits. The body genes are read by the trait table as before; the brain is read only by
`Brain`, so `TraitSet.unread_genes()` does not list it.

**Brain layout.** The 198 numbers are grouped per hidden neuron so a neuron's wiring travels together: for
each of the 8 hidden neurons its bias, its 17 incoming weights and its 6 outgoing weights (24 numbers), then
the 6 output biases. Crossover by unit takes whole neurons, with their outgoing weights, from either parent,
which is the "per-neuron block" recommendation under [Storing the brain in the DNA](#storing-the-brain-in-the-dna).

**Mutation.** `ANIMAL_LAYOUT` sets about 0.70 expected changes per child for the body (the prototype's 0.01 per
digit, unchanged) and 1.0 for the brain (about 0.0025 per brain digit), so the brain's 396 digits do not take
over the mutation count (0.01 per digit would have given about 4 changes in the brain alone). Both numbers
are data on the layout and can be overridden per call. The first-digit-dominates problem
([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)) is not addressed: it needs the owner's call
on Gray code or per-position weights, and neither is built.

**Cost of thinking.** `traits.py` has three placeholder constants: 0.0005 per hidden or output neuron, 0.0001
per active connection (a weight above 0.25 in absolute value; biases are not counted), and the 0.25 threshold.
`brain_upkeep` is added to `basal_metabolism`. A random brain costs about 4% of an animal's basal budget (2.7%
to 7% over 300 random animals, *measured*), and a fully wired one (every weight at +2) about 4.3% on average
(2.9% to 7.6%). Because random weights are mostly above the threshold, the connection term only varies between
0 and 0.018 per tick, so pruning is a weak lever until the constants are calibrated against a world. They move
into the `TRAIT.3` config object.

**Tests.** `tests/test_brain.py` (the worked example, a reference forward pass written against the documented
layout, output ranges, repeatability, zero brain, cost counting, adapter), `tests/test_dna_blocks.py` (blocks,
segments, per-segment mutation counts, per-neuron crossover) and `tests/test_animal_brain.py` (the hookup, the
cost, pinned decisions for a fixed genome). All randomness is seeded.

**Not built yet.**

- Using the decision. `think` only returns it. Setting `flag_wants_to_attack`, `flag_wants_mate`,
  `flag_ready_to_signal`, `signal_to_emit`, movement and feeding from the outputs, and retiring the fixed rule
  as a second source of truth, belongs with the world loop (`WORLD.2`). The fixed rule still runs on every tick.
- Seeding the first generation (`BRAIN.9`, [#27](https://github.com/dwhagar/evolutionSimulator/issues/27)).
  `DNA.random` gives random brains, which behave randomly, as warned under
  [Getting evolution started](#getting-evolution-started).
- Crossover is settled (`DNA.7`, [#14](https://github.com/dwhagar/evolutionSimulator/issues/14)): `reproduce` defaults
  to `crossover_linked`, which cuts between whole neurons unless `gene_fidelity` is lowered. Set it to 1.0
  for animals that must never blend inside a neuron.
- Memory ([#24](https://github.com/dwhagar/evolutionSimulator/issues/24)), learning
  ([#26](https://github.com/dwhagar/evolutionSimulator/issues/26)) and an evolvable size
  ([#28](https://github.com/dwhagar/evolutionSimulator/issues/28)).

## Speed

A plain Python forward pass of the recommended 17-8-6 network took about 16 to 21 microseconds,
*measured* over 20,000 calls on this machine with only the standard library (no numpy). A larger
17-12-6 network took about 22 microseconds and a 24-16-6 network about 35. At 20 microseconds a
population of 1,000 animals costs 20 milliseconds per tick for brains alone, which is acceptable for
the first version; running the brain every second or third tick divides that by two or three. If
populations grow into the tens of thousands, numpy could be added later as an optional dependency;
the current project has no dependencies, so that is a decision for then, not now.

## Risks and how to see them early

| Risk | Why | What to do |
| --- | --- | --- |
| Genome bloat | 396 of 461 digits become brain digits, so most mutation lands in the brain | Mutation per segment and per genome, not per digit (above) |
| Jumpy evolution | First digit of every weight dominates | Gray code or per-position mutation weight; see [#15](https://github.com/dwhagar/evolutionSimulator/issues/15) |
| Dead start | Random brains never reproduce | Seed from the current rule |
| Hard to understand | Weights are numbers, not rules | Log what each creature does (outputs per tick) and plot a handful of behaviours: fraction of time moving toward food, distance kept from threats |
| Brain size runaway | Free thinking | Energy cost per neuron and active connection |
| Spurious cleverness | The world offers nothing for a brain to be good at | Link brain testing to the world model (`WORLD.1`); a world with only static food and no predators will not show a brain advantage |
| Hidden bugs | A forward pass is easy to get subtly wrong | A reference test: weights chosen so the output is known (the worked example above is a ready-made test) |
| Hand-written rules disagree with the brain | Two sources of behaviour | The brain's outputs are the only decision; the rule remains only as a seed generator and fallback |

Early tests worth building: the worked example above returns the stated numbers; outputs always lie in
their ranges for any inputs in range; a seeded brain agrees with the rule on 95% or more of random
inputs; the same seed gives the same decisions; an all-zero brain gives a defined, harmless
behaviour (stand still); a brain's energy cost rises with its number of active connections.

## Open questions

Tracked as GitHub issues so the owner can answer there. Each has a recommended default that the first
brain will assume until answered.

| Question | Issue | Default |
| --- | --- | --- |
| Replace the fixed rule with a neural network, or keep the rule and make its weights genes? | [#23](https://github.com/dwhagar/evolutionSimulator/issues/23) | Neural network (level 2) |
| Should creatures have memory from one tick to the next? | [#24](https://github.com/dwhagar/evolutionSimulator/issues/24) | No, add later |
| Should thinking cost energy? | [#25](https://github.com/dwhagar/evolutionSimulator/issues/25) | Yes, per neuron and active connection |
| Do creatures learn during life, or does only evolution change brains? | [#26](https://github.com/dwhagar/evolutionSimulator/issues/26) | Evolution only |
| Start with brains that imitate today's rules, or random brains? | [#27](https://github.com/dwhagar/evolutionSimulator/issues/27) | Imitate the rules |
| Is the brain's size fixed, or can it evolve? | [#28](https://github.com/dwhagar/evolutionSimulator/issues/28) | Fixed |

Related questions already open: the world model ([#10](https://github.com/dwhagar/evolutionSimulator/issues/10)) decides what the inputs can be in practice;
crossover ([#14](https://github.com/dwhagar/evolutionSimulator/issues/14)) and mutation size ([#15](https://github.com/dwhagar/evolutionSimulator/issues/15)) apply to brain weights too and matter more there; and whether
animals have sexes ([#4](https://github.com/dwhagar/evolutionSimulator/issues/4)) changes input 11.

## Sources

Standard references, cited from memory for orientation. Check any figure before relying on it.

- Floreano, Dürr and Mattiussi 2008, "Neuroevolution: from architectures to learning",
  *Evolutionary Intelligence*: overview of evolving network weights, shape and learning rules.
- Stanley and Miikkulainen 2002, "Evolving neural networks through augmenting topologies",
  *Evolutionary Computation*: NEAT, and the competing-conventions problem for crossover.
- Braitenberg 1984, *Vehicles: Experiments in Synthetic Psychology*: how very small direct
  sensor-to-motor wiring already produces lifelike steering; a good way to see why a few weights go far.
- Sims 1994, "Evolving 3D morphology and behavior by competition", *Artificial Life*, and Yaeger 1994,
  PolyWorld: classic evolved-creature simulations with evolved neural controllers.
- Hinton and Nowlan 1987, "How learning can guide evolution", *Complex Systems*: the Baldwin effect,
  for learning during life.
- Aiello and Wheeler 1995, "The expensive-tissue hypothesis", *Current Anthropology*: why brains cost
  energy.
- Salimans et al. 2017, "Evolution strategies as a scalable alternative to reinforcement learning":
  evidence that simple weight-perturbation search is competitive on small problems.
- This repository: [DNA and reproduction](../research/dna-and-reproduction.md),
  [DNA and traits objects](dna-and-traits.md) and `src/evolution_simulator/traits.py`.

## Glossary

- **Neuron:** a unit that adds up weighted inputs plus a bias and squashes the result.
- **Weight:** a number saying how strongly one input affects a neuron; the thing that evolves.
- **Bias:** a constant added before squashing; sets how easily a neuron fires.
- **Hidden layer:** the middle layer, between inputs and outputs, where combinations form.
- **Feedforward:** information flows one way, input to output, with no loops.
- **Recurrent:** some outputs loop back as inputs next tick, which gives memory.
- **Activation function:** the squashing curve (`tanh` here).
- **Neuroevolution:** evolving a network's weights (and sometimes shape) by selection instead of by
  training on examples.
- **Egocentric:** measured from the creature's own position and heading.
- **Fitness:** how well a creature does in the sense that matters here: it survives and breeds.
