"""Commands (UX.6): everything a viewer can ask the simulation session to do.

One small set of plain values, so that whatever carries them (a call in the same process, a pipe to
the simulation process, a headless script) carries every command the same way. A new ability is a
new command type here and a handler in ``Session``, never a new channel. Commands are immutable and
hold only numbers and strings, so they pickle and could go over a socket as JSON.

``NewRun`` (UX.17) carries a whole ``WorldConfig``, a tree of frozen dataclasses of numbers, strings
and booleans, so it too pickles. Still to come in later items: ``save`` and ``load`` (UX.9, UX.18),
``set_snapshot_rate`` / ``want`` and ``shutdown`` (UX.7), and the interventions (UX.20).
"""

from __future__ import annotations

from dataclasses import dataclass

from evolution_simulator.world.world import WorldConfig


class CommandError(ValueError):
    """A command could not be carried out (a bad speed, an animal that is not there). Nothing was
    changed."""


@dataclass(frozen=True, slots=True)
class Play:
    """Run at the current speed."""


@dataclass(frozen=True, slots=True)
class Pause:
    """Stop running. Any ticks still owed by ``Step`` are cancelled."""


@dataclass(frozen=True, slots=True)
class Step:
    """Pause and run exactly ``ticks`` ticks, as fast as the computer allows."""

    ticks: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.ticks, int) or isinstance(self.ticks, bool) or self.ticks < 1:
            raise CommandError(
                f"Step needs a whole number of ticks, one or more, got {self.ticks!r}."
            )


MAX_SPEED = "max"
"""The speed name for "as fast as the computer can" (a preset next to the fixed ones)."""


@dataclass(frozen=True, slots=True)
class SetSpeed:
    """How fast to run: a preset name from ``SPEED_PRESETS`` (``"day"``, ``"year"`` ...), ``"max"``
    for as fast as possible, or a number of simulated seconds per real second."""

    speed: float | str

    def __post_init__(self) -> None:
        if isinstance(self.speed, str):
            return
        if isinstance(self.speed, bool) or not self.speed > 0.0 or self.speed == float("inf"):
            raise CommandError(f"A speed must be a positive finite number, got {self.speed!r}.")


@dataclass(frozen=True, slots=True)
class Select:
    """Send the details of this animal (its brain too) with each update until deselected. The
    viewer picks the id from the frame it already has."""

    animal_id: int


@dataclass(frozen=True, slots=True)
class Deselect:
    """Stop sending an animal's details."""


@dataclass(frozen=True, slots=True)
class NewRun:
    """Throw the current world away and start a new one (UX.17): a world built from ``config``,
    filled with ``animals`` founders and ``plants`` plants (the founders carry the seeded brains
    unless ``seeded`` is False), paused at tick 0. The run being replaced is not saved. The speed
    the viewer had set stays, unless ``config.traits.time.speed`` was changed from its default,
    which then becomes the speed."""

    config: WorldConfig
    animals: int = 0
    plants: int = 0
    seeded: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.config, WorldConfig):
            raise CommandError(f"NewRun needs a WorldConfig, got {self.config!r}.")
        for name, cap in (("animals", self.config.max_animals), ("plants", self.config.max_plants)):
            count = getattr(self, name)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise CommandError(
                    f"A run needs a whole number of {name}, zero or more, got {count!r}."
                )
            if count > cap:
                raise CommandError(f"A run can start with at most {cap:,} {name}, got {count:,}.")

    @property
    def label(self) -> str:
        """A few words for a title bar: ``world, seed 7``."""
        return f"world, seed {self.config.seed}"


Command = Play | Pause | Step | SetSpeed | Select | Deselect | NewRun
