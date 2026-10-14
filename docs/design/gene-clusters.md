# Gene clusters: traits that read several genes, and genes that affect each other

Design note for `DNA.14`. Written 2026-10-14 by the Research 2 thread. It answers the owner's reply to
[#36](https://github.com/dwhagar/evolutionSimulator/issues/36) question 1: traits should interact
**both ways**, through shared costs and trade-offs and through genes that affect each other, with
**clusters of genes** going into each trait's expression. It builds on
[dna-traits-interaction.md](dna-traits-interaction.md) (what is built) and the diploid model
(`DNA.13`, [dna-and-traits.md](dna-and-traits.md#diploid-genomes)).

The measured figures below come from running the merged code (`DNA.crossover_linked` on the animal
layout, 20,000 crossovers of an all-0 genome with an all-1 genome). The formulas and weights are
proposals.

## Summary

- A **cluster** is a set of genes that feed one trait and sit next to each other in the genome.
  Clustering has two halves: how the trait reads the genes, and where the genes sit.
- **Reading.** A `TraitDef` already reads several genes, but only as an equal-weight mean. Proposal: each
  gene in a trait gets a **weight** and a **role**, `main` or `modifier`. The default stays the mean, so
  nothing built changes. A **modifier** gene scales how strongly the main gene shows, which is "genes
  affect each other": the effect of one gene depends on another.
- **Where genes sit.** Tag genes with a `cluster` name in the layout and check that a cluster's genes are
  consecutive. Crossover already keeps neighbours together (measured: adjacent genes are split in 3.7% of
  crossovers, genes 10 apart in 37%), so nothing more is needed to keep a cluster of three together about
  93% of the time. A switch to treat a whole cluster as one unit is an option, off by default.
- **Order of operations with diploids:** dominance first, between a gene's own two copies; then the
  cluster, between different genes. They answer different questions and do not conflict.
- **Shared costs** (the other direction) are already how `traits.py` works; the one addition is a way to
  list which traits pay into which cost, so the trade-offs can be seen and audited.
- Two owner questions at the end; both have defaults.

## The words

| Word | Meaning | Where it lives |
| --- | --- | --- |
| Pleiotropy | One gene affects several traits | Built: several `TraitDef` rows read `size` |
| Polygeny / cluster | Several genes feed one trait | Built as an equal mean; extended here |
| Epistasis | One gene changes what another gene does | New: modifier role |
| Dominance | Two copies of one gene combine | Built (`DNA.13`), per gene, `DominanceModel` |
| Linkage | Nearby genes are inherited together | Built: `crossover_linked` |
| Shared cost / trade-off | Traits draw on one budget | Built in the formulas of `traits.py` |

## What exists today

- `TraitDef(name, genes, lo, hi, scale, kind, mutation_step)`. With several `genes`, the trait is
  `lo..hi` mapped from the **mean** of the gene values. `TraitSet.position_biases()` already scales
  the mutation step up by the number of genes, since an averaged gene moves the trait by only its share.
- `GeneSpec(id, length, segment)`: `segment` groups genes for the mutation budget ("body", "brain") and
  genes of a segment must be consecutive. It is not a cluster: a segment holds dozens of genes.
- `DNA.crossover_linked(mean_cuts=1.0, gene_fidelity=0.9)`: about one cut point per genome, falling
  between genes 90% of the time.
- `DiploidDNA.value(gene_id)` blends the two copies with `DominanceModel.blend`
  (`(a + b) / 2 + c * |a - b| / 2`, with `c` from -1 to 1 per gene); `TraitDef.express` reads through it, so
  haploid and diploid genomes both work unchanged.
- No trait uses more than one gene yet except in tests.

## How a trait reads a cluster

### The shape

```python
GeneTerm("fertility", role="main")                 # weight 1.0
GeneTerm("size", role="modifier", weight=0.2)
TraitDef("litter_capacity", genes=(GeneTerm(...), ...), combine=Combine.MODIFIED)
```

A plain string is a term with weight 1 and role `main`, so every existing row keeps working.

| `combine` | Value of the cluster `u` (0 to 1) | Use |
| --- | --- | --- |
| `MEAN` (default) | `sum(w_i * g_i) / sum(w_i)` over all terms | Polygeny: several genes add up. Plain strings give today's equal mean |
| `MODIFIED` | `clamp(g_main * (1 + 2 * sum(w_j * (g_j - 0.5))), 0, 1)` over the modifiers | Epistasis: modifiers push the main gene's effect up (weight above 0) or down (below 0) |

`g` are the gene values after dominance. The `2 * (g - 0.5)` makes a modifier at 0.5 neutral, so a
cluster with all modifiers at their middle value behaves exactly like the main gene alone, and a modifier
at an extreme changes the main gene's effect by up to `2 * 0.5 * w = w`. With weights of 0.2, one
modifier swings the effect by up to plus or minus 20%.

Two more combiners are possible but not proposed for the first build:

- `SWITCH`: a gene below a threshold silences another entirely (what the brain's on/off genes do for
  neurons, `BRAIN.23`). Add when a trait needs it.
- A pairwise product term. It is hard to reason about and to tune; avoid unless a case needs it.

### Worked example: litter capacity

From the reproduction design ([reproduction-genes.md](reproduction-genes.md)): the litter is
`1 + round(7 * u)`. Let `u` depend on `fertility` (main) with `size` and `recovery` as modifiers
(weight 0.2 each): a big, quick-healing body carries a bigger litter.

| Animal | fertility | size | recovery | factor `1 + 2(0.2(size - 0.5) + 0.2(recovery - 0.5))` | `u` | Litter |
| --- | --- | --- | --- | --- | --- | --- |
| Neutral modifiers | 0.75 | 0.5 | 0.5 | 1.00 | 0.75 | 6 |
| Big, quick healer | 0.75 | 1.0 | 1.0 | 1.40 | 1.00 (clamped from 1.05) | 8 |
| Small, slow healer | 0.75 | 0.0 | 0.0 | 0.60 | 0.45 | 4 |

The same `fertility` gene gives litters of 4, 6 or 8 depending on two other genes, which is the owner's
"genes affect each other", and it still costs nothing in code beyond the table row.

Existing code-level interactions (speed divided by `1 + 0.8 * size`, sight range narrowed by field of
view) can stay as formulas in `traits.py`; they are interactions between *traits*. Move one into the
table only when it should be evolvable at the gene level or visible in `explain` (below).

## Dominance and epistasis together

Dominance acts **inside one gene**, between the two copies. Epistasis acts **between genes**. So:

1. Read each gene's value through the dominance model, as `TraitDef.express` does now.
2. Combine the genes of the cluster.

Worked example for a diploid animal (dominance coefficient 0 unless stated):

| Gene | Copy A | Copy B | Dominance `c` | Expressed |
| --- | --- | --- | --- | --- |
| fertility | 0.9 | 0.5 | 0.5 (partly dominant high) | `0.7 + 0.5 * 0.2 = 0.80` |
| size | 0.2 | 0.8 | 0 | 0.50 |
| recovery | 0.9 | 0.9 | 0 | 0.90 |

Factor `1 + 2(0.2 * 0 + 0.2 * 0.4) = 1.16`; `u = 0.80 * 1.16 = 0.928`; litter `1 + round(6.496) = 7`.

The alternative, combining the cluster inside each copy and then blending, was rejected: it would need
every cluster rule to run twice, it hides the per-gene dominance the owner asked for in `#3`, and
heterozygotes would not match what the single-gene dominance model predicts. `Genome.value` stays the one
read, so no change to `DNA` or `DiploidDNA` is needed for this.

A per-gene dominance coefficient is the only dominance setting; there is no cluster-level dominance.

## Where clusters sit in the layout

### Tag and check

Add `cluster: str | None = None` to `GeneSpec`. `GenomeLayout` checks that the genes of one cluster are
consecutive (as it already does for segments) and exposes `layout.clusters`, a mapping from name to the
gene IDs in order. `TraitSet` checks that every gene a trait reads as a cluster belongs to one cluster
(a trait may also read single genes elsewhere; the tag is advice about inheritance, not a limit on
reading).

### Why adjacency is enough

Measured with the defaults (`mean_cuts` 1.0, `gene_fidelity` 0.9) on the animal layout, 28 units:

| Units apart | Chance the two genes come from different parents |
| --- | --- |
| 1 (neighbours) | 3.7% |
| 2 | 7.4% |
| 5 | 18.5% |
| 10 | 36.9% |
| 20 | 73.8% |

| Setting | Neighbours split | 10 apart | A gene cut open inside |
| --- | --- | --- | --- |
| `mean_cuts` 1.0 (default) | 3.7% | 36.9% | 8.5% of children (first 25 units) |
| `mean_cuts` 2.0 | 7.3% | 44.9% | 17.1% |

A cluster of `n` consecutive genes is split in about `3.7% * (n - 1)` of crossovers, so a three-gene
cluster stays whole about 93% of the time and a gene 10 away is close to unlinked. The rare split is the
slightly odd inheritance the owner asked for (`#14`). No new crossover code is needed.

**Option, off by default:** a layout flag `cluster_units`. With it on, consecutive genes of one cluster
merge into one unit for crossover (a "supergene"), so a cluster is never cut apart except by the
fidelity setting. Useful as an experiment: compare runs with and without.

### Proposed cluster order for the animal body

Genes are placed so that every cluster is consecutive. Changing the order moves positions, so it should
land with the next layout version bump (`REPRO.7`'s delta already bumps it to 5). Names are the current
and planned gene IDs.

| Cluster | Genes in order | Feeds |
| --- | --- | --- |
| frame | size, speed, agility | mass, energy store, speed, turning |
| repair | somatic_maint, recovery | wear, healing, upkeep |
| sight | sight_range, sight_fov | reach, field of view |
| hearing and calling | hearing, encoder_fidelity | hearing range, call radius and cost |
| chemical | smell, taste | smell range, toxin detection |
| touch | touch | tactile range |
| diet | herbivore_eff, carnivore_eff | feeding efficiency, gut upkeep |
| temperament | aggression, fear | fight or flight |
| reproduction | repro_drive, repro_cooldown, fertility, parenting, sex_strategy | the whole reproduction design |

Today the encoder gene sits after the reproduction genes and the sex digit after it; the proposal moves
`encoder_fidelity` beside `hearing` and keeps `sex_strategy` in the reproduction cluster. `touch` is
alone, so it has no cluster tag.

## Mutation and robustness

A trait that averages `n` genes with equal weights moves by `1/n` of the change in one gene. A modifier
moves the trait by at most its weight times the change. `TraitSet.position_biases()` already scales the
step for equal means; with weights it should use each gene's share of the total weight, so the bias a
gene gets matches how much it can move the trait. Clustering therefore makes a trait steadier against a
single mutation, and a mutation in a modifier a quieter, second-order change. Genes read by several traits
(pleiotropy) keep the mean of the steps they are asked for.

## The other direction: shared costs

Traits already interact through shared budgets in `traits.py`: upkeep (size, senses, repair, drive,
readiness, recovery), wear, speed damping, birth cost. The one addition is **visibility**:
`TraitSet.explain(trait_name)` returns, for a trait, the genes and weights behind it, the traits that
read the same genes (pleiotropy), and the cost terms that name it (a small table next to the `TRAIT.3`
config object mapping cost term to the traits it reads). This is for reading and tests, not for the
simulation, so a trade-off can be checked without reading `traits.py`, and the "no free lunch" test (no
trait can be raised to its maximum without a net cost) can run over the table.

## What to build

1. `trait_defs.py`: `GeneTerm`, `Combine`, `TraitDef.combine`; plain gene IDs still accepted;
   validation (exactly one `main` for `MODIFIED`, weights finite, `MEAN` ignores roles);
   `express` follows the table above; `traits_reading` and `position_biases` read the weights.
2. `dna.py`: `GeneSpec.cluster`, `GenomeLayout.clusters`, the contiguity check, and the optional
   `cluster_units` flag for crossover.
3. `layouts.py`: tag the clusters in the table above and reorder the body when the layout version next
   changes.
4. `TraitSet.explain`, and the cost table in the `TRAIT.3` config.
5. Rows: `litter_capacity` as in the example once the reproduction genes land; none are needed to
   exercise the machinery before that.
6. Tests: a plain-ID trait gives the same value as before; `MODIFIED` with neutral modifiers equals the
   main gene; modifiers at 0 and 1 give the factor above and clamp; weights change `position_biases`;
   a cluster that is not consecutive is rejected; a diploid heterozygote follows the order dominance
   then cluster (the example above); and a crossover test that neighbouring cluster genes are split in
   under 6% of children with the defaults.
7. Update [dna-traits-interaction.md](dna-traits-interaction.md) when it lands.

## Constants

| Name | Value | Used in |
| --- | --- | --- |
| `MODIFIER_SWING` | 2.0 | `MODIFIED`: factor is `1 + 2 * sum(w * (g - 0.5))` |
| Default modifier weight | 0.2 | cluster rows that do not give one |
| `CLUSTER_UNITS` | off | `GenomeLayout` crossover flag |

## Questions for the owner

To go on [#69](https://github.com/dwhagar/evolutionSimulator/issues/69), numbered 7 and 8. Each has a
default this note assumes.

7. **What "genes affect each other" means.** The proposal is a modifier gene that strengthens or weakens
   another gene's effect (a big body carrying bigger litters). Is that the kind of interaction you want?
   Default: yes, plus the average of several genes for the rest. A switch (one gene turns another off) can
   be added later.
8. **Linked clusters.** Genes in a cluster sit together and are inherited together about 93% of the time
   (for three genes). Is that tight enough, or should a cluster always be inherited whole? Default: the
   current setting, with the whole-cluster switch available for experiments.
