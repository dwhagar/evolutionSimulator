# Research: basic life-form traits for the simulation

Status: first draft, written by the "Research 2" thread. Companion to the DNA and reproduction research (Research 1). Input for the Foundations 1 scaffolding of the trait and DNA objects.

Scope: which real-world traits are worth keeping in a scaled-down evolution simulation, what ranges and units to use, and which trade-offs make selection pressures interesting. It does not cover DNA encoding or recombination (Research 1) or the world model.

A note on sources: the scaling exponents and ranges below are the usual textbook figures (Kleiber, Peters, Calder, West/Brown/Enquist, Smith and Fretwell, Stearns and others). They are quoted from memory and are good to about one significant figure. They are meant as sensible starting values for a simulation, not citations to build on. Where the number matters, check the original paper before relying on it.

## 1. Design principles

1. **Few genes, many consequences.** Real organisms have thousands of traits but a handful of axes explain most of the variation between species: body size, pace of life, diet and sensory/locomotor investment. A simulation gets rich behavior from about 8 to 12 traits if the costs between them are wired up correctly.
2. **Every benefit has a cost.** A trait that is free to increase will run to its maximum and nothing interesting evolves. Each trait below lists the cost it must pay. This is the single most important property of the set.
3. **Costs in energy, not in arbitrary penalties.** Express everything as energy per tick (or per unit distance). One currency makes trade-offs comparable and easy to tune.
4. **Allometry does the coupling for free.** Most real trade-offs are power laws of body mass. Using them means large size automatically implies lower mass-specific metabolism, longer life, slower reproduction, and so on, without special-case rules.
5. **Normalize.** Work in dimensionless simulation units with a reference organism at 1.0, not in kilograms and meters. Real exponents carry over; absolute numbers do not matter.

## 2. Scaling laws worth using

`m` is body mass relative to the reference organism (1.0). Exponents are approximate.

| Quantity | Scaling | Notes |
|---|---|---|
| Basal metabolic rate | `m^0.75` | Kleiber's law. Mass-specific rate is `m^-0.25`, so small animals burn more per gram. |
| Body length | `m^(1/3)` | Isometric. Surface area is `m^(2/3)`. |
| Max sustained speed | `~m^0.17` up to medium sizes, falling off for very large animals | Hump-shaped in real data (Garland 1983). A simple rising power law is fine for a first pass. |
| Cost of moving one unit of distance | `~m^0.7` total, or `~m^-0.3` per unit mass | Larger animals are cheaper per gram per meter (Taylor and colleagues). |
| Lifespan | `~m^0.2` | Roughly, across mammals. |
| Age at maturity / generation time | `~m^0.25` | |
| Maximum population growth rate | `~m^-0.25` | Small organisms can recover faster. |
| Fasting endurance | rises with size, with an exponent of very roughly `0.3` to `0.4` | Reserves scale faster than metabolism. |

Takeaway: a single size gene gives a coherent "small and fast-living" to "large and slow-living" spectrum. That alone produces r/K-style strategies.

## 3. Proposed trait set

Tiers: **1** is the minimum viable set, **2** is the next addition, **3** is optional or stretch.

Ranges are phenotype ranges in simulation units. "Scale" says whether the gene maps linearly or logarithmically onto the range.

### 3.1 Morphology and energetics

| Trait | Tier | Range (scale) | Effect | Cost / trade-off |
|---|---|---|---|---|
| `size` (mass) | 1 | 0.1 to 10 (log) | Bigger wins fights, stores more energy, lives longer, is harder to eat. | Basal cost `m^0.75`, slower reproduction, needs more food in absolute terms, becomes a larger target, slower to mature. |
| `metabolic_efficiency` (or "pace of life") | 1 | 0.5 to 1.5 (linear multiplier on basal rate) | Higher rate: faster growth, earlier maturity, higher activity ceiling. | Burns food faster, shortens lifespan (pace-of-life / rate-of-living pattern). |
| `reserve_capacity` | 1 | 0.02 to 0.5 of body mass (linear) | Survive famine, fund reproduction in lean times. | Carrying cost raises movement cost; fat is not available as weapon or armor mass. |
| `max_lifespan` | 1 | derived from `size` and pace, then a gene multiplier of 0.5 to 2 | Longer reproductive window. | Longevity is paid for by reduced early reproduction or higher upkeep. |

### 3.2 Locomotion

| Trait | Tier | Range (scale) | Effect | Cost / trade-off |
|---|---|---|---|---|
| `speed_factor` | 1 | 0.2 to 2.0 multiplier on the allometric baseline (linear) | Catch prey, flee predators, reach food first. | Movement energy per distance rises with speed (drag and muscle inefficiency, roughly quadratic at high speed); more muscle mass raises basal cost. |
| `agility` | 3 | 0 to 1 | Turning rate, dodging. | Trades against top speed and size. |

### 3.3 Sensing

