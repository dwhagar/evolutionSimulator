# Gene balancers

The owner's rule (2026-10-14, [#216](https://github.com/dwhagar/evolutionSimulator/issues/216) question 4): **every gene needs two balancers.** The first is a link to another gene or trait that changes when this gene rises (the owner's example: more seeds, easier to eat). The second is a direct cost: upkeep, a share of a budget, a delay or a risk. This file is the table of them, kept for every gene of the plant layout (version 3) and the animal layout (version 9), and `tests/test_balance_audit.py` fails when a gene has fewer than two entries, when an entry names a gene that does not exist, and when a planned entry names no task. [`src/evolution_tools/balance_audit.py`](../../src/evolution_tools/balance_audit.py) reads it and measures what the entries do ([gene-balance-audit.md](gene-balance-audit.md) has the results); the standard is in [gene-balance.md](gene-balance.md#proposal-1-the-balance-standard-and-the-audit).

**Columns.** *Kind* is `link` (another gene or trait moves with this one), `cost` (a direct price) or `world` (what the world pushes back with: food, grazers, density, another animal). *Status* is `built` (the code does it today) or `planned` (a TODO item will, named in *Task*). A gene with fewer than two **built** entries has a gap; the audit prints those and the planned entries say which task closes them. When a task lands, change `planned` to `built`. A new gene is not finished until it has two rows here.

## Plants

| Gene | Kind | Balancer | Status | Task |
| --- | --- | --- | --- | --- |
| `max_biomass` | link | Sets mass and the canopy radius (2 to 12): a wide canopy shades smaller neighbours and is seen from farther (SENSE.21), and the soil limit counts its biomass. | built | - |
| `max_biomass` | cost | Upkeep grows with mass to the power 0.5 (`plant.upkeep_scale * mass ** 0.5`), paid every tick whatever the size. | built | - |
| `max_biomass` | cost | A bigger plant takes longer to germinate (a countdown on the new plant, shortened by a better provisioned seed). | planned | TRAIT.13 |
| `growth_rate` | link | `longevity` lowers it: a long life slows growth by up to 30% (TRAIT.8). | built | - |
| `growth_rate` | cost | Growth upkeep `growth_cost * base_growth ** 2 * body_upkeep` and softer tissue, so a fast grower is easy to eat. | planned | TRAIT.13 |
| `toxicity` | cost | Defence upkeep `0.05 * toxicity ** 1.5`, the same whatever the plant's size. | built | - |
| `toxicity` | world | Grazers eat less of it or are poisoned (`AnimalTraits.feed`), less so with the animal's `taste`. | built | - |
| `toxicity` | link | Upkeep that follows body upkeep and falls with `longevity`, and a dose that follows the amount eaten. | planned | TRAIT.13, TRAIT.18 |
| `dispersal_radius` | world | Seedlings land under the soil limit and the shade of whatever stands at the landing place. | built | - |
| `dispersal_radius` | cost | A travel cost from the seed provision: the farther the seeds go, the less each is worth. | planned | TRAIT.13 |
| `seed_clutch` | cost | The seed budget caps the clutch (35% of biomass, less with `longevity`): a bigger clutch is not paid for, it is capped. | built | - |
| `seed_clutch` | link | The budget is shared with `seed_provision`: more seeds means smaller seeds (`seed_capacity`). | built | - |
| `seed_clutch` | world | Seedlings near the parent count as neighbours in the soil limit and the shade. | built | - |
| `root_reach` | link | Soil capacity and faster regrowth after grazing for a wide reach. | planned | TRAIT.13 |
| `root_reach` | cost | Root upkeep and a diversion of growth from the shoot. | planned | TRAIT.13 |
| `seed_provision` | link | A seed starts with this share of the parent's full size, so a seedling starts bigger and sooner paid for (`set_starting_biomass`). | built | - |
| `seed_provision` | cost | The seed budget buys `budget / (provision * max_biomass)` seeds: a bigger seed is fewer seeds. | built | - |
| `seed_provision` | link | A bigger reserve shortens germination and lowers the death hazard of a waiting seed. | planned | TRAIT.13 |
| `seeding_interval` | cost | Each burst spends biomass from the budget and needs 85% of full size, vitality above 0.4 and the cooldown over. | built | - |
| `seeding_interval` | link | The first seeds wait for 6% of the lifespan, and the cooldown starts after every burst. | built | - |
| `seeding_interval` | link | Faster seeding or growth lowers the effective toughness. | planned | TRAIT.13 |
| `longevity` | link | Slows growth by up to 30% (TRAIT.8). | built | - |
| `longevity` | cost | Shrinks the seed budget by up to 40% (TRAIT.8). | built | - |
| `longevity` | link | Divides defence upkeep, because long-lived tissue is built once. | planned | TRAIT.13 |

## Animals

| Gene | Kind | Balancer | Status | Task |
| --- | --- | --- | --- | --- |
| `size` | link | Sets mass, health, the energy store and the litter capacity; slows speed and turning (drag); sets the touch range and how far it is seen (SENSE.21). | built | - |
| `size` | cost | Basal upkeep grows with mass to the power 0.75, a bigger body pays more to move and more to be born (birth cost follows the newborn's energy store), and matures later. | built | - |
| `speed` | cost | Moving burns `kinetic_burn * mass * (speed / 3.5) ** 2` per tick, convex in speed. | built | - |
| `speed` | link | Raises loudness (hearing) and how visible it is (SENSE.21), and is slowed by size, camouflage and a pregnancy. | built | - |
| `speed` | cost | A standing upkeep for muscle, paid at rest. | planned | TRAIT.19 |
| `agility` | cost | Reflex upkeep `0.06 * agility ** 2` in the basal metabolism. | built | - |
| `agility` | link | Turning is slowed by size drag. | built | - |
| `somatic_maint` | cost | Repair upkeep grows with its square, and a birth surcharge and a stretched mating cooldown. | built | - |
| `somatic_maint` | link | Slows wear (a longer life) and lengthens the cooldown, and the birth cost rises with it. | built | - |
| `recovery` | cost | Upkeep `0.10 * recovery ** 2`, and healing spends energy per point. | built | - |
| `recovery` | link | Raises the litter capacity together with `fertility` and `size`. | built | - |
| `sight_range` | cost | Sensing upkeep by the area seen, times `1 + acuity`. | built | - |
| `sight_range` | link | Acuity lengthens the reach, and the reach is dimmed at night. | built | - |
| `sight_fov` | cost | Sensing upkeep grows with the field of view. | built | - |
| `sight_fov` | link | A wide field caps the acuity (`working_acuity`), so field and acuity trade against each other; the field also sets how much of the surroundings are seen at all. | built | - |
| `sight_acuity` | link | Capped by the field of view (`working_acuity`): a wide field leaves little acuity. | built | - |
| `sight_acuity` | cost | Raises the sensing upkeep by `1 + acuity`. | built | - |
| `hearing` | cost | Sensing upkeep by the area heard. | built | - |
| `hearing` | link | Reaches what it hears in proportion to its loudness (speed, calls), so a quiet animal is missed. | built | - |
| `encoder_fidelity` | cost | The energy of each call grows from 1.5 to 7.5 with it. | built | - |
| `encoder_fidelity` | link | Sets the call radius (0 to 60), so the benefit and the cost are one gene. | built | - |
| `smell` | cost | Sensing upkeep by the area smelled. | built | - |
| `smell` | link | Reaches what smells strongly (scent grows with biomass and with trails, SENSE.20). | built | - |
| `taste` | cost | Upkeep `0.08 * taste ** 2`. | built | - |
| `taste` | link | Detects poison before the bite and shields against what is eaten (`AnimalTraits.inspect_food`, the poison shield). | built | - |
| `taste` | link | Combines with `resistance` with diminishing returns, so an animal does not max both. | planned | TRAIT.15 |
| `touch` | cost | Upkeep `0.08 * touch ** 2`. | built | - |
| `touch` | link | The tactile range scales with the body radius (`size`). | built | - |
| `herbivore_eff` | cost | Gut upkeep `0.06 * e ** 2`. | built | - |
| `herbivore_eff` | link | Penalises the other diet (`diet_penalty` 0.4 times `carnivore_eff`). | built | - |
| `herbivore_eff` | link | Digests tough plants, offsetting the food value that toughness takes away. | planned | TRAIT.13, TRAIT.14 |
| `carnivore_eff` | cost | Gut upkeep `0.06 * e ** 2`. | built | - |
| `carnivore_eff` | link | Penalises the other diet, and sets the bite damage of an attack. | built | - |
| `aggression` | cost | Temperament upkeep `0.04 * (aggression ** 2 + fear ** 2)`, a placeholder. | built | - |
| `aggression` | link | Trades against `fear` and is raised by hunger and crowding, lowered by a parent's protection of its young. | built | - |
| `fear` | cost | Temperament upkeep, as above. | built | - |
| `fear` | link | Stops the search for a mate and shields the young (`parenting`). | built | - |
| `repro_drive` | cost | Drive upkeep and wear: wear grows by `1 + 0.6 * drive`, upkeep by its square. | built | - |
| `repro_drive` | link | Lowers the energy needed to start looking for a mate, scaled by the sex digit (`sex_strategy`). | built | - |
| `repro_cooldown` | cost | Readiness upkeep for a short gap between matings, and the repair stretch. | built | - |
| `repro_cooldown` | link | Stretched by `somatic_maint`. | built | - |
| `fertility` | cost | Upkeep, a gestation burden on the mother's upkeep and speed, and a birth cost that grows with the litter. | built | - |
| `fertility` | link | Sets the chance a mating takes, the litter capacity (with `size` and `recovery`) and the gestation time. | built | - |
| `parenting` | cost | The birth cost grows with the share of the newborn's energy the parent gives (`care_fraction`). | built | - |
| `parenting` | link | Sets how long the young depend on the parent and how bold the parent is near them (SENSE.14). | built | - |
| `parenting` | link | A juvenile body that is weaker at birth, so a parent's gift and protection matter. | planned | TRAIT.19 |
| `sex_strategy` | cost | Scales the drive upkeep and wear by its effective drive (digit 2 more, digit 3 less). | built | - |
| `sex_strategy` | link | Sets the sex and the drive modifier. | built | - |
| `sex_strategy` | world | A sex ratio check that gives a newborn a sex if one is lost in a normal population. | planned | TRAIT.19 |
| `brain_gain` | link | Scales every neuron's input sum, so the weights that evolve can match any gain. | built | - |
| `brain_gain` | cost | The weights above the dead zone cost brain upkeep (recorded free: any gain can be matched by weights). | built | - |
| `reaction_time` | cost | A faster thinker pays more brain upkeep (decision interval 1 to 4 hours). | built | - |
| `reaction_time` | link | Sets how often the brain looks and the reward window it learns over (BRAIN.11, WORLD.16). | built | - |
| `curiosity` | link | Nudges every brain output at random, so the animal moves, eats and mates less reliably. | built | - |
| `curiosity` | cost | A noisy speed burns more than a steady one, because the kinetic burn is convex (recorded free). | built | - |
| `learning_rate` | cost | Plasticity upkeep `0.004 * learning_rate` per tick, paid by every animal. | built | - |
| `learning_rate` | link | Sets how strongly a night's learning changes the weights. | built | - |
| `camouflage` | cost | Upkeep `0.03 * camouflage ** 2` and a top speed lowered by up to 25% (SENSE.21). | built | - |
| `camouflage` | link | Others see the animal from up to half as far (`SensingRules.visibility`), together with size and movement. | built | - |
| `brain` | cost | Upkeep per neuron and per active connection (a weight above the dead zone), scaled by the decision interval. | built | - |
| `brain` | link | Each sense and each output matters only if the wiring uses it, and a long brain mutates about once per child however long it is. | built | - |
