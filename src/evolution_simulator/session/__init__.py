"""The simulation session (UX.6): one simulation run at the speed asked for, driven by commands.

No window code, no threads and no dependencies, so it runs in the simulation process, in a script
or under a test, and the core never imports Qt or numpy. The pieces:

- ``Session``: ``handle(command)`` and ``update()``, which says what to send.
- ``commands``: ``Play``, ``Pause``, ``Step``, ``SetSpeed``, ``Select``, ``Deselect``.
- ``snapshot``: ``Frame``, ``Block`` and ``Status``, the packed picture of the world.
- ``FakeSimulation``: a made-up world with the same face as ``World``, for building screens.
- ``Simulation``: what the session needs from a world (``World`` has all of it).
"""

from evolution_simulator.session.commands import (
    MAX_SPEED,
    Command,
    CommandError,
    Deselect,
    Pause,
    Play,
    Select,
    SetSpeed,
    Step,
)
from evolution_simulator.session.fake import FakeSimulation
from evolution_simulator.session.protocol import Simulation
from evolution_simulator.session.session import (
    Session,
    SessionEvent,
    SessionRules,
    StatusChanged,
    Update,
)
from evolution_simulator.session.snapshot import (
    ANIMAL_COLUMNS,
    ANIMAL_FLAGS,
    CORPSE_COLUMNS,
    FRAME_FORMAT,
    PLANT_COLUMNS,
    PLANT_FLAGS,
    Block,
    Frame,
    Status,
)

__all__ = [
    "ANIMAL_COLUMNS",
    "ANIMAL_FLAGS",
    "CORPSE_COLUMNS",
    "FRAME_FORMAT",
    "MAX_SPEED",
    "PLANT_COLUMNS",
    "PLANT_FLAGS",
    "Block",
    "Command",
    "CommandError",
    "Deselect",
    "FakeSimulation",
    "Frame",
    "Pause",
    "Play",
    "Select",
    "Session",
    "SessionEvent",
    "SessionRules",
    "SetSpeed",
    "Simulation",
    "Status",
    "StatusChanged",
    "Step",
    "Update",
]
