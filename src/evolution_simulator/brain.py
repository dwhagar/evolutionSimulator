"""Brain: a small feedforward neural network that turns what a creature senses into what it does.

A ``Brain`` is a pure function of its weights. It knows nothing about DNA, traits or the world:
``decide(inputs)`` takes a list of numbers and returns a list of numbers. Where the weights come
from (the genome) and what the inputs and outputs mean (the senses and actions) are handled outside,
in ``dna.py``, ``traits.py`` and ``brain_adapter.py``. See ``docs/design/brain.md``.

Network: ``inputs`` -> ``hidden`` neurons (``tanh``) -> ``outputs``. An output is ``tanh`` (range
-1 to 1) when the shape marks it signed, and a logistic curve (range 0 to 1) otherwise. There is no
memory and no randomness, so equal weights and equal inputs always give equal outputs.

Weight layout
-------------
A brain is described by one flat sequence of numbers, grouped per hidden neuron so that a neuron's
whole wiring travels together when genomes are recombined (the "competing conventions" problem in
the design note). For each hidden neuron ``j`` in turn:

    bias_j, weight from input 0 .. inputs-1, weight to output 0 .. outputs-1

followed by the ``outputs`` output biases. That is ``hidden * (inputs + 1 + outputs) + outputs``
numbers: 222 for the default 20-8-6 shape.

Gain
----
``gain`` multiplies every neuron's input sum before its curve, so a high gain makes sharp, nearly
on-off decisions and a low gain makes gradual ones. 1 leaves the network as designed.

Dead zone
---------
A brain can be built with a ``dead_zone``: a weight (not a bias) whose absolute value is at or below
it is off. It does nothing in ``decide`` and is not counted by ``active_connections``, so the
energy cost of a connection and its effect on behaviour use the same threshold (``BRAIN.21``). The
numbers given to the brain, and returned by ``to_values``, are never changed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BrainShape:
    """The size of a network and which outputs are signed (``tanh``) rather than 0 to 1."""

    inputs: int
    hidden: int
    outputs: int
    signed_outputs: tuple[bool, ...] = ()
    """One flag per output; empty means every output is signed."""

    def __post_init__(self) -> None:
        if self.inputs < 1 or self.hidden < 1 or self.outputs < 1:
            raise ValueError("A brain needs at least one input, one hidden neuron and one output.")
        signed = self.signed_outputs or (True,) * self.outputs
        if len(signed) != self.outputs:
            raise ValueError(
                f"Expected {self.outputs} signed-output flags, got {len(self.signed_outputs)}."
            )
        object.__setattr__(self, "signed_outputs", tuple(bool(flag) for flag in signed))

    @property
    def neuron_size(self) -> int:
        """Numbers per hidden neuron: its bias, incoming weights and outgoing weights."""
        return 1 + self.inputs + self.outputs

    @property
    def weight_count(self) -> int:
        """Numbers needed to describe a brain of this shape (weights and biases)."""
        return self.hidden * self.neuron_size + self.outputs

    @property
    def group_sizes(self) -> tuple[int, ...]:
        """Sizes of the blocks that belong together: one per hidden neuron, then the output biases."""
        return (self.neuron_size,) * self.hidden + (self.outputs,)


DEFAULT_SHAPE = BrainShape(
    inputs=28,
    hidden=8,
    outputs=6,
    signed_outputs=(True, False, False, False, False, False),
)
"""The animal brain: 28 inputs (the sense-channel table, 20 until `SENSE.14`), 8 hidden neurons, 6 actions.
Output 0 is the signed turn; the other five run from 0 to 1. It is the shape a seeded brain has; the
genome holds up to ``DEFAULT_BLUEPRINT.max_hidden`` neurons and switches some of them off."""


def _logistic(x: float) -> float:
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


class Brain:
    """An immutable feedforward network with a fixed shape.

    Build one from a flat list of numbers with ``Brain.from_values``; the layout is in the module
    docstring. ``decide`` is the only behaviour.
    """

    __slots__ = ("_hidden", "_outputs", "_values", "dead_zone", "gain", "shape")

    def __init__(
        self,
        shape: BrainShape,
        values: Sequence[float],
        dead_zone: float = 0.0,
        gain: float = 1.0,
    ) -> None:
        if len(values) != shape.weight_count:
            raise ValueError(f"Expected {shape.weight_count} brain values, got {len(values)}.")
        numbers = tuple(float(v) for v in values)
        if not all(math.isfinite(v) for v in numbers):
            raise ValueError("Brain values must be finite numbers.")
        if not (math.isfinite(dead_zone) and dead_zone >= 0.0):
            raise ValueError(f"The dead zone must be a finite number, 0 or more, got {dead_zone}.")
        if not (math.isfinite(gain) and gain > 0.0):
            raise ValueError(f"The gain must be a finite number above 0, got {gain}.")

        def weight(value: float) -> float:
            return 0.0 if abs(value) <= dead_zone else value

        size = shape.neuron_size
        hidden: list[tuple[float, tuple[float, ...]]] = []
        outgoing: list[list[float]] = [[] for _ in range(shape.outputs)]
        for j in range(shape.hidden):
            block = numbers[j * size : (j + 1) * size]
            hidden.append((block[0], tuple(weight(w) for w in block[1 : 1 + shape.inputs])))
            for k, w in enumerate(block[1 + shape.inputs :]):
                outgoing[k].append(weight(w))
        output_biases = numbers[shape.hidden * size :]
        object.__setattr__(self, "shape", shape)
        object.__setattr__(self, "dead_zone", float(dead_zone))
        object.__setattr__(self, "gain", float(gain))
        object.__setattr__(self, "_values", numbers)
        object.__setattr__(self, "_hidden", tuple(hidden))
        object.__setattr__(
            self,
            "_outputs",
            tuple((output_biases[k], tuple(outgoing[k])) for k in range(shape.outputs)),
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Brain is immutable.")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Brain is immutable.")

    @classmethod
    def from_values(
        cls,
        shape: BrainShape,
        values: Sequence[float],
        dead_zone: float = 0.0,
        gain: float = 1.0,
    ) -> Brain:
        return cls(shape, values, dead_zone, gain)

    @classmethod
    def zeros(cls, shape: BrainShape) -> Brain:
        """Every weight and bias zero: signed outputs are 0 and the other outputs 0.5."""
        return cls(shape, (0.0,) * shape.weight_count)

    def to_values(self) -> tuple[float, ...]:
        """The flat layout ``from_values`` reads, as given (the dead zone is not applied); a round
        trip gives an equal brain."""
        return self._values

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Brain):
            return NotImplemented
        return (
            self.shape == other.shape
            and self.dead_zone == other.dead_zone
            and self.gain == other.gain
            and self._values == other._values
        )

    def __hash__(self) -> int:
        return hash((self.shape, self.dead_zone, self.gain, self._values))

    def __repr__(self) -> str:
        s = self.shape
        return f"Brain({s.inputs}-{s.hidden}-{s.outputs})"

    def decide(self, inputs: Sequence[float]) -> tuple[float, ...]:
        """One pass through the network: ``inputs`` in, one number per output out."""
        return self.decide_with_hidden(inputs)[1]

    def decide_with_hidden(
        self, inputs: Sequence[float]
    ) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """Like ``decide`` but also returns the hidden neurons' activations, which learning
        (``BRAIN.24``) logs: ``(hidden, outputs)``."""
        if len(inputs) != self.shape.inputs:
            raise ValueError(f"Expected {self.shape.inputs} inputs, got {len(inputs)}.")
        gain = self.gain
        hidden = tuple(
            math.tanh(gain * (bias + math.sumprod(weights, inputs)))
            for bias, weights in self._hidden
        )
        signed = self.shape.signed_outputs
        result: list[float] = []
        for k, (bias, weights) in enumerate(self._outputs):
            total = gain * (bias + math.sumprod(weights, hidden))
            result.append(math.tanh(total) if signed[k] else _logistic(total))
        return hidden, tuple(result)

    def with_output_offsets(
        self, weight_offsets: Sequence[Sequence[float]], bias_offsets: Sequence[float]
    ) -> Brain:
        """A brain whose output layer is this one's plus learned changes (``BRAIN.24``).

        ``weight_offsets[k][j]`` is added to the weight from hidden neuron ``j`` to output ``k`` and
        ``bias_offsets[k]`` to output ``k``'s bias. The dead zone applies to the sum, so a learned
        change can switch a connection off or on. This brain is not changed.
        """
        shape = self.shape
        if len(weight_offsets) != shape.outputs or len(bias_offsets) != shape.outputs:
            raise ValueError(f"Expected offsets for {shape.outputs} outputs.")
        if any(len(row) != shape.hidden for row in weight_offsets):
            raise ValueError(f"Expected {shape.hidden} weight offsets per output.")
        values = list(self._values)
        size = shape.neuron_size
        out_start = 1 + shape.inputs
        for j in range(shape.hidden):
            for k in range(shape.outputs):
                values[j * size + out_start + k] += weight_offsets[k][j]
        base = shape.hidden * size
        for k in range(shape.outputs):
            values[base + k] += bias_offsets[k]
        return Brain(shape, values, self.dead_zone, self.gain)

    # -------------------------------------------------------------------------
    # Size, for the energy cost of thinking
    # -------------------------------------------------------------------------

    @property
    def neuron_count(self) -> int:
        """Hidden plus output neurons (inputs are senses, not neurons)."""
        return self.shape.hidden + self.shape.outputs

    def active_connections(self, threshold: float = 0.0) -> int:
        """Connections still on whose weight has an absolute value above ``threshold``.

        Weights inside the dead zone are off, so with the default threshold this is every
        connection that takes part in ``decide``. Counts the weights between layers (input to
        hidden, hidden to output), not the biases.
        """
        count = sum(1 for _, weights in self._hidden for w in weights if abs(w) > threshold)
        count += sum(1 for _, weights in self._outputs for w in weights if abs(w) > threshold)
        return count


@dataclass(frozen=True)
class BrainBlueprint:
    """The brain as the genome stores it: room for ``max_hidden`` hidden neurons, each with a gate
    (``BRAIN.23``).

    Each slot is a group of ``2 + inputs + outputs`` values: the gate, the neuron's bias, its weight
    from each input and its weight to each output. After the slots come the ``outputs`` output
    biases. A slot whose gate is above zero holds a neuron that exists in the creature; the others are
    spare code that costs nothing and does nothing until a mutation wakes them. ``build`` turns genome
    values into an ordinary ``Brain`` of whatever size that gives, once, at birth: the shape never
    changes during a life.
    """

    inputs: int
    max_hidden: int
    outputs: int
    signed_outputs: tuple[bool, ...] = ()

    def __post_init__(self) -> None:
        # BrainShape does the checking (sizes, the signed flags); it is also what a build returns.
        shape = BrainShape(self.inputs, self.max_hidden, self.outputs, self.signed_outputs)
        object.__setattr__(self, "signed_outputs", shape.signed_outputs)

    @property
    def neuron_size(self) -> int:
        """Values per slot: gate, bias, incoming weights, outgoing weights."""
        return 2 + self.inputs + self.outputs

    @property
    def value_count(self) -> int:
        """Values the genome holds for the brain."""
        return self.max_hidden * self.neuron_size + self.outputs

    @property
    def group_sizes(self) -> tuple[int, ...]:
        """One group per slot, then the output biases: what recombination keeps together."""
        return (self.neuron_size,) * self.max_hidden + (self.outputs,)

    def slots_on(self, values: Sequence[float]) -> tuple[int, ...]:
        """The slots whose neuron exists: gate above zero. With every gate off the slot with the
        highest gate (the lowest on a tie) is used, so a brain always has one hidden neuron."""
        if len(values) != self.value_count:
            raise ValueError(f"Expected {self.value_count} brain values, got {len(values)}.")
        size = self.neuron_size
        gates = [values[j * size] for j in range(self.max_hidden)]
        on = tuple(j for j, gate in enumerate(gates) if gate > 0.0)
        return on if on else (max(range(self.max_hidden), key=lambda j: (gates[j], -j)),)

    def build(self, values: Sequence[float], dead_zone: float = 0.0, gain: float = 1.0) -> Brain:
        """The creature's brain: the slots that are on, with the dead zone and gain applied."""
        slots = self.slots_on(values)
        size = self.neuron_size
        flat: list[float] = []
        for j in slots:
            flat.extend(values[j * size + 1 : (j + 1) * size])  # everything but the gate
        flat.extend(values[self.max_hidden * size :])
        shape = BrainShape(self.inputs, len(slots), self.outputs, self.signed_outputs)
        return Brain(shape, flat, dead_zone, gain)


DEFAULT_BLUEPRINT = BrainBlueprint(
    inputs=DEFAULT_SHAPE.inputs,
    max_hidden=16,
    outputs=DEFAULT_SHAPE.outputs,
    signed_outputs=DEFAULT_SHAPE.signed_outputs,
)
"""The genome's brain: up to 16 hidden neurons of 36 values each, 582 values in all."""