| Trait | Tier | Range (scale) | Effect | Cost / trade-off |
|---|---|---|---|---|
| `sense_range` | 1 | 1 to 10 world units (linear or log) | See food, mates and threats earlier. | Sensing and the neural tissue behind it are expensive in real animals (brain tissue is a large share of basal metabolism). Modeling choice: cost `~range^2`, because the scanned area grows quadratically. |
| `sense_field_of_view` | 2 | 30 to 360 degrees | Wide: see predators everywhere (prey-like). Narrow: depth and distance for hunting (predator-like). | At fixed total cost, a wider field means a shorter effective range. |
| `sense_acuity` | 3 | 0 to 1 | Tell food from threat at distance, see camouflaged targets. | Competes with range and FOV for the same sensing budget. |

### 3.4 Feeding

| Trait | Tier | Range (scale) | Effect | Cost / trade-off |
|---|---|---|---|---|
| `diet_preference` | 2 | 0 (plant) to 1 (meat) | Which food sources are usable and at what efficiency. | Specialization trade-off: assimilation efficiency for plants plus assimilation for meat is capped, so a generalist is mediocre at both. |
| `attack` | 2 | 0 to 1 | Damage dealt; required to hunt. | Mass and upkeep; reduces speed or reserves at fixed size. |
| `defense` (armor) | 2 | 0 to 1 | Damage reduction against predators. | Adds mass and movement cost, reduces speed. |

Realism anchors: trophic transfer between levels is about 10 percent, so each step up the food chain supports far fewer individuals. Carnivores assimilate food more efficiently than herbivores (plant material is harder to digest), while meat is rarer and costs a chase. Ectotherms convert a much larger fraction of intake to growth and reproduction than endotherms (roughly 10 percent or more against 1 to 3 percent), because endotherms spend most of their energy staying warm.

### 3.5 Reproduction and life history

| Trait | Tier | Range (scale) | Effect | Cost / trade-off |
|---|---|---|---|---|
| `maturity_threshold` | 1 | 0.3 to 1.0 of adult size or age (linear) | Earlier first reproduction means more generations, less time to grow. | Smaller, weaker adults; early reproduction in many species reduces later survival or growth. |
| `offspring_investment` | 1 | 0.05 to 0.5 of parent mass per offspring (log) | Bigger, better-provisioned young survive more often. | Fewer offspring per unit of energy (Smith and Fretwell trade-off between offspring size and number). |
| `litter_size` | 2 | 1 to 8 (integer, or derived from available energy / investment) | More offspring per event. | Competes with `offspring_investment` for the same parental energy budget. In the simplest design this is not a gene but falls out of the energy split. |
| `parental_care` | 3 | 0 to 1 | Raises offspring survival. | Delays the parent's next reproduction and costs energy and time. |
| `reproduction_cooldown` | 2 | derived from size and pace | Limits reproductive rate. | |

Recommended simplification for Foundations 1: reproduction is "spend energy `offspring_investment` per offspring once reserves exceed a threshold". Litter size then emerges from `reserve_capacity` and `offspring_investment` rather than being a separate gene.

### 3.6 Environment tolerance (optional)

| Trait | Tier | Range (scale) | Effect | Cost / trade-off |
|---|---|---|---|---|
| `temperature_optimum` | 3 | world's temperature range | Where the organism thrives. | Mismatch with local temperature adds an energy penalty. |
| `temperature_tolerance` | 3 | narrow to broad | How far from the optimum it can live. | Generalist versus specialist: broad tolerance lowers peak performance ("jack of all trades"). |

Only worth adding if the world has a climate gradient. Without one, these evolve to meaningless values.

### 3.7 Behavior

`aggression`, `boldness`, `sociality`, `curiosity` and similar traits exist in real animals and strongly affect fitness, but they are better modeled as parameters of a decision rule (or a small brain) than as independent gene-level scalars. This is a design decision and is raised as an open question rather than specified here. Tier 3.

## 4. Minimal viable trait set (Tier 1)

Seven genes are enough to produce nontrivial evolution:

1. `size`
2. `metabolic_efficiency` (pace of life)
3. `reserve_capacity`
4. `speed_factor`
5. `sense_range`
6. `maturity_threshold`
7. `offspring_investment`

Lifespan is derived (size, pace, plus a multiplier) rather than a separate primary gene in the first cut.

### Per-tick energy budget (sketch)

All terms are in energy units per tick for an organism of mass `m`:

```
upkeep   = k_basal * m**0.75 * metabolic_efficiency
movement = k_move  * m**0.7  * (1 + reserve_capacity) * distance * (1 + (speed/speed_ref)**2) / 2
sensing  = k_sense * sense_range**2
net      = intake - upkeep - movement - sensing
```

Death: reserves reach zero, or age exceeds `max_lifespan`, or the organism is killed.
Reproduction: reserves exceed `maturity_threshold`-scaled requirement, then `offspring_investment * m` is transferred to each offspring.

The constants (`k_*`) are the tuning knobs for the whole simulation. They are calibrated so that the reference organism roughly breaks even in an average-quality patch of environment. The exact functional forms above are proposals, not biology, and are expected to change once the world model exists.

