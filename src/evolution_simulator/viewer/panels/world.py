"""The world view slot (UX.12): the world seen from above, with its toolbar.

The drawing lives in ``viewer/worldview/`` (camera, colour modes, gliding, the canvas); this module
only hands the window its panel.
"""

from evolution_simulator.viewer.registry import PanelSpec, ViewerContext
from evolution_simulator.viewer.worldview.panel import WorldPanel


def build(context: ViewerContext) -> WorldPanel:
    return WorldPanel(context)


PANEL = PanelSpec(id="world", title="World", area="center", factory=build, order=10)
