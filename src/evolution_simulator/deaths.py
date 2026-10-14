"""Why an organism died (UX.6): the cause the body records when it dies, read by the world's
death events and the viewer."""

from __future__ import annotations

from enum import StrEnum


class DeathCause(StrEnum):
    STARVATION = "starvation"
    """Out of energy (an animal) or out of biomass (a plant)."""
    OLD_AGE = "old_age"
    """Worn out: an animal's accumulated wear used up its body, or a plant reached its lifespan."""
    PREDATION = "predation"
    """Killed by another animal's bite."""
    POISON = "poison"
    """Killed by a toxic meal."""
    EATEN = "eaten"
    """A plant grazed down."""
    DAMAGE = "damage"
    """Health lost to anything not named above (the default for damage with no cause given)."""
