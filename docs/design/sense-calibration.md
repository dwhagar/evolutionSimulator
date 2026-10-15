# Sense calibration (SENSE.13)

**Status.** Measured on `main` after `WORLD.15`'s first reading; **no constant has changed**. The
sense bill meets the first aim of [senses.md](senses.md) (a typical animal pays 10 to 15% of its
upkeep) and misses the second (a specialist at 30 to 40%), which `SENSE.11` already showed cannot both
hold when cost follows area. Both tools are in `src/evolution_tools/` (with wrappers in `scripts/`): `sense_calibration.py` (the bill and the
noise, no world) and `sense_probe.py` (scripted foragers in a world).

## The bill

Sense cost as a share of the whole upkeep bill (`basal_metabolism`), mean over 400 animals, seed 1
(`python -m evolution_tools.sense_calibration`):

| Animals | Eye | Hearing | Smell | Touch | Taste | All senses |
|---|---|---|---|---|---|---|
| First generation | 1.4% | 2.1% | 2.9% | 3.0% | 3.0% | **12.4%** (10th to 90th: 9.7 to 15.8%) |
| Random genomes | 1.3% | 2.5% | 3.6% | 3.6% | 3.3% | 14.3% (7.2 to 21.9%) |
| One sense at 1, the others at 0 | 5.3% | 8.9% | 11.9% | 12.0% | 12.0% | the same |
| One sense at 1, the others at 0.5 | 4.7% | 8.0% | 10.8% | 11.0% | 11.0% | 15.5 to 19.7% |

- **Typical animal: inside the aim.** A founder pays 12.4% and nine in ten pay 10 to 16%.
- **Specialist: outside it.** A creature that maxes one sense pays 5 to 12% alone and 16 to 20% with
  the other senses in the middle (25% at the 90th percentile), not 30 to 40%. Reaching 30% would take
  costs two to three times higher, which would put a typical animal near 30% too, and the probe below
  shows what that does to survival, so it is not proposed.
- **The eye is the cheapest sense**, as it should be if it is the most useful: even at range 1 and
  field 1 it is 5% against 9 to 12% for the others. Its cost goes with `1 + acuity`, and acuity is
  capped by the field (`acuity = min(sight_acuity, 1 - sight_fov)`).
- **Touch and taste cost most per use.** They are 3% each at the middle and 12% at 1, as much as an
  eye, smell and hearing together, because they are charged by the gene squared and not by area.

## What a sense is worth

`python -m evolution_tools.sense_probe ...` puts 100 foragers with the same fixed rule in a 1,000 by 1,000
world with 1,500 harmless plants that never run out, 1,200 ticks, three seeds. Only the senses differ.
"Eaten" is energy eaten per animal; the share alive is low in every row because the default upkeep
bill kills a population in about 1,000 hourly ticks (`WORLD.15`), so read the rows against each other.

| Probe | Result |
|---|---|
| Which senses | blind 79; hearing alone 69 (plants are silent); smell alone (0.5) 682; eye alone (mid) 744; eye, smell and hearing 754. **Any working long-range sense is about ten times a blind forager**, and the blind and hearing-only populations are all dead. |
| Eye field, along its frontier (reach 0.5) | field 0 / acuity 1: 620; 0.2: 662; 0.5: 744; 0.8: 772; 1.0 / 0: 752. **A wide field is worth about 20 to 25% more than a narrow, sharp eye**, because the probe is looking for plants that are everywhere. A predator that needs to judge size and distance would read this differently; this probe cannot say. |
| Eye reach (field 0.5) | 0.25: 586; 0.5: 744; 0.75: 794; 1.0: 829. Longer reach keeps paying, at a falling rate (+27% for the first doubling, +11% for the second). |
| Smell gene (smell only) | 0.25: 589; 0.5: 682; 0.75: 746; 1.0: 776. The same shape. |
| Cost scale on every sense (eye, smell, hearing at the middle) | x0: 757, 56% alive; x1: 754, 41%; x2: 775, 35%; x4: 747, 21%. **Cost does not change what is eaten but halves the survivors from x0 to x4**, so it is the right lever for the price of a sense. |
| Noise scale on every sense | x0: 736; x1: 754; x3: 756; x6: 752. **Noise does not matter** to a forager that walks at a plant it can sense; it would matter to targeting a moving prey. |
| Light floor (eye only) | 0.0: 737; 0.25: 744; 0.5: 772; 1.0: 758. Darkness costs little here because a plant does not move and the animal still has its night to find one. |

## Decisions

- **Keep the cost constants** (vision 8e-6, hearing and smell 2.5e-6 per square unit, touch and taste
  0.08): the typical bill is in the aim, and the probe says a higher price only costs lives.
- **Keep the noise numbers.** They matter for hunting and fleeing, which a plant eater does not test;
  calibrate them with the predator tests after `WORLD.15` gives a population that survives.
- **Sleep factors (vision 0, hearing 0.5, smell 0.5, touch 1) and the light floor stay.** The sleep
  factors only decide whether a predator finds a sleeper, and no run has predators that live long
  enough to test it.
- **Smell trails (`SENSE.20`) stay off.** The decision was to wait for a founder run that breeds, and
  there is none yet (`WORLD.15`). Smell alone is nearly as good as the eye for finding plants (682
  against 744), so a trail would mostly help predators following prey.

**For the owner (still open from `SENSE.11`):** touch and taste cost 3% each at the middle and 12% at
the top, charged by the gene squared. Nothing in this probe uses them (the plants are harmless and
touch is always known), so it cannot say whether they are worth that. Making them free would lower a
typical bill from 12.4% to about 6%. Left as it is until someone
decides.
