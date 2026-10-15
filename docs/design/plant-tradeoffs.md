# Plant trade-offs, effort to eat and animal resistance

Design for TRAIT.13 to TRAIT.16, from the owner's request of 2026-10-14. Written by the TODO thread from the code as it is on main; the numbers below are the shape of each rule, not tuned values (the build threads tune them, after WORLD.15, and record them in [trait-config.md](trait-config.md)). The owner answered the three design questions in [#216](https://github.com/dwhagar/evolutionSimulator/issues/216) with the defaults named here (bigger plants pay more to stay poisonous; `toughness` is its own gene; an animal carries the poison it ate and its meat poisons whoever eats it, with no animal toxin gene for now). The second balancer is a direct cost (question 4, answered).

## What the owner asked for

- Every free plant gene gets a balancing trait, and the genes all interact with each other.
- Toxicity and size are linked. A bigger plant takes longer to germinate.
- `root_reach` must do something (today `PlantTraits.root_radius` is read nowhere).
- The faster a plant seeds, the easier it is to eat.
- An **effort to eat** is built in: tougher plants and more toxic plants take longer to eat.
- Animals get a **resistance** gene: the more an animal resists toxic plants (or poisoned animals), the longer it takes to eat, but the more food it can eat.

## The rule behind all of it: two balancers per gene

The owner's general rule (2026-10-14, for every gene, plant and animal): **every gene needs two balancers.** The first is an **inter-gene reaction**: the gene is connected to other genes through auxiliary traits, so raising it changes something else about the organism. The owner's example: a plant with more seeds is easier to eat, so it is more likely to get eaten. The second is a **direct cost** (the owner's answer to question 4): upkeep, a share of a budget or a delay, as on the animal side since TRAIT.9. Both are recorded per gene in the balancer table, and a test fails if a gene has fewer than two entries. ([#216](https://github.com/dwhagar/evolutionSimulator/issues/216), question 4.)

In the table below, the "side effect" part is the first balancer (the inter-gene link) and the "cost" part is the second one. The animal genes need the same table (TRAIT.17).

The TRAIT.9 rule for animals also still applies:

The TRAIT.9 rule for animals applies: no gene can be raised to its maximum for free. Every gene below is either paid for (upkeep, a share of the seed budget, a delay) or limited by another gene. A test per layout (the animal one from TRAIT.9 is the model) raises each gene alone to its maximum and checks that the plant or animal is worse off in some way that the table below names.

## Plant genes and what balances each

Today's plant genes: `max_biomass` (size), `growth_rate`, `toxicity`, `dispersal_radius`, `seed_clutch`, `root_reach`, `seed_provision`, `seeding_interval`, `longevity`. One new gene: `toughness` (question 2 in the issue; the default is yes). That makes plant layout version 4, with a migration from 3 (the new gene starts in the middle, so old saved plants behave about as before).

| Gene (raised) | What it buys | What balances it (cost or side effect) |
|---|---|---|
| `max_biomass` (bigger) | More total biomass, more shade over neighbours, more to eat and more seeds. | Upkeep grows with mass (exists). **New:** a longer germination delay (see below). More toxin to maintain if the plant is toxic (see toxicity). More visible (SENSE.21 size). |
| `growth_rate` (faster) | Reaches full size and seeding age sooner. | **New:** growth upkeep (the machinery costs even at rest), and softer tissue (effective toughness is lowered), so fast growers are easier to eat. Shorter life already (`longevity`, exists). |
| `toughness` (new, higher) | Takes longer to eat, so fewer bites per grazer and per day (effort to eat). | Upkeep (structural tissue), and it slows growth: the plant puts energy into structure, not leaves. Lowered again by fast seeding. |
| `toxicity` (higher) | Poisons grazers, and raises the effort to eat. | Defence upkeep grows with toxicity and, with the default for question 1, with size (`toxin_cost * toxicity^1.5 * size factor`); it slows growth a little; and a seed carries toxin, so `seed_provision` has to cover it. |
| `seeding_interval` (shorter, faster seeding) | More bursts per lifetime. | Each burst spends biomass (exists), and **new:** the plant is easier to eat (effective toughness falls as seeding gets faster), because it is spending on seed and not on defence. |
| `seed_clutch` (more seeds) | More seedlings per burst. | **Inter-gene link:** a plant with more seeds is easier to eat (the owner's example): effective toughness falls with the clutch, as with fast seeding. **Cost:** the burst budget is shared, so each seed gets less (`seed_provision` is the share of the plant's own size per seed; a bigger clutch spends more of the budget). More seeds also compete with each other near the parent. |
| `seed_provision` (bigger seeds) | A seedling starts bigger and survives better, and germinates sooner. | It spends more of the burst budget, so fewer seeds can be paid for. |
| `dispersal_radius` (further) | Seeds escape the parent's shade and soil limit and reach new ground. | **New:** a travel cost per seed (energy in proportion to the distance, taken from the seed's provision), so far seeds start smaller. |
| `root_reach` (wider) | **New:** the radius of ground the plant draws on (fixing the dead gene; see below). | Root upkeep that grows with the reach squared, and it competes with more neighbours. |
| `longevity` (longer life) | A longer seeding career. | Slower growth (exists, TRAIT.8). |

