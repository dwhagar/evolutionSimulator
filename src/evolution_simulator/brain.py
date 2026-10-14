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
numbers: 198 for the default 17-8-6 shape.
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
    inputs=17,
    hidden=8,
    outputs=6,
    signed_outputs=(True, False, False, False, False, False),
)
"""The first animal brain (design note): 17 senses, 8 hidden neurons, 6 actions, 198 numbers.
Output 0 is the signed turn; the other five run from 0 to 1."""


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

    __slots__ = ("_hidden", "_outputs", "shape")

    def __init__(self, shape: BrainShape, values: Sequence[float]) -> None:
        if len(values) != shape.weight_count:
            raise ValueError(f"Expected {shape.weight_count} brain values, got {len(values)}.")
        numbers = tuple(float(v) for v in values)
        if not all(math.isfinite(v) for v in numbers):
            raise ValueError("Brain values must be finite numbers.")
        size = shape.neuron_size
        hidden: list[tuple[float, tuple[float, ...]]] = []
        outgoing: list[list[float]] = [[] for _ in range(shape.outputs)]
        for j in range(shape.hidden):
            block = numbers[j * size : (j + 1) * size]
            hidden.append((block[0], block[1 : 1 + shape.inputs]))
            for k, weight in enumerate(block[1 + shape.inputs :]):
                outgoing[k].append(weight)
        output_biases = numbers[shape.hidden * size :]
        object.__setattr__(self, "shape", shape)
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
    def from_values(cls, shape: BrainShape, values: Sequence[float]) -> Brain:
        return cls(shape, values)

    @classmethod
    def zeros(cls, shape: BrainShape) -> Brain:
        """Every weight and bias zero: signed outputs are 0 and the other outputs 0.5."""
        return cls(shape, (0.0,) * shape.weight_count)

    def to_values(self) -> tuple[float, ...]:
        """The flat layout ``from_values`` reads; a round trip gives an equal brain."""
        values: list[float] = []
        for j, (bias, incoming) in enumerate(self._hidden):
            values.append(bias)
            values.extend(incoming)
            values.extend(weights[j] for _, weights in self._outputs)
        values.extend(bias for bias, _ in self._outputs)
        return tuple(values)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Brain):
            return NotImplemented
        return self.shape == other.shape and self.to_values() == other.to_values()

    def __hash__(self) -> int:
        return hash((self.shape, self.to_values()))

    def __repr__(self) -> str:
        s = self.shape
        return f"Brain({s.inputs}-{s.hidden}-{s.outputs})"

    def decide(self, inputs: Sequence[float]) -> tuple[float, ...]:
        """One pass through the network: ``inputs`` in, one number per output out."""
        if len(inputs) != self.shape.inputs:
            raise ValueError(f"Expected {self.shape.inputs} inputs, got {len(inputs)}.")
        hidden = [
            math.tanh(bias + sum(w * x for w, x in zip(weights, inputs)))
            for bias, weights in self._hidden
        ]
        signed = self.shape.signed_outputs
        result: list[float] = []
        for k, (bias, weights) in enumerate(self._outputs):
            total = bias + sum(w * h for w, h in zip(weights, hidden))
            result.append(math.tanh(total) if signed[k] else _logistic(total))
        return tuple(result)

    # -------------------------------------------------------------------------
    # Size, for the energy cost of thinking
    # -------------------------------------------------------------------------

    @property
    def neuron_count(self) -> int:
        """Hidden plus output neurons (inputs are senses, not neurons)."""
        return self.shape.hidden + self.shape.outputs

    def active_connections(self, threshold: float = 0.0) -> int:
        """Connections whose weight has an absolute value above ``threshold``.

        Counts the weights between layers (input to hidden, hidden to output), not the biases.
        """
        count = sum(1 for _, weights in self._hidden for w in weights if abs(w) > threshold)
        count += sum(1 for _, weights in self._outputs for w in weights if abs(w) > threshold)
        return count
