"""The creature inspector slot (UX.14 and UX.15 replace this)."""

from evolution_simulator.viewer.panels._placeholder import Placeholder
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext


def build(context: ViewerContext) -> Placeholder:
    return Placeholder(context, "Creature inspector", "UX.14 and UX.15")


PANEL = PanelSpec(id="inspector", title="Inspector", area="right", factory=build, order=10)