### The links the owner named

- **Toxicity and size.** Default (question 1, A): the defence upkeep is `toxin_cost * toxicity^1.5` scaled by the plant's mass share, so a big plant pays more to be as poisonous as a small one. Alternatives: B (a bite of a big plant carries more toxin) and C (a bigger plant is less poisonous per bite). Whatever the answer, the toxin must cost something that grows with size.
- **Size and germination.** A seed does not start growing at once: it waits `germination_days = base * (max_biomass / reference) ^ exponent` simulated days, shortened by a well provisioned seed (`seed_provision`). A tiny, fast plant germinates almost at once; a giant takes a season. Until then the seed is a plant that is alive but does not grow, cannot be eaten and cannot seed. (Build it as a countdown on the new plant, like `seed_cooldown`; it must be saved and restored.)
- **Seeding, seed count and ease of eating.** The effective toughness of a plant is `toughness * (1 - growth_softness * growth_rate_share) * (1 - seeding_softness * seeding_speed_share) * (1 - clutch_softness * clutch_share)` where the shares are the gene values on the 0 to 1 scale, with seeding speed the inverse of the interval. Faster growth, faster seeding or a bigger clutch gives a lower number.

### Fixing `root_reach`

The soil limit in `PlantRules` uses one fixed neighbourhood (25 units) for every plant, on purpose: the note there says that if root reach set the neighbourhood the plants would simply shrink their roots to dodge competition. The fix has to give a reach a **benefit that grows with it** as well as a cost, so neither end is free:

- Benefit: the plant draws on the ground within its own reach. A wide reach claims more ground, so in a sparse place the plant finds more soil, and a plant with a wide reach is less hurt by one dense patch next to it (it averages over more ground).
- Cost: the upkeep of the roots (grows with the reach squared), and a wide reach overlaps more neighbours, so in a dense stand it shares its soil with more of them.
- Test: with the same stand, a plant with the narrowest reach and one with the widest do worse than a middle one in at least one world (a sparse one for narrow, a dense one for wide). If the test cannot show that, record why and remove the gene instead (plant layout bump).

`PlantRules.neighbourhood` stays as the middle of the reach scale.

## Effort to eat (TRAIT.14)

Today an animal eats `graze_amount * dt` of a plant per tick whatever the plant is. Add an **eat effort** to every plant: `effort = 1 + tough_w * effective_toughness + toxin_w * toxicity` (so an ordinary soft, harmless plant has effort 1 and a tough, toxic one has a large number). The bite an animal takes per tick becomes `graze_amount * dt / (effort * handling)`, where `handling` is 1 for an animal with no resistance (TRAIT.15 changes it). The plant takes the damage and loses the biomass it gave, as now.

What this changes:

