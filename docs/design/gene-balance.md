# Gene balance: how every gene is kept in check

Design proposal, written 2026-10-15 by the genetics research thread from the code on main (after TRAIT.9, SENSE.20 and the plant trade-off request of #216). The research behind it is in [research/gene-interactions-and-balance.md](../research/gene-interactions-and-balance.md). It builds on [plant-tradeoffs.md](plant-tradeoffs.md) (TRAIT.13 to TRAIT.16), [dna-traits-interaction.md](dna-traits-interaction.md) and [gene-clusters.md](gene-clusters.md), and amends the first of those where noted. Nothing here is built; every number is the shape of a rule for a build thread to tune. Open points are in [Decisions for the owner](#decisions-for-the-owner), each with a default.

## Summary

The owner's rule is that every gene needs balancers. The first balancer is genes reacting to each other. This note proposes how to do that for every current plant and animal gene, with five changes in how the genome is thought about and one tool to keep it honest.

1. **A standard for "balanced".** A gene is balanced when raising it to its maximum, or dropping it to its minimum, makes the organism worse off in at least one realistic world, and the reason is written down. The two ends are both checked: a gene with a benefit and no cost runs to the top, and a gene with a cost and no modelled benefit sinks to zero (`parenting` does today).
2. **A balance audit** (a script plus a fast test) that sweeps each gene alone and reports which genes still have a free end. It starts before any layout change and gives a baseline.
3. **Toxin as a dose.** Today poison damage is the same whatever amount is eaten (a finding, below). One animal state, `toxin_load`, that builds with the dose eaten and decays with a half-life, fixes that and gives resistance, "eat more", slow eating, size effects, poisoned animals and poisoned meat from one mechanism.
4. **Defences with two jobs.** Toughness slows the eater and also lowers the food value; toxin harms the eater. Resistance answers toxin only; the animal's gut and size answer toughness.
5. **A short list of gene-to-gene links** (about a dozen, most already in the TRAIT.13 to TRAIT.15 plan) chosen so that the real fast-soft-short against slow-tough-long strategy axis appears from the genes without coding two plant types.
6. **No new genes beyond the two already planned** (`toughness`, `resistance`), plus one optional pair (a toxin type and a resistance type) that the owner should decide on now, because adding them later costs another layout bump on each side.

## What the code does today (findings)

Measured on main with `PlantTraits` and `AnimalTraits`; the sweeps set every other plant gene to 0.5.

| # | Finding | Evidence | Why it matters |
| --- | --- | --- | --- |
| F1 | **Poison damage does not depend on how much is eaten.** `AnimalTraits.feed` applies `toxicity * (1 - 0.5 * taste) * 25 * dt` once per call whatever `biomass` is. | `feed(0.1, toxicity=1)` and `feed(5.0, toxicity=1)` both cost 18.73 health on the same animal; the energy gained is 0.04 against 2.01. | Making toxic or tough plants slower to eat (TRAIT.14) would multiply the poison taken per unit of food by the effort. A dose that follows the amount eaten is needed first. |
| F2 | `growth_rate` is free. | 0 to 1 raises growth from 0.17 to 0.85 per hour at the same upkeep (0.166); the upkeep share of growth falls from 0.98 to 0.20. Its only brake is the `longevity` coupling. | Selection pushes every plant to maximum growth. |
| F3 | `dispersal_radius` is free; `seed_clutch` costs nothing beyond the shared budget cap. | 10 to 70 units, no change in upkeep or budget. | Seeds go as far as the gene allows for no cost. |
| F4 | `root_reach` is dead. `PlantTraits.root_radius` is read nowhere except the viewer catalogue. | `grep root_radius` finds only `traits.py`, `trait_defs.py` and `catalogue.py`. | `TraitSet.unread_genes()` passes because a trait row reads the gene; the check misses a trait nobody uses. |
| F5 | The toxin upkeep does not follow plant size. `chemical_defense_tax = 0.05 * toxicity ** 1.5`, whatever the plant. | At toxicity 1 it is 62% of body upkeep for a 20-biomass plant and 23% for a 200-biomass one. | Big plants can be as poisonous as small ones almost for free. This is the "toxicity and size linked" request. |
| F6 | `parenting` has a cost and almost no benefit, so founders sit at zero and it stays there (the chemostat result already noted in the DNA notes). | `FOUNDER_LEVELS["parenting"] = 0.0`. | A gene with no modelled benefit is balanced only by sinking. |
| F7 | A small animal population can lose a sex by chance. | Known quirk in [dna-and-traits.md](dna-and-traits.md). | Fisher's sex-ratio balance needs both sexes present to work. |

Everything else in the animal table of [dna-and-traits.md](dna-and-traits.md#what-every-gene-costs) (TRAIT.9) holds: every animal gene pays or has a recorded reason. The animal side is closer to the standard than the plant side.

## Proposal 1: the balance standard and the audit

### The standard

Every gene must have, written in the per-gene tables below:

- **An internal balancer**: a cost (upkeep, production, time or risk) or a link to another gene or trait that grows as the gene rises. Convex costs (a square or higher power) against saturating benefits, so there is a stable middle.
- **An external check**: what in the world pushes back when the gene is high or low (food, grazers, density, another species adapting). The second kind of balancer the owner has in mind may be one of these; see [question 1](#decisions-for-the-owner).
- **Both ends checked.** Not only "not free at the top" but "not useless at the bottom", with a reason for any gene allowed to sink or run to an end (`TraitSet.free` already records a reason for animals; plants get the same table).

### The audit (`scripts/balance_audit.py`, plus a small test)

1. For each gene in a layout, set the rest to the founder values, step the gene through 0, 0.125 ... 1 (nine points), and compute a fitness proxy in each reference environment.
2. **Plant proxy**: expected number of established seedlings over a lifetime (growth minus upkeep and grazing losses, then seeds times establishment). Reference environments: a sparse stand with no grazers; a dense stand (soil limit and shade bite); a grazed stand (a scripted grazer that bites on contact at the effort-adjusted rate); a stand grazed by a toxin-adapted grazer.
3. **Animal proxy**: net energy per hour, then lifetime offspring in the chemostat of `scripts/reproduction_check.py` (the TRAIT.9 check is the model). Environments: rich and poor plants, with and without toxic plants, with and without prey.
4. **Report**: for each gene and environment, the best value and whether the proxy rises, falls or peaks as the gene goes up. A gene whose proxy is monotonic in every environment is listed with the reason on record, or fails.
5. **Fixed budget**: the audit varies one gene with the rest fixed, on purpose (the Y-model warning in the research note: comparing a mixed population hides trade-offs).
6. **Dead-gene check**: the audit also fails a gene whose sweep changes nothing in any environment. This catches `root_reach`, which `unread_genes()` cannot.
7. **Test**: a fast version (three points per gene, two environments) in the normal test suite; the full sweep stays a script that writes a table into the changelog notes of a layout bump.

It needs no layout change, so it can be built first and used to see which proposals below bite.

## Proposal 2: toxin as a dose (fixes F1, carries TRAIT.14 to TRAIT.16)

**State.** `AnimalTraits.toxin_load`, a number in dose units, saved and restored with the animal (persistence field tables).

**In.** Each bite adds `eaten * toxicity * (1 - taste_shield * taste)` (the shield stays; it is how much of the toxin the animal's palate lets through). Meat adds `meat_eaten * concentration` where the corpse's concentration comes from the dead animal's load per unit of mass (TRAIT.16).

**Out.** Each tick the load falls by a half-life, `load *= 0.5 ** (dt / halflife)`, with `halflife = detox_halflife / (1 + detox_gain * resistance)`.

**Harm.** Damage per reference tick is `poison_damage * max(0, load / threshold - 1) * dt`, with `threshold = tolerance_per_mass * mass * (1 + tolerance_gain * resistance)`. A bigger animal tolerates more toxic food; a resistant one tolerates more again.

**Illustration** (the numbers are made up to show the shape, not tuned): an animal of mass 2.5 has a threshold of 10 dose units; the half-life is 12 hours. Eating a plant of toxicity 0.8 at 5 biomass an hour adds 4 units an hour, so the load passes the threshold after about 3 hours of continuous eating. The steady intake it can sustain is `threshold * ln 2 / halflife / toxicity`, about 0.7 biomass an hour, against 5 an hour of a harmless plant. With resistance 1 (and both gains set to 1) the half-life is 6 hours and the threshold 20, so it sustains about 2.9, four times as much. That is the owner's "more resistance, more food eaten" without a stomach rule: the resistant animal eats more of the toxic plant per day, and a harmless plant gets it nothing.

**Why this form.** It matches the detoxification-limitation picture in the research (section 7.1), it removes F1, slower eating no longer multiplies the poison taken per unit of food (the dose follows the amount), and it gives TRAIT.16 a ready-made state: a poisoned animal is one with a high load, and its meat carries it. It replaces the flat `poison_damage` per bite and the `1 - resist_shield * resistance` multiplier of the TRAIT.15 plan, but keeps the intent (resistance protects, eating is slower, more can be eaten). **This is the change to settle before TRAIT.14 starts.**

## Proposal 3: plant balance (amends TRAIT.13)

`plant-tradeoffs.md` already covers the table of plant genes. These amendments sharpen it from the findings and research.

1. **Toxin upkeep follows body upkeep (F5).** Replace `toxin_cost * toxicity ** 1.5` with `defence_share * body_upkeep * toxicity ** 1.5`, divided by `1 + defence_longevity * longevity` (long-lived tissue is built once and lasts, which is why trees are tougher than annuals). With `defence_share` 0.3 a mid plant pays about what it does today (0.045 against 0.05) and a 200-biomass plant pays about 2.7 times as much as a 20-biomass one, instead of the same. The exponent on size is the existing 0.5 of the body upkeep; a rules field can make it steeper.
2. **Toughness is the quantitative defence.** Upkeep for toughness grows with the plant's mass, divided by the same longevity factor, it slows growth (as planned), and it lowers the **food value** of the plant: the energy an animal gets from the biomass it eats is multiplied by `1 - fibre_loss * effective_toughness * (1 - herbivore_eff)`. A tough plant is slower to eat and worth less per bite, and a fine herbivore gut (`herbivore_eff`, which costs gut upkeep) digests fibre better. Default on (question 3).
3. **Growth costs something (F2).** A growth upkeep `growth_cost * base_growth ** 2 * body_upkeep` (machinery kept even at rest, as the plan says) and the softer-tissue link. Together these are the resource-availability trade-off: fast growers are cheap to lose.
4. **`root_reach` (F4).** Give it three effects and three costs, and keep the neighbourhood of 25 as the middle of the scale.
   - Benefit 1, soil: the plant draws on `capacity * (1 + root_gain * reach_share)`, so in a dense stand a wide reach keeps more soil access.
   - Benefit 2, tolerance (default, question 4): a grazed plant with a wide reach regrows faster (`repair_share` and the lower `dies_below_biomass` rise with reach), as stored root reserves do in real plants.
   - Cost 1: root upkeep, `root_cost * reach_share ** 2 * body_upkeep`.
   - Cost 2: a root-to-shoot diversion of growth, `growth * (1 - root_shoot * reach_share)`.
   - Cost 3 (already planned): the dead end has to be shown not to be a corner; the audit's sparse and dense stands do that. In a sparse stand soil is not short and narrow wins on cost; in a dense or grazed one wide wins. If the audit cannot show that, remove the gene (plant layout bump) as TRAIT.13 already allows.
5. **Seed and germination.** The plan's germination delay stays, with two refinements: the delay scales with `(max_biomass / 80) ** exponent / (1 + provision_gain * seed_provision)`, and a seed that is waiting has a death hazard per day that a bigger provision lowers (seeds rot or are eaten). The real exponent for development time against mass is about 0.25, but plant sizes here span only a factor of 10, which gives a delay only 1.8 times longer for the largest than the smallest, so start at 0.5 and say so in the rules docs. The hazard gives the provision gene a benefit that the budget alone does not: bigger seeds survive the wait.
6. **Dispersal travel cost** and the **seed budget share** stay as in the plan.

## Proposal 4: effort to eat (amends TRAIT.14)

The plan's formula stands: `effort = 1 + tough_w * effective_toughness + toxin_w * toxicity`, and the bite per tick is `graze_amount * dt / (effort * handling)`. Two additions:

- It depends on Proposal 2. With dose-based poison, a tough or toxic plant eaten slowly gives the animal more time to clear its load, so the toxin term in the effort is also a natural brake on poisoning. No separate "poison clock" decision is needed.
- Effort is time, which is a different currency from energy. That is deliberate (research section 3.2). Do not add a new brain input for it.

## Proposal 5: animal resistance (amends TRAIT.15)

`resistance` (0 to 1, animal layout version 10) works through the toxin load: it shortens the half-life, raises the threshold, and sets `handling = 1 + handling_cost * resistance` for the bite (slower eating, as the owner asked). Costs:

- **Upkeep** that grows with resistance squared (detox organs), in the TRAIT.9 cost table.
- **Handling** (already listed): resistant animals eat slowly on every plant, including harmless ones.
- **Speed** (question 8, default on): a small reduction of top speed and agility with resistance, like the locomotor cost of resistant garter snakes. A different currency from upkeep.
- **Taste and resistance overlap.** Protection from the two combines as `1 - (1 - taste_shield) * (1 - resistance_shield)`, so an animal with sharp taste gains less from resistance and the other way round. The cheap way to keep both from being maxed.
- **Toughness is not answered by resistance.** The gut, size and time answer it.

With no toxic plants in the world, resistance costs upkeep and handling for nothing and should sink; with toxic plants it should rise. That is the dependence on the world the audit checks.

## Proposal 6: poisoned animals and meat (TRAIT.16)

Falls out of Proposal 2 with no extra rules: an animal's `toxin_load` is carried into its corpse as concentration (load divided by mass); a meat eater's bite adds dose by that concentration and is slowed by the meat toughness constant. A resistant plant eater that keeps a high load is a poisonous prey, so hunters need resistance too: the chain plant toxin, herbivore resistance, hunter resistance, as for monarchs and milkweed (research 7.3). Aposematism and mimicry stay a later option.

## Proposal 7: animal links and conditional additions

Add only if the audit shows the gene runs to an end:

- **A standing cost for speed.** Muscle is paid for at rest. `speed_standing * speed ** 2` in basal metabolism, like agility's. Today only moving costs (TRAIT.9).
- **A benefit for parenting (F6).** Juveniles get a weaker body that rises with maturity (health, speed and bite from half at birth to full at maturity), so a newborn's starting energy and the parents' protection matter. This is a world and reproduction change (`REPRO.9` territory), not a gene change.
- **Pace of life.** A modest link from `repro_drive` to effective aggression, so fast life histories go with bold behaviour. Only if the long-run correlation fails to appear by itself.
- **Sex ratio check (F7).** The audit reports the sex ratio over a long run; if a sex is lost in a population of normal size, assign the sex at birth.

## The per-gene tables

"Now" is what balances the gene in the code today. "Gap" is what is missing against the standard. "Proposal" is the change, with the section above.

### Plants (layout version 3, plus `toughness` in version 4)

| Gene | What it buys | Now | Gap | Proposal |
| --- | --- | --- | --- | --- |
| `max_biomass` | More total biomass, shade over neighbours, more to eat, more seeds | Upkeep grows with mass to the power 0.5; soil limit; shade from taller neighbours | Bigger is cheaper per biomass; no time cost; toxin cost ignores size (F5) | Germination delay with size (P3.5); toxin and toughness upkeep follow body upkeep (P3.1, P3.2); size visibility (SENSE.21) |
| `growth_rate` | Faster size and earlier seeding | Slower with longevity | Free (F2) | Growth upkeep and softer tissue (P3.3); fast-soft link |
| `toxicity` | Harms grazers, raises effort | Defence upkeep `0.05 * t ** 1.5` | Size-independent (F5) | Upkeep follows body upkeep and longevity (P3.1); dose-based poison (P2); effort (P4) |
| `toughness` (new) | Slower eating, lower food value | Not built | New | Upkeep, growth, softer when growing or seeding fast, lower food value (P3.2); cheaper for long-lived plants |
| `dispersal_radius` | Escape shade and soil limit | Soil limit near the parent | Free (F3) | Travel cost from seed provision (plan) |
| `seed_clutch` | More seedlings per burst | Shared budget cap | No cost below the cap | Plan keeps the cap; add the seed-to-seed crowding near the parent through the soil limit that exists |
| `seed_provision` | Bigger, hardier seedlings | Takes a share of the budget, so fewer seeds | The bigger seed has no extra benefit | Dormancy hazard and shorter germination for a bigger reserve (P3.5) |
| `seeding_interval` | More bursts per lifetime | Each burst spends biomass; plant must be 85% grown | Faster is cheap once grown | Softer tissue with faster seeding (plan) |
| `root_reach` | None (dead, F4) | Nothing | Dead gene | Soil capacity, regrowth, root upkeep, shoot diversion (P3.4), or remove |
| `longevity` | Longer seeding career | Growth ×(1 − 0.3 g), seed budget ×(1 − 0.4 g) | None serious | Defence upkeep ÷ (1 + k g) as the resource-availability link (P3.1) |

### Animals (layout version 8, plus `resistance` in version 10)

| Gene | What it buys | Now | Gap | Proposal |
| --- | --- | --- | --- | --- |
| `size` | Energy store, health, bite, litter modifier | Basal mass^0.75, speed and turn drag, birth cost, later maturity | None known | Visibility (SENSE.21); body-size toxin threshold (P2); audit |
| `speed` | Top speed | Kinetic burn `mass * (v/3.5)²`, size drag | No standing cost | Conditional standing cost (P7) |
| `agility` | Turn rate | 0.06 a², size drag | None | Audit |
| `somatic_maint` | Slower wear | Repair upkeep a², birth cost, cooldown stretch | None | Audit |
| `recovery` | Healing, rest regain | 0.10 r² upkeep, litter modifier | None | Audit |
| `sight_range`, `sight_fov`, `sight_acuity` | Seeing | Area cost ×(1 + acuity); acuity capped by field | None | Audit |
| `hearing`, `encoder_fidelity` | Hearing, calling | Area cost, noise; call energy | Call value depends on listeners | Audit (does calling pay?) |
| `smell` | Smelling, scent trails | Area cost, noise | None | Audit |
| `taste` | Detects poison, shields | 0.08 t² | Overlaps resistance | Combined shield with diminishing returns (P5) |
| `touch` | Tactile range | 0.08 t² | None | Audit |
| `herbivore_eff`, `carnivore_eff` | Energy from plants and meat | Gut upkeep 0.06 e²; diet penalty 0.4 on the other diet | Fibre not modelled | `herbivore_eff` digests tough plants (P3.2) |
| `aggression`, `fear` | Attack and flight tendencies | Placeholder upkeep 0.04 (a² + f²); sex offsets; fear stops mate-seeking | Placeholder cost | Audit; recheck with fight and flight costs (BRAIN.10) |
| `repro_drive` | Finds mates earlier | Wear ×(1 + 0.6 d); upkeep d² | None | Audit |
| `repro_cooldown` | Shorter gap between matings | Readiness upkeep, repair stretch | None | Audit |
| `fertility` | Chance, litter, gestation | Upkeep, gestation burden, birth cost | None | Audit |
| `parenting` | Newborn starts with more energy | Birth cost | No modelled benefit (F6) | Juvenile fragility (P7) |
| `sex_strategy` | Sex, drive modifier | Drive costs; Fisher balance if both sexes needed | Chance loss of a sex (F7) | Ratio check (P7) |
| `brain_gain`, `curiosity` | Brain sharpness, exploration | Free, with recorded reasons | None | Audit |
| `reaction_time`, `learning_rate` | Fast decisions, plasticity | Cheaper when slower; upkeep | None | Audit |
| brain block | Behaviour | Neuron and connection costs | None | Audit |
| `resistance` (new) | Tolerates and handles toxin | Not built | New | Load half-life and threshold, handling, upkeep, speed (P2, P5) |

## The links between genes

Most of what the owner asked for ("genes affect each other") is the set of couplings below. "Built" couplings exist; the rest are proposals.

| Link | Direction | Real-world basis | Status |
| --- | --- | --- | --- |
| `size` feeds mass, health, energy, drag, litter | One gene, many traits | Pleiotropy | Built |
| `fertility` scaled by `size` and `recovery` | Modifier cluster | Epistasis | Built |
| `sight_acuity` capped by `sight_fov` | Frontier | Optical trade-off | Built |
| `longevity` lowers growth and seed share | Long life costs growth | Life-history trade-off | Built (TRAIT.8) |
| Faster growth or seeding lowers effective toughness | Fast and soft | Resource availability | TRAIT.13 |
| `max_biomass` lengthens germination | Big and slow | Allometry of development | TRAIT.13 (P3.5) |
| `max_biomass` raises toxin upkeep | Big and poisonous costs more | Dose scales with tissue | TRAIT.13 (P3.1) |
| `longevity` lowers defence upkeep | Long-lived tissue is cheaper to defend | Resource availability, apparency | New (P3.1) |
| `seed_provision` shortens germination and cuts seed hazard | Bigger seeds establish better | Seed size against number | New (P3.5) |
| `root_reach` raises soil capacity and regrowth, costs upkeep and shoots | Roots as reserve | Tolerance, root-to-shoot allocation | TRAIT.13 (P3.4) |
| Toughness lowers food value, `herbivore_eff` offsets it | Defence and digestion | Fibre digestion | New (P3.2) |
| Toxin raises effort, and dose follows amount eaten | Defended food is slow and dangerous | Detox limitation, handling time | TRAIT.14 (P2, P4) |
| `size` raises the toxin threshold | Big eaters tolerate more | Dose per body mass | New (P2) |
| `resistance` shortens load half-life and raises threshold, slows handling | One gene, three effects | Detox limitation | TRAIT.15 (P5) |
| `taste` and `resistance` combine with diminishing returns | Avoid or tolerate, not both | Substitutable defences | New (P5) |
| `resistance` costs speed | Cost in another currency | Resistant snakes crawl slower | New (P5, question 8) |
| Load carried into corpse, passed to hunters | Poison up the chain | Sequestration | TRAIT.16 (P6) |

## Things to watch (not proposals)

- **The arms race may end in a corner.** A scalar toxin and a scalar resistance can both run to their maximum if the benefits stay large. The audit's grazed stand with and without adapted grazers shows whether they cycle. If they do not, question 5 is the answer.
- **Costs that never bite.** If a world is always rich, costs of resistance and defence will be invisible, which is realistic but makes the audit pass for the wrong reason; keep a poor reference environment in it.
- **Number scales.** All the shares above are order-of-magnitude. The TRAIT.9 chemostat is the way to tune them. Re-run it after each of TRAIT.13 to TRAIT.16.
- **A varied world.** Without patchy soil or seasons there is no spatial or temporal balancing selection (research section 5). That is a world feature; it is listed as a proposal in question 6 and not designed here.

## Phase 2 options (not proposed for the first build)

| Option | What | Cost | When |
| --- | --- | --- | --- |
| Toxin types and matching resistance | A categorical `toxin_type` digit on plants and `resistance_type` digit on animals; resistance is full against its own type, half against a neighbour, zero otherwise | One digit per side, so a plant version 4 and animal version 10 can carry them if decided now; otherwise another bump each | After TRAIT.14 to TRAIT.16 have run, or now (question 5) |
| Choosing food by profitability | A grazer in contact with several plants takes the one with the best energy per effort | Small; real effect needs the brain to see plant quality | After TRAIT.14 |
| Aposematism and mimicry | Poisonous animals advertise; harmless ones copy | Needs SENSE.21 camouflage and TRAIT.16 | Later |
| Scaling mutation by pleiotropy | Smaller mutation steps for genes that many traits read | Small; `traits_reading` gives the count | If `size` jumps cause trouble |
| Patchy soil and seasons | World features that vary the best genotype | A WORLD item | After WORLD.15 and TRAIT.13 to TRAIT.16 |
| Cluster blocks (supergenes) | `cluster_units=True` | Built, off by default | If clusters should never split |

## Decisions for the owner

Each has a recommended default that the builds use until it is answered. Questions 1 to 5 change what is built; 6 to 8 are smaller.

1. **What is the second balancer you had in mind?** The first is genes reacting to each other. Candidates, from the research: (A) the world pushing back, such as other species adapting and density effects; (B) costs paid in the world, in energy, time and risk; (C) something else, tell me. *Default: nothing is assumed. The tables carry both an internal balancer and an external check for every gene, which covers A and B until you say.*
2. **Make toxin a dose with a load that decays (Proposal 2)?** (A) Yes, this replaces the flat poison per bite and the resistance shield of the TRAIT.15 plan; (B) No, keep the flat poison and add a stomach limit. *Default A. It fixes F1 and gives resistance, eating more, poisoned animals and size effects from one mechanism.*
3. **Do tougher plants also give less food?** (A) Yes, and a better herbivore gut offsets it; (B) No, tough plants only take longer to eat. *Default A.*
4. **What is `root_reach` for?** (A) Soil capacity only, with root upkeep; (B) Soil capacity and regrowth after grazing, with root upkeep and slower shoot growth; (C) Remove the gene. *Default B.*
5. **Add toxin types and matching resistance now?** (A) Not now, scalar first, then decide after the long run; (B) Yes now, so they ride in plant version 4 and animal version 10; (C) Never. *Default A. B keeps several plant types alive and gives true arms-race cycles, but doubles the first build; if the long run shows a corner, it costs one more layout bump on each side.*
6. **Add a varied world (patchy soil, seasons) as a later item?** *Default yes, after the TRAIT.13 to TRAIT.16 builds.*
7. **Make the balance audit a gate for layout changes?** *Default yes: a layout bump must show the audit table, and a free gene needs a recorded reason.*
8. **Does resistance also slow the animal, like the garter snake?** *Default yes, a small top-speed and agility cost.*

## Order of work

The existing order in [plant-tradeoffs.md](plant-tradeoffs.md#order-of-work) stands. Added here, in order:

1. **Balance audit** (new, no layout change, no dependency; can start now). Gives the baseline and the reference environments.
2. **Dose-based poison** (Proposal 2, new, small, no layout change). Before TRAIT.14. It touches `AnimalTraits.feed`, persistence of the animal state, the `BehaviourRules` fields and the tests that fixed poison per bite.
3. **TRAIT.12, TRAIT.13** with the amendments of Proposal 3, then **TRAIT.14** (Proposal 4), by the plant thread after WORLD.15.
4. **TRAIT.15** (Proposal 5), after SENSE.21 and TRAIT.14, then **TRAIT.16** (Proposal 6).
5. **Conditional animal items** (Proposal 7) only as far as the audit asks.
6. **Re-run the audit and the chemostat** after each step, and record the tuning in [trait-config.md](trait-config.md).

Layout bumps: plant version 4 (`toughness`; the optional toxin type if question 5 is B), animal version 10 (`resistance`; the optional resistance type if question 5 is B). No other layout change is proposed. Each build keeps the migration and the old-save loading checks of the existing plan.

## What is not decided here

The tuning numbers (all shares, gains and half-lives), the exact fitness proxies in the audit, the viewer changes (inspector fields for effort, load, resistance, toughness and germination; chart names for the new genes), and the second balancer, which the owner has not yet named.
