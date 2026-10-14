"""A form generated from a frozen config dataclass (UX.17).

``ConfigForm(default)`` looks at the dataclass ``default`` is an instance of and builds an editor for
each field: a check box for a ``bool``, a text box for numbers, text and tuples, a collapsible
section for a nested dataclass, and a section with an *enabled* box for ``X | None`` (a day cycle or
learning that can be switched off). Nothing in it names a field, so what ``TraitRules`` grows later
appears in the form by itself, with the explanation written under the field in the source as its
tooltip.

- ``value()`` builds the dataclass from what is typed, running the classes' own checks, and raises
  ``ConfigError`` (with the dotted path of the field) when something does not fit.
- ``set_value(instance)`` fills the form from an instance.
- A field that differs from ``default`` has a bold label, and its section says how many changed.
- ``set_filter(text)`` hides the fields that do not match, so one of a hundred and fifty is quick to
  find.
"""

from __future__ import annotations

import ast
from collections.abc import Collection
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.viewer.configdata import (
    class_doc,
    coerce,
    field_info,
    is_config_class,
    optional_of,
)

INVALID_STYLE = "border: 1px solid #c0392b;"


class ConfigError(ValueError):
    """A field of the form does not hold a usable value."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path
        self.message = message


def format_value(value: Any) -> str:
    """How a value is written in a box; ``parse_text`` reads it back."""
    if value is None:
        return "none"
    if isinstance(value, tuple):
        if not any(isinstance(v, tuple) for v in value):
            return ", ".join(format_value(v) for v in value)
        return repr(value)
    if isinstance(value, str):
        return value
    return repr(value)


def parse_text(text: str, hint: Any) -> Any:
    """What a box holds as a value of ``hint``; ``ValueError`` says what was wrong."""
    if hint is str:
        return text
    text = text.strip()
    if hint is int:
        try:
            return int(text.replace("_", ""))
        except ValueError:
            raise ValueError("expected a whole number") from None
    if hint is float:
        try:
            return coerce(float(text), float)
        except ValueError:
            raise ValueError("expected a number") from None
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        raise ValueError("could not read this; write numbers separated by commas") from None
    return coerce(value, hint)


class _Editor:
    """What the form keeps for one field or section."""

    path: str
    widgets: tuple[QWidget, ...] = ()

    def get(self) -> Any:
        raise NotImplementedError

    def set(self, value: Any) -> None:
        raise NotImplementedError

    def leaves(self) -> list[_Leaf]:
        return []

    def filter(self, words: list[str]) -> bool:
        """Show or hide by the words; true if anything here is shown."""
        raise NotImplementedError


class _Leaf(_Editor):
    def __init__(
        self, form: ConfigForm, path: str, name: str, hint: Any, default: Any, doc: str
    ) -> None:
        self.form, self.path, self.hint, self.default = form, path, hint, default
        self.optional = optional_of(hint) is not None
        self.base = optional_of(hint) or hint
        self.label = QLabel(name.replace("_", " "), form)
        self.search = f"{path} {name.replace('_', ' ')} {doc}".lower()
        tip = (
            f"{doc}\n\nDefault: {format_value(default)}"
            if doc
            else f"Default: {format_value(default)}"
        )
        self.label.setToolTip(tip)
        self.edit: QCheckBox | QLineEdit
        if self.base is bool and not self.optional:
            self.edit = QCheckBox(form)
            self.edit.toggled.connect(form._edited)
        else:
            self.edit = QLineEdit(form)
            self.edit.textChanged.connect(form._edited)
        self.edit.setToolTip(tip)
        self.widgets = (self.label, self.edit)
        self.modified = False
        self.valid = True

    def get(self) -> Any:
        if isinstance(self.edit, QCheckBox):
            return self.edit.isChecked()
        text = self.edit.text()
        if self.optional and text.strip().lower() in ("", "none"):
            return None
        try:
            return parse_text(text, self.base)
        except ValueError as error:
            raise ConfigError(self.path, str(error)) from None

    def set(self, value: Any) -> None:
        if isinstance(self.edit, QCheckBox):
            self.edit.setChecked(bool(value))
        else:
            self.edit.setText(format_value(value))

    def leaves(self) -> list[_Leaf]:
        return [self]

    def refresh(self) -> None:
        try:
            self.modified = self.get() != self.default
            self.valid = True
        except ConfigError:
            self.modified, self.valid = True, False
        font = self.label.font()
        font.setBold(self.modified)
        self.label.setFont(font)
        if isinstance(self.edit, QLineEdit):
            self.edit.setStyleSheet("" if self.valid else INVALID_STYLE)

    def filter(self, words: list[str]) -> bool:
        shown = all(word in self.search for word in words)
        for widget in self.widgets:
            widget.setVisible(shown)
        return shown


class _Section(_Editor):
    """A dataclass: a header that folds its fields, and an *enabled* box when it can be ``None``."""

    def __init__(
        self,
        form: ConfigForm,
        path: str,
        name: str,
        cls: type,
        default: Any,
        *,
        optional: bool,
        skip: Collection[str] = (),
        root: bool = False,
        off_by_default: bool = False,
    ) -> None:
        self.form, self.path, self.cls, self.optional = form, path, cls, optional
        self.default = default
        self.off_by_default = off_by_default
        """The default of an optional section is ``None`` (``default`` is then a blank instance)."""
        self.title = name.replace("_", " ").capitalize()
        self.skip = skip
        self.children: dict[str, _Editor] = {}
        self.expanded = root
        self._expanded_by_user = root
        self.widget = QWidget(form)
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        self.body = QWidget(self.widget)
        self.layout = QFormLayout(self.body)
        self.layout.setContentsMargins(14 if not root else 0, 2, 0, 6)
        self.layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        if not root:
            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            self.toggle = QToolButton(self.widget)
            self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.toggle.setAutoRaise(True)
            self.toggle.clicked.connect(self._clicked)
            head.addWidget(self.toggle)
            self.enabled = QCheckBox("on", self.widget)
            self.enabled.setToolTip(
                "Off means this part of the world is left out (for example, no night)."
            )
            self.enabled.setVisible(optional)
            self.enabled.setChecked(True)
            self.enabled.toggled.connect(self._enabled_changed)
            head.addWidget(self.enabled)
            head.addStretch(1)
            outer.addLayout(head)
            doc = class_doc(cls)
            if doc:
                self.toggle.setToolTip(doc)
        outer.addWidget(self.body)
        self.widgets = (self.widget,)
        self._build_children()
        self._show_body()

    def _build_children(self) -> None:
        infos = [i for i in field_info(self.cls) if i.name not in self.skip]
        # plain fields first, then the sections, so the numbers are not buried under them
        infos.sort(key=lambda i: is_config_class(optional_of(i.hint) or i.hint))
        for info in infos:
            path = f"{self.path}.{info.name}" if self.path else info.name
            default = getattr(self.default, info.name, info.default)
            inner = optional_of(info.hint)
            kind = inner if inner is not None and is_config_class(inner) else info.hint
            if is_config_class(kind):
                blank = default if default is not None else kind()
                child: _Editor = _Section(
                    self.form,
                    path,
                    info.name,
                    kind,
                    blank,
                    optional=inner is not None,
                    off_by_default=default is None,
                )
                self.layout.addRow(child.widget)
            else:
                child = _Leaf(self.form, path, info.name, info.hint, default, info.doc)
                child.set(default)  # so a section that starts switched off has values to enable
                self.layout.addRow(child.label, child.edit)
            self.children[info.name] = child

    # -- values ----------------------------------------------------------------

    def get(self) -> Any:
        if self.optional and not self.enabled.isChecked():
            return None
        kwargs = {
            name: getattr(self.default, name) for name in self.skip if hasattr(self.default, name)
        }
        for name, child in self.children.items():
            kwargs[name] = child.get()
        try:
            return self.cls(**kwargs)
        except (ValueError, TypeError) as error:
            raise ConfigError(self.path, str(error)) from None

    def set(self, value: Any) -> None:
        if self.optional:
            self.enabled.setChecked(value is not None)
            if value is None:
                return
        for name, child in self.children.items():
            child.set(getattr(value, name))
        self._show_body()

    def leaves(self) -> list[_Leaf]:
        return [leaf for child in self.children.values() for leaf in child.leaves()]

    # -- showing ---------------------------------------------------------------

    def _clicked(self) -> None:
        self.expanded = self._expanded_by_user = not self.expanded
        self._show_body()

    def _enabled_changed(self, on: bool) -> None:
        self.body.setEnabled(on)
        if on and not self.expanded:
            self.expanded = self._expanded_by_user = True
            self._show_body()
        self.form._edited()

    def _show_body(self) -> None:
        if hasattr(self, "toggle"):
            self.toggle.setArrowType(
                Qt.ArrowType.DownArrow if self.expanded else Qt.ArrowType.RightArrow
            )
            self.body.setVisible(self.expanded)

    def refresh(self) -> None:
        """Count what differs from the default in this section and say so in the header."""
        for child in self.children.values():
            if isinstance(child, _Section):
                child.refresh()
        if not hasattr(self, "toggle"):
            return
        count = sum(1 for leaf in self.leaves() if leaf.modified)
        if self.optional and self.enabled.isChecked() == self.off_by_default:
            count += 1
        self.toggle.setText(self.title + (f"  ({count} changed)" if count else ""))
        font = self.toggle.font()
        font.setBold(count > 0)
        self.toggle.setFont(font)

    def filter(self, words: list[str]) -> bool:
        title_match = bool(words) and all(
            word in f"{self.path} {self.title}".lower() for word in words
        )
        # a section whose own name matches shows all its fields
        inner = [] if title_match else words
        shown = False
        for child in self.children.values():
            shown = child.filter(inner) or shown
        shown = shown or title_match or not words
        if hasattr(self, "toggle"):
            self.widget.setVisible(shown)
            self.expanded = shown if words else self._expanded_by_user
            self._show_body()
        return shown


class ConfigForm(QWidget):
    """The form for the dataclass ``default`` is an instance of; ``skip`` names top-level fields
    the form leaves out (the setup screen has its own seed box)."""

    changed = Signal()
    """Something was edited (the form may or may not hold a valid value now)."""

    def __init__(
        self,
        default: Any,
        *,
        value: Any | None = None,
        skip: Collection[str] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if not is_config_class(type(default)):
            raise TypeError(f"ConfigForm needs a dataclass instance, got {default!r}.")
        self.default = default
        self._loading = True  # until built
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._root = _Section(
            self,
            "",
            type(default).__name__,
            type(default),
            default,
            optional=False,
            skip=skip,
            root=True,
        )
        layout.addWidget(self._root.widget)
        layout.addStretch(1)
        self._loading = False
        self.set_value(default if value is None else value)

    # -- the value -------------------------------------------------------------

    def value(self) -> Any:
        """The dataclass the form holds; ``ConfigError`` when a field is not usable."""
        return self._root.get()

    def set_value(self, value: Any) -> None:
        """Fill the form from an instance of the same dataclass (skipped fields are ignored)."""
        self._loading = True
        try:
            self._root.set(value)
        finally:
            self._loading = False
        self._edited()

    def reset(self) -> None:
        self.set_value(self.default)

    def error(self) -> ConfigError | None:
        """What is wrong with the form now, or ``None`` if ``value()`` would work."""
        try:
            self.value()
        except ConfigError as error:
            return error
        return None

    def fields(self) -> dict[str, QWidget]:
        """The input widget of each plain field by dotted path (for tests and the setup screen)."""
        return {leaf.path: leaf.edit for leaf in self._root.leaves()}

    def modified(self) -> list[str]:
        """Dotted paths of the fields that differ from the default."""
        return [leaf.path for leaf in self._root.leaves() if leaf.modified]

    def set_filter(self, text: str) -> None:
        """Show only the fields whose name, path or explanation holds every word of ``text``."""
        self._root.filter(text.lower().split())

    # -- changes ---------------------------------------------------------------

    def _edited(self, *_: object) -> None:
        if self._loading:
            return
        for leaf in self._root.leaves():
            leaf.refresh()
        self._root.refresh()
        self.changed.emit()