- A tough or toxic plant is eaten slowly, so it survives more grazing, but it also pays for its toughness and toxin (the table above). It is no longer free to be dangerous.
- A grazer on a tough plant spends longer standing still beside it. Time spent eating is time not spent fleeing or mating, so effort has a cost for animals too. (Do not add a new brain input for this; the existing eat and attack output already covers it.)
- Taste (`inspect_food`) and the poison damage (`feed`) stay as they are, but poison damage per bite is now per unit of food eaten, so a slow eater takes the same poison for the same food and only gets the food slower. Check that the poison clock (damage over time per reference tick) is not doubled by the slower eating; the build should state which one it uses.
- The viewer shows the effort in the plant inspector (UX thread, small item after the build).

## Animal resistance (TRAIT.15)

A new animal gene `resistance` (0 to 1). It is a new gene in the animal layout, so it is **layout version 10** (SENSE.21 takes version 9 for the camouflage gene and merges first; if it has not merged when this starts, ask the TODO thread whether to share one bump). The migration from 9 starts it in the middle, like the other new genes.

What a higher value does, both from one number:

- **Takes less poison.** The poison damage in `feed` is multiplied by `1 - resist_shield * resistance`, on top of the taste shield that exists.
- **Eats slower.** `handling = 1 + handling_cost * resistance`, so a resistant animal chews, filters and detoxifies: the bite per tick in the effort formula is smaller.
- **Eats more.** A resistant animal can take a bigger meal before it is full: the energy it can take in from one sitting (or the stomach limit; the build chooses, following what is in `feed` and the energy store) grows with `1 + intake_gain * resistance`. This is what the owner asked for ("able to eat more food"), and it is what makes slow, resistant eating pay off on a rich, toxic plant.
- **Costs.** Upkeep that grows with the resistance (the detox organs), recorded in the TRAIT.9 cost table. It must also have a reason not to be at its maximum on a world of soft, harmless plants (there it only slows eating and costs upkeep).

The same resistance applies to poisoned meat (TRAIT.16).

## Poisoned animals (TRAIT.16, after TRAIT.15)

Default (question 3, A): an animal that ate poison keeps a `toxin_load` that fades by a half-life, and its corpse's meat carries the load it had at death. A meat eater taking in meat from a poisoned animal takes the poison like a plant eater would, reduced by resistance, and the effort to eat meat follows the same formula (meat has a toughness of its own, a rules constant). Prey that are poisoned then are less rewarding to hunt, so the hunters evolve resistance too. Option B (animals with a toxin gene of their own, venom or poisonous skin) is a bigger project and would be a new item after this one if the owner picks it.

## Order of work

1. WORLD.15 (Foundations 3) makes founders breed. Plant and feeding numbers depend on it, so none of the builds below start before it merges (a plant layout bump changes the `state_digest` of the default run).
2. TRAIT.12 (plants start longer-lived), then TRAIT.13 (genes, costs, germination, `root_reach`, cost table and test), by one thread, because both retune the plant side. Plant layout version 4.
3. TRAIT.14 (effort to eat) by the same thread; it needs the `toughness` gene.
4. TRAIT.15 (animal resistance gene, animal layout version 10) by the thread that built SENSE.21, since it holds the layout bump history. It needs TRAIT.14 (the effort formula) and SENSE.21 (version 9).
5. TRAIT.16 (poisoned animals), after TRAIT.15, if the owner confirms the default.
6. TRAIT.17 (the same two-balancer table and test for every animal gene) is independent of the plant builds apart from the layout bumps; it comes after TRAIT.15 so the new gene is in the table, and can start earlier as an audit that lists the gaps.
7. A small viewer item (inspector fields: toughness, germination, effort, resistance) and the species/gene-chart names for the new genes, after each layout bump (the catalogue names and units are in `catalogue.py` and the viewer tables).

Each build updates [dna-and-traits.md](dna-and-traits.md), [trait-config.md](trait-config.md) (new rules fields), the persistence field tables and the layout version notes, and checks old saved plants and animals load (migration).
