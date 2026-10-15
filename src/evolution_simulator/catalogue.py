"""Names, units and one-line meanings for every gene and trait (UX.29).

The inspector and the setup screens show a gene or a trait by what it is called to a person, not by
its ID, with its unit and a line on what it does. This module is that text, in one place, and a test
(``tests/test_catalogue.py``) checks that it covers every gene of every layout and every trait of
both trait tables, and names nothing that does not exist, so adding a gene without describing it
fails.

``describe_gene(id)`` and ``describe_trait(name)`` give a ``Description``. A gene's unit says what
the stored value means (most are a level from 0 to 1 that the trait table stretches onto a range);
a trait's unit is the unit of the number the simulation uses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Description:
    """How to show one gene or trait to a person."""

    name: str
    """A short display name."""
    unit: str
    """The unit of its value; empty for a plain number."""
    meaning: str
    """One line on what it does."""


LEVEL = "level 0 to 1"


def _gene(name: str, meaning: str, unit: str = LEVEL) -> Description:
    return Description(name, unit, meaning)


GENES: dict[str, Description] = {
    # --- animal body
    "size": _gene(
        "Size", "Body mass: a big body is stronger and carries more, and costs more to run."
    ),
    "speed": _gene("Speed", "How fast it can move; fast movers burn more energy."),
    "agility": _gene("Agility", "How sharply it turns; agile bodies cost more to keep."),
    "somatic_maint": _gene(
        "Body repair", "How much it spends on slowing wear, to live longer at a running cost."
    ),
    "recovery": _gene(
        "Recovery", "How fast the body heals and regains energy at rest; costs upkeep."
    ),
    "sight_range": _gene("Sight range", "How far it can see before acuity lengthens it."),
    "sight_fov": _gene("Field of vision", "How wide it sees; a wider field shortens the reach."),
    "sight_acuity": _gene("Sight acuity", "Sharper eyes reach further and err less, at a cost."),
    "hearing": _gene("Hearing", "How far it hears footsteps and calls."),
    "encoder_fidelity": _gene("Call strength", "How far its calls carry and what each call costs."),
    "smell": _gene("Smell", "How far it smells food, prey and threats."),
    "taste": _gene("Taste", "Its chance to detect toxin in food it inspects."),
    "touch": _gene("Touch", "How far past its body it can feel contact."),
    "herbivore_eff": _gene("Plant digestion", "How much energy it gets from eating plants."),
    "carnivore_eff": _gene(
        "Meat digestion", "How much energy it gets from meat, and how hard it bites."
    ),
    # --- behaviour and reproduction
    "aggression": _gene("Aggression", "How eager it is to attack; scales how close prey looks."),
    "fear": _gene("Fear", "How readily it flees; scales how close a threat looks."),
    "repro_drive": _gene(
        "Mating drive", "Urge to find a mate: lowers the energy needed to start looking."
    ),
    "repro_cooldown": _gene("Mating pause", "How long it rests between matings."),
    "fertility": _gene(
        "Fertility", "Chance a mating takes, litter size and gestation; costs upkeep."
    ),
    "parenting": _gene(
        "Parenting", "Share of its energy it gives each young, and how it protects them."
    ),
    "sex_strategy": _gene(
        "Sex and strategy",
        "0 or 2 impregnates, 1 or 3 bears the young; 2 raises and 3 lowers the mating drive.",
        "digit 0 to 3",
    ),
    # --- brain
    "brain_gain": _gene(
        "Brain gain", "Multiplies every neuron's input sum: high is sharp, low is gradual."
    ),
    "reaction_time": _gene("Reaction time", "How many hours pass between its brain's decisions."),
    "curiosity": _gene(
        "Curiosity", "Size of the random nudge on its actions, which learning needs."
    ),
    "learning_rate": _gene("Learning rate", "How strongly it learns from its day when it sleeps."),
    "camouflage": _gene(
        "Camouflage",
        "How hard it is to see: others see it from less far, at a cost in upkeep and speed.",
    ),
    "brain": _gene(
        "Brain",
        "The network's gates, biases and weights: up to 16 hidden neurons, switched on by their gates.",
        "numbers -2 to 2",
    ),
    # --- plant
    "max_biomass": _gene("Full size", "How big the plant grows, and so its canopy."),
    "growth_rate": _gene("Growth rate", "How fast it gains biomass when light and soil allow."),
    "toxicity": _gene("Toxicity", "How poisonous it is to a grazer."),
    "dispersal_radius": _gene("Seed dispersal", "How far its seeds land from it."),
    "seed_clutch": _gene("Seeds per burst", "How many seeds it makes at once."),
    "root_reach": _gene("Root reach", "How far its roots reach for soil."),
    "seed_provision": _gene(
        "Seed provision", "Share of its own full size that a seed starts with."
    ),
    "seeding_interval": _gene("Seeding interval", "Shortest gap between seed bursts."),
    "longevity": _gene("Longevity", "A long life slows growth and shrinks the seed budget."),
}


def _trait(name: str, unit: str, meaning: str) -> Description:
    return Description(name, unit, meaning)


TRAITS: dict[str, Description] = {
    # --- animal: the gene values as they are (0 to 1)
    "speed": _trait("Speed gene", LEVEL, "The speed gene's value."),
    "agility": _trait("Agility gene", LEVEL, "The agility gene's value."),
    "size": _trait("Size gene", LEVEL, "The size gene's value."),
    "somatic_maint": _trait("Repair", LEVEL, "Repair: slows wear, costs upkeep."),
    "sight_range": _trait("Sight range gene", LEVEL, "The sight range gene's value."),
    "sight_fov": _trait("Field of vision gene", LEVEL, "The field of vision gene's value."),
    "sight_acuity": _trait("Acuity gene", LEVEL, "The sight acuity gene's value."),
    "camouflage": _trait(
        "Camouflage", LEVEL, "Share of the way to its best hiding: seen from up to half as far."
    ),
    "hearing": _trait("Hearing gene", LEVEL, "The hearing gene's value."),
    "smell": _trait("Smell gene", LEVEL, "The smell gene's value."),
    "touch": _trait("Touch gene", LEVEL, "The touch gene's value."),
    "taste": _trait("Taste", LEVEL, "Its chance to detect toxin in food it inspects."),
    "herbivore_eff": _trait("Plant digestion", LEVEL, "Share of a plant's energy it can use."),
    "carnivore_eff": _trait(
        "Meat digestion", LEVEL, "Share of meat's energy it can use, and bite strength."
    ),
    "aggression": _trait(
        "Aggression", LEVEL, "How eager it is to attack, before hunger and crowding."
    ),
    "fear": _trait("Fear", LEVEL, "How readily it flees, before wear makes it worse."),
    "encoder_fidelity": _trait("Call gene", LEVEL, "The call strength gene's value."),
    "repro_drive": _trait(
        "Mating drive", LEVEL, "Urge to find a mate: lowers the energy needed to start looking."
    ),
    "fertility": _trait(
        "Fertility", LEVEL, "Chance a mating takes, litter size, gestation; costs upkeep."
    ),
    "recovery": _trait(
        "Recovery", LEVEL, "How fast the body heals and regains energy at rest; costs upkeep."
    ),
    # --- animal: derived values in the simulation's units
    "mass": _trait(
        "Body mass", "mass units", "Body mass, 1 to 4; it sets strength, reach and cost."
    ),
    "sight_reach": _trait(
        "Sight reach", "world units", "How far it sees, before acuity lengthens it."
    ),
    "fov_half_degrees": _trait(
        "Field of vision", "degrees", "The angle it sees either side of the direction it faces."
    ),
    "hearing_range": _trait("Hearing range", "world units", "How far it hears."),
    "smell_range": _trait("Smell range", "world units", "How far it smells."),
    "tactile_factor": _trait(
        "Touch reach", "x body radius", "How far past its body it feels contact."
    ),
    "call_radius": _trait("Call radius", "world units", "How far its calls carry."),
    "call_energy_cost": _trait("Call cost", "energy", "What one call costs."),
    "sex_strategy": _trait(
        "Sex and strategy",
        "digit 0 to 3",
        "Its sex (even or odd digit) and its mating-drive strategy.",
    ),
    "care_fraction": _trait(
        "Care fraction",
        "share of energy store",
        "Share of its energy store each young starts with.",
    ),
    "cooldown_days": _trait(
        "Mating pause", "days", "Simulated days between matings, before repair stretches it."
    ),
    "litter_capacity": _trait(
        "Litter capacity",
        "share of the largest litter",
        "Fertility sets the litter; a big or quick-healing body carries more.",
    ),
    "brain_gain": _trait("Brain gain", "x", "Multiplies every neuron's input sum."),
    "decision_interval": _trait(
        "Decision interval", "hours", "Hours between brain decisions; a slower thinker is cheaper."
    ),
    "curiosity": _trait("Curiosity", "action units", "Size of the random nudge on its actions."),
    "learning_rate": _trait("Learning rate", "x", "Strength of the nightly learning step."),
    # --- plant
    "toxicity": _trait("Toxicity", LEVEL, "How poisonous it is to a grazer."),
    "max_biomass": _trait("Full biomass", "biomass", "The biomass at full size."),
    "canopy_radius": _trait(
        "Canopy radius", "world units", "How wide it spreads, and so how much it shades."
    ),
    "base_growth_rate": _trait(
        "Growth rate", "biomass per hour", "How fast it gains biomass when light and soil allow."
    ),
    "dispersal_radius": _trait(
        "Dispersal radius", "world units", "How far its seeds land from it."
    ),
    "seed_count": _trait("Seeds per burst", "seeds", "How many seeds it makes at once."),
    "root_radius": _trait("Root radius", "world units", "How far its roots reach."),
    "seed_provision": _trait(
        "Seed provision", "share of full size", "Share of its own full size a seed starts with."
    ),
    "seeding_days": _trait("Seeding interval", "days", "Shortest gap between seed bursts."),
    "longevity": _trait(
        "Longevity", LEVEL, "A long life slows growth and shrinks the seed budget."
    ),
    "lifespan_days": _trait(
        "Lifespan", "days", "Simulated days until an uneaten plant dies of old age."
    ),
}


def describe_gene(gene_id: str) -> Description:
    """The display name, unit and meaning of a gene; ``KeyError`` for an unknown ID."""
    return GENES[gene_id]


def describe_trait(name: str) -> Description:
    """The display name, unit and meaning of a trait; ``KeyError`` for an unknown name."""
    return TRAITS[name]
