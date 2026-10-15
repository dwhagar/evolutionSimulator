"""Where each animal of a family tree goes (UX.39), with no window involved.

``build_layout(view)`` turns a ``FamilyView`` into a tree around the selected animal: its ancestors
above it (father to the left of mother), its descendants below it, one row per generation. An animal
that two paths lead to (a pair of siblings that mated, say) is drawn once for each path, so the picture
stays a tree. Columns are in units of one node's width; rows are generations, negative above the
animal.

The layout is the usual tidy one: leaves take the next free column and a parent sits in the middle of
what hangs from it. The ancestors and the descendants are laid out on their own and then slid
sideways so that the selected animal is the same column in both.
"""

from __future__ import annotations

from dataclasses import dataclass

from evolution_simulator.world.views import FamilyView, KinView

MAX_NODES = 128
"""The most nodes drawn; a bigger tree is cut, descendants first."""


@dataclass(frozen=True)
class Placed:
    kin: KinView
    row: int
    """0 for the selected animal, -1 for its parents, +1 for its children and so on."""
    column: float
    """In node widths from the left edge of the tree."""


@dataclass(frozen=True)
class TreeLayout:
    nodes: tuple[Placed, ...]
    """The selected animal first."""
    edges: tuple[tuple[int, int], ...]
    """``(upper, lower)`` indexes into ``nodes``: a parent above and its child below."""
    width: float
    """The columns used, in node widths (at least 1)."""
    rows: tuple[int, int]
    """The first and last row."""
    forgotten: int
    """Parents the view names that the world no longer remembers (above the selected animal)."""
    cut: bool
    """Nodes were left out to stay within ``MAX_NODES``."""


class _Node:
    __slots__ = ("column", "kids", "kin", "row")

    def __init__(self, kin: KinView, row: int) -> None:
        self.kin = kin
        self.row = row
        self.kids: list[_Node] = []
        self.column = 0.0


def _tidy(root: _Node) -> None:
    """Give every node of the tree a column."""
    next_leaf = 0.0

    def place(node: _Node) -> None:
        nonlocal next_leaf
        if not node.kids:
            node.column = next_leaf
            next_leaf += 1.0
            return
        for kid in node.kids:
            place(kid)
        node.column = (node.kids[0].column + node.kids[-1].column) / 2.0

    place(root)


def _shift(root: _Node, by: float) -> None:
    stack = [root]
    while stack:
        node = stack.pop()
        node.column += by
        stack.extend(node.kids)


def build_layout(view: FamilyView, limit: int = MAX_NODES) -> TreeLayout:
    by_id = {kin.id: kin for kin in view.kin}
    centre = by_id[view.center]
    children: dict[int, list[KinView]] = {}
    for kin in view.kin:
        for parent in kin.parents:
            children.setdefault(parent, []).append(kin)
    for kids in children.values():
        kids.sort(key=lambda k: (k.born, k.id))

    counted = 1
    cut = False
    forgotten = 0

    def grow_up(node: _Node) -> None:
        nonlocal counted, cut, forgotten
        if -node.row >= view.up:
            return
        for parent_id in node.kin.parents:
            parent = by_id.get(parent_id)
            if parent is None:
                forgotten += 1
                continue
            if counted >= limit:
                cut = True
                continue
            counted += 1
            kid = _Node(parent, node.row - 1)
            node.kids.append(kid)
            grow_up(kid)

    def grow_down(node: _Node) -> None:
        nonlocal counted, cut
        if node.row >= view.down:
            return
        for child in children.get(node.kin.id, ()):
            if counted >= limit:
                cut = True
                continue
            counted += 1
            kid = _Node(child, node.row + 1)
            node.kids.append(kid)
            grow_down(kid)

    above, below = _Node(centre, 0), _Node(centre, 0)
    grow_up(above)
    grow_down(below)
    _tidy(above)
    _tidy(below)
    _shift(above, below.column - above.column)  # the selected animal is one column in both
    left = min(_lowest(above), _lowest(below))
    _shift(above, -left)
    _shift(below, -left)
    width = max(_highest(above), _highest(below)) + 1.0

    nodes: list[Placed] = [Placed(centre, 0, above.column)]
    edges: list[tuple[int, int]] = []

    def collect(node: _Node, index: int) -> None:
        for kid in node.kids:
            nodes.append(Placed(kid.kin, kid.row, kid.column))
            kid_index = len(nodes) - 1
            edges.append((kid_index, index) if kid.row < 0 else (index, kid_index))
            collect(kid, kid_index)

    collect(above, 0)
    collect(below, 0)
    rows = (min(p.row for p in nodes), max(p.row for p in nodes))
    return TreeLayout(tuple(nodes), tuple(edges), width, rows, forgotten, cut)


def _lowest(root: _Node) -> float:
    return min(_columns(root))


def _highest(root: _Node) -> float:
    return max(_columns(root))


def _columns(root: _Node) -> list[float]:
    found, stack = [], [root]
    while stack:
        node = stack.pop()
        found.append(node.column)
        stack.extend(node.kids)
    return found
