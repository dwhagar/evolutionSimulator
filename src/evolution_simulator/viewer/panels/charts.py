"""The charts slot (UX.16 replaces this)."""

from evolution_simulator.viewer.panels._placeholder import Placeholder
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext


def build(context: ViewerContext) -> Placeholder:
    return Placeholder(context, "Charts", "UX.16")


PANEL = PanelSpec(id="charts", title="Charts", area="right", factory=build, order=20)
