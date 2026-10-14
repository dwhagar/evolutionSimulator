"""Reading the frozen config dataclasses generically (UX.17).

The setup screen builds its form from ``WorldConfig`` and the rules tree under it by looking at the
dataclasses themselves, so a field added to ``TraitRules`` (``TRAIT.11`` moves more into it) shows up
without anyone editing the form. This module is that reading, with no Qt in it:

- ``field_info(cls)``: the fields of a dataclass with their resolved types and the one-line
  explanation written under each field in the source.
- ``coerce(value, hint)``: a value checked against a type hint (``int``, ``float``, ``bool``, ``str``,
  tuples, the ``X | None`` of an optional section), lists from JSON turned into tuples.
- ``to_data`` / ``from_data``: a config tree to plain dicts and back, for presets saved as JSON. A
  field missing from the data keeps its default and an unknown one is ignored, so a preset saved
  before a field was added or removed still loads.
"""

from __future__ import annotations

import ast
import inspect
import math
import textwrap
import types
import typing
from dataclasses import MISSING, dataclass, fields, is_dataclass
from functools import cache
from itertools import pairwise
from typing import Any

NoneType = type(None)


@dataclass(frozen=True)
class FieldInfo:
    name: str
    hint: Any
    """The resolved type hint (``float``, ``tuple[float, float]``, a dataclass, ``X | None`` ...)."""
    doc: str
    """What the source says about the field (the string right under it), whitespace collapsed; may
    be empty."""
    default: Any
    """The field's own default, or ``MISSING`` when it has none (the class must then be built from
    a value)."""


def is_config_class(hint: Any) -> bool:
    return isinstance(hint, type) and is_dataclass(hint)


def optional_of(hint: Any) -> Any | None:
    """``X`` for ``X | None`` (a section or value that can be switched off), else ``None``."""
    if typing.get_origin(hint) in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(hint) if a is not NoneType]
        if len(args) == 1 and len(typing.get_args(hint)) == 2:
            return args[0]
    return None


@cache
def field_info(cls: type) -> tuple[FieldInfo, ...]:
    hints = typing.get_type_hints(cls)
    docs = _field_docs(cls)
    out = []
    for f in fields(cls):
        if not f.init:
            continue
        default = f.default
        if default is MISSING and f.default_factory is not MISSING:
            default = f.default_factory()
        out.append(FieldInfo(f.name, hints[f.name], docs.get(f.name, ""), default))
    return tuple(out)


def class_doc(cls: type) -> str:
    """The first paragraph of the class docstring ('' when there is none worth showing)."""
    doc = inspect.getdoc(cls) or ""
    if doc.startswith(f"{cls.__name__}("):  # the signature dataclass writes when there is no doc
        return ""
    return " ".join(doc.split("\n\n")[0].split())


def _field_docs(cls: type) -> dict[str, str]:
    """The string literal under each ``name: type = value`` line of the class body, which is how
    the config files explain a field. Empty when the source cannot be read (a frozen build)."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    except (OSError, TypeError, SyntaxError):
        return {}
    body = tree.body[0].body if tree.body and hasattr(tree.body[0], "body") else []
    docs: dict[str, str] = {}
    for line, after in pairwise(body):
        if (
            isinstance(line, ast.AnnAssign)
            and isinstance(line.target, ast.Name)
            and isinstance(after, ast.Expr)
            and isinstance(after.value, ast.Constant)
            and isinstance(after.value.value, str)
        ):
            docs[line.target.id] = " ".join(after.value.value.split())
    return docs


# -----------------------------------------------------------------------------
# Values
# -----------------------------------------------------------------------------


def coerce(value: Any, hint: Any) -> Any:
    """``value`` as ``hint`` wants it, or ``ValueError`` saying what was expected."""
    inner = optional_of(hint)
    if inner is not None:
        return None if value is None else coerce(value, inner)
    if hint is bool:
        if isinstance(value, bool):
            return value
        raise ValueError(f"expected true or false, got {value!r}")
    if hint is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise ValueError(f"expected a whole number, got {value!r}")
    if hint is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, float) and math.isnan(value):
                raise ValueError("expected a number, got nan")
            return float(value)
        raise ValueError(f"expected a number, got {value!r}")
    if hint is str:
        if isinstance(value, str):
            return value
        raise ValueError(f"expected text, got {value!r}")
    if typing.get_origin(hint) is tuple:
        args = typing.get_args(hint)
        if not isinstance(value, (tuple, list)):
            value = (value,)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(coerce(v, args[0]) for v in value)
        if len(value) != len(args):
            raise ValueError(f"expected {len(args)} values, got {len(value)}")
        return tuple(coerce(v, a) for v, a in zip(value, args))
    raise ValueError(f"a value of type {hint!r} cannot be edited here")


def to_data(value: Any) -> Any:
    """A config tree as plain dicts, lists and scalars (what ``json`` takes)."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_data(getattr(value, f.name)) for f in fields(value) if f.init}
    if isinstance(value, (tuple, list)):
        return [to_data(v) for v in value]
    return value


def from_data(cls: type, data: dict[str, Any]) -> Any:
    """The inverse of ``to_data`` for the dataclass ``cls``; see the module docstring for what is
    missing or unknown. Values that do not fit raise ``ValueError`` (as the classes' own checks
    do)."""
    if not isinstance(data, dict):
        raise ValueError(f"expected a section of {cls.__name__}, got {data!r}")  # noqa: TRY004
    kwargs = {}
    for info in field_info(cls):
        if info.name not in data:
            continue
        kwargs[info.name] = _from_data(info.hint, data[info.name], info.name)
    return cls(**kwargs)


def _from_data(hint: Any, value: Any, name: str) -> Any:
    inner = optional_of(hint)
    if inner is not None:
        return None if value is None else _from_data(inner, value, name)
    try:
        if is_config_class(hint):
            return from_data(hint, value)
        return coerce(value, hint)
    except ValueError as error:
        raise ValueError(f"{name}: {error}") from error
