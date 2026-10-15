# Gene balance audit: the baseline

This is the first run of the balance audit (TRAIT.17, 2026-10-15). It follows the standard in [gene-balance.md](gene-balance.md#proposal-1-the-balance-standard-and-the-audit) and checks the table of balancers in [gene-balancers.md](gene-balancers.md). The tool is [`src/evolution_tools/balance_audit.py`](../../src/evolution_tools/balance_audit.py); run it with `scripts/balance-audit.ps1` (or `.bat`), or `PYTHONPATH=src python -m evolution_tools.balance_audit`. The plant layout is version 3 and the animal layout version 9.

**The table of balancers is a claim, and the audit is the arbiter.** A gene can have two entries in the table and still run to an end, because the balancers are too weak, or because the world does not use them yet. The audit shows which.

## How it measures

For each gene it holds every other gene at the reference values, steps the gene through nine points from 0 to 1, and computes a fitness proxy in each reference environment. Per gene and environment it reports the best value and whether the proxy rises, falls, peaks, dips or stays flat. Two proxies are Euler–Lotka growth rates per day, where a lineage that leaves nothing gets a floor.

- **Plants** run the real `PlantTraits` code (growth, defence upkeep, seed budget, `launch_seeds`, grazing) in four stands: *sparse* (no neighbours), *dense* (a big neighbour shading and taking soil), *grazed* (a grazer that avoids toxin), and *adapted grazer* (a grazer that does not). The stands are stand-ins: they have no space beyond one neighbour and a landing distance.
- **Animals** run the real `AnimalTraits` code (`feed`, `mate`, `give_birth`, ageing, injury) as the reproduction chemostat does, in five habitats: *rich plants*, *poor plants*, *toxic plants*, *prey* and *predator*. Each animal has an income of its own, so one gene value can be compared with another at a fixed budget. A newborn that cannot live off its parents' gift counts for less.
- **Verdicts.** `ok`: the best value is inside the range somewhere, or differs between environments. `top` or `bottom`: best at that end in every environment where the gene matters. `dead`: the sweep changes nothing anywhere, or no code reads the gene's trait (a static scan, which is how `root_reach` is caught).
- **The standard.** A gene that is `top`, `bottom` or `dead` fails unless a reason is recorded in `RECORDED` (in the tool). The audit fails the other way too: a recorded failure that no longer fails is stale, and a fix takes its entry out.
- **Direct cost.** The share of the reference body's burn that the gene's upkeep adds from bottom to top. It is upkeep only: costs paid in another currency (time, risk, a share of a budget, a slower body) are not in it.
- **Fast version.** `tests/test_balance_audit.py` runs three points and two habitats with three animals each (about 10 seconds), and the plant audit in full (about a second). The full animal sweep takes about 8 minutes on three cores.

## What it cannot see

- The animal habitats have **no space and no brain**. The senses (`sight_range`, `sight_fov`, `sight_acuity`, `hearing`, `smell`, `touch`, `encoder_fidelity`) and the brain genes (`brain_gain`, `reaction_time`, `curiosity`, `learning_rate`) show their cost and none of their benefit, so they sink or stay flat. They are recorded as **blind**, not balanced. Their benefit has to be audited in a real world; the recorded task is `-` until TODO adds a world-audit item.
- Every modelled benefit is a stand-in and a guess: the escape chance of `agility`, the competition benefit of `aggression`, the predator model of `camouflage` and `fear`, the meeting chance, the plant stands. The audit shows where costs bite and where the proxy has a free end, not where the genes settle in a real world.
- It does not see the founder breeding problem of WORLD.15. The reference organisms are independent of it.

## Plants

| Gene | sparse | dense | grazed | adapted grazer | Verdict | Direct cost | Note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `max_biomass` | 0.00 down | 0.00 down | 0.00 down | 0.00 down | bottom (recorded) | +82.2% | A lone plant gains nothing from size here (no light race for the canopy, no seed or grazing benefit). Size needs its benefit side. (TRAIT.13) |
| `growth_rate` | 1.00 up | 1.00 up | 1.00 up | 1.00 up | top (recorded) | free | Growth is free: no growth upkeep and no softer tissue yet. (TRAIT.13) |
| `toxicity` | 0.00 down | 0.00 down | 0.75 peak | 0.62 down | ok | +30.1% |  |
| `dispersal_radius` | 1.00 up | 1.00 up | 1.00 up | 1.00 up | top (recorded) | free | Scattering seeds is free: no travel cost from the seed provision yet. (TRAIT.13) |
| `seed_clutch` | 0.25 up | 0.25 up | 0.25 up | 0.25 up | top (recorded) | free | Free below the seed budget cap and the cap stops it, so it sits at the top. (TRAIT.13) |
| `root_reach` | = | = | = | = | dead (recorded) | free | no code reads its trait. The roots do nothing yet. (TRAIT.13) |
| `seed_provision` | 0.00 down | 0.00 down | 0.00 down | 0.00 down | bottom (recorded) | free | More small seeds beat fewer big ones: a big reserve has no benefit yet (no germination delay, no hazard of a waiting seed). (TRAIT.13) |
| `seeding_interval` | 0.00 down | 0.00 down | 0.00 down | 0.12 down | bottom (recorded) | free | Seeding early and often is free: toughness does not drop with it yet. (TRAIT.13) |
| `longevity` | 0.50 peak | 0.62 peak | 0.50 peak | 0.50 peak | ok | free |  |

How to read it: `toxicity` and `longevity` are the two genes the audit calls balanced. Toxicity peaks in the grazed stand, sinks without a grazer and sinks again against an adapted grazer, which is the world dependence the standard asks for. Longevity peaks inside the range everywhere.

The failures are the plant trade-offs of TRAIT.13: size has no benefit for a lone plant, growth and dispersal are free, a clutch is free below the seed budget cap, a big seed reserve has no benefit yet, early seeding costs no toughness, and `root_reach` is dead because nothing reads `root_radius`.

## Animals

| Gene | rich plants | poor plants | toxic plants | prey | predator | Verdict | Direct cost | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `size` | 0.12 peak | 0.12 peak | 0.12 peak | 0.12 peak | 0.12 peak | ok | +37.2% |  |
| `speed` | = | 0.25 down | 0.75 up | = | 0.62 up | ok | free |  |
| `agility` | = | 1.00 up | 1.00 up | = | 1.00 up | top (recorded) | +6.8% | The stand-in escape benefit is generous and agility has no real cost beyond its small upkeep. Recheck when turning matters in a real world. (REPRO.9) |
| `somatic_maint` | 0.00 down | 0.00 down | 0.00 down | 0.00 down | 0.00 down | bottom (recorded) | +22.6% | Its benefit is a longer life, which r discounts: the late-life gain does not pay for the repair upkeep in a growth rate. (REPRO.9) |
| `recovery` | = | 0.00 down | 0.50 peak | = | 0.75 peak | ok | +11.3% |  |
| `sight_range` | = | = | 0.12 down | = | = | bottom (recorded) | +4.4% | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `sight_fov` | = | = | = | = | = | dead (recorded) | +0.6% | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `sight_acuity` | = | = | = | = | = | dead (recorded) | +0.8% | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `hearing` | = | 0.00 down | 0.00 down | = | 0.00 down | bottom (recorded) | +6.4% | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `encoder_fidelity` | = | = | = | = | = | dead (recorded) | free | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `smell` | = | 0.00 down | 0.00 down | = | 0.00 down | bottom (recorded) | +8.9% | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `taste` | = | 0.00 down | 0.75 up | = | 0.00 down | ok | +9.0% |  |
| `touch` | = | 0.00 down | 0.00 down | = | 0.00 down | bottom (recorded) | +9.0% | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `herbivore_eff` | 0.62 up | 0.88 up | 0.88 up | = | 0.88 up | top (recorded) | +6.8% | A better gut is only held back by its upkeep and the diet penalty. Plants have no fibre or toughness yet. (TRAIT.14) |
| `carnivore_eff` | 0.00 down | 0.00 down | 0.00 down | 0.75 up | 0.00 down | ok | +6.8% | Balanced in the full sweep. (-) |
| `aggression` | = | 1.00 up | 1.00 up | = | 1.00 up | top (recorded) | +4.5% | The stand-in competition benefit has no matching injury or lost mate yet. (REPRO.9) |
| `fear` | = | = | 0.00 down | = | 0.75 peak | ok | +4.5% | Balanced in the full sweep. (-) |
| `repro_drive` | 1.00 up | 0.75 peak | 0.62 peak | 1.00 up | 0.88 peak | ok | +5.7% |  |
| `repro_cooldown` | 0.00 down | 0.25 peak | 0.25 peak | 0.00 down | 0.12 down | ok | -4.6% |  |
| `fertility` | 1.00 up | 0.88 up | 0.88 up | 1.00 up | 1.00 up | top (recorded) | +4.5% | The litter and the chance of a mating are cheap at the audit scale; newborns do not compete with each other in a real world. Recheck with the long-run check. (REPRO.9) |
| `parenting` | 0.00 down | 0.00 down | 0.00 down | 0.00 down | 0.00 down | bottom (recorded) | free | Any parenting above about 0.05 stops births in these habitats: the gift to the newborn costs more than the protection gains. Needs the juvenile body. (REPRO.10) |
| `sex_strategy` | 0.50 down | 0.50 down | 0.50 down | 0.50 down | 0.50 down | ok | -0.6% |  |
| `brain_gain` | = | = | = | = | = | dead (recorded) | free | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `reaction_time` | = | = | = | = | = | dead (recorded) | -2.3% | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `curiosity` | = | = | = | = | = | dead (recorded) | free | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `learning_rate` | = | = | = | = | = | dead (recorded) | +0.9% | Blind: the habitats have no space, no other animals to be seen or heard and no brain. (-) |
| `camouflage` | = | = | = | = | 0.62 up | top (recorded) | +3.4% | Its benefit (fewer predators) is the stand-in and its cost placeholders, so it sits at the top wherever a predator is. (REPRO.9) |

How to read it: `size`, `speed`, `recovery`, `taste`, `carnivore_eff`, `fear`, `repro_drive`, `repro_cooldown` and `sex_strategy` pass. `sex_strategy` is a category, so only a dead sweep fails it.

The recorded failures:

- `agility`, `aggression` (top): the stand-in benefits are generous and the real costs are small. Recheck when a real world uses them (REPRO.9).
- `somatic_maint` (bottom): its benefit is a longer life, which the growth rate discounts (REPRO.9).
- `herbivore_eff` (top): plants have no fibre or toughness yet (TRAIT.13, TRAIT.14).
- `fertility` (top): a bigger litter is cheap at this scale (REPRO.9, with the long-run check).
- `parenting` (bottom): any parenting above about 0.05 stops births in these habitats, because the gift to the newborn costs more than the protection earns (REPRO.10, TRAIT.19). It matches the first-litter finding of WORLD.15.
- `camouflage` (top): the benefit is a predator-only stand-in and the costs are placeholders (REPRO.9).
- the blind senses and brain genes, as above.

## Adding a gene

A gene added later is one entry in the balancer table (two rows) and, if it has a benefit, a benefit in the proxy. Run the audit; if the gene fails, either fix it or record why in `RECORDED`. The planned genes (`toughness` and `resistance`, `hearing_acuity` and `smell_acuity` in layout 10) already have rows in the table, marked planned.
