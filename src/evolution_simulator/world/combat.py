"""Attacks and meat (``BRAIN.10``).

An animal whose brain says "eat or attack" and that touches no plant bites the nearest animal in
contact that it counts as prey (``senses.classify``: a meat eater at most 0.8 times its mass). The
bite does ``damage * carnivore efficiency * sqrt(attacker mass / prey mass)`` damage. What a kill
is worth is the corpse it leaves (``corpses.py``), which the killer eats like any other meat.

``AttackRules`` lives in ``config.py`` (``TRAIT.11``) and is re-exported here.
"""

from __future__ import annotations

from evolution_simulator.config import AttackRules

__all__ = ["AttackRules"]
