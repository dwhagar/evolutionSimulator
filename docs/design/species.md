# Species tracking

Task `SPECIES.1`, written 2026-10-14 by the Viewer 2 thread. The code is
[`src/evolution_simulator/species.py`](../../src/evolution_simulator/species.py): a read-only observer in
the core (no Qt, no numpy) that notices when one population has drifted into two. The settings and the
ranking default follow the owner's questions
[#206](https://github.com/dwhagar/evolutionSimulator/issues/206) (what counts as a species) and
[#207](https://github.com/dwhagar/evolutionSimulator/issues/207) (how to rank them). Both are closed with the owner's answers, which are the defaults below; every
one of them is still a setting.

## What it does

`SpeciesTracker(world)` listens to the end of every step. Every `period_days` simulated days (default 7)
it samples the living animals and, separately, the plants (at most `sample_size`, default 300, of each),
groups the sampled genomes, and updates a record per species: first and last day seen, size at each
sample, the centre genome, and how far the centre is from where the world started. `ranking`, `species`,
`get` and `founder` read the result; `add_sample_listener` tells a recorder or a chart a sample has just
been taken. Nothing is drawn from the world's random generator and nothing in the world is changed, so a
run has the same `state_digest` with or without a tracker (tested).

## The distance, and why it is cheap

Two genomes are `DNA.distance` apart: the fraction of digits that differ. The tracker reads each sampled
genome as one base-4 integer, so the distance is `((x ^ y) | (x ^ y) >> 1) & mask` and a popcount, a few
C-speed operations however long the genome is. Only the sampled genomes are converted, so a big
population costs no more than a small one. A diploid genome counts as both strands one after the other.

The **centre** of a group is its digit-wise most common genome (the consensus; a tie goes to the lower
digit). The **spread** of a group is the mean distance of its members to its centre.

## The rules

All numbers are `SpeciesRules`, saved with the tracker.

| Setting | Default | Meaning |
|---|---|---|
| `period_days` | 7 | Simulated days between samples. |
| `sample_size` | 300 | Most genomes sampled of each kind. The sample is chosen by a hash of the organism id and a salt, so it is repeatable and does not depend on the order of the list. |
| `separation` | 2.0 | Two groups are separate when the gap between their centres is over this many times the spread inside them. |
| `min_gap` | 0.04 | ... and at least this fraction of the digits. |
| `confirm` | 3 | Samples in a row a split, a merge or a disappearance must hold. |
| `merge_ratio` | 0.5 | Species merge when their gap stays under this share of the gap they would need to split. |
| `min_members`, `min_share` | 5, 0.05 | Fewest genomes in a group that splits off, and its least share of the species. |
| `top_count` | 5 | Lines per kind that `top` gives. |
| `history_points`, `extinct_kept` | 520, 200 | Bounds on what is kept (below). |

**Issue 206 (confirmed: option A).** A species is a group whose centre is clearly farther from its
neighbours' centres than its own members are from it: over twice the spread, and never under 4% of the
digits. The issue's other options are a fixed distance and a mating-compatibility test; either would only
change `required_gap` (and, for the second, what the tracker is shown), so the choice can change without
touching the rest.

**Splitting.** Each sample, each live species is cut in two by two-means on the distance (started from its
two most distant members, a few rounds). If the two halves are separate by the rule above and both are big
enough, a streak counter goes up; any sample where they are not resets it. At `confirm` in a row the species
splits: **the larger half keeps the id** and the old record, the smaller becomes a new species whose
`parent` is the old id. A three-way split is two splits, on successive samples, so the tree stays binary.

**Merging.** Two live species whose centres stay closer than `merge_ratio` of the gap they would need to
split, for `confirm` samples in a row, are one again: the smaller is marked `merged_into` the larger and
ends. A pair between the two limits is left as it is. The gap between "split at 1x" and "merge at 0.5x" is
the hysteresis that stops a borderline pair flickering between one species and two.

**Assignment.** Each sampled genome joins the species whose centre is nearest, and each centre then moves
to the consensus of its members. A line that drifts keeps its id and its divergence grows.

**Fading.** A species with no members in a sample that took in the whole population is extinct at once. If
the population was bigger than the sample (so one rare line may just have missed), it must be missing for
`confirm` samples. When nothing of a kind is alive every species of that kind ends, and a later population
starts a new first species (the founders stay what they were). A genome of a different length (a new
layout) restarts the kind.

## What is recorded

For each species (`SpeciesInfo`): `id`, `kind`, `parent`, `first_day`, `last_day`, `extinct_day`,
`merged_into`, `size` (the sample scaled up to the population), `peak`, `centre`, `spread`, and:

- **`divergence`**: the distance of the centre from the **founding consensus**, the consensus of the first
  sample of the kind. This is issue 207's default ranking, "how far has it come".
- **`relative_divergence`**: the distance of the centre from the centre of the largest species of the
  kind, issue 207's second option ("how unlike the mainstream").
- `size`, the third option. `ranking(kind, by="divergence" | "relative" | "size", count=None)` orders by
  any of them, largest value first. `top(kind)` is the owner's choice for issue 207: the `top_count`
  (default 5) living species of the kind that are **most divergent, furthest from the founding genome**.
- **`points`**: day, size and divergence at each sample, for the charts (`UX.41`) and the recorder
  (`SPECIES.2`).

Ids are unique across both kinds and never reused.

**Bounded.** A sample is at most `sample_size` genomes per kind. A species' own series keeps at most
`history_points` samples (ten years of weekly ones); past that the older half is thinned to every second
point. At most `extinct_kept` extinct species are kept, oldest dropped first.

## Saving

`to_dict` / `SpeciesTracker.restore(source, data)` carry everything, including the rules, the streak
counters and the next sample time, so a restored tracker goes on exactly as an uninterrupted one would
(tested). The save and load code sits behind functions of its own, like the recorder's `save_history` and
`load_history_data`: `save_species(tracker, path)` and `load_species_data(path)` write and read the dict as
JSON (gzipped for `.gz`, the same bytes for the same state), and `migrate(data)` brings an old dict to the
current layout.

The dict has its own **`SPECIES_FORMAT`** (now 1) and a `_MIGRATIONS` chain, so a change to its layout
bumps the number and adds one step. Storage is moving to SQLite (`STORE.1` and `STORE.2`), so the run
store does **not** keep a species file yet and `RUN_FORMAT` is unchanged: `STORE.2` can put
`tracker.to_dict()` in a table, read it back with `migrate`, and nothing has to be migrated twice. The run
host, the headless runner and the viewer do not make a tracker either; that is `SPECIES.2` (recording).

## Cost

Measured on the build machine, one sample of 300 animals (1260 digits) and 600 plants (33 digits):
**about 58 ms**, whatever the population is above that (1000 animals and 1800 plants, the same).
Only the sample is read. At the default period that is one sample per 168 hourly ticks, where a step of a
300-animal world takes about 40 ms, so the tracker adds under 1% to a run. Over a two-year real run
(105 samples) the plant-only samples took 3 to 11 ms each.

## What the checks showed

- **Synthetic populations** (`tests/test_species.py`, and larger ones while building it): one
  interbreeding population stays one species for any number of samples; two lines apart by 10% of the
  digits split on the third sample; a pair 3% apart (under the 4% floor) or less than twice the spread
  apart never splits; two lines that drift back together merge into the larger; a line that disappears is
  marked extinct. Starting from one genome with mutation and no crossing between two isolated groups, the
  groups split after roughly 250 to 300 generations at a mutation rate of 0.0002 per digit per
  generation. At a rate ten times higher the populations are so varied (spread about 0.16) that the
  4% floor and the 2x rule never see two clear groups, so isolated lines do not split; the settings are
  worth revisiting once the real mutation rate is settled.
- **A real world** (`populate(animals=60, plants=300)` for two simulated years): the founders do not
  breed yet (`WORLD.15`), so the 60 animals died out
  in the first two months and the animal tracker correctly ended its one species. Plants lived on and
  split into six lines over the two years (first split on day 308, the later ones as the lines drifted),
  each with a parent id. The caution is that plant genomes are 33 digits, so one digit is 3%, and the
  founding consensus of 300 random plants is itself a made-up genome: a surviving subset sits far from it
  from the first sample (divergence 0.6 to 0.7), so for plants `relative_divergence` is the more useful
  ranking. To repeat the animal check on a real breeding population, run `longrun` style scripts again
  once WORLD.15 has merged.

## Not decided

- Whether to rank plants and animals together (they are separate here, each with its own founders).
- Whether a sexual split needs a mating test; this tracker sees genomes only.
