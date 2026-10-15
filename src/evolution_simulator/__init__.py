"""Evolution simulator."""

import sys

MINIMUM_PYTHON = (3, 12)
"""The oldest Python the project supports (the owner's rule, INFRA.11); ``pyproject.toml`` says the
same in ``requires-python`` and a test keeps the two together."""

if sys.version_info < MINIMUM_PYTHON:  # pragma: no cover - needs an old interpreter
    _need = ".".join(str(n) for n in MINIMUM_PYTHON)
    _have = ".".join(str(n) for n in sys.version_info[:3])
    raise RuntimeError(
        f"Evolution Simulator needs Python {_need} or newer; this is Python {_have}."
    )

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("evolution-simulator")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.0.0"