## 5. Trade-off map

Each cell says what pushes against what. These are what make selection non-trivial.

| Increasing... | helps with | but hurts |
|---|---|---|
| `size` | combat, reserves, longevity, being safe from small predators | upkeep, maturation time, reproduction rate, being seen |
| `speed_factor` | chasing, fleeing | movement cost per distance, muscle upkeep |
| `sense_range` | finding food, avoiding threats | constant energy cost, whatever else the sensing budget could buy |
| `reserve_capacity` | famine and breeding funding | carrying cost, a larger body for the same functional mass |
| `metabolic_efficiency` (higher pace) | fast growth, early breeding | upkeep, lifespan |
| `offspring_investment` | offspring survival | number of offspring |
| `maturity_threshold` (earlier) | more generations | smaller, weaker adults |
| `diet_preference` specialization | efficiency on the preferred food | flexibility when it is scarce |

### Strategies that should be able to emerge

These are sanity checks for the design: a good parameterization lets each of them be stable in a different environment.

- **Small fast breeder (r-strategist):** small `size`, high pace, early maturity, low investment per offspring. Wins in empty, resource-rich, unpredictable environments.
- **Large slow investor (K-strategist):** large `size`, low pace, late maturity, high investment per offspring. Wins in crowded, stable environments near carrying capacity.
- **Scout:** high `sense_range`, moderate speed, small reserves. Wins where food is patchy and far apart.
- **Hoarder:** big reserves and low speed. Wins where food is seasonal or rare.

## 6. Notes for Foundations 1 (trait and DNA objects)

These are suggestions for the scaffolding, not requirements.

- **Trait definition as data.** A trait is a small immutable record: `name`, `tier`, `kind` (continuous, integer, categorical), `lo`, `hi`, `scale` (linear or log), `default`, `mutation_sigma`, and a short description. The registry of traits is a plain list, so adding a trait does not require changing the engine.
- **Gene value versus phenotype value.** Keep a genotype value in a fixed interval (for example 0 to 1) and a mapping function to the phenotype range. Log-scale traits like `size` map the interval onto an exponential range.
- **Derived traits are functions, not genes.** Lifespan, litter size and cooldowns are computed from primary traits and size. Keep them in one module of pure functions so they are easy to test and tune.
- **Allometry in one place.** All exponents and `k_*` constants live in a single configuration object. Nothing else hard-codes them.
- **Polygenic mapping (coordinate with Research 1).** Real quantitative traits are controlled by many small-effect loci, which makes offspring values cluster around the parental mean with natural variation. A trait that reads the mean of `n` loci, where `n` is a per-trait setting, reproduces that. `n = 1` is the simple case.
- **Clamping.** The phenotype is always clamped to `[lo, hi]` after mutation, so a bad mutation cannot produce an invalid organism.
- **Testing.** Property tests are cheap and valuable here: phenotype always within range, mapping monotonic, budget non-negative for the reference organism, and a "free lunch" test that no trait can be moved to its maximum without a net cost.

## 7. Open questions

Filed as GitHub issues so they can be answered there. They are the points where the right answer depends on the user's intent rather than on biology.

- [#6 Fixed trait set or open-ended traits?](https://github.com/dwhagar/evolutionSimulator/issues/6)
- [#7 Strict biological scaling or free traits with explicit costs?](https://github.com/dwhagar/evolutionSimulator/issues/7)
- [#8 Predators and diet traits in the first version?](https://github.com/dwhagar/evolutionSimulator/issues/8)
- [#9 Behavior as genes or as a decision rule/brain?](https://github.com/dwhagar/evolutionSimulator/issues/9)
- [#10 World model: grid or continuous space, and what is one time step?](https://github.com/dwhagar/evolutionSimulator/issues/10)
- [#11 How should aging and lifespan work (and are climate traits in scope)?](https://github.com/dwhagar/evolutionSimulator/issues/11)

Until they are answered, the recommendation in each issue is the working assumption (the world model in #10 has none, so assume continuous 2D with a fixed tick): fixed trait set, allometric coupling, plants only, no behavior genes, hard lifespan cap, no climate traits.

## 8. Further reading

- Kleiber, M. (1932). Body size and metabolism.
- Peters, R. H. (1983). *The Ecological Implications of Body Size.*
- Calder, W. A. (1984). *Size, Function, and Life History.*
- West, G. B., Brown, J. H., Enquist, B. J. (1997). A general model for the origin of allometric scaling laws in biology.
- Brown, J. H. and others (2004). Toward a metabolic theory of ecology.
- Smith, C. C., Fretwell, S. D. (1974). The optimal balance between size and number of offspring.
- Stearns, S. C. (1992). *The Evolution of Life Histories.*
- Garland, T. (1983). The relation between maximal running speed and body mass in terrestrial mammals.
- Taylor, C. R., Heglund, N. C., Maloiy, G. M. O. (1982). Energetics and mechanics of terrestrial locomotion.
