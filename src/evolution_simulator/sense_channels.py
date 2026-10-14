"""Sense channels: one table of everything the brain is told (``SENSE.8``).

Each row is one brain input: its name, its range, who supplies it, and which senses can report it.
``brain_adapter`` generates ``INPUT_NAMES``, ``Percepts`` and ``build_inputs`` from this table, so
adding an input is one row here (plus the brain's shape, which is a separate decision) and the
sensing step reads the same rows to know which sense may report what. The design is in
``docs/design/senses.md``.

The row order is the input order, and so the order of the brain's input weights: reordering or
inserting rows changes what every saved brain means, so do it together with a genome layout bump.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, make_dataclass
from typing import Any

SENSE_KINDS: tuple[str, ...] = ("vision", "hearing", "smell", "touch")
"""The fixed list of outer senses (``SENSE.6``: new kinds are added by the developers)."""

SOURCES: tuple[str, ...] = ("body", "world")
"""``body``: the animal supplies it from its own state. ``world``: the sensing step supplies it,
and it is a field of ``Percepts``."""

ROLES: tuple[str, ...] = ("level", "flag", "bearing", "closeness", "strength")
"""What kind of number it is. ``bearing`` and ``closeness`` come in pairs for one ``target``;
``flag`` is 0 or 1; ``strength`` is a signal loudness; ``level`` is anything else. A bearing with
no target (the direction of the loudest call) stands alone."""

TARGETS: tuple[str, ...] = ("plant", "prey", "threat", "mate", "young")
"""The classes of thing the brain is told about by nearest member."""


@dataclass(frozen=True)
class InputChannel:
    """One brain input."""

    name: str
    low: float
    high: float
    source: str
    role: str = "level"
    senses: tuple[str, ...] = ()
    """Which senses can report it; empty for body inputs."""
    target: str | None = None
    """For bearing and closeness rows, the class of thing they describe."""
    scaled_by: str | None = None
    """Name of a ``Temperament`` field that scales this input (``BRAIN.14``)."""
    ambient: bool = False
    """A world input that is the state of the world, not something sensed (daylight): it does not
    count against ``Percepts.senses_nothing``."""
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ValueError(f"Channel name {self.name!r} must be a valid identifier.")
        if not self.low < self.high:
            raise ValueError(
                f"Channel {self.name!r} needs low < high, got {self.low}, {self.high}."
            )
        if self.source not in SOURCES:
            raise ValueError(f"Channel {self.name!r} has unknown source {self.source!r}.")
        if self.role not in ROLES:
            raise ValueError(f"Channel {self.name!r} has unknown role {self.role!r}.")
        if self.role == "flag" and (self.low, self.high) != (0.0, 1.0):
            raise ValueError(f"Flag channel {self.name!r} must run from 0 to 1.")
        unknown = set(self.senses) - set(SENSE_KINDS)
        if unknown:
            raise ValueError(f"Channel {self.name!r} names unknown senses {sorted(unknown)}.")
        if self.source == "body" and self.senses:
            raise ValueError(f"Body channel {self.name!r} cannot be reported by a sense.")
        if self.ambient and self.source != "world":
            raise ValueError(f"Channel {self.name!r}: only a world channel can be ambient.")
        if self.target is not None and self.role not in ("bearing", "closeness"):
            raise ValueError(
                f"Channel {self.name!r}: only bearing and closeness rows have a target."
            )
        if self.role == "closeness" and self.target is None:
            raise ValueError(f"Closeness channel {self.name!r} needs a target.")
        if self.target is not None and self.target not in TARGETS:
            raise ValueError(f"Channel {self.name!r} has unknown target {self.target!r}.")

    @property
    def is_flag(self) -> bool:
        return self.role == "flag"

    def clamp(self, value: float) -> float:
        """The value as the brain sees it: finite, inside the range (a flag is 0.0 or 1.0)."""
        if self.is_flag:
            return 1.0 if value else 0.0
        if not math.isfinite(value):
            raise ValueError(f"Brain input {self.name!r} must be a finite number, got {value}.")
        return min(self.high, max(self.low, value))


def _pair(
    target: str, senses: tuple[str, ...], scaled_by: str | None = None, what: str = ""
) -> tuple[InputChannel, ...]:
    return (
        InputChannel(
            f"{target}_direction", -1.0, 1.0, "world", "bearing", senses, target,
            description=f"Bearing to the nearest {what or target}, -1 hard left to +1 hard right.",
        ),
        InputChannel(
            f"{target}_closeness", 0.0, 1.0, "world", "closeness", senses, target, scaled_by,
            description=f"Closeness of the nearest {what or target}: 1 in contact, 0 out of reach.",
        ),
    )  # fmt: skip


INPUT_CHANNELS: tuple[InputChannel, ...] = (
    InputChannel("energy_ratio", 0.0, 1.0, "body", description="Energy as a fraction of the store."),
    InputChannel("health_ratio", 0.0, 1.0, "body", description="Health as a fraction of maximum."),
    InputChannel("vitality", 0.0, 1.0, "body", description="Age and wear, 1 in the prime."),
    InputChannel("ready_to_mate", 0.0, 1.0, "body", "flag", description="Mating cooldown is over."),
    *_pair("plant", ("vision", "smell")),
    *_pair("prey", ("vision", "hearing", "smell"), "aggression", "possible prey"),
    *_pair("threat", ("vision", "hearing", "smell"), "fear", "threat"),
    *_pair("mate", ("vision", "hearing", "smell"), "repro_drive", "possible mate"),
    InputChannel("touching", 0.0, 1.0, "world", "flag", ("touch",), description="Something is in contact."),
    InputChannel("alarm_strength", 0.0, 1.0, "world", "strength", ("hearing",), description="Alarm call heard."),
    InputChannel("mating_call_strength", 0.0, 1.0, "world", "strength", ("hearing",), description="Mating call heard."),
    InputChannel("call_direction", -1.0, 1.0, "world", "bearing", ("hearing",), description="Bearing to the loudest call."),
    InputChannel("crowding", 0.0, 1.0, "world", "level", ("vision", "hearing"), description="Other animals in reach."),
    InputChannel("pain", 0.0, 1.0, "body", description="Health lost since the last decision; 20% of maximum or more reads 1."),
    InputChannel("daylight", 0.0, 1.0, "world", "level", ambient=True, description="0 full night, 1 full day."),
    InputChannel("relative_size", -1.0, 1.0, "world", "level", ("vision", "hearing"), description="Size of the nearest prey or threat against its own: log2(mass ratio) / 2."),
    # Added with SENSE.14 (animal layout v8), after the rows above so their order is unchanged.
    *_pair("young", ("vision", "hearing", "smell"), "parenting", "own young still dependent on it"),
    InputChannel("mate_similarity", 0.0, 1.0, "world", "level", ("vision", "hearing", "smell"), description="How alike the nearest possible mate's genome is to its own: 1 identical, 0 as different as strangers."),
    InputChannel("tiredness", 0.0, 1.0, "body", description="Time awake as a share of a day; 0 just woken, 1 a whole day without sleep."),
    InputChannel("edge_direction", -1.0, 1.0, "world", "bearing", ("vision", "touch"), description="Bearing to the nearest edge of the world, -1 hard left to +1 hard right."),
    InputChannel("edge_closeness", 0.0, 1.0, "world", "level", ("vision", "touch"), description="Closeness of the nearest edge of the world: 1 in contact, 0 out of reach."),
    InputChannel("clock_sin", -1.0, 1.0, "world", "level", ambient=True, description="Sine of the position in the day (0 midnight): with the cosine it tells dawn from dusk."),
    InputChannel("clock_cos", -1.0, 1.0, "world", "level", ambient=True, description="Cosine of the position in the day (1 midnight, -1 noon)."),
)  # fmt: skip


def validate_channels(channels: Iterable[InputChannel]) -> tuple[InputChannel, ...]:
    """The channels as a tuple, after checking the table as a whole."""
    rows = tuple(channels)
    names = [c.name for c in rows]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate channel names in the sense-channel table.")
    for target in {c.target for c in rows if c.target}:
        roles = sorted(c.role for c in rows if c.target == target)
        if roles != ["bearing", "closeness"]:
            raise ValueError(f"Target {target!r} needs exactly one bearing and one closeness row.")
    return rows


def body_channels(channels: Iterable[InputChannel] = INPUT_CHANNELS) -> tuple[InputChannel, ...]:
    """The rows the animal fills in from its own state."""
    return tuple(c for c in channels if c.source == "body")


def world_channels(channels: Iterable[InputChannel] = INPUT_CHANNELS) -> tuple[InputChannel, ...]:
    """The rows the sensing step fills in; these are the fields of ``Percepts``."""
    return tuple(c for c in channels if c.source == "world")


def channels_for_target(
    target: str, channels: Iterable[InputChannel] = INPUT_CHANNELS
) -> tuple[InputChannel, ...]:
    """The bearing and closeness rows of one class of thing."""
    return tuple(c for c in channels if c.target == target)


def senses_reporting(
    name: str, channels: Iterable[InputChannel] = INPUT_CHANNELS
) -> tuple[str, ...]:
    """Which senses may report a channel."""
    for c in channels:
        if c.name == name:
            return c.senses
    raise KeyError(f"No sense channel named {name!r}.")


def input_names(channels: Iterable[InputChannel] = INPUT_CHANNELS) -> tuple[str, ...]:
    return tuple(c.name for c in channels)


def percepts_class(
    channels: Iterable[InputChannel] = INPUT_CHANNELS,
    name: str = "Percepts",
    module: str = __name__,
) -> type:
    """Build the frozen ``Percepts`` dataclass: one field per world channel, defaulting to "nothing"
    (0.0, or False for a flag), plus ``senses_nothing``."""
    fields: list[tuple[str, type, Any]] = [
        (c.name, bool if c.is_flag else float, field(default=False if c.is_flag else 0.0))
        for c in world_channels(channels)
    ]

    sensed = tuple(c.name for c in world_channels(channels) if not c.ambient)

    def senses_nothing(self: Any) -> bool:
        """True when the world reports nothing at all: no creature, plant, contact, call or crowd.
        The time of day is not a sense and does not count."""
        blank = type(self)()
        return all(getattr(self, n) == getattr(blank, n) for n in sensed)

    cls = make_dataclass(
        name,
        fields,
        frozen=True,
        namespace={"senses_nothing": property(senses_nothing)},
        module=module,
    )
    cls.__doc__ = (
        'What the world tells a creature about its surroundings; everything defaults to "nothing". '
        "Generated from the sense-channel table (`SENSE.8`): one field per world channel. "
        "Bearings run -1 to 1, closeness and strengths 0 to 1; values outside the range are clamped "
        "when the inputs are built."
    )
    return cls


def inputs_builder(
    channels: Iterable[InputChannel],
    temperament_factor: Callable[[str, Any], float],
) -> Callable[..., tuple[float, ...]]:
    """A ``build_inputs`` function for a channel table.

    The result takes ``percepts`` (with the world channels), an optional ``temperament`` and one
    keyword per body channel, and returns the inputs in table order, each clamped to its range.
    ``temperament_factor(scaled_by, temperament)`` gives the multiplier for a scaled channel.
    """
    rows = validate_channels(channels)
    body_names = {c.name for c in body_channels(rows)}

    def build_inputs(percepts: Any, temperament: Any = None, **body: float) -> tuple[float, ...]:
        missing = body_names - body.keys()
        extra = body.keys() - body_names
        if missing or extra:
            raise TypeError(
                f"Body inputs must be exactly {sorted(body_names)}; "
                f"missing {sorted(missing)}, unexpected {sorted(extra)}."
            )
        values: list[float] = []
        for c in rows:
            raw = body[c.name] if c.source == "body" else getattr(percepts, c.name)
            value = c.clamp(raw)
            if c.scaled_by is not None and temperament is not None:
                value = min(c.high, value * temperament_factor(c.scaled_by, temperament))
            values.append(value)
        return tuple(values)

    return build_inputs
