# Research: how genes interact and what keeps them in check

Written 2026-10-15 by the genetics research thread. Input for the design proposal in [design/gene-balance.md](../design/gene-balance.md). This note says what real biology does and what that means for a simulation. It does not say what to build; the design note does.

**A note on sources.** Most of this is textbook population genetics, ecology and life-history theory, quoted from memory. In the source list at the end, entries marked **checked** had a source page (usually an abstract) found during this research; entries marked **memory** were not looked up and should be checked against the original before anyone cites them. Where a number matters it is flagged. Nothing here is a finding about this simulator; those are in the design note.

## 1. The question

The owner's rule is that no gene may be free: a gene that only helps will be pushed to its maximum by selection and nothing interesting evolves. Real genomes have the same problem, and real organisms solve it with a small set of mechanisms. This note collects them, sorted by what a simulation can borrow.

## 2. Vocabulary

| Term | Meaning | Real example | What it is in a simulation |
| --- | --- | --- | --- |
| Pleiotropy | One gene affects several traits | A gene for body size changes metabolism, lifespan, speed and food needs | One gene read by several traits (built: `size` feeds `mass`, health, energy, speed drag, litter) |
| Antagonistic pleiotropy | Pleiotropy where one effect helps and another hurts, often at different ages | A gene that raises early fertility and shortens life (Williams 1957) | A gene whose benefit and cost are on different traits, or at different life stages |
| Trade-off | Two traits cannot both be improved because they draw on one budget | Seed size against seed number (Smith and Fretwell 1974) | A shared energy store or a fixed share of a burst budget |
| Epistasis | One gene changes what another does | Modifier genes that scale a main gene | `Combine.MODIFIED` clusters (built) |
| Diminishing-returns epistasis | The benefit of a gene shrinks as other beneficial genes are added | Repeated beneficial mutations in microbes each help less than the one before | Saturating benefit curves |
| Polygeny | Many genes feed one trait | Height, milk yield | `Combine.MEAN` (built) |
| Linkage | Nearby genes are inherited together | A supergene holding a whole mimicry pattern | Gene clusters and `crossover_linked` (built) |
| Dominance | Two copies of one gene combine | Sickle-cell heterozygotes | `DominanceModel` (built) |
| Balancing selection | Selection that keeps more than one version of a gene alive | Heterozygote advantage, frequency-dependent selection | An effect that makes the common type worse off or the rare type better off |
| Arms race (Red Queen) | Two species evolve against each other and neither gets ahead | Host and parasite, predator and prey | Plant toxin and animal resistance both evolving |

## 3. Why genes do not run to their maximum

### 3.1 Resource trade-offs

An organism has one budget of energy, time and material. Putting more into one trait leaves less for the others, which is a **trade-off**. Three points matter for design:

1. **The cost has to be real and in the same currency.** A trade-off exists only if the two traits draw on the same budget (Stearns 1989; Roff and Fairbairn). In simulations the cheapest way is one energy store that every cost comes out of, which is how this simulator already works.
2. **Acquisition hides allocation.** The "Y-model" (van Noordwijk and de Jong 1986) points out that when individuals differ in how much resource they get at all, the ones with more can afford both traits, so across a population the two traits correlate **positively** even though each individual trades them off. A test that measures trade-offs across a mixed population can miss real ones. Measure with the budget held fixed.
3. **The shape of the curve decides the outcome.** If the benefit of a trait saturates and its cost accelerates (convex cost), there is a stable middle value (a generalist). If the cost saturates and the benefit accelerates, extremes win and the population splits (specialists). This is the Levins fitness-set argument. A squared or higher-power cost with a saturating benefit is the safe default for "keep it in the middle".

### 3.2 Kinds of cost

| Cost | What it is | Example |
| --- | --- | --- |
| Maintenance | Paid every day for having the trait | Brain tissue, defensive chemicals kept in the leaves |
| Production | Paid once, when the trait is built or used | Making a seed, a birth |
| Allocation | Energy put here cannot go there | Growth against defence (growth-differentiation balance, Herms and Mattson 1992) |
| Ecological | The trait makes you easier for something else to exploit | Bright colours attract predators; a conspicuous seed attracts seed eaters |
| Autotoxicity or self-harm | The defence harms the owner too | Cyanogenic plants and frost (see 6.4) |
| Pleiotropic | The gene that gives the benefit also changes something else | Resistance mutations in a nerve channel that also slow the muscle (see 7.2) |
| Time | The trait makes a task slower | Handling time of tough or toxic food |

