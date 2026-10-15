# Body colour and hiding in foliage

Design note for `TRAIT.20`, written 2026-10-15 by the genetics research thread. It answers the owner's description of how creatures look ([#129](https://github.com/dwhagar/evolutionSimulator/issues/129): colour tied to diet, "its own value as when it's closer to the foliage they are in they are harder to see", tougher plants darker) and the four questions in [#246](https://github.com/dwhagar/evolutionSimulator/issues/246). It extends [How visible a thing is](sense-genes.md#how-visible-a-thing-is-sense21) (`SENSE.21`) and follows the balance standard of [gene-balance.md](gene-balance.md) and the plant design of [plant-tradeoffs.md](plant-tradeoffs.md). The build is `TRAIT.21`, in animal layout version 10 together with `TRAIT.15` (resistance) and `SENSE.22` (hearing and smell acuity). Nothing here is built, and every number is the shape of a rule for the build to tune. The owner has not yet answered the four questions; this note uses their defaults and says what changes if an answer differs (see [Decisions](#decisions-for-the-owner)).

## Summary

1. **A new animal gene, `colour`**: three digits, read as a position from 0 to 1 on a colour line. The first generation starts at its diet colour (carnivore red, herbivore blue, omnivore purple in between) plus a small spread, and it mutates freely (large steps are common).
2. **A shared palette function** in the core turns the position into an RGB colour. The simulator uses it for hiding and the viewer uses it for drawing, so what the owner sees is what the animals "see".
3. **The background an animal sits against** is a blend of bare ground and plant foliage, weighted by how much of the ground nearby is covered by plant canopy. Tougher plants are darker (the owner's wish), so their foliage is a darker green.
4. **The visibility rule gets one more factor.** An animal is seen from `reach * size * motion * (1 - camouflage_strength * camouflage) * contrast`, where `contrast` falls to one half when the coat matches the background perfectly and a moving animal gets only half of that benefit. Numbers from a prototype: a rust-red coat is best below about 30% plant cover, a green coat above it, and a blue coat is never best, so no colour is best everywhere.
5. **Colour sits alongside the camouflage gene.** Colour is the passive match to a place; camouflage is the active effort (staying still and low, with upkeep and slowing) that works anywhere. They multiply, which is the diminishing-returns combination.
6. **Two balancers**: the link through the shared visibility trait (size, speed and camouflage all act on it, and the benefit of a matching coat is cut by movement) and a direct cost, a small pigment upkeep that grows with how vivid the coat is. It enters the balance audit as a "not dominated" check across open ground, thick cover and a mosaic.
7. **A deviation from the TODO wording, for a reason**: the colour line runs red, purple, blue, teal, green, not red, green, blue. On the owner's order the middle of the line is the colour of the foliage, and since random founders have mixed diets most of them would start hidden in plants. See [The colour line](#the-colour-line) and [question 5](#decisions-for-the-owner).

## What exists today

- `visibility = size * motion * (1 - camouflage_strength * camouflage)` (`SensingRules.visibility`, `config.py`), computed once per neighbour in `WorldSenses.perceive` and stored on `Neighbour.visibility`. It scales how far the viewer's vision reaches. Touch and overlap always see.
- `camouflage` is the last body gene (4 digits) with upkeep `0.03 * camouflage ** 2` and a top-speed cut of up to 25% (`BodyRules`). First generations start at 0.
- Plants have a canopy radius (2 to 12) from `max_biomass`, no colour, and (after `TRAIT.13`) a `toughness` gene.
- The percept the brain receives carries no colour; only the distance at which something is seen changes. Nothing in the engine knows what colour an animal is.
- The viewer draws creatures by diet today and `UX.43` redraws them round, with colour from diet "for now".

## Why this shape (real-world basis)

Background matching is the commonest form of camouflage: an animal that resembles the typical background around it is harder for predators and prey to detect (Endler 1978 and 1984; Merilaita and others; memory). Three well-known features shape the rule:

- **It is habitat-specific.** A coat that matches one background stands out on another, so populations in different habitats differ, and a coat that matches an average of several backgrounds is a compromise (Merilaita, Tullberg and others; memory). That is the "no colour is best everywhere" the owner asked for, and it is why a single "hiding" number would be wrong.
- **Movement breaks it.** A matching animal that moves is seen far more easily than one that keeps still. Hiding therefore trades against foraging and hunting time.
- **Vivid colours cost.** Bright pigments, carotenoids above all, are costly because animals cannot make them and must find them in their food; colour is also tied to diet in this sense (flamingos, finches; memory). A dull coat is cheap.

(These are standard results quoted from memory; check the originals before citing them.)

## The colour gene

**What it is.** `colour`, a body gene of 3 digits (64 steps), read as `dna.value("colour")` from 0 to 1 and expressed as a trait of the same name with no further scaling. Three digits gives a step of about 1.6% of the line, finer than anything the audit or the viewer needs, and costs one digit more than two.

### The colour line

The gene is a position on a line of five anchor colours, with straight-line interpolation of RGB between neighbours (`evolution_simulator/colour.py`, shared with the viewer):

| Position | Colour | RGB (0 to 1) | Used for |
| --- | --- | --- | --- |
| 0.00 | rust red | (0.70, 0.30, 0.22) | The carnivore colour; also the nearest thing to bare earth on the line |
| 0.25 | purple | (0.55, 0.20, 0.60) | The omnivore colour (between red and blue) |
| 0.50 | blue | (0.20, 0.30, 0.85) | The herbivore colour |
| 0.75 | teal | (0.15, 0.60, 0.60) | A step on the way to green |
| 1.00 | leaf green | (0.20, 0.65, 0.20) | The nearest thing to foliage on the line |

**Why not red, green, blue?** The owner's description says "red to green to blue", and the TODO wording follows it. On that order the starting colour of an animal between a carnivore and a herbivore, an omnivore, is the middle of the line, which is green, the colour of the foliage. First generations have random diet genes, so most would be near the middle and most founders would start well hidden among plants, while `SENSE.21` starts everyone unhidden on purpose ("evolution has to find it"). Putting green at the far end keeps the owner's colours (red carnivores, blue herbivores, omnivores in between, green reachable by mutation) and makes every founder start visible. The only visible difference to the owner is that an omnivore is purple. If the owner prefers the other order, the cost is a founder rule that avoids the middle (question 5).

**The same mapping for diet.** `diet_colour(carnivore_eff, herbivore_eff)` gives the position a creature with those diet genes would have: `0.25 * (1 - tilt)` where `tilt = carnivore_eff - herbivore_eff` runs from -1 (all plants) to +1 (all meat), so the position runs from 0.5 (blue) to 0.0 (red) and a balanced diet gives 0.25 (purple). `UX.43` uses this function for the drawing until the gene lands, and `TRAIT.21` uses the same function for founders, so nothing changes colour when the build merges.

### Founders and mutation

- **Founders.** `founder_animal_dna` sets `colour = diet_colour(...)` plus a uniform spread of `FOUNDER_COLOUR_SPREAD` (0.04), clamped to 0 to 0.5, so a population is a cloud around the diet colour and not clones. Nobody starts above 0.5, so nobody starts the colour of foliage.
- **Mutation.** "Mutating freely": the trait row uses a large `mutation_step` (0.15), so `position_biases` favours the low digits little and most mutations move the coat noticeably. A herbivore's descendants can reach green in a handful of generations, and a red carnivore can evolve a green coat, as the owner asked. After the first generation colour and diet evolve independently, as `SENSE.19` did for the eye.
- **Diploid.** Codominant blending: a red parent and a blue parent give a purple child, an ordinary incomplete-dominance picture. No dominance setting is needed.
- **Position in the cluster table.** `colour` sits next to `camouflage`, and both are tagged a cluster `look` so crossover keeps them together (a genome that hides well keeps its coat and its effort; neighbours split in about 2 to 3% of children). Moving no existing gene.

## What the animal sits against

The background is a colour, the blend of bare ground and foliage at the animal's position:

```
background = ground + cover * (foliage - ground)        in RGB
foliage    = plant_green * (1 - foliage_darkening * toughness)
```

| Setting | Starting value | Meaning |
| --- | --- | --- |
| `ground` | (0.55, 0.45, 0.30) | Bare earth, a dull brown |
| `plant_green` | (0.20, 0.55, 0.20) | Foliage of a soft plant |
| `foliage_darkening` | 0.5 | A plant of toughness 1 is half as bright (the owner's "tougher plants are darker") |
| `cover` | 0 to 1 | Share of the ground nearby that is under plant canopy, below |
| `toughness` | 0 to 1 | The canopy-weighted mean toughness of the nearby plants; 0 until `TRAIT.13` adds the gene |

**Cover.** A coarse grid over the world (`ColourRules.cover_cell` 20 units, the same size as the scent field's cell but a separate grid, because scent trails are off by default). Each live plant adds its canopy area (`pi * canopy_radius ** 2`) and canopy area times toughness to the cell holding its centre. The cover at a position is the mean of the 3 by 3 cells around it: `min(1, canopy area / (9 * cell area))`, and the toughness is the canopy-weighted mean. The grid changes only when a plant is born or dies (canopy radius and toughness are fixed for life), so it is updated incrementally on those events and rebuilt from the plants after a load. That makes it a pure function of the live plants: saving and loading does not change a run (a periodic refresh would, because a loaded world could not recover the older grid a continuous run was using). One lookup per animal per tick.

**Plants darker when tougher** (`UX.44`) uses the same `foliage_darkening`, so what the owner sees on the screen is what the hiding rule uses. A tough, dark stand is a worse place to hide for a bright green coat and a better one for a dull one, which couples the plants' `toughness` gene to the animals' colour: a cross-species link that makes the animals' best coat depend on what grows around them.

## The visibility rule

```
visibility = size * motion * (1 - camouflage_strength * camouflage) * contrast
contrast   = 1 - colour_match_strength * match * (1 - motion_break * speed_ratio)
match      = max(0, 1 - distance(rgb(colour), background) / colour_match_radius)
```

`distance` is the straight-line distance between two RGB triples (at most 1.73; in practice under 1). The existing factors are unchanged.

| Setting (`SensingRules.colour`) | Value | Meaning |
| --- | --- | --- |
| `colour_match_strength` | 0.5 | A perfect match is seen from half the distance, like camouflage 1 |
| `colour_match_radius` | 0.6 | A coat farther than this from the background gets no benefit |
| `motion_break` | 0.5 | A moving animal at full speed gets half the benefit, so a matching coat works best for an animal that stays still |
| `cover_cell`, `cover_radius_cells` | 20, 1 | The grid above |

**What the prototype gives.** Contrast factor (1 is seen from the full distance, 0.5 from half) for an animal that keeps still, with soft plants, by cover and colour. A lower number is better hidden.

| Plant cover | Rust red (0.00) | Purple (0.25) | Blue (0.50) | Teal (0.75) | Green (1.00) | Best position |
| --- | --- | --- | --- | --- | --- | --- |
| 0.00 (bare) | 0.69 | 0.83 | 1.00 | 0.94 | 0.85 | 0.05 (rust) |
| 0.25 | 0.75 | 0.86 | 1.00 | 0.89 | 0.77 | 0.05 (rust) |
| 0.40 | 0.79 | 0.89 | 1.00 | 0.87 | 0.73 | 0.95 (green) |
| 0.50 | 0.82 | 0.91 | 1.00 | 0.86 | 0.70 | 0.95 (green) |
| 0.75 | 0.89 | 0.97 | 1.00 | 0.84 | 0.63 | 1.00 (green) |
| 1.00 (thick) | 0.97 | 1.00 | 1.00 | 0.84 | 0.58 | 1.00 (green) |

- The best coat switches from rust to green at about 30% cover. Below it the dull red-brown end hides best, above it green does; a mosaic gives neither a clear win, which is what keeps both coats alive in a world with patches.
- **Blue is never best.** Herbivore blue and carnivore red both start visible (blue is never helped by any cover). Under default answer A (diet is only a starting point) the founders' colour is where evolution leaves from, so selection should move herbivores toward green fast. That is the owner's choice of colour and is a result, not a bug; the audit reports it.
- Tough plants (toughness 0.8, soft plants darkened 40%) move the green end to 0.74 at half cover and 0.78 at full cover: a bright green coat hides worse in a tough, dark stand.
- **Stacked with camouflage and the other factors.** The worst case for a viewer is a small, still, camouflaged animal with a perfect match: `0.7 * 0.7 * 0.5 * 0.5 = 0.12` of the reach. Touch and overlap still see it, so nothing is invisible. No floor is proposed.

The percept the brain receives is unchanged: `Neighbour.visibility` is one number, the viewer's reach times it, so colour changes only how far an animal is seen from, and the viewer's brain has no colour input. A creature that cannot see colour cannot learn "red means danger"; colour as a percept is a later option (see [What is not decided](#what-is-not-decided)).

**Who is hidden from whom.** The rule applies to everyone who looks at the animal: predators, prey, mates and the animal's own young (a classified `mate` or `young` neighbour is seen through the same visibility). Hiding therefore has a reproductive cost for free: a well-hidden animal is harder for a mate to find. Prey benefit most (the life-dinner principle, see [the research note](../research/gene-interactions-and-balance.md)), but a hunter benefits too, since a hidden hunter is approached less warily.

## How it sits with the camouflage gene

Default (question 2 A): keep both.

| | `colour` | `camouflage` |
| --- | --- | --- |
| What it is | The coat: a passive match to a place | The effort: keeping still and low |
| Works | Only where the background matches the coat | Anywhere |
| Cost | Pigment upkeep, small | Upkeep `0.03 * camouflage ** 2` and up to 25% slower |
| Moving | Half the benefit when moving | Always on, whatever the animal does |

The two factors multiply, the diminishing-returns combination of the balance note: hiding fully by both is a quarter of the distance, not none. A specialist in a uniform place can hide cheaply by colour alone; a generalist moving between open ground and cover cannot match both, and pays for camouflage instead. If the owner picks B (colour replaces camouflage) the gene is removed in layout 10 and its upkeep and slowing disappear; the `motion` factor (still 0.7 against moving 1.3) already gives the stillness part of the benefit, so the change is smaller than it looks.

## The two balancers and the audit

The owner's rule (every gene has an inter-gene link and a direct cost, in the balancer table of `TRAIT.17`) gives `colour`:

| Kind | What | Detail |
| --- | --- | --- |
| Link through an auxiliary trait | The shared `visibility` trait | `colour` acts on it with `size`, `speed` (through motion and `motion_break`) and `camouflage`; the benefit of a matching coat falls as the animal moves; the best coat depends on the plants' `toughness` and on cover, and the founders' value reads `herbivore_eff` and `carnivore_eff` |
| Direct cost | A pigment upkeep | `body.colour_cost * chroma(colour) ** 2` per reference tick, with `chroma` the spread between an RGB colour's largest and smallest channel. Starting value `colour_cost` 0.02: about 2% of a basal 0.44 for blue (the most vivid, chroma 0.65), 1% for rust (0.48). Vivid coats cost more and dull ones less, as carotenoid pigments do; the table is the palette's own, so there is nothing to keep in step |
| External check (not a balancer by the owner's count, but what makes the audit pass) | The background | No colour is best on every background; a hidden animal is seen less by its mates; a moving animal gains half as much |

Under question 1 C (diet pulls the colour) the direct cost is replaced by `colour_cost * distance(colour, diet_colour) ** 2`, which also removes the arbitrary pigment table; this is the one case where the answer changes the build. It is the better physical story (diet-derived pigments), and its drawback is that a red carnivore that evolves a green coat is penalised for it.

### Where it enters the balance audit (`TRAIT.17`)

- **Layout**: `colour` is a continuous body gene but behaves like a categorical one: its value matters only through the background. The audit therefore uses the "not dominated" check from the toxin types (best at an end in every environment fails; a value best or worst in every environment is reported), as well as the normal dead-gene check.
- **Reference environments** (a new environment set for the animal audit): open ground (cover 0.05), thick cover (0.95), and a mosaic (0.5), each with and without hunters, and with plants of toughness 0 and 0.8 once `TRAIT.13` exists.
- **Proxy** (a closed form, no chemostat needed for this gene): a survival rate per hour of `1 - h * visibility_factor`, with `h` set so a founder-coloured animal loses about 1% an hour to hunters in a world with hunters, 0 without, minus the pigment upkeep, plus the mate-finding term (a mate sees a hidden animal from `visibility` of its reach). The sweep goes through nine positions as for other genes.
- **Pass**: the best position differs between open ground and thick cover (rust-red end against green end), and no position is best in all three. The audit reports the sparse-ground, mosaic and thick-cover optimum. If the optimum is the same everywhere, the cover rule is not biting and should be retuned before merging.

## Percepts, frames and the viewer

- **Percepts**: no change (see above).
- **Frame**: each creature record carries `colour` (the position 0 to 1) and, with `UX.44`, each plant record its `toughness`. This is a frame format bump, read by `UX.43` and `UX.44`. The viewer turns the position into RGB with `colour.rgb(position)` and the sex spots (question 4 default A: females spotted) from the sex already in the frame; spots do not affect visibility.
- **Inspector**: the animal's detail shows its colour position and a swatch, the background it sits against (cover and toughness there), its current contrast factor, and the pigment upkeep. The plant detail shows its darkness.
- **Until `TRAIT.21` merges**: `UX.43` computes `diet_colour` from the diet genes, so there is no jump when the gene lands.

## Layout 10, migration and persistence

- **Layout**: animal version 10 adds `colour` (3 digits) next to `camouflage` with the resistance genes (`TRAIT.15`) and the acuity genes (`SENSE.22`) in one bump; the body's expected mutations stay 0.01 per digit, so `segment_mutations["body"]` is recomputed from the new body length (`TRAIT.15` and `SENSE.22` do the same).
- **Migration from 9**: every migrated animal gets `colour = diet_colour(its own diet genes)` so a saved world looks as it did and no animal is suddenly hidden. A round-trip test (save, migrate, load) is part of the build.
- **Persistence**: `colour` is part of the genome (nothing new to save); the cover grid is derived from the plants and rebuilt on load, so it needs no field in the save.
- **Digest**: adding the gene and the factor changes the state digest of any default run, as every layout bump does.

## Build checklist for `TRAIT.21`

1. `evolution_simulator/colour.py`: the palette, `rgb(position)`, `chroma(position)`, `diet_colour(carnivore_eff, herbivore_eff)`, `match(position, background)`, with no dependence on the world (so the numpy core and the viewer can use them).
2. `ColourRules` in `config.py` (nested in `SensingRules` for the match; `BodyRules.colour_cost` for the upkeep) with validation, and the rules-tree docs in [trait-config.md](trait-config.md).
3. The gene, trait row (`mutation_step` 0.15), `look` cluster, founder rule and migration in `layouts.py` and `trait_defs.py`; the upkeep in `AnimalTraits.basal_metabolism`; the cost-table entry ("colour upkeep").
4. The cover grid in `world/` (update on plant birth and death, one lookup per animal), `SensingRules.visibility` takes the contrast, `WorldSenses.perceive` passes the animal's cover and toughness and speed ratio.
5. Frame and inspector fields; catalogue names and units.
6. Tests: the table above reproduced by the rule; contrast is 1 for a coat far from the background and 0.5 at a perfect match when still; moving halves the benefit; the grid after save and load equals the grid of a continuous run; founders never start above 0.5; migration from 9 keeps the colour of the diet; the balance audit entry.

## Decisions for the owner

Questions 1 to 4 are those in [#246](https://github.com/dwhagar/evolutionSimulator/issues/246); their defaults are used here. Questions 5 and 6 are new and small.

1. **Is colour its own gene?** *Default A: yes, starting at the diet colour, mutating freely.* C (a cost for straying from the diet colour) changes the direct cost, as above. B (worked out from diet) removes the gene and the hiding by colour; the visibility rule falls back to `SENSE.21`.
2. **The existing camouflage gene.** *Default A: keep both.* B removes it in layout 10.
3. **What closer to foliage means.** *Default A: a blend of plant green (darker for tough plants) and bare ground, weighted by cover.* B (plants only) gives a background that is plant green or nothing; open ground then has no colour, and the rust-red end of the line has no use, so a carnivore colour would be dead weight.
4. **Which sex is spotted?** *Default A: females.* Display only.
5. **New: the order of the colour line.** *Default: red, purple, blue, teal, green (this note).* The alternative is red, green, blue, with a founder rule that keeps omnivores off the middle (for example omnivores purple and the green stretch skipped), at the price of two ways to read the same line.
6. **New: the form of the direct cost.** *Default: a pigment upkeep that grows with how vivid the coat is (about 2% of a basal metabolism at most).* The alternative is to cost the distance from the diet colour (this is question 1 C).

## What is not decided

The tuning numbers (match strength and radius, motion break, darkening, upkeep, palette stops); whether colour should wash out at night (reach already scales with daylight; scaling `match` by it too is a one-line option); colour as a percept for the brain (red as danger, recognising kin by colour), which belongs to a sense item; aposematism and mimicry (a poisonous animal that wants to be seen, [gene-balance.md](gene-balance.md#phase-2-options-not-proposed-for-the-first-build)); and the numpy build, where the palette and the match are pure functions over arrays and the cover grid is already an array.
