# Learning during life: sleep, memory and nightly updates

Design note for `BRAIN.15`. Written 2026-10-14 by the Research 1 thread. It builds on
[brain.md](brain.md) and [brain-shape.md](brain-shape.md), and on the owner's answers in
[#23](https://github.com/dwhagar/evolutionSimulator/issues/23), [#24](https://github.com/dwhagar/evolutionSimulator/issues/24) and
[#26](https://github.com/dwhagar/evolutionSimulator/issues/26): the brain changes during life, creatures sleep at night to regain energy and
their weights update, that update is also their memory, and there are no recurrent memory neurons at the
start.

**Who this is for.** The owner, who is new to neural networks, and the thread that builds this. The early
sections explain the ideas in plain terms; the later ones give the design and the figures.

**Status.** Draft design, nothing built. Figures marked *measured* come from a small test written for this
note that uses the real `Brain` class on a toy problem (described under [A test of the rule](#a-test-of-the-rule)).
It shows that the rule works and what its settings do, not how it will behave in the finished world.

## Contents

1. [Summary](#summary)
2. [Learning versus evolution](#learning-versus-evolution)
3. [What learning needs](#what-learning-needs)
4. [Learning rules, in plain terms](#learning-rules-in-plain-terms)
5. [Recommended design](#recommended-design)
6. [What counts as reward](#what-counts-as-reward)
7. [Curiosity](#curiosity)
8. [How big a night's change can be](#how-big-a-nights-change-can-be)
9. [Memory: what nightly learning can and cannot remember](#memory-what-nightly-learning-can-and-cannot-remember)
10. [Sleep](#sleep)
11. [Are learned changes inherited?](#are-learned-changes-inherited)
12. [A test of the rule](#a-test-of-the-rule)
13. [What changes in the code](#what-changes-in-the-code)
14. [Risks and tests](#risks-and-tests)
15. [Open questions](#open-questions)
16. [Sources](#sources)

## Summary

- **The idea.** During the day a creature acts, and the brain keeps a short log of what it sensed, what it
  did and what happened next. At night the creature sleeps (regaining energy, `WORLD.5`), and the brain
  nudges a few of its numbers toward the choices that turned out well and away from the ones that turned out
  badly. Those nudges *are* its long-term memory.
- **Recommendation: reward-weighted nightly updates.** Each decision is logged with a **reward** (a score for
  how the next few moments went: energy gained, health lost, a mating achieved). At night, each output
  connection moves a little in the direction that would have made rewarded choices more likely. Only the
  **output layer** learns (6 outputs, 8 hidden neurons: at most 54 numbers); the inherited hidden neurons stay
  as they are. It is a standard method (reward-modulated learning, see [Sources](#sources)), simple enough to write in
  a few lines of Python, and it needs no extra genes except a learning rate.
- **It needs curiosity.** Learning from reward requires trying things, so choices must contain some
  randomness. *Measured*: with no randomness a creature learns nothing at all, and too much randomness
  slows learning down. So **curiosity is a gene** ([brain-shape.md](brain-shape.md)).
- **It works, but not instantly.** In the test, creatures that must learn which of two foods is safe go from 50% right (chance) to about 60% after
  one night, 71% after three, and 79% after seven (*measured*, 40 encounters a day). The settings that gave this are a
  learning rate of 1 and a cap on how far any number may move in one night.
- **Learned changes are not inherited** (default; [#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 5). A child starts
  from the weights in its parents' DNA. What *is* inherited is the ability to learn, the learning rate and
  curiosity, and those evolve.
- **Limits worth knowing.** Nightly learning remembers habits ("this food is bad", "flee that shape"), not
  places or events ("food is over there"). Remembering places needs recurrent memory neurons, which the owner
  has put off.

## Learning versus evolution

Two different processes change brains.

| | Evolution | Learning |
| --- | --- | --- |
| What changes | The DNA, between generations | The creature's own numbers, during its life |
| What drives it | Who survives and has children | Reward the creature itself experiences |
| Time scale | Many generations | Days |
| Passed to children | Yes, that is the point | No (default) |

They work together. Evolution can produce brains that are good at learning, and learning lets a
creature adapt to the world it was born into (for example which plants near its birthplace are poisonous),
which evolution alone could only track very slowly. Biologists call the way learning ability can steer
evolution the *Baldwin effect* (see [Sources](#sources)).

## What learning needs

Any learning scheme needs four things.

1. **A signal of good and bad.** The creature has to be told, in its own terms, whether something went well.
   Here that is the reward ([What counts as reward](#what-counts-as-reward)).
2. **A record of what it did and what it saw.** To credit a choice, the brain has to remember it at least
   until the outcome is known. This is a short log kept during the day.
3. **A rule for changing weights.** It decides which numbers move, which way and how far.
4. **Limits.** Without limits a few bad experiences can wreck a good inherited brain.

The owner's decision gives the schedule: record by day, update at night.

## Learning rules, in plain terms

| Rule | In plain words | Needs | Verdict |
| --- | --- | --- | --- |
| Hebbian ("neurons that fire together wire together") | A connection grows when the neuron before it and the neuron after it are active at the same time | Nothing external | Cannot tell good from bad, so it strengthens whatever the creature happens to do. Useful for noticing patterns, not for improving behaviour. |
| Reward-modulated Hebbian | The same, but the change is multiplied by how well things turned out (reward minus what is normal) | A reward, plus randomness in choices | **Recommended.** Strengthens what led to reward, weakens what led to punishment. |
| Trial and error on the weights ("weight perturbation") | Try small random changes to the weights for a while, keep them if the creature did better | A reward, a long trial period per change | Works but slow; each change needs many encounters to judge. |
| Value learning (Q-learning and relatives) | The creature learns how good each situation and action is, and picks the best | A reward, a table or a second network | Powerful but needs a second learned thing and a definition of "situation"; a step beyond the first version. |
| Copying a teacher (supervised learning, backpropagation) | Adjust the weights to match known right answers | Right answers | There are none: nobody knows the right behaviour. |

**Recommendation: reward-modulated learning** on the output layer, applied at night. In terms the project
already uses: the day is the experience, the reward is the teacher's mark, and the night is when the marks
are turned into changed weights.

## Recommended design

### Day: log the decisions

Each time the brain decides, it adds one **snapshot** to a log of fixed size (for example the last 64
decisions; the oldest are dropped when it is full):

- the **hidden activations** (8 numbers, or however many neurons exist),
- the **outputs the brain proposed** (6 numbers),
- the **actions actually taken**, which are the outputs plus curiosity noise (6 numbers),
- the **reward**, filled in once the outcome of that decision is known (see below).

This is a few hundred numbers per creature, so memory is not a concern. The brain needs one small addition:
a way to return the hidden activations as well as the outputs.

### Night: turn the log into small changes

For each connection from hidden neuron `j` to output `k`, and for each output bias:

```
change = learning_rate × (reward − usual_reward) × (action_k − proposal_k) × hidden_j
```

summed over the day's snapshots. In words: if the creature did *more* than the brain proposed (positive
noise) and that was followed by better-than-usual reward, strengthen the connection; if the extra was
followed by worse-than-usual reward, weaken it, and the reverse for doing *less* than proposed. The "usual
reward" is the day's average, so a creature in a rich world is not rewarded merely for being there. After
all snapshots, each change is **capped** so no number moves more than a limit in one night.

In Python, the rule (this version was run to check that it respects the cap):

```python
import statistics

def nightly_update(out_weights, out_biases, snapshots, eta, cap):
    """New output weights and biases after one night of reward-weighted learning.

    snapshots: list of (hidden, outputs, actions, reward) from the day.
    """
    baseline = statistics.fmean(s[3] for s in snapshots)
    dw = [[0.0] * len(row) for row in out_weights]
    db = [0.0] * len(out_biases)
    for hidden, outputs, actions, reward in snapshots:
        for k, (o, a) in enumerate(zip(outputs, actions)):
            g = eta * (reward - baseline) * (a - o)
            db[k] += g
            for j, h in enumerate(hidden):
                dw[k][j] += g * h
    clip = lambda d: max(-cap, min(cap, d))
    new_w = [[w + clip(d) for w, d in zip(row, drow)] for row, drow in zip(out_weights, dw)]
    new_b = [b + clip(d) for b, d in zip(out_biases, db)]
    return new_w, new_b
```

### What learns, and what does not

- **Only the output layer learns** at first: the weights from hidden neurons to outputs and the output
  biases (54 numbers for 8 hidden neurons). The hidden layer, which reads the senses, stays as inherited.
  This mirrors the usual picture of real brains, with fixed ways of seeing the world and flexible ways of
  responding, and keeps changes small and easy to test. Letting hidden neurons learn too is a possible later
  step.
- **Dormant neurons do not learn** (neurons switched off by the shape genes, [brain-shape.md](brain-shape.md)). Neurons that
  exist learn; the dead zone applies to learned values too, so a connection can be learned away.
- **The inherited weights are never overwritten.** Learned values are stored as **offsets** on top of the
  inherited weights, kept on the creature and never written to its DNA (see [inheritance](#are-learned-changes-inherited)).
  The brain used during the day is inherited weights plus offsets.

## What counts as reward

The reward should come from the creature's own state, what it would feel, not from a score the simulator
keeps for fitness. The traits code already tracks the right quantities.

| Component | Measured how | Why |
| --- | --- | --- |
| Energy gained | Rise in `current_energy / max_energy` over the next few ticks | Food found and eaten is the basic good |
| Health lost | Fall in `current_health / max_damage_capacity` | Being attacked, poisoned or injured is the basic bad |
| Mating achieved | A mating (`AnimalTraits.give_birth` returned true) | The reward that evolution itself selects for |
| Safety | Threat closeness input falling after a threat was sensed | Learning to get away |
| Nothing happened | Zero | Doing nothing earns nothing |

Reward for a decision is a weighted sum of those over a short window after it (for example the next 10
ticks), with the weights in the `TRAIT.3` config. A starting guess: energy gain counts 1, health lost counts 2,
mating counts 1, safety counts 0.5. Two practical rules:

- **Reward the outcome, not the action.** Do not give reward "for eating"; give it for the energy that
  eating produces. Poisonous food then punishes itself with the health loss.
- **Subtract the usual level** (the day's average reward) so a creature is not rewarded for being in a
  generous world.

## Curiosity

A creature that always does what its brain says never finds out whether anything else would be better, and
the rule above has nothing to learn from. The fix is a little **randomness in the actions**: the action
taken is the brain's proposal plus a small random nudge whose size is the creature's **curiosity**. Curiosity
costs something real, because exploring wastes effort, so evolution has to balance it.

*Measured* in the test (learning rate 0.15, cap 0.5):

| Curiosity (size of random nudge) | Correct on day 2 | Day 5 | Day 8 |
| --- | --- | --- | --- |
| 0 | 50% | 50% | 50% |
| 0.05 | 52% | 55% | 56% |
| 0.2 | 54% | 63% | 68% |
| 0.4 | 55% | 67% | 73% |

With no curiosity there is no learning at all. Some is essential, more helps up to a point (at a learning rate of 2.5
and a cap of 1.0, curiosity 0.3 gave 79% on day 8 and 0.5 gave 73%). This also covers `BRAIN.16`, the random wander when a creature cannot
decide: the same noise provides it.

## How big a night's change can be

There are two settings: the **learning rate** (how strongly one night responds to what happened) and the
**cap** (the most any one number may move in a night). The cap protects a creature from one freak day.
In the test, *measured* (share of right decisions after 1, 3 and 7 nights; chance is 50%):

Cap, with learning rate 1.0 and curiosity 0.3:

| Cap per night | After 1 night | After 3 nights | After 7 nights |
| --- | --- | --- | --- |
| 0.15 | 53% | 59% | 66% |
| 0.3 | 55% | 64% | 74% |
| 0.5 | 58% | 68% | 78% |
| 1.0 | 60% | 71% | 79% |

Learning rate, with cap 0.5 and curiosity 0.2:

| Learning rate | After 1 night | After 3 nights | After 7 nights |
| --- | --- | --- | --- |
| 0.05 | 52% | 55% | 60% |
| 0.15 | 54% | 61% | 68% |
| 0.4 | 57% | 66% | 74% |

The weights can range over -2 to 2 (a span of 4), so a cap of 0.5 allows an eighth of the full range in one
night, and one of 1.0 a quarter of it. A middle choice, **a cap of 0.5 per night and a learning rate of 1.0
as the starting point**, learns visibly within a few days without letting a single night rewrite a brain.
Returns diminish above the cap of 0.5. The learning rate is a gene, so creatures that benefit from fast
learning can evolve it, and the cap stays a world setting that limits how far any creature can move.

**Fading.** An optional pull back toward the inherited weights each night (for example 10 to 20% of the
distance) models forgetting. In the test it slowed learning (reaching 62% instead of 68% on day 8 at a
20% pull) because the toy world never changes. In a world that changes, forgetting is useful; it is a
setting, off by default.

## Memory: what nightly learning can and cannot remember

The owner's decision is that nightly changes *are* the creature's memory. They are a good memory for:

- **Habits and preferences:** which food is safe, which shapes mean danger, how cautious to be.
- **Skills**: better steering toward food, learned thresholds for fleeing.

They cannot remember:

- **Places or events:** where food was, that a predator was just there. The brain changes only at
  night, so nothing it learns today affects today.
- **Anything within a day.**

Remembering places or events within a day needs *recurrent* neurons whose values carry over between
decisions (`BRAIN.4` put these off). The log kept during the day is not memory in this sense: the brain
does not read it while deciding, only at night. If recurrent memory is added later the two fit together, with
short-term memory in the recurrent neurons and long-term memory in nightly changes.

## Sleep

Sleep is the owner's mechanism for regaining energy and applying learning. `WORLD.5` (day-night cycle) owns
the details; what learning needs from it is small.

- **A recurring night** of some number of ticks, during which a creature that can sleep goes to sleep.
- **Energy regained** while asleep, at a rate that exceeds its resting use.
- **One learning update** at the start or end of sleep, using the day's log. It is cheap: the log has at
  most 64 snapshots, so the update is a few thousand multiplications per creature per night, which is
  negligible beside a day of decisions.
- **The log empties** after the update, so each night learns from one day.

Open choices (see [Open questions](#open-questions)): whether sleeping creatures are vulnerable (cannot sense or flee, and
so can be eaten), whether they must be somewhere safe, and whether a creature can skip sleep when
starving. Vulnerability makes sleep a real trade-off: night is when energy is restored and learning
happens, and also the most dangerous time. It would also give evolution a reason to vary how much creatures
sleep.

## Are learned changes inherited?

**Default: no.** A child's brain is built from the genome at birth, the same way as today, and the
parent's nightly offsets die with it ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 5).

- **Why not.** Passing learned changes to children (called Lamarckian inheritance) does not happen in real
  life, and it would need a path from brain back into DNA, which is the opposite of how the DNA objects work
  (DNA is immutable and only inherited, never edited by a creature).
- **What is inherited instead.** The *ability* to learn: the learning rate, curiosity and the hidden
  neurons that decide what a creature can notice. These evolve like any gene. Creatures born into a world
  with a stable answer will, over generations, evolve the answer into their weights, and learning then matters
  less; creatures in a changing world keep learning.
- **How it is built.** `AnimalTraits` keeps the offsets next to the brain. The genome is never changed. A
  later option that does not break this: let a fraction of a parent's offsets become a *bias* in the child's
  starting weights. That is a decision to revisit if the owner wants it, not a start.

## A test of the rule

To check that the rule learns, and to measure what its settings do, a small test used the real `Brain` class.

**The task.** Two kinds of food, A and B. In each life one kind is nourishing and the other is toxic, picked at
random, so the answer cannot be inherited and has to be learned. Each day the creature meets 40 pieces of
food, one at a time, and decides whether to eat. Eating the good kind gives reward +1, eating the bad kind -1,
not eating 0. The creature starts with random weights (no head start in either direction), explores with the
given curiosity, and learns each night with the rule above. The score is the share of decisions that were
right (eating good food or refusing bad food), averaged over 1,500 lives. Chance is 50%.

**Results** (also in the tables above): no learning stays at 50%. With learning rate 1.0, cap 1.0 and curiosity 0.3, the score
is 60% on day 2, 67% on day 3, 71% on day 4, 74% on day 5, 78% on day 7 and 79% on day 8.

**What it shows and does not show.** It shows that the nightly rule learns from reward alone, that
curiosity is required, and that the cap trades speed for safety. It is a toy with two inputs and one output;
the real brain has 17 inputs and 6 outputs, a world with many things happening at once, and rewards that
arrive late and mixed together, so real learning will be slower and noisier. The settings should be
re-tuned in the real world (`WORLD.2`), not copied from this table.

## What changes in the code

A checklist for the build thread, after the shape work in [brain-shape.md](brain-shape.md):

1. **`Brain`**: a method that returns the hidden activations along with the outputs (a second method, so
   the existing `decide` is unchanged), and an optional offsets argument or a way to build a brain
   from inherited weights plus offsets.
2. **A day log object** (fixed size, oldest dropped) in the animal's traits, filled during `think()`
   with hidden activations, proposal, action and the reward once it is known.
3. **Reward**: a function from the state changes in the table above, with weights in the `TRAIT.3` config.
4. **Curiosity noise** added to the outputs before they are acted on, from an injected `random.Random` (so
   runs repeat).
5. **`nightly_update`** as above, as a pure function, plus the cap, the optional fade and the dead zone.
6. **Sleep hook** for `WORLD.5`: a call that runs the update once and clears the log.
7. **Genes**: learning rate and curiosity, as in [brain-shape.md](brain-shape.md).

## Risks and tests

| Risk | Why | Mitigation |
| --- | --- | --- |
| A creature learns the wrong thing | Reward is noisy; a bad day looks like evidence | Cap per night; subtract the usual reward; fade toward inherited weights |
| Learning wrecks a good inherited brain | Large updates | Learning on the output layer only, with a cap; offsets kept separate from DNA |
| No learning happens | No curiosity | Curiosity gene; a minimum above zero in the seeded start |
| Learning dominates evolution | Everything is learned, nothing is inherited | Learning rate has a cost through curiosity; a world with stable answers selects for inheriting them |
| Cheating the reward | Reward defined badly (for example for actions rather than outcomes) | Reward only for outcomes; review the weights with the first runs |
| Runs do not repeat | Randomness | Inject the random number generator everywhere |
| Cost | Nightly updates for every creature | Measured negligible: a few thousand operations per creature per night |

Tests worth writing: with zero curiosity the weights are unchanged; with zero learning rate the weights are
unchanged; the cap is respected for every number; the update direction is right on a hand-made log (one
rewarded snapshot with positive noise strengthens the connection, one punished snapshot weakens it); offsets
never appear in the DNA and a child is built from DNA only; same seed gives the same night; the dead zone
applies to learned values; the toy task reaches at least 70% by day 5 with the default settings.

## Open questions

Decisions the owner should make, raised as issues. Each has a default the build will use until answered.

| Question | Issue | Default |
| --- | --- | --- |
| What counts as reward (energy, health, mating, safety) and how much each matters? | [#55](https://github.com/dwhagar/evolutionSimulator/issues/55) (`BRAIN.19`) | Energy gained 1, health lost 2, mating 1, safety 0.5 |
| How much may one night change a creature? | [#56](https://github.com/dwhagar/evolutionSimulator/issues/56) (`BRAIN.20`) | Medium: no number moves more than 0.5 in one night (an eighth of its range) |
| Are sleeping creatures vulnerable (cannot sense or flee)? | [#57](https://github.com/dwhagar/evolutionSimulator/issues/57) (`WORLD.6`) | Yes, which makes night a trade-off (belongs to `WORLD.5`) |

Already asked: whether learned changes are inherited ([#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 5,
default no).

## Sources

Standard references, cited from memory. Check any detail before relying on it.

- Hebb 1949, *The Organization of Behavior*: the origin of "fire together, wire together".
- Williams 1992, "Simple statistical gradient-following algorithms for connectionist reinforcement
  learning", *Machine Learning*: REINFORCE, the reward times exploration noise rule behind this note's design.
- Florian 2007, "Reinforcement learning through modulation of spike-timing-dependent synaptic plasticity",
  *Neural Computation*: reward-modulated learning, the same idea in spiking networks.
- Sutton and Barto, *Reinforcement Learning: An Introduction*: the standard text on value learning and the
  other methods in the table.
- Hinton and Nowlan 1987, "How learning can guide evolution", *Complex Systems*: the Baldwin effect.
- Diekelmann and Born 2010, "The memory function of sleep", *Nature Reviews Neuroscience*: sleep and memory
  consolidation in real brains.
- This repository: [brain.md](brain.md), [brain-shape.md](brain-shape.md),
  `src/evolution_simulator/brain.py`, `brain_adapter.py` and `traits.py`.
