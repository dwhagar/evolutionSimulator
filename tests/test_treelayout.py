"""Where the animals of a family tree go (UX.39): no window needed."""

from evolution_simulator.deaths import DeathCause
from evolution_simulator.viewer.inspector.treelayout import build_layout
from evolution_simulator.world.ancestry import AncestryBook


def book_of(*rows):
    book = AncestryBook()
    for animal_id, parents in rows:
        book.born(animal_id, parents, animal_id % 2, animal_id, (0.0, 0.0))
    return book


def place(layout):
    return {(p.kin.id, p.row): p.column for p in layout.nodes}


def test_a_lone_animal_is_one_node():
    layout = build_layout(book_of((1, ())).family_of(1))
    assert [(p.kin.id, p.row, p.column) for p in layout.nodes] == [(1, 0, 0.0)]
    assert layout.edges == () and layout.width == 1.0 and layout.rows == (0, 0)
    assert layout.forgotten == 0 and not layout.cut


def test_parents_sit_above_father_left_and_the_child_between_them():
    layout = build_layout(book_of((1, ()), (2, ()), (3, (1, 2))).family_of(3))
    columns = place(layout)
    assert columns == {(3, 0): 0.5, (1, -1): 0.0, (2, -1): 1.0}
    assert layout.width == 2.0 and layout.rows == (-1, 0)
    assert sorted(layout.edges) == [(1, 0), (2, 0)]  # (upper, lower) as indexes into the nodes
    assert layout.nodes[0].kin.id == 3


def test_children_hang_below_in_birth_order_and_the_parent_is_centred_over_them():
    book = book_of((1, ()), (2, (1,)), (3, (1,)), (4, (1,)))
    layout = build_layout(book.family_of(1))
    assert place(layout) == {(1, 0): 1.0, (2, 1): 0.0, (3, 1): 1.0, (4, 1): 2.0}
    assert layout.rows == (0, 1) and layout.width == 3.0
    assert sorted(layout.edges) == [(0, 1), (0, 2), (0, 3)]


def test_ancestors_and_descendants_share_the_selected_animals_column():
    #  1 2        parents 1 and 2 above 3; children 4, 5, 6 below it
    book = book_of((1, ()), (2, ()), (3, (1, 2)), (4, (3,)), (5, (3,)), (6, (3,)))
    columns = place(build_layout(book.family_of(3)))
    assert columns[(3, 0)] == 1.0 == (columns[(4, 1)] + columns[(6, 1)]) / 2
    assert columns[(1, -1)] == 0.5 and columns[(2, -1)] == 1.5
    assert min(columns.values()) >= 0.0


def test_a_wider_side_is_never_cut_off_on_the_left():
    book = book_of(*[(n, ()) for n in range(1, 9)], (9, tuple(range(1, 3))), (10, (9,)), (11, (9,)))
    layout = build_layout(book.family_of(9))
    assert min(p.column for p in layout.nodes) == 0.0
    assert layout.width >= max(p.column for p in layout.nodes) + 1.0


def test_an_animal_reached_by_two_paths_is_drawn_for_each():
    book = book_of((1, ()), (2, (1,)), (3, (1,)), (4, (2, 3)))  # siblings 2 and 3 mated
    layout = build_layout(book.family_of(4))
    shown = sorted(p.kin.id for p in layout.nodes)
    assert shown == [1, 1, 2, 3, 4]
    assert len(layout.edges) == len(layout.nodes) - 1  # still a tree


def test_a_forgotten_ancestor_is_counted_and_not_drawn():
    book = AncestryBook(max_dead=0)
    for animal_id, parents in ((1, ()), (2, (1,)), (3, (2,))):
        book.born(animal_id, parents, 0, 0, (0.0, 0.0))
    book.died(1, 5, DeathCause.OLD_AGE)
    layout = build_layout(book.family_of(3))
    assert sorted(p.kin.id for p in layout.nodes) == [2, 3] and layout.forgotten == 1


def test_a_big_tree_is_cut_at_the_limit():
    rows = [(1, ())] + [(10 + n, (1,)) for n in range(40)]
    view = AncestryBook()
    for animal_id, parents in rows:
        view.born(animal_id, parents, 0, animal_id, (0.0, 0.0))
    layout = build_layout(view.family_of(1), limit=10)
    assert len(layout.nodes) == 10 and layout.cut
    assert len(layout.edges) == 9
