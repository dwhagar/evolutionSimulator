"""The time and speed controls slot (UX.13 replaces this)."""

from evolution_simulator.session import Frame
from evolution_simulator.viewer.panels._placeholder import Placeholder
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext


def _line(frame: Frame) -> str:
    return f"{frame.elapsed}, {'night' if frame.is_night else 'day'} {frame.day}"


def build(context: ViewerContext) -> Placeholder:
    return Placeholder(context, "Controls", "UX.13", _line)


PANEL = PanelSpec(id="controls", title="Controls", area="top", factory=build, order=10)