**Costs are not always found.** Reviews of plant defence report that fitness costs of resistance are detected in roughly half of the experiments and are hard to see when the genetic background is not controlled (Bergelson and Purrington 1996, checked through papers that cite it). Costs also depend on the environment: a defence that costs little in a rich place may cost a lot in a poor one. For a simulation this is good news: costs can be modest and still matter if the environment is sometimes poor.

### 3.3 Life-history trade-offs

The classic set, all with solid evidence and all used in this simulator already or easy to add:

- **Reproduction against survival** (Cole 1954, Williams 1966, Reznick 1985). Costly reproduction shortens life.
- **Repair against reproduction** (the disposable soma theory, Kirkwood 1977). Built as `somatic_maint` against fertility and birth cost.
- **Offspring size against number** (Smith and Fretwell 1974). Built for plants as `seed_provision` against `seed_clutch`.
- **Fast against slow pace of life.** Species line up along one axis: fast growth, early maturity, many offspring, short life against slow growth, late maturity, few offspring, long life. Behaviour lines up too: bolder, more aggressive individuals tend to sit at the fast end (the "pace-of-life syndrome", Reale and others 2010). A good set of pairwise couplings should make this axis appear by itself; it should not be coded as two archetypes.
- **Expensive tissue.** Brain and gut compete for the same energy (Aiello and Wheeler 1995): animals with big brains have smaller guts. A shared metabolic ceiling would produce this without a special rule.

## 4. How genes interact

### 4.1 Pleiotropy

Most genes affect several traits, and the more traits one gene touches, the more of its mutations are harmful, because a change that helps one trait usually hurts another. Fisher's geometric model (1930) and Orr's "cost of complexity" (2000) say that adaptation is slower for organisms whose genes are more pleiotropic. Practical consequence: the most pleiotropic genes (here `size`) should change in small steps, and big jumps should be rare. The simulator's position-biased mutation already does this per gene; the number of traits a gene feeds could set the step automatically.

### 4.2 Epistasis

Types: magnitude epistasis (one gene changes how big another's effect is), sign epistasis (one gene flips the sign of another's effect), and diminishing returns. Two points for a design:

- **Magnitude epistasis is what the modifier clusters already do.** `litter_capacity` (fertility scaled by size and recovery) is a good model.
- **Diminishing returns is the cheapest balancer there is.** If two genes protect against the same thing (taste to avoid poison, resistance to survive it), the combined protection is `1 - (1 - a)(1 - b)`, not `a + b`. Doubling up gives less than twice the protection but costs twice as much, so selection spreads the effort instead of maxing both.
- **Compensation.** A harmful change in one gene can be repaired by a change in another. This makes the genome tolerant of mutation and is why populations carry hidden variation. It needs no special rule in a simulation; it appears when two genes feed one trait.

### 4.3 Linkage and supergenes

Genes that sit close together on a chromosome are inherited together. Natural selection can favour keeping a set of co-adapted alleles together, and the tool is suppressed recombination, often by an inversion. These blocks are called **supergenes**. Examples: mimicry patterns in *Heliconius* butterflies, the S-locus of primroses, social type in ants (all from memory). The simulator's gene clusters and `crossover_linked` are the right model; no more is needed unless the owner wants clusters to be inherited as blocks (`cluster_units`, built but off).

A caution: many reported growth-versus-defence "trade-offs" may be linkage and not pleiotropy, and the two are hard to tell apart when genes are close (noted in recent reviews of plant defence costs, checked). A simulation can tell them apart exactly, which is a feature: it can state which one a given coupling is.

### 4.4 Dominance and mutation-selection balance

Most new mutations are harmful and partly recessive, so they hide in heterozygotes and are removed slowly. The balance between new harmful mutations and their removal (mutation-selection balance) sets how much variation a population carries. In a diploid simulation this appears automatically.

## 5. Keeping variation alive: balancing selection

Without something extra, selection removes variation and the population converges on one genotype. The real mechanisms:

