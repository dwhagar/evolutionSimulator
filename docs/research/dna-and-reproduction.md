# DNA and reproduction: how real organisms exchange and vary DNA

Research note for the DNA object. Written 2026-10-14 by the Research 1 thread.

**Purpose.** Summarise how real reproduction copies, mixes and changes DNA, and turn that into
concrete options and defaults for the simulator. It is the input for the scaffolding of the DNA
object. Life-form traits are covered separately (Research 2); this note only says what the DNA
side must provide so traits can be attached to it.

**Status.** Draft. Open questions are tracked as GitHub issues (listed at the end), each with a
recommended default so work can continue before they are answered. Prototype Python files from
the owner have not arrived yet and will be folded in when they do.

**Confidence.** The biology here is textbook material. Numeric rates are order-of-magnitude
figures for orientation, not values to copy; the simulation will use scaled-down rates anyway
(see [Parameter table](#parameter-table-scaled-for-a-simulation)).

## Contents

1. [Summary and recommendations](#summary-and-recommendations)
2. [DNA in one page](#dna-in-one-page)
3. [Mutation types](#mutation-types)
4. [Asexual reproduction](#asexual-reproduction)
5. [Sexual reproduction and meiosis](#sexual-reproduction-and-meiosis)
6. [Ploidy and dominance](#ploidy-and-dominance)
7. [Costs and benefits of sex](#costs-and-benefits-of-sex)
8. [Choosing an abstraction level](#choosing-an-abstraction-level)
9. [Variable-length genomes](#variable-length-genomes)
10. [Proposed operators](#proposed-operators)
11. [Parameter table (scaled for a simulation)](#parameter-table-scaled-for-a-simulation)
12. [What the DNA object must provide](#what-the-dna-object-must-provide)
13. [Open questions](#open-questions)
14. [Sources](#sources)

## Summary and recommendations

- Real heredity has three sources of variation: **mutation** (new changes to the sequence),
  **recombination** (shuffling existing variation between chromosomes inside one meiosis), and
  **mixing of parents** (fertilisation combines a gamete from each parent). Asexual organisms
  only have the first; sexual organisms have all three.
- Most mutations are neutral or harmful and a few are helpful. A simulator needs a mutation
  step that is mostly small and local, with rare larger events (insertions, deletions,
  duplications). A mutation rate that is too high destroys good genomes ("error catastrophe");
  too low and nothing adapts.
- Sexual reproduction is modelled well by two operators: **meiosis** (make one gamete from one
  parent: independent assortment of chromosomes plus a few crossovers within each chromosome)
  and **fertilisation** (join two gametes). Textbook GA "one-point" and "uniform" crossover are
  simplified versions of the same idea and are useful for haploid genomes.
- Recommended starting design (each point is an open issue with this as the default):
  1. **Gene-level genome** with a stable ID per gene slot: an ordered list of chromosomes, each
     an ordered list of genes ([#2](https://github.com/dwhagar/evolutionSimulator/issues/2)).
  2. **Diploid** (two copies of every chromosome) with a per-gene dominance setting; haploid
     available as a configuration ([#3](https://github.com/dwhagar/evolutionSimulator/issues/3)).
  3. **One `reproduce` interface** with two paths, clone-plus-mutate for one parent and
     meiosis-plus-fertilisation-plus-mutate for two
     ([#4](https://github.com/dwhagar/evolutionSimulator/issues/4)).
  4. **Fixed number of gene slots** at first, with stable gene IDs reserved so duplication and
     deletion can be added later ([#5](https://github.com/dwhagar/evolutionSimulator/issues/5)).
  5. Every random operation takes an injected `random.Random` so runs are reproducible.

## DNA in one page

- **Molecule.** DNA is two strands of a sequence over four bases (A, C, G, T) that pair A-T and
  C-G. The sequence on one strand determines the other, which is what makes copying possible:
  separate the strands and rebuild each partner.
- **Genes and the genetic code.** A gene is a stretch of sequence that is transcribed to RNA and
  usually translated to a protein. Translation reads the sequence in three-base **codons**; 64
  codons map to 20 amino acids plus stop signals, so the code is redundant (several codons per
  amino acid). That redundancy is why some mutations change nothing.
- **Most DNA is not genes.** In humans only a few percent codes for protein; the rest includes
  regulatory regions (switches that control when and how much a gene is used), repeats and
  structural sequence. A single regulatory change can alter a trait as much as a protein change.
- **Chromosomes and genome.** The genome is split into chromosomes (humans 23 pairs, fruit
  flies 4, many bacteria one circular chromosome). A gene's position on a chromosome is its
  **locus**; the versions that can occupy a locus are its **alleles**.
- **Genotype to phenotype.** The genotype (sequence) does not directly set the phenotype
  (observable traits). Genes interact with each other and with the environment. Two patterns
  matter for the trait design:
  - **Pleiotropy:** one gene affects several traits.
  - **Polygeny:** one trait is shaped by many genes (height, skin colour), which gives smooth,
    bell-curve-like variation rather than discrete types.
- **Ploidy.** Haploid organisms carry one copy of each chromosome; diploid organisms carry two
  (one inherited from each parent). Some plants and fish carry more (polyploid).

## Mutation types

Mutation is any heritable change to the sequence. In real organisms the source is mostly
copying errors during DNA replication and unrepaired damage, plus occasional larger rearrangements.

### Small-scale changes

| Type | What happens | Typical effect | Simulation analogue |
| --- | --- | --- | --- |
| Substitution (point mutation) | One base replaced by another | Often neutral; can change one amino acid | Change one base, or nudge one numeric value |
| Synonymous substitution | New codon, same amino acid | Usually neutral | Change that does not alter the trait |
| Missense substitution | New codon, different amino acid | Mild to severe | Small change to a trait value |
| Nonsense substitution | Codon becomes a stop | Usually severe (truncated protein) | Gene switched off |
| Insertion / deletion (indel) | A few bases added or removed | If not a multiple of 3 it shifts the reading frame ("frameshift") and usually breaks the gene | Add or remove a short run in a gene; rare |
| Regulatory change | Substitution or indel in a switch region | Changes expression level or timing | Scale a gene's effect up or down |

Substitutions are not uniform. **Transitions** (A↔G, C↔T) happen roughly twice as often as
**transversions** (purine↔pyrimidine), a ratio usually called ts/tv. Certain sites are
**mutational hotspots** (for example methylated CpG sites mutate much faster). Both are optional
realism for a simulator.

### Structural changes

| Type | What happens | Notes |
| --- | --- | --- |
| Gene or segment duplication | A section is copied, giving two copies | Main route to new genes: one copy keeps the old job and the other is free to change |
| Deletion of a segment | A section is lost | Often harmful; sometimes tolerated if a duplicate exists |
| Inversion | A section is flipped end to end | Suppresses recombination inside the flipped region, so it keeps gene combinations together |
| Translocation | A section moves to another chromosome | Can cause sterility in hybrids and drives speciation |
| Transposition | A mobile element copies or moves itself | A large share of many genomes (about half of the human genome is derived from such elements) |
| Whole-genome duplication | Ploidy doubles | Common in plants; a rare but powerful event |
| Aneuploidy | A chromosome is gained or lost in meiosis | Usually lethal or damaging in animals |

### How often, and with what effect

- Order of magnitude: about 1 in 100 million bases per generation in humans (roughly 1.2 × 10⁻⁸
  per base per generation, around 60 to 70 new point mutations per child), about 10⁻⁹ to 10⁻¹⁰
  per base per replication in bacteria, and higher again in RNA viruses (about 10⁻⁴ to 10⁻⁶ per
  base). **Drake's rule** is the observation that, across DNA microbes, the rate per *genome*
  per replication is roughly constant (about 0.003), so organisms with bigger genomes evolve
  lower per-base rates.
- In humans the paternal germline contributes about three to four times as many new mutations as
  the maternal one, rising with the father's age, because sperm cells go through many more cell
  divisions.
- The **distribution of fitness effects** is the key shape for a simulator: most new mutations
  are neutral or slightly harmful, a smaller share strongly harmful or lethal, and only a very
  small share beneficial. A common simplification is that effects are roughly exponential or
  gamma-distributed with a heavy tail on the harmful side.
- **Mutation-selection balance:** harmful mutations keep arriving and selection keeps removing
  them, so populations carry a steady load of mildly harmful variants.
- **Error catastrophe:** above a threshold mutation rate (relative to genome length) selection
  can no longer hold the best sequence, and the population drifts into worse genomes. Keep the
  default per-genome rate low, on the order of one change per organism per generation or less.
- Mutation rates are themselves evolvable. Some lineages evolve higher rates when conditions
  change, and some genes mutate faster than others. Evolvable rates are a possible later
  extension and need no support from the first version except that the rate should be a
  per-organism or per-gene parameter, not a global constant.

## Asexual reproduction

One parent, no mixing. Examples: binary fission in bacteria, budding in yeast and hydra,
fragmentation, spore formation, and parthenogenesis in some insects and lizards.

- **Copy fidelity.** The child is a copy of the parent apart from replication errors. Variation
  between individuals comes only from mutation.
- **Consequences.**
  - Good combinations of genes are preserved intact, so a lineage can multiply quickly once
    adapted.
  - Beneficial mutations that arise in different lineages cannot be brought together unless one
    lineage acquires both in sequence ("clonal interference": two lineages with different
    beneficial mutations compete instead of combining).
  - Harmful mutations accumulate in a lineage that has no way to remove them. **Muller's
    ratchet** is the click-by-click loss of the least-mutated class in small asexual populations.
  - No cost of finding a mate, and no cost of making males (see
    [Costs and benefits of sex](#costs-and-benefits-of-sex)).
- **Horizontal gene transfer (HGT).** Bacteria are asexual but still swap DNA by three routes:
  *conjugation* (a plasmid passes through a physical bridge), *transformation* (taking up free
  DNA from the environment), and *transduction* (a virus carries DNA between cells). This is
  mixing without reproduction, and it spreads traits such as antibiotic resistance. It is a
  candidate later feature: "an organism may copy a gene from a neighbour" is a small operator.
- **Facultative sex.** Many species switch: aphids and water fleas clone while conditions are
  good and reproduce sexually when conditions worsen. This is a ready-made behaviour for a
  simulator that supports both modes.

## Sexual reproduction and meiosis

Two parents each contribute a **gamete** (egg or sperm in animals) that carries half of the
parent's genome. Fertilisation fuses two gametes into a zygote with a full set again.

### Meiosis step by step

Meiosis is the cell-division process that makes gametes. It is the source of nearly all the
recombination in a sexual species.

1. **Replication.** The cell copies each chromosome, so every chromosome now consists of two
   identical sister chromatids.
2. **Pairing (prophase I).** Homologous chromosomes (the maternal and the paternal copy of the
   same chromosome) find each other and line up gene for gene.
3. **Crossing over (prophase I).** Programmed double-strand breaks are made and repaired using
   the homolog, producing crossovers where chromatids from the two homologs swap sections.
   Visible crossovers are called **chiasmata**. This is *recombination*.
4. **Independent assortment (metaphase / anaphase I).** The homologous pairs split, and for each
   pair the maternal or paternal chromosome goes to a given daughter cell at random,
   independently of the other pairs.
5. **Second division (meiosis II).** Sister chromatids separate, giving four haploid cells.
6. **Fertilisation.** Two gametes fuse, restoring the diploid number.

### What each step does to variation

- **Independent assortment** alone gives 2ⁿ distinct gametes for n chromosome pairs (about 8
  million for humans, n = 23) before any crossover. Genes on different chromosomes assort
  independently (Mendel's second law).
- **Crossover** shuffles genes on the same chromosome. Genes that are close together are rarely
  separated (they are *linked*), and genes far apart are separated about half the time and
  behave as if unlinked. The map distance of 1 centimorgan is a 1% chance of a crossover between
  two loci per meiosis.
- **Number of crossovers.** Typically at least one per chromosome (needed to hold homologs
  together and segregate them correctly, the "obligate crossover"), and usually one to three on
  most chromosomes. In humans, about 25 to 40 crossovers per meiosis in total, with somewhat
  more in females than males. Crossovers repel each other (**interference**), so they are more
  evenly spaced than a random scatter would give.
- **Hotspots.** In many species crossovers cluster at specific places (in mammals, set by a
  protein called PRDM9), so the chance of a crossover is not uniform along the chromosome.
- **Unequal crossing over.** If the homologs misalign, a crossover can create a duplication on
  one chromatid and a deletion on the other, which is a route to structural change.
- **Gene conversion.** Repairing a break can copy a short stretch from one homolog onto the
  other without a full crossover, so an allele is overwritten. It is a small effect and optional.
- **Segregation errors.** Occasionally a pair fails to separate and the gamete has too many or
  too few chromosomes (aneuploidy). Ignore in a first version.

### Mendelian inheritance

For a single gene with two alleles in a diploid species, a heterozygote (A/a) produces A and a
gametes in equal numbers. Crossing two heterozygotes gives genotypes in 1:2:1 (AA : Aa : aa),
and phenotypes in 3:1 if A is fully dominant. This falls out of the meiosis model above with no
special casing and is a good unit test for any implementation.

### Other sexual systems worth knowing

- **Sex determination.** Mammals use XY (males carry one X and one Y, whose genes barely
  recombine). Birds use ZW. Some reptiles determine sex by temperature. Many species, including
  most fungi and protists, have mating types rather than two sexes. A simulator may skip sexes
  entirely and let any two individuals mate.
- **Life cycles.** In animals the diploid phase dominates and the haploid phase is only the
  gametes. Plants and algae alternate between a multicellular haploid and a multicellular diploid
  phase. A simulator should treat "make a gamete" and "fuse gametes" as separate steps so either
  cycle can be built.
- **Selfing and inbreeding.** Mating with oneself or a relative increases homozygosity, which
  exposes recessive harmful alleles ("inbreeding depression"). Mate choice and population size
  both affect it.
- **Hybrids and speciation.** When two groups drift apart, their offspring may be less fit
  (incompatible gene combinations, or chromosome rearrangements that disrupt meiosis). A simple
  proxy is to measure genetic distance between parents and reduce fertility beyond a threshold.

## Ploidy and dominance

- **Diploid advantages.** A second copy masks recessive harmful mutations, keeps hidden variation
  in the population, allows heterozygote advantage (sickle-cell trait in malaria regions is the
  standard example), and gives meiosis a real homologous pair to work on.
- **Haploid advantages.** Half the data, no dominance rules, and every mutation is exposed to
  selection immediately, so adaptation is fast and purging is efficient.
- **Dominance models** for numeric traits, in increasing complexity:
  1. *Additive / codominant:* the phenotype contribution is the mean (or sum) of the two alleles.
  2. *Complete dominance:* a gene has a dominant and recessive allele and the dominant one wins.
  3. *Per-gene dominance coefficient* `h` between 0 and 1: heterozygote value = recessive +
     h × (dominant − recessive). Covers the first two as `h = 0.5` and `h = 1`.
- **Recommendation.** A per-gene dominance coefficient `h` defaulting to 0.5. It costs one number
  per gene and keeps haploid, codominant and dominant cases inside one model (a haploid genome
  is a diploid one where both copies are the same object).

## Costs and benefits of sex

Sex is expensive, yet nearly universal in complex organisms, which has produced a large body of
theory. The points below are the ones that change simulator behaviour.

- **Twofold cost.** A sexual female passes only half her genome to each child while an asexual
  one passes all of it. In a species with males that do not feed offspring, asexual mutants
  should outbreed sexual females about two to one. Whether the simulator shows this depends on
  whether it models sexes at all; without distinct sexes the cost is largely absent.
- **Benefits.**
  - Brings together beneficial mutations from different lineages (Fisher-Muller).
  - Slows Muller's ratchet because recombination can rebuild a mutation-free chromosome.
  - **Red Queen hypothesis:** parasites adapt to common genotypes, so rare genotypes (made by
    shuffling) are favoured, which keeps sex worthwhile. Needs a parasite model to appear.
  - Lets selection act on each gene separately by breaking up linkage (the Hill-Robertson effect:
    in linked asexual genomes selection on one gene interferes with selection on its neighbours).
- **Practical expectation.** In a stable environment with simple selection, asexual populations
  often do as well or better. Sex shines in changing environments, with many interacting genes
  and with parasites or competition that favours novelty. If the simulator offers both modes, the
  environment model matters as much as the reproduction code for what the user sees.

## Choosing an abstraction level

Three levels of detail are plausible. They differ in how much real genetics they reproduce and
in how much code and runtime they cost.

| Level | Genome is | Mutation | Recombination | Cost | Fidelity |
| --- | --- | --- | --- | --- | --- |
| A. Vector | A list of numbers (one per trait) | Add Gaussian noise or flip a flag | Uniform or one-point crossover | Lowest | Low: no genes, no linkage, no structural change |
| B. Gene-level | Chromosomes of gene slots; each gene holds an allele (a number or short sequence) plus metadata (ID, dominance, mutation rate) | Per-gene value change, rare duplication/deletion/loss of function | Meiosis with crossovers between gene slots | Medium | Good: linkage, dominance, hidden variation, hotspots |
| C. Sequence | Real A/C/G/T strings read through a codon table | Base substitutions, indels, frameshifts | Meiosis with crossovers at base positions | Highest | Highest: realistic mutation spectrum and structural events, but needs a gene finder and a sequence-to-trait layer |

**Recommendation: B, designed so C can be reached later.** Give each gene slot an ID and a
small value type, so a gene can be a number now and a base string later without changing
crossover. Use A-style numeric mutation for values that are numbers (Gaussian step, clipped) and
reserve A/C/G/T substitution for sequence-valued genes. This tracks
[#2](https://github.com/dwhagar/evolutionSimulator/issues/2).

## Variable-length genomes

If genomes can grow or shrink, the two parents' chromosomes no longer line up index by index.
Real chromosomes align by shared sequence, which the simulator can emulate cheaply:

- Give every gene a **stable ID** (an integer assigned when it first appears, copied on
  duplication with a new ID or a "paralog of" link).
- Align parents by ID. Where one parent lacks a gene, treat it as a deletion allele (null).
- Place crossover points *between* aligned genes, not at raw list indices.
- Handle a duplicate carefully: unequal crossing over is the mechanism that makes duplications
  and deletions in real life, so allowing it is realistic, but it is also the largest source of
  bugs in simple implementations. Leave it out of the first version.

Start with fixed gene slots and stable IDs ([#5](https://github.com/dwhagar/evolutionSimulator/issues/5)).
Duplication, deletion and gene birth can then be added as pure mutation operators that edit the
slot list and nothing else.

## Proposed operators

These are reference definitions, not final API. The sketch below was run once to check it
behaves (crossover count, lengths preserved, deterministic with a seed). It uses base strings at
sequence level; for gene-level use replace "base" with "allele" and drop the transition model.

```python
from __future__ import annotations

import random

BASES = "ACGT"
TRANSITION = {"A": "G", "G": "A", "C": "T", "T": "C"}

# A chromosome is a list of loci; each locus holds one allele (a base here, or a number).
Chromosome = list


def point_mutate(chrom: Chromosome, rate: float, rng: random.Random,
                 ts_tv_ratio: float = 2.0) -> Chromosome:
    """Per-locus substitution. Transitions are favoured over transversions."""
    out = list(chrom)
    p_transition = ts_tv_ratio / (ts_tv_ratio + 1.0)
    for i, base in enumerate(out):
        if rng.random() < rate:
            if rng.random() < p_transition:
                out[i] = TRANSITION[base]
            else:
                out[i] = rng.choice([b for b in BASES if b not in (base, TRANSITION[base])])
    return out


def indel_mutate(chrom: Chromosome, rate: float, rng: random.Random,
                 max_len: int = 3) -> Chromosome:
    """Insert or delete a short run at random positions (rate ~ 1/10 of substitutions)."""
    out = list(chrom)
    i = 0
    while i < len(out):
        if rng.random() < rate:
            n = rng.randint(1, max_len)
            if rng.random() < 0.5:
                del out[i:i + n]
            else:
                out[i:i] = [rng.choice(BASES) for _ in range(n)]
                i += n
        i += 1
    return out


def one_point_crossover(a: Chromosome, b: Chromosome, rng: random.Random):
    """Classic GA crossover for haploid parents: swap tails after one random cut."""
    cut = rng.randint(1, min(len(a), len(b)) - 1)
    return a[:cut] + b[cut:], b[:cut] + a[cut:]


def uniform_crossover(a: Chromosome, b: Chromosome, rng: random.Random, p: float = 0.5):
    """Classic GA crossover for haploid parents: swap each locus independently."""
    c1, c2 = [], []
    for x, y in zip(a, b):
        if rng.random() < p:
            x, y = y, x
        c1.append(x)
        c2.append(y)
    return c1, c2


def meiotic_recombine(a: Chromosome, b: Chromosome, rng: random.Random,
                      mean_crossovers: float = 1.0) -> Chromosome:
    """One gamete chromosome from a homologous pair. Crossover points are a Poisson
    process along the chromosome; the starting homolog is chosen at random."""
    n = len(a)
    t = rng.expovariate(mean_crossovers) if mean_crossovers > 0 else 2.0
    points = []
    while t < 1.0:
        points.append(int(t * n))
        t += rng.expovariate(mean_crossovers)
    points = sorted({p for p in points if 0 < p < n})
    src, other = (a, b) if rng.random() < 0.5 else (b, a)
    out, prev = [], 0
    for p in points + [n]:
        out.extend(src[prev:p])
        src, other = other, src
        prev = p
    return out


def make_gamete(genome: list[tuple[Chromosome, Chromosome]], rng: random.Random,
                mean_crossovers: float = 1.0) -> list[Chromosome]:
    """Independent assortment: each homologous pair contributes one recombined chromosome."""
    return [meiotic_recombine(m, p, rng, mean_crossovers) for m, p in genome]
```

Notes on the choices:

- `meiotic_recombine` is the main operator. Setting `mean_crossovers` to 0 gives pure independent
  assortment, and larger values give more shuffling. A Poisson process has no interference; to add
  it, space crossovers with a gamma distribution (shape above 1) instead of exponential gaps.
- `one_point_crossover` and `uniform_crossover` are for comparison and for a haploid mode. They
  have known biases: one-point keeps adjacent genes together (positional bias) and can never
  separate genes at opposite ends from keeping each other apart, while uniform treats all genes as
  unlinked.
- Fertilisation is just "take one gamete from each parent": the child's chromosome pair *i* is
  `(gamete_from_parent1[i], gamete_from_parent2[i])`. For a haploid mode, skip pairs and use
  `one_point_crossover` or `uniform_crossover` on the two parents directly.
- Mutation is applied to the gamete (after recombination), which mirrors biology where most
  mutations arise during gamete formation. Apply it per parent so the paternal bias can be added
  later by giving the two parents different rates.
- Mutation rate is best defined **per gene or per base per generation**, and the simulation
  should derive per-organism expectations from that. A fixed per-organism probability would
  silently change meaning when genome size changes.
- All functions return new lists and never edit their inputs, so a parent's genome stays valid
  after it reproduces.

## Parameter table (scaled for a simulation)

Real rates (about 10⁻⁸ per base) would give essentially no variation in a simulation with a few
hundred genes and a few hundred individuals, so values are scaled up so that the *expected number
of changes per organism per generation* is meaningful. The columns give the real range and a
starting default for a gene-level genome of 10 to 100 genes; all are meant to be configurable.

| Parameter | Real organisms | Suggested default | Notes |
| --- | --- | --- | --- |
| Point-mutation rate | ~10⁻⁸ per base per generation (humans); ~10⁻¹⁰ per base per division (bacteria) | 0.005 per gene per generation (about 0.05 to 0.5 changes per organism) | Keep expected changes per organism at or below about 1 |
| Mutation step size (numeric allele) | n/a | Gaussian, σ = 5% of the allowed range, clipped | Smaller steps for conservative traits |
| Indel / structural rate | ~1/10 of substitutions; duplication and deletion rarer still | 0 in the first version; later ~10% of the point rate | Gated behind variable-length support |
| Loss-of-function (gene switched off) | A few percent of mutations | 2% of mutation events | Optional |
| Beneficial fraction | Well under 1% of mutations; context dependent | Not hard coded; emerges from the environment | Do not bake in a "good mutation" probability |
| Crossovers per chromosome | 1 to 3, at least 1 (obligate) | Mean 1 | Use 0 to test independent assortment |
| Crossover interference | Strong in most species | Off at first | Gamma-spaced points if wanted |
| Chromosomes | 23 pairs (human), 4 (fly), 1 (bacteria) | 2 to 8 pairs | Genes spread across chromosomes so linkage is observable |
| Ploidy | 1 or 2 (sometimes more) | 2, with haploid option | See [#3](https://github.com/dwhagar/evolutionSimulator/issues/3) |
| Dominance coefficient `h` | Varies per gene; many harmful alleles are recessive (`h` near 0.1) | 0.5 | Per gene |
| Paternal mutation bias | 3 to 4 times maternal in humans | 1 (equal) | Only matters with distinct sexes |
| Mating | Any compatible pair, or by mate choice | Any two organisms | See [#4](https://github.com/dwhagar/evolutionSimulator/issues/4) |
| Horizontal gene transfer | Common in bacteria | Off | Later, small operator |

## What the DNA object must provide

Requirements the scaffolding should satisfy. Items marked *later* should not be built yet but
must not be designed out.

**Data model**

- `Genome` is an ordered collection of `Chromosome` objects; each `Chromosome` is an ordered
  sequence of genes. For diploid organisms a genome holds homologous chromosome *pairs*.
- Each gene has a **stable ID**, an **allele value** (number now, sequence *later*), and optional
  metadata: dominance coefficient, per-gene mutation rate, chromosome and position.
- Genomes are **immutable values** or are copied on reproduction; reproduction must never
  modify a parent.
- Equality and a **distance function** (for example, the fraction of genes that differ, or the
  summed absolute difference of numeric alleles) for species, speciation and mate-compatibility
  checks.

**Operations**

- `mutate(genome, rates, rng) -> Genome`
- `make_gamete(genome, rng, params) -> Gamete` (haploid set of chromosomes, one per pair, after
  recombination)
- `fertilise(gamete_a, gamete_b) -> Genome`
- `clone(genome) -> Genome` (asexual path, followed by `mutate`)
- `reproduce(*parents, rng, params) -> Genome` as the single entry point: one parent clones,
  two parents recombine.
- Serialise and deserialise (JSON-friendly) so runs and populations can be saved and compared.

**Interface with traits (Research 2)**

- The DNA object exposes `genome.get_allele(gene_id)` or an iterator over genes and does *not*
  know about traits. A separate **gene-to-trait map** reads alleles and produces the phenotype,
  so pleiotropy (one gene, several traits) and polygeny (several genes, one trait) are both
  expressible. For a diploid genome the mapping receives both alleles and the dominance
  coefficient.
- Traits state which gene IDs they depend on; DNA never encodes trait names.
- Trait ranges and trait mutation step sizes should be supplied by the trait definitions
  (for example, `step = 0.05 × (max − min)`), not hard coded in DNA.

**Engineering conventions**

- Every random choice takes an injected `random.Random` (no module-level `random`); seeds
  reproduce a run exactly.
- Operators are pure functions returning new objects, easy to unit test.
- Tests worth writing from the start: Mendelian 1:2:1 ratio of offspring from a heterozygote
  cross; `mean_crossovers = 0` gives pure independent assortment; offspring genome length equals
  parent length for fixed-length genomes; zero mutation rate means a clone equals its parent;
  same seed gives the same offspring; a parent is unchanged after reproduction.

## Open questions

Tracked as GitHub issues so they can be answered there. Each lists a recommended default that
this note and the first scaffolding will assume until answered.

| Question | Issue | Default |
| --- | --- | --- |
| Level of detail of the genome (vector, gene-level, sequence) | [#2](https://github.com/dwhagar/evolutionSimulator/issues/2) | Gene-level |
| Haploid or diploid | [#3](https://github.com/dwhagar/evolutionSimulator/issues/3) | Diploid with haploid option |
| Asexual, sexual or both; distinct sexes | [#4](https://github.com/dwhagar/evolutionSimulator/issues/4) | Both modes, no sexes |
| Fixed or variable length genomes | [#5](https://github.com/dwhagar/evolutionSimulator/issues/5) | Fixed, with stable gene IDs |

Prototype Python files from the owner are expected later in this thread; this note will be
updated to reflect any choices made there.

## Sources

The biology is standard textbook material; these are starting points for checking any detail.

- Alberts et al., *Molecular Biology of the Cell*: chapters on DNA replication and repair, and on
  meiosis and recombination.
- Kong et al. 2012, "Rate of de novo mutations and the importance of father's age to disease risk"
  (*Nature*), and Halldorsson et al. 2019, "Characterizing mutagenic effects of recombination
  through a sequence-level genetic map" (*Science*): human mutation and crossover rates.
- Drake 1991 and Drake et al. 1998, "Rates of spontaneous mutation" (*Genetics*): mutation rates
  across microbes and Drake's rule.
- Muller 1964, "The relation of recombination to mutational advance"; Felsenstein 1974, "The
  evolutionary advantage of recombination" (*Genetics*): Muller's ratchet and the benefits of
  sex.
- Maynard Smith, *The Evolution of Sex* (1978): the twofold cost of sex.
- Search results used to cross-check figures (accessed 2026-10-14):
  [de novo mutation review, PMC3538533](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3538533/),
  [human mutation and recombination, PMC4746749](https://pmc.ncbi.nlm.nih.gov/articles/PMC4746749),
  [four-generation pedigree, Nature 2025](https://ideas.repec.org/a/nat/nature/v643y2025i8071d10.1038_s41586-025-08922-2.html)
  (about 1.2 × 10⁻⁸ per base per generation, strong paternal bias, maternal excess of
  recombination).
- GA operator tutorials used for the crossover and mutation comparison:
  [Obitko, Crossover and Mutation](https://www.obitko.com/tutorials/genetic-algorithms/crossover-mutation.html),
  [Salimi lecture notes on genetic operators](https://faculty.kashanu.ac.ir/file/download/page/1572728546-session-4.pdf).
