"""What the setup screen starts a run from, and the presets it offers (UX.17).

``RunSetup`` is the whole answer to "what world?": how many animals and plants to start with,
whether the founders carry the seeded brains, and the ``WorldConfig`` (seed included). It is a plain
frozen value with no Qt in it, so it can be saved as JSON (a user's own presets) and turned into the
``NewRun`` command the session understands. The built-in presets are a few starting points; their
numbers are only suggestions, and the form can change any of them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from evolution_simulator.session import NewRun
from evolution_simulator.viewer.configdata import from_data, to_data
from evolution_simulator.world.bounds import Bounds
from evolution_simulator.world.world import WorldConfig


@dataclass(frozen=True)
class RunSetup:
    animals: int = 120
    plants: int = 600
    seeded: bool = True
    """Founders get the seeded brain (``BRAIN.9``); off leaves the brains random, and those mostly
    die before they breed."""
    config: WorldConfig = field(default_factory=WorldConfig)

    def command(self) -> NewRun:
        """The command that starts this run; ``CommandError`` if the counts do not fit the caps."""
        return NewRun(self.config, self.animals, self.plants, self.seeded)

    def with_seed(self, seed: int) -> RunSetup:
        return replace(self, config=replace(self.config, seed=seed))

    def to_json(self) -> str:
        return json.dumps(
            {
                "animals": self.animals,
                "plants": self.plants,
                "seeded": self.seeded,
                "config": to_data(self.config),
            },
            indent=1,
        )

    @classmethod
    def from_json(cls, text: str) -> RunSetup:
        """The setup ``to_json`` wrote; ``ValueError`` if the text is not one."""
        try:
            data: Any = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"not a saved setup: {error}") from None
        if not isinstance(data, dict):
            raise ValueError("not a saved setup")  # noqa: TRY004
        defaults = cls()
        for name in ("animals", "plants"):
            if not isinstance(data.get(name, 0), int) or isinstance(data.get(name), bool):
                raise ValueError(f"{name} must be a whole number")  # noqa: TRY004
        return cls(
            animals=data.get("animals", defaults.animals),
            plants=data.get("plants", defaults.plants),
            seeded=bool(data.get("seeded", defaults.seeded)),
            config=from_data(WorldConfig, data.get("config", {})),
        )


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    setup: RunSetup


def _builtin() -> tuple[Preset, ...]:
    base = RunSetup()
    return (
        Preset("Default", "The standard world: 1000 by 1000 units, 120 animals, 600 plants.", base),
        Preset(
            "Small and quick",
            "A 500 by 500 world with 40 animals and 200 plants; each tick is cheap, so it runs "
            "fast. Good for trying something out.",
            replace(
                base, animals=40, plants=200, config=WorldConfig(bounds=Bounds((500.0, 500.0)))
            ),
        ),
        Preset(
            "Large world",
            "A 2000 by 2000 world with 300 animals and 3000 plants. Much slower to run, because "
            "every tick has far more organisms to work through.",
            replace(
                base, animals=300, plants=3000, config=WorldConfig(bounds=Bounds((2000.0, 2000.0)))
            ),
        ),
        Preset(
            "No night",
            "Permanent daylight: no day cycle, so there is no night and nobody sleeps.",
            replace(base, config=WorldConfig().with_rules(day_cycle=None)),
        ),
        Preset(
            "No learning",
            "Brains stay as they were born; nothing is learned in life.",
            replace(base, config=WorldConfig().with_rules(learning=None)),
        ),
    )


BUILTIN_PRESETS: tuple[Preset, ...] = _builtin()