| Mechanism | How it works | Example | Simulator relevance |
| --- | --- | --- | --- |
| Heterozygote advantage (overdominance) | The mixed genotype beats both pure ones | Sickle-cell and malaria (Allison 1954) | Possible with the dominance model; needs a gene with an optimum in the middle, so low priority |
| Negative frequency dependence | A type does worse the more common it is | Rare prey are overlooked because predators form a search image; rare host types escape parasites that adapted to the common ones (Red Queen); Janzen-Connell effects around adult trees; Fisher's sex ratio | **The most useful one.** It appears whenever the other species adapts to the common type, so it needs matching, not only strength (see 8.2) |
| Spatial variation | Different places favour different genotypes, with migration between them | Clines in white clover cyanogenesis (see 6.4) | Needs a world that is not uniform (patchy soil, light, grazing) |
| Temporal variation | The best genotype changes with the season or the year | Beak size of Galapagos finches after droughts (Grant and Grant; memory) | Needs seasons or events; a world task |
| Mutation-selection balance | New harmful variants arrive as fast as they are removed | Genetic disease | Automatic |

Sex ratio is a clean example of negative frequency dependence (Fisher 1930): if one sex is rare, each of its members has more offspring, so selection pulls the ratio back to even. It works in the simulator as long as mating needs one of each sex and the sex is inherited, but a small population can still lose a sex by chance (a known quirk in [dna-and-traits.md](../design/dna-and-traits.md)).

## 6. Plants and what eats them

### 6.1 Defence theories

Plant ecology has four overlapping ideas about when a plant defends itself. All four predict the same thing: **defence is costly and is worth its cost only in some conditions.**

- **Optimal defence** (McKey 1974; memory): defend the most valuable and most exposed tissue most.
- **Growth-differentiation balance** (Herms and Mattson 1992; memory, the search did not return the paper): a plant either grows or builds defensive chemistry; the two compete for the same carbon. Anything that slows growth (shade, poor soil) shifts it toward defence.
- **Resource availability** (Coley, Bryant and Chapin 1985; memory): plants that grow fast in rich places are cheap to lose and so invest little in defence, while slow-growing plants in poor places invest heavily, because lost tissue takes long to replace. Long-lived leaves are tougher and better defended.
- **Apparency** (Feeny 1976; memory): big, long-lived, easy-to-find plants face more enemies and use defences that work against everything.

Together they give the **fast-soft-short against slow-tough-long** axis for plants. In this simulator `growth_rate`, `longevity` and (new) `toughness` can be coupled so that axis appears on its own.

### 6.2 Two kinds of defence

| | Qualitative | Quantitative |
| --- | --- | --- |
| Examples | Alkaloids, cardenolides, cyanogenic glycosides | Tannins, lignin, silica, tough leaves |
| Dose needed | Small | Large |
| Cost | Often cheap per unit, but must be kept | High, grows with tissue |
| Works against | Generalists. Specialists evolve resistance | Nearly everything |
| Resistance by the herbivore | Specific, and can be gained by one mutation | General: a better gut, bigger size, more time |

This matches the owner's two plant defences: `toxicity` is the qualitative one (animal `resistance` answers it) and `toughness` is the quantitative one (answered by the animal's digestion and size, not by resistance). The two should not be interchangeable.

### 6.3 Resistance and tolerance

Plants can **resist** (stop the herbivore) or **tolerate** (grow back after damage). Tolerance rests on stored reserves and buds, often belowground (Strauss and Agrawal 1999; memory). The two are usually traded against each other. This gives the dead `root_reach` gene a real job: roots hold the reserve a grazed plant regrows from, and they gather soil resources, and they cost shoot growth (the root-to-shoot allocation of Bloom, Chapin and Mooney 1985; memory).

### 6.4 Cyanogenesis in white clover: a worked example of a gene held in check

*Trifolium repens* is either cyanogenic (releases hydrogen cyanide when damaged) or not. Both types live together, and the proportion forms clines with temperature. Explanations that have been tested: cyanogenic plants are eaten less, but they cost resources to make and may suffer when frost damages the tissue and releases the cyanide inside the plant (checked). A direct freezing test found cyanogenic genotypes less freezing-tolerant across the species but not within polymorphic populations; other work links the polymorphism to drought stress and finds that herbivory does not explain the clines; a recent field experiment found that producing cyanogenic glycosides alone, without being able to release cyanide, still gave a fitness advantage (all checked, abstract level). The lesson is that **the same defence was held in check by several different costs and benefits at once, and which one dominates depends on the place.** That is the goal for the simulator's genes: a handful of couplings and an environment that is not uniform.

