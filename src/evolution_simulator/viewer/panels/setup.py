"""The setup screen (UX.17): choose a world and start a new run.

A dock on the left, closed at first; File > New run (Ctrl+N) opens it. From the top:

- **Presets**: a few built-in starting points and the user's own (saved in the viewer settings under
  ``setup/presets``), with a note on what the chosen one is.
- **Counts and seed**: animals, plants, whether the founders carry the seeded brains, the seed of the
  world and a button for a random one.
- **Settings**: a form generated from the frozen ``WorldConfig`` and the rules under it
  (``viewer.config_form``), with a filter box. Nothing in it names a field.
- **Run name**: what the saved run is called (empty names it after its seed).
- **Start run**: sends ``NewRun`` through the backend, then saves the run at once (``RunManager``;
  the owner's default is that history is always recorded), so the run is in the list from tick 0. Nothing is started while any box holds
  something that does not fit; the line under the form says what is wrong. A run that was saved
  (UX.18) gets its last checkpoint and is detached first; one that was never saved is only thrown
  away after a yes.

The last run started is remembered (``setup/last``) and comes back the next time the program opens.
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from evolution_simulator.runs import RunError
from evolution_simulator.session import RunStarted
from evolution_simulator.viewer.config_form import ConfigError, ConfigForm
from evolution_simulator.viewer.presets import BUILTIN_PRESETS, Preset, RunSetup
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext
from evolution_simulator.viewer.run_manager import RunManager
from evolution_simulator.world.world import WorldConfig

log = logging.getLogger(__name__)

PRESETS_KEY = "setup/presets"
LAST_KEY = "setup/last"
SEED_LIMIT = 2**32
MAX_COUNT = 1_000_000
"""The most a count box takes; the real cap is ``max_animals`` and ``max_plants`` in the form, which
``NewRun`` checks."""


class SetupPanel(QWidget):
    def __init__(
        self,
        context: ViewerContext,
        *,
        settings: QSettings | None = None,
        confirm: Callable[[str], bool] | None = None,
        ask_name: Callable[[], str | None] | None = None,
    ) -> None:
        """``settings`` is where presets and the last run are kept (the window's, by default);
        ``confirm`` is asked before a run in progress is thrown away, ``ask_name`` for the name of a
        preset being saved. Tests pass their own; the defaults open a message box."""
        super().__init__()
        self.context = context
        self.settings = settings if settings is not None else context.settings
        self._confirm = confirm or self._ask_yes_no
        self._ask_name = ask_name or self._ask_text
        self.preset: Preset | None = None
        self.user_presets: dict[str, Preset] = {}
        self._applying = False
        self.setMinimumWidth(380)

        self.presets = QComboBox()
        self.save_button = QPushButton("Save as preset...")
        self.delete_button = QPushButton("Delete")
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.animals = self._count_box("Animals the world starts with.")
        self.plants = self._count_box("Plants the world starts with.")
        self.seeded = QCheckBox("Founders have the seeded brain")
        self.seeded.setToolTip(
            "Off leaves the first animals' brains random; those mostly die before they breed."
        )
        self.seed = QLineEdit()
        self.seed.setToolTip("The same seed, settings and counts give the same run.")
        self.name = QLineEdit()
        self.name.setPlaceholderText("seed 0")
        self.name.setToolTip(
            "What the saved run is called in the list of saved runs; empty names it after its seed."
        )
        self.random_seed = QPushButton("Random")
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter the settings...")
        self.filter.setClearButtonEnabled(True)
        self.form = ConfigForm(WorldConfig(), skip={"seed"})
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.reset_button = QPushButton("Reset to preset")
        self.start_button = QPushButton("Start run")
        self.start_button.setDefault(True)

        self._layout_widgets()
        self._connect()
        self._load_presets()
        self.apply(self._remembered() or BUILTIN_PRESETS[0].setup)
        context.controller.event_received.connect(self._on_event)

    # -------------------------------------------------------------------------
    # Building
    # -------------------------------------------------------------------------

    @staticmethod
    def _count_box(tip: str) -> QSpinBox:
        box = QSpinBox()
        box.setRange(0, MAX_COUNT)
        box.setGroupSeparatorShown(True)
        box.setToolTip(tip)
        return box

    def _layout_widgets(self) -> None:
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(self.presets, 1)
        row.addWidget(self.save_button)
        row.addWidget(self.delete_button)
        layout.addLayout(row)
        layout.addWidget(self.note)
        counts = QHBoxLayout()
        counts.addWidget(QLabel("Animals"))
        counts.addWidget(self.animals, 1)
        counts.addWidget(QLabel("Plants"))
        counts.addWidget(self.plants, 1)
        layout.addLayout(counts)
        seed = QHBoxLayout()
        seed.addWidget(QLabel("Seed"))
        seed.addWidget(self.seed, 1)
        seed.addWidget(self.random_seed)
        layout.addLayout(seed)
        name = QHBoxLayout()
        name.addWidget(QLabel("Run name"))
        name.addWidget(self.name, 1)
        layout.addLayout(name)
        layout.addWidget(self.seeded)
        layout.addWidget(self.filter)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)

    def _connect(self) -> None:
        self.presets.activated.connect(self._preset_chosen)
        self.save_button.clicked.connect(self.save_preset)
        self.delete_button.clicked.connect(self.delete_preset)
        self.random_seed.clicked.connect(self.pick_random_seed)
        self.filter.textChanged.connect(self.form.set_filter)
        self.reset_button.clicked.connect(self.reset)
        self.start_button.clicked.connect(self.start)
        for box in (self.animals, self.plants):
            box.valueChanged.connect(self._edited)
        self.seeded.toggled.connect(self._edited)
        self.seed.textChanged.connect(self._edited)
        self.seed.textChanged.connect(self._name_hint)
        self.form.changed.connect(self._edited)

    # -------------------------------------------------------------------------
    # The setup in the boxes
    # -------------------------------------------------------------------------

    def setup(self) -> RunSetup:
        """What the boxes hold; ``ValueError`` (``ConfigError`` for the form) if it does not fit."""
        text = self.seed.text().strip().replace("_", "")
        try:
            seed = int(text)
        except ValueError:
            raise ConfigError("seed", "expected a whole number") from None
        config = replace(self.form.value(), seed=seed)
        return RunSetup(self.animals.value(), self.plants.value(), self.seeded.isChecked(), config)

    def apply(self, setup: RunSetup) -> None:
        """Put a setup in the boxes."""
        self._applying = True
        try:
            self.animals.setValue(setup.animals)
            self.plants.setValue(setup.plants)
            self.seeded.setChecked(setup.seeded)
            self.seed.setText(str(setup.config.seed))
            self.form.set_value(setup.config)
        finally:
            self._applying = False
        self._edited()

    def _name_hint(self, text: str) -> None:
        self.name.setPlaceholderText(f"seed {text.strip() or 0}")

    def pick_random_seed(self) -> None:
        self.seed.setText(str(random.SystemRandom().randrange(SEED_LIMIT)))

    def reset(self) -> None:
        """Back to the chosen preset (keeping the seed in the box)."""
        preset = self.preset or BUILTIN_PRESETS[0]
        self.apply(replace(preset.setup, config=replace(preset.setup.config, seed=self._seed())))

    def _seed(self) -> int:
        try:
            return int(self.seed.text().strip().replace("_", ""))
        except ValueError:
            return 0

    def _edited(self, *_: object) -> None:
        if self._applying:
            return
        try:
            setup = self.setup()
            setup.command()
        except ValueError as error:
            self.status.setText(f'<span style="color:#c0392b">{error}</span>')
            self.start_button.setEnabled(False)
        else:
            changed = len(self.form.modified())
            text = f"{setup.animals:,} animals, {setup.plants:,} plants, seed {setup.config.seed}"
            if changed:
                text += f"; {changed} setting{'s' if changed != 1 else ''} changed from the default"
            self.status.setText(text)
            self.start_button.setEnabled(True)
        self._describe()

    def _describe(self) -> None:
        preset = self.preset
        if preset is None:
            self.note.setText("")
            return
        text = preset.description
        try:
            same = replace(self.setup(), config=replace(self.form.value(), seed=0))
        except ValueError:
            same = None
        if same != replace(preset.setup, config=replace(preset.setup.config, seed=0)):
            text += " (edited)"
        self.note.setText(text)

    # -------------------------------------------------------------------------
    # Presets
    # -------------------------------------------------------------------------

    def _load_presets(self) -> None:
        self.user_presets = {}
        raw = self.settings.value(PRESETS_KEY) if self.settings is not None else None
        if isinstance(raw, str) and raw:
            try:
                stored = json.loads(raw)
                for name, text in stored.items():
                    setup = RunSetup.from_json(text)
                    self.user_presets[name] = Preset(name, "Your own preset.", setup)
            except (ValueError, AttributeError):
                log.warning("The saved presets could not be read; ignoring them.", exc_info=True)
        self._fill_combo(self.preset.name if self.preset else BUILTIN_PRESETS[0].name)

    def _fill_combo(self, current: str) -> None:
        self.presets.clear()
        for preset in (*BUILTIN_PRESETS, *self.user_presets.values()):
            self.presets.addItem(preset.name, preset)
        index = self.presets.findText(current)
        self.presets.setCurrentIndex(max(index, 0))
        self.preset = self.presets.currentData()
        self.delete_button.setEnabled(self.preset.name in self.user_presets)

    def _preset_chosen(self, index: int) -> None:
        self.choose_preset(self.presets.itemText(index))

    def choose_preset(self, name: str) -> None:
        """Select a preset by name and fill the boxes from it, keeping the seed in the box."""
        index = self.presets.findText(name)
        if index < 0:
            raise KeyError(name)
        self.presets.setCurrentIndex(index)
        self.preset = self.presets.currentData()
        self.delete_button.setEnabled(self.preset.name in self.user_presets)
        self.reset()

    def save_preset(self) -> bool:
        """Keep the boxes as a preset under a name asked for; false if nothing was saved."""
        try:
            setup = self.setup()
        except ValueError as error:
            self.context.show_message(f"Cannot save a preset: {error}")
            return False
        name = (self._ask_name() or "").strip()
        if not name:
            return False
        if name in {p.name for p in BUILTIN_PRESETS}:
            self.context.show_message(f"{name!r} is a built-in preset; pick another name.")
            return False
        self.user_presets[name] = Preset(name, "Your own preset.", setup)
        self._store_presets()
        self._fill_combo(name)
        self._describe()
        self.context.show_message(f"Saved the preset {name!r}.")
        return True

    def delete_preset(self) -> bool:
        preset = self.preset
        if preset is None or preset.name not in self.user_presets:
            return False
        del self.user_presets[preset.name]
        self._store_presets()
        self._fill_combo(BUILTIN_PRESETS[0].name)
        self.context.show_message(f"Deleted the preset {preset.name!r}.")
        return True

    def _store_presets(self) -> None:
        if self.settings is None:
            return
        stored = {name: p.setup.to_json() for name, p in self.user_presets.items()}
        self.settings.setValue(PRESETS_KEY, json.dumps(stored))
        self.settings.sync()

    def _remembered(self) -> RunSetup | None:
        raw = self.settings.value(LAST_KEY) if self.settings is not None else None
        if not isinstance(raw, str) or not raw:
            return None
        try:
            return RunSetup.from_json(raw)
        except ValueError:
            log.warning("The last setup could not be read; starting from the default.")
            return None

    # -------------------------------------------------------------------------
    # Starting
    # -------------------------------------------------------------------------

    def start(self) -> bool:
        """Start a run from the boxes. Returns whether the backend took the command."""
        try:
            setup = self.setup()
            command = setup.command(self.name.text().strip())
        except ValueError as error:
            self.context.show_message(f"Cannot start: {error}", 8000)
            return False
        manager = RunManager.for_controller(self.context.controller)
        frame = self.context.controller.frame
        if (
            manager.current_run is None
            and frame is not None
            and frame.tick > 0
            and not self._confirm(
                f"The run in progress ({frame.elapsed}, tick {frame.tick:,}) is not saved and "
                "will be lost. Start a new run anyway?"
            )
        ):
            return False
        if manager.current_run is not None:
            manager.detach()  # a saved run gets its last checkpoint, before its world is replaced
        if not self.context.send(command):
            return False
        if self.settings is not None:
            self.settings.setValue(LAST_KEY, setup.to_json())
            self.settings.sync()
        text = (
            f"Started a new run: {setup.animals:,} animals, {setup.plants:,} plants, "
            f"seed {setup.config.seed}. Press Space to play."
        )
        if manager.can_save:  # history is always recorded: the run is saved from its first tick
            try:
                manager.save_now(command.name)
            except (RunError, OSError) as error:
                text = f"Started a new run, but it could not be saved: {error}"
        self.context.show_message(text, 8000)
        return True

    def _ask_yes_no(self, text: str) -> bool:
        answer = QMessageBox.question(self, "Start a new run?", text)
        return answer == QMessageBox.StandardButton.Yes

    def _ask_text(self) -> str | None:
        name, ok = QInputDialog.getText(self, "Save preset", "Name of the preset:")
        return name if ok else None

    def _on_event(self, event: object) -> None:
        if isinstance(event, RunStarted):
            manager = RunManager.for_controller(self.context.controller)
            # a saved run names itself (with when it was saved); an unsaved one is just "world"
            self.context.set_run_label(manager.label if manager.current_run else event.label)

    def reveal(self) -> None:
        """Bring the dock this panel sits in to the front (File > New run)."""
        widget = self.parentWidget()
        while widget is not None and not isinstance(widget, QDockWidget):
            widget = widget.parentWidget()
        if widget is not None:
            widget.show()
            widget.raise_()
        self.start_button.setFocus()


def build(context: ViewerContext) -> SetupPanel:
    panel = SetupPanel(context)
    new_run = QAction("&New run...", panel)
    new_run.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
    new_run.triggered.connect(panel.reveal)
    context.actions["new_run"] = new_run
    context.add_menu_action("file", new_run)
    return panel


PANEL = PanelSpec(id="setup", title="New run", area="left", factory=build, order=10, visible=False)
