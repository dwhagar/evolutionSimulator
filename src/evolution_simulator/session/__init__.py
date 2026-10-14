"""The simulation session (UX.6): one simulation run at the speed asked for, driven by commands.

No window code, no threads and no dependencies, so it runs in the simulation process, in a script
or under a test, and the core never imports Qt or numpy. The pieces:

- ``Session``: ``handle(command)`` and ``update()``, which says what to send.
- ``commands``: ``Play``, ``Pause``, ``Step``, ``SetSpeed``, ``Select``, ``Deselect``, ``NewRun``.
- ``snapshot``: ``Frame``, ``Block`` and ``Status``, the packed picture of the world.
- ``FakeSimulation``: a made-up world with the same face as ``World``, for building screens.
- ``Simulation``: what the session needs from a world (``World`` has all of it).
- ``SimClient`` (``ProcessClient``, ``InProcessClient``, ``fake_client``), ``Host`` and ``run_host``:
  the simulation in its own process, the viewer's one way to reach it (UX.7); ``messages`` holds
  what they say to each other and ``WorldSpec`` / ``FakeSpec`` / ``NewRunSpec`` / ``ResumeSpec`` are
  picklable recipes for a simulation. The host also keeps the statistics history (``HistoryBatch``) and
  the run folder (``RunNotice``, ``SaveNow``) of its world (UX.31).
"""

from evolution_simulator.session.client import (
    Inbox,
    InProcessClient,
    ProcessClient,
    SimClient,
    fake_client,
)
from evolution_simulator.session.commands import (
    MAX_SPEED,
    Command,
    CommandError,
    Deselect,
    NewRun,
    Pause,
    Play,
    Select,
    SetSpeed,
    Step,
)
from evolution_simulator.session.fake import FakeSimulation
from evolution_simulator.session.host import Host, HostRules, make_host, run_host
from evolution_simulator.session.messages import (
    Ack,
    CommandRejected,
    Crashed,
    EventBatch,
    HistoryBatch,
    HostInfo,
    Ready,
    RequestHistory,
    RequestPlants,
    RunNotice,
    SaveNow,
    SetFrameRate,
    Shutdown,
    Stopped,
)
from evolution_simulator.session.protocol import Simulation
from evolution_simulator.session.session import (
    RunStarted,
    Session,
    SessionEvent,
    SessionRules,
    StatusChanged,
    Update,
    build_world,
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
from evolution_simulator.session.specs import FakeSpec, NewRunSpec, Prepared, ResumeSpec, WorldSpec

__all__ = [
    "ANIMAL_COLUMNS",
    "ANIMAL_FLAGS",
    "CORPSE_COLUMNS",
    "FRAME_FORMAT",
    "MAX_SPEED",
    "PLANT_COLUMNS",
    "PLANT_FLAGS",
    "Ack",
    "Block",
    "Command",
    "CommandError",
    "CommandRejected",
    "Crashed",
    "Deselect",
    "EventBatch",
    "FakeSimulation",
    "FakeSpec",
    "Frame",
    "HistoryBatch",
    "Host",
    "HostInfo",
    "HostRules",
    "InProcessClient",
    "Inbox",
    "NewRun",
    "NewRunSpec",
    "Pause",
    "Play",
    "Prepared",
    "ProcessClient",
    "Ready",
    "RequestHistory",
    "RequestPlants",
    "ResumeSpec",
    "RunNotice",
    "RunStarted",
    "SaveNow",
    "Select",
    "Session",
    "SessionEvent",
    "SessionRules",
    "SetFrameRate",
    "SetSpeed",
    "Shutdown",
    "SimClient",
    "Simulation",
    "Status",
    "StatusChanged",
    "Step",
    "Stopped",
    "Update",
    "WorldSpec",
    "build_world",
    "fake_client",
    "make_host",
    "run_host",
]