### 6.5 Seeds: size, number, dispersal and timing

- **Seed size against number.** The textbook compromise is many small seeds with little each against few large seeds with more (Smith and Fretwell 1974). Seed mass varies about 10^11-fold across species, so the compromise lands very differently in different plants (checked, Westoby and others). Bigger seeds give bigger seedlings with more reserves, which survive shade, drought and competition better; seed mass also affects where seeds go and how long they stay in the soil before germinating (checked, Moles and Leishman). A test of the colonisation idea (small seeds are better colonisers because there are more of them) was **not** supported in one community, and small-seeded species make more seeds per area of canopy per year but not more per plant over a lifetime (checked).
- **Dispersal.** Far dispersal lets seeds escape the parent's shade and the natural enemies that gather around it (Janzen 1970 and Connell 1971, memory), and escape crowding by siblings (Hamilton and May 1977, memory). It costs a structure or a food reward: wings, fruit flesh, or a fat reserve for the seed to be carried.
- **Germination time.** Development time scales with body mass to roughly the power 1/4 across species (the basic-traits note, [basic-traits.md](basic-traits.md), from West, Brown and Enquist). Larger-seeded and larger plants being slower to establish is reported in comparative work (memory, not verified here). Seeds that wait in the soil can be eaten or rot, so a longer wait is a **hazard**, and a bigger seed reserve survives it better.
- **Seed predation.** Seeds are eaten by animals before they sprout. This is a second reason a bigger reserve matters.

## 7. The animal side of toxins

### 7.1 Why animals cannot just eat more of everything

The **detoxification limitation hypothesis** (Freeland and Janzen 1974, memory) says a herbivore's intake of plants with secondary compounds is limited by how fast it can detoxify them, not by its stomach. Consequences that match the owner's resistance gene closely:

