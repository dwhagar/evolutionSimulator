"""What the Brain tab shows, as plain data with no window involved (UX.15).

``input_rows`` and ``output_rows`` are the labelled bars; ``network_model`` is the wiring as edges
for drawing; ``sense_geometry`` is what the overlays on the world view draw. All of them read an
``AnimalDetail`` and none of them needs the brain to have run: a detail whose ``brain`` is still
``None`` gives rows with no value, and the network still has its wiring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from evolution_simulator.brain import BrainNetwork
from evolution_simulator.brain_adapter import ACTION_THRESHOLD, OUTPUT_NAMES
from evolution_simulator.config import DEFAULT_RULES
from evolution_simulator.sense_channels import INPUT_CHANNELS, InputChannel
from evolution_simulator.sense_genes import vision_reach, working_acuity
from evolution_simulator.world.views import AnimalDetail

OUTPUT_TIPS: dict[str, str] = {
    "turn": "Steering: -1 hard left to +1 hard right",
    "speed": "How fast it wants to move, as a share of its top speed",
    "eat_or_attack": "Eat what it touches, or attack it",
    "seek_mating": "Look for a mate",
    "alarm_call": "Call out a warning",
    "mating_call": "Call for a mate",
}
"""What each output of the network means, in words."""

_ACTIONS = ("eat_or_attack", "seek_mating", "alarm_call", "mating_call")


@dataclass(frozen=True)
class BarRow:
    """One labelled bar. ``value`` is ``None`` until the brain has run; ``low`` and ``high`` are the
    ends of the bar (a bar from -1 to 1 is drawn from its middle)."""

    key: str
    label: str
    group: str
    value: float | None
    low: float
    high: float
    text: str
    tip: str
    marker: float | None = None
    """A tick on the bar: the network's own output where the animal then did something else."""
    threshold: float | None = None
    """A line on the bar: above this an action output counts as "do it"."""

    @property
    def signed(self) -> bool:
        return self.low < 0.0


def _label(name: str) -> str:
    return name.replace("_", " ")


def _text(value: float | None, signed: bool) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}" if signed else f"{value:.2f}"


def input_group(channel: InputChannel) -> str:
    """The heading an input is listed under: what it is about, else which sense reports it."""
    if channel.source == "body":
        return "Body"
    if channel.ambient:
        return "Time and light"
    if channel.target is not None:
        return channel.target.capitalize()
    if len(channel.senses) == 1:
        return channel.senses[0].capitalize()
    return "Surroundings"


def _input_tip(channel: InputChannel) -> str:
    parts = [channel.description or _label(channel.name)]
    parts.append(f"Runs from {channel.low:g} to {channel.high:g}.")
    if channel.senses:
        parts.append("Reported by " + ", ".join(channel.senses) + ".")
    return " ".join(parts)


def input_rows(detail: AnimalDetail) -> list[BarRow]:
    """The inputs in the brain's order, with the last run's values when they are in hand."""
    trace = detail.brain
    values = (
        trace.inputs if trace is not None and len(trace.inputs) == len(INPUT_CHANNELS) else None
    )
    rows = []
    for i, channel in enumerate(INPUT_CHANNELS):
        value = None if values is None else values[i]
        rows.append(
            BarRow(
                key=channel.name,
                label=_label(channel.name),
                group=input_group(channel),
                value=value,
                low=channel.low,
                high=channel.high,
                text=_text(value, channel.low < 0.0),
                tip=_input_tip(channel),
            )
        )
    return rows


def grouped(rows: Sequence[BarRow]) -> list[BarRow]:
    """The rows gathered by group (groups in the order they first appear, rows keeping their order
    inside), for listing. The brain's own order is the order of ``input_rows``."""
    order: dict[str, int] = {}
    for row in rows:
        order.setdefault(row.group, len(order))
    return sorted(rows, key=lambda row: order[row.group])


