"""The creature inspector slot (UX.14): the dock is in ``viewer/inspector``, whose tabs are the
``tab_*`` modules there (UX.15 adds the brain's)."""

from evolution_simulator.viewer.inspector.panel import InspectorPanel
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext


def build(context: ViewerContext) -> InspectorPanel:
    return InspectorPanel(context)


PANEL = PanelSpec(id="inspector", title="Inspector", area="right", factory=build, order=10)