- Toxin is a **dose** (amount eaten times concentration, relative to body size), not an on/off property of the plant.
- The body has a **load** that builds as toxic food goes in and falls as the liver and kidneys clear it. Harm comes when the load is above what the body can handle.
- A better detox system (more enzyme, a less sensitive target) lets an animal eat **more** of a toxic plant per day before the limit, which is exactly "more resistance, more food eaten".
- Animals dilute toxins by mixing foods, and **avoid** the worst by taste and learning (the simulator's `taste` and brain). Avoidance and tolerance are substitutes; having a lot of both is wasteful.
- Time spent handling food is time not spent doing other things. **Handling time** is the standard cost in feeding models (Holling), and animals that choose among foods should prefer the one with the most energy per unit of handling time (optimal foraging, Stephens and Krebs; memory). If prey choice follows profitability, defended plants are eaten less, which is the plant's benefit from being tough.

### 7.2 Resistance is expensive, and in a different currency

Garter snakes (*Thamnophis*) that eat toxic newts have evolved resistance to tetrodotoxin through changes in a sodium channel. The resistance is heritable, varies among individuals and litters, and is highest where the toxic newts are (checked). It has a **locomotor cost**: snakes with the most resistant channel allele crawl more slowly, and the same allele lowers channel excitability, a pleiotropic effect (checked). The newts also pay an energy cost to make the toxin, so both sides of the arms race are paying (checked). The lesson for design: **resistance can be paid for in speed or handling, not only in upkeep**, which makes it a different kind of cost from the ones animals already carry.

### 7.3 Sequestration and warning signals

Monarch butterflies are largely insensitive to the cardenolides in milkweed because the target (the sodium pump) has changed so the toxin binds poorly. They store a subset of the toxins in their bodies, which makes them poisonous to predators (checked). Sequestration has costs: in one study of tropical milkweed, caterpillars that converted plant compounds into others carried a growth burden, and females laid more eggs on plants with intermediate toxin levels, a sign of a benefit-cost balance (checked). Other work found no cost of sequestration earlier, so the evidence is mixed (checked). Poisonous animals often advertise it (**aposematism**), and harmless species copy the signal (Batesian mimicry), which works only while the copy is rare (negative frequency dependence), while two poisonous species sharing a signal (Mullerian mimicry) both gain by it. For the simulator this means: an animal that eats toxic plants can become toxic itself, which links plant defence, animal resistance and "poisoned meat" in one chain.

## 8. Arms races

### 8.1 Red Queen and the life-dinner principle

Van Valen (1973) argued that species in close interaction must keep evolving just to stay where they are. Dawkins and Krebs (1979) added an asymmetry, the **life-dinner principle**: the rabbit runs for its life and the fox for its dinner, so selection on the prey side is stronger. Applied to plants and herbivores, an individual plant that is eaten loses everything; an individual herbivore that fails to eat one plant loses a meal. Escape-and-radiate coevolution between plants and insects (Ehrlich and Raven 1964; memory) is the large-scale version.

### 8.2 Matching versus strength

Two models of host-enemy genetics (Agrawal and Lively 2002; memory):

- **Inverse gene-for-gene, or "strength"**: a defence works against all enemies and a counter-defence defeats it. Selection pushes both to the maximum until costs stop them. There is no cycling.
- **Matching alleles**: a defence works only against enemies that do **not** carry the matching counter. Whichever type is common is the one the enemy adapts to, so the common type loses and the rare one gains. This gives sustained cycles and keeps many types alive. It is the typical model of host and parasite.

A scalar "toxicity" and a scalar "resistance" are the strength model. It still gives cycles if both are costly (an unused resistance is a cost with no gain and falls, then toxin without any resistance in the herbivores is easy to eat around), but the cycles are slow and the end state is one toxin level. A small categorical element (a toxin type and a resistance type, one digit each) would turn it into the matching model and keep several plant types alive. It would cost two digits and one more layout bump each.

### 8.3 Costs on both sides

Arms races end when the marginal cost of the next step exceeds its benefit. Real examples show costs on both sides: the newt pays to make toxin, the snake pays in speed (checked). Escalation theory (Vermeij; memory) adds that the strongest defences appear where enemies are strongest, and that the most expensive defences are found in the richest places.

## 9. Lessons for a simulation

1. **Every gene needs a cost and a reason not to be at either end.** A cost with no matching benefit sinks a gene to zero (it falls out of the population), and a benefit with no cost sends it to the maximum. Check both ends.
2. **Put costs in one currency, with a few in time or risk.** One energy store for upkeep and production; time (handling), risk (visibility) and speed for the rest. Resistance costing speed is the snake case.
3. **Use convex costs and saturating benefits.** A squared upkeep and a diminishing return give a stable middle. Linear against linear gives a corner.
4. **Link genes so that strategies emerge.** The fast-soft-short against slow-tough-long axis comes from a few pairwise links. It should not be coded as types.
5. **Make toxin a dose, not a flag.** Dose per unit eaten, a load that builds and decays, a threshold that scales with body size. This one mechanism gives resistance, "eat more", poisoned animals, sequestration and size effects with no more rules.
6. **Give defences two jobs, the way real ones do.** Toughness slows the eater and lowers the food value; toxin harms the eater. A defence that only slows eating is weaker than one that also pays the eater less.
7. **Keep avoidance, tolerance and escape as substitutes.** Taste, resistance and speed all reduce poisoning or predation; with diminishing returns between them, none is maxed.
8. **Frequency dependence needs matching.** Strength-only arms races end in a corner. A categorical element, or choice by profitability so that animals prefer the less defended plant, adds negative frequency dependence cheaply.
9. **Variation needs a varied world.** Uniform soil and a constant climate remove spatial and temporal balancing selection. Seasons and patchy fertility are world features, not gene features, and are listed as a proposal only.
10. **Test with the budget fixed.** The Y-model warns that population-wide correlations hide trade-offs. The balance audit in the design note varies one gene at a time with the rest at founder values.
11. **Say whether a coupling is pleiotropy or linkage.** In a simulation the difference is exact and worth recording.
12. **Do not expect costs to show everywhere.** Costs that vanish in some environments are realistic. Keep each cost modest and make sure at least one environment makes it bite.

## 10. Sources

Entries marked **checked** were found during this research (abstract or summary level). Entries marked **memory** are from memory; check them before citing.

| Topic | Source | Status |
| --- | --- | --- |
| Costs of resistance in plants | Bergelson and Purrington 1996, Surveying patterns in the cost of resistance in plants, *American Naturalist* 148:536-558; and later reviews of resistance costs ([Costs of resistance in plants: from theory to evidence](https://pure.sruc.ac.uk/en/publications/costs-of-resistance-in-plants-from-theory-to-evidence/)) | checked (through citing papers) |
| Garter snake resistance to newt toxin and its cost | Work from the Brodie group on *Thamnophis sirtalis* and *Taricha* (authors and years not confirmed here); [an article in Evolution 44(3):651](https://academic.oup.com/evolut/article/44/3/651/6869754); [PMC2265765](https://pmc.ncbi.nlm.nih.gov/articles/PMC2265765); [locomotor cost dataset](https://datadryad.org/dataset/doi:10.5061/dryad.7f1h767); [Berkeley Evolution 101 on coevolution](https://evolution.berkeley.edu/biological-warfare-and-the-coevolutionary-arms-race/is-it-coevolution) | checked |
| Monarch insensitivity and sequestration | [Danainae sodium pump evolution](https://researchwith.montclair.edu/en/publications/the-evolution-of-cardenolide-resistant-forms-of-na-supsupk-supsup/); [Cardenolides, toxicity, and the costs of sequestration](https://hal.univ-antilles.fr/hal-03217023v1) | checked |
| White clover cyanogenesis | Kooyers and Olsen 2008 (freezing); [urban and drought studies](https://pmc.ncbi.nlm.nih.gov/articles/PMC5204167); [field experiment on drought, herbivory and climate](https://www.biorxiv.org/content/10.1101/2025.03.07.642096.full.pdf) | checked |
| Seed size, number, dispersal, germination | Westoby, Jurado and Leishman; [Moles, Leishman and Fenner](https://www.cef-cfr.ca/uploads/Membres/MolesLeishmanFenner08.pdf); [Small-seeded species produce more seeds per square metre of canopy](https://researchers.mq.edu.au/en/publications/small-seeded-species-produce-more-seeds-per-square-metre-of-canop/) | checked |
| Antagonistic pleiotropy | Williams 1957, *Evolution* 11:398 | memory |
| Offspring size and number | Smith and Fretwell 1974, *American Naturalist* 108:499 | memory |
| Trade-offs and the Y-model | Stearns 1989; van Noordwijk and de Jong 1986; Roff and Fairbairn | memory |
| Fisher's geometric model, cost of complexity | Fisher 1930; Orr 2000, *Evolution* 54:13 | memory |
| Disposable soma | Kirkwood 1977, *Nature* 270:301 | memory |
| Pace-of-life syndrome | Reale and others 2010, *Phil Trans R Soc B* 365:4051 | memory |
| Expensive tissue | Aiello and Wheeler 1995, *Current Anthropology* 36:199 | memory |
| Sickle-cell and malaria | Allison 1954 | memory |
| Plant defence theories | McKey 1974; Feeny 1976; Coley, Bryant and Chapin 1985, *Science* 230:895; Herms and Mattson 1992, *Quarterly Review of Biology* 67:283 | memory |
| Tolerance and resistance | Strauss and Agrawal 1999, *Trends in Ecology and Evolution* 14:179 | memory |
| Root-to-shoot allocation | Bloom, Chapin and Mooney 1985, *Annual Review of Ecology and Systematics* 16:363 | memory |
| Detoxification limitation | Freeland and Janzen 1974, *American Naturalist* 108:269 | memory |
| Foraging and handling time | Holling 1959; Stephens and Krebs 1986 | memory |
| Red Queen and life-dinner principle | Van Valen 1973; Dawkins and Krebs 1979 | memory |
| Plant-insect coevolution | Ehrlich and Raven 1964, *Evolution* 18:586 | memory |
| Gene-for-gene and matching alleles | Agrawal and Lively 2002, *Evolutionary Ecology Research* 4:79 | memory |
| Dispersal and enemy escape | Janzen 1970; Connell 1971; Hamilton and May 1977 | memory |
| Mimicry | Bates 1862; Muller 1879 | memory |
| Allometry of development time | West, Brown and Enquist 2001, *Nature* 413:628 (via [basic-traits.md](basic-traits.md)) | memory |
