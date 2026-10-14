"""The world view slot (UX.12 replaces this)."""

from evolution_simulator.session import Frame
from evolution_simulator.viewer.panels._placeholder import Placeholder
from evolution_simulator.viewer.registry import PanelSpec, ViewerContext


def _line(frame: Frame) -> str:
    width, height = frame.world_size[0], frame.world_size[1]
    return (
        f"{width:g} by {height:g} units, {frame.animal_count} animals, "
        f"{frame.plant_count} plants, {frame.corpse_count} corpses"
    )


def build(context: ViewerContext) -> Placeholder:
    return Placeholder(context, "World view", "UX.12", _line)


PANEL = PanelSpec(id="world", title="World", area="center", factory=build, order=10)