def output_rows(detail: AnimalDetail) -> list[BarRow]:
    """The six outputs: what the animal decided (the wander fallback included), with the network's
    own proposal as a tick when it differs."""
    decision, trace = detail.decision, detail.brain
    proposal = trace.proposal if trace is not None and len(trace.proposal) == 6 else None
    rows = []
    for i, name in enumerate(OUTPUT_NAMES):
        if decision is not None:
            value: float | None = float(getattr(decision, name))
        elif trace is not None and len(trace.action) == len(OUTPUT_NAMES):
            value = trace.action[i]
        else:
            value = None
        signed = name == "turn"
        tip = OUTPUT_TIPS.get(name, _label(name))
        if name in _ACTIONS:
            tip += f". Above {ACTION_THRESHOLD:g} counts as doing it."
        marker = None
        if proposal is not None and decision is not None and decision.wandering:
            marker = proposal[i]
            if name in ("turn", "speed"):
                tip += " The wander fallback replaced the network's own answer (the tick)."
        rows.append(
            BarRow(
                key=name,
                label=_label(name),
                group="What it decided",
                value=value,
                low=-1.0 if signed else 0.0,
                high=1.0,
                text=_text(value, signed),
                tip=tip,
                marker=marker,
                threshold=ACTION_THRESHOLD if name in _ACTIONS else None,
            )
        )
    return rows


# --- the drawn network --------------------------------------------------------------


@dataclass(frozen=True)
class Edge:
    source: int
    """Index of the neuron in the layer before (an input, or a hidden neuron)."""
    target: int
    weight: float


@dataclass(frozen=True)
class NetworkModel:
    inputs: int
    hidden: int
    outputs: int
    slots: tuple[int, ...]
    """The genome slot each hidden neuron came from."""
    input_edges: tuple[Edge, ...]
    """Input to hidden connections that are switched on (a weight of 0 is off)."""
    output_edges: tuple[Edge, ...]
    """Hidden to output connections that are switched on."""
    max_weight: float
    """The biggest absolute weight, to scale line widths against."""


def network_model(network: BrainNetwork) -> NetworkModel:
    """The wiring as edges, leaving out the connections that are off."""
    input_edges = tuple(
        Edge(i, j, w)
        for j, row in enumerate(network.input_weights)
        for i, w in enumerate(row)
        if w != 0.0
    )
    output_edges = tuple(
        Edge(j, k, w)
        for k, row in enumerate(network.output_weights)
        for j, w in enumerate(row)
        if w != 0.0
    )
    biggest = max((abs(e.weight) for e in (*input_edges, *output_edges)), default=0.0)
    hidden = len(network.hidden_biases)
    slots = network.slots if len(network.slots) == hidden else tuple(range(hidden))
    return NetworkModel(
        inputs=network.inputs,
        hidden=hidden,
        outputs=len(network.output_biases),
        slots=tuple(slots),
        input_edges=input_edges,
        output_edges=output_edges,
        max_weight=biggest,
    )


# --- the senses on the world view ---------------------------------------------------


@dataclass(frozen=True)
class SenseGeometry:
    """How far each outer sense reaches, in world units; ``None`` for one the detail cannot say
    (a stand-in simulation has no sense genes)."""

    vision_range: float | None = None
    fov_half_degrees: float | None = None
    """Degrees either side of the way it faces."""
    hearing_range: float | None = None
    smell_range: float | None = None
    touch_range: float | None = None
    """From the middle of the body, so a little more than its radius."""

    @property
    def any(self) -> bool:
        return any(
            value is not None
            for value in (self.vision_range, self.hearing_range, self.smell_range, self.touch_range)
        )


def sense_geometry(detail: AnimalDetail) -> SenseGeometry:
    """The ranges the overlays draw, worked out as the animal's traits do (acuity lengthens the eye,
    low vitality shortens eye and ear). The vitality floor is the default rules'."""
    t = detail.traits
    floor = DEFAULT_RULES.body.sense_floor
    scale = floor + (1.0 - floor) * min(1.0, max(0.0, detail.vitality))
    vision = fov = hearing = smell = touch = None
    if all(key in t for key in ("sight_reach", "sight_fov", "sight_acuity")):
        acuity = working_acuity(t["sight_fov"], t["sight_acuity"])
        vision = vision_reach(t["sight_reach"], acuity) * scale
    if "fov_half_degrees" in t:
        fov = t["fov_half_degrees"]
    if "hearing_range" in t:
        hearing = t["hearing_range"] * scale
    if "smell_range" in t:
        smell = t["smell_range"]
    if "tactile_factor" in t:
        touch = detail.radius * t["tactile_factor"]
    return SenseGeometry(vision, fov, hearing, smell, touch)
