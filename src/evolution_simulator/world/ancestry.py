"""Who is whose child, for animals that are gone too (UX.39).

A living animal knows its parents' ids (``Animal.parents``) and the world can list its living
children, but an animal that dies leaves the world and takes its place in the family with it. The
family tree view needs the dead: grandparents, siblings who did not live, children who died young.
``AncestryBook`` keeps one small record per animal (``Kin``: parents, sex, birth, death and cause,
and its family key) so a tree can be drawn from any animal.

It is bounded: every living animal has a record (there are never more than ``max_animals``), and
the newest ``max_dead`` dead ones are kept, the oldest forgotten first. An ancestor that has been
forgotten is simply missing: a child's ``parents`` still names it, and a tree stops there. A record
is a few dozen bytes, so the default 20,000 dead ones are about a megabyte.

The book is bookkeeping about the past. It changes nothing about what happens next, so it is not in
``World.state_digest``; it is saved with the world (``persistence.py``) so a loaded run keeps its
history, and a save from before it is seeded from the living animals.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from typing import Any

from evolution_simulator.deaths import DeathCause
from evolution_simulator.world.views import FamilyView, KinView

DEFAULT_MAX_DEAD = 20_000
"""How many dead animals are remembered."""
DEFAULT_UP = 4
"""Generations of ancestors a ``FamilyView`` carries by default (a great-great-grandparent)."""
DEFAULT_DOWN = 3
"""Generations of descendants a ``FamilyView`` carries by default (a great-grandchild)."""
DEFAULT_LIMIT = 120
"""The most animals a ``FamilyView`` carries; the descendants are cut first."""


class Kin:
    """One animal's record. ``died`` and ``cause`` are filled in when it dies."""

    __slots__ = ("born", "cause", "died", "family", "id", "parents", "sex")

    def __init__(
        self,
        animal_id: int,
        parents: tuple[int, ...],
        sex: int,
        born: int,
        family: tuple[float, float],
        died: int | None = None,
        cause: DeathCause | None = None,
    ) -> None:
        self.id = animal_id
        self.parents = parents
        self.sex = sex
        self.born = born
        self.family = family
        self.died = died
        self.cause = cause

    def view(self) -> KinView:
        return KinView(
            self.id,
            self.parents,
            self.sex,
            self.born,
            self.died,
            self.cause,
            self.family[0],
            self.family[1],
        )


class AncestryBook:
    def __init__(self, max_dead: int = DEFAULT_MAX_DEAD) -> None:
        if max_dead < 0:
            raise ValueError(f"The book cannot remember {max_dead} dead animals.")
        self.max_dead = max_dead
        self._kin: dict[int, Kin] = {}
        self._children: dict[int, list[int]] = {}
        """Child ids by parent id, in birth order (ids only ever grow)."""
        self._dead: deque[int] = deque()
        """The dead, oldest first, so the forgotten one is always at the front."""

    def __len__(self) -> int:
        return len(self._kin)

    def __contains__(self, animal_id: object) -> bool:
        return animal_id in self._kin

    @property
    def dead_count(self) -> int:
        return len(self._dead)

    def get(self, animal_id: int) -> Kin | None:
        return self._kin.get(animal_id)

    def children_of(self, animal_id: int) -> tuple[int, ...]:
        """The remembered children of an animal, alive or dead, oldest first."""
        return tuple(self._children.get(animal_id, ()))

    # -- keeping it

    def born(
        self,
        animal_id: int,
        parents: tuple[int, ...],
        sex: int,
        tick: int,
        family: tuple[float, float],
    ) -> None:
        """An animal came into the world (a founder has no parents)."""
        self._kin[animal_id] = Kin(animal_id, tuple(parents), sex, tick, family)
        for parent in parents:
            self._children.setdefault(parent, []).append(animal_id)

    def died(self, animal_id: int, tick: int, cause: DeathCause) -> None:
        """An animal left the world. The oldest dead are forgotten past ``max_dead``."""
        kin = self._kin.get(animal_id)
        if kin is None or kin.died is not None:
            return
        kin.died = tick
        kin.cause = cause
        self._dead.append(animal_id)
        while len(self._dead) > self.max_dead:
            self._forget(self._dead.popleft())

    def _forget(self, animal_id: int) -> None:
        kin = self._kin.pop(animal_id, None)
        if kin is None:
            return
        for parent in kin.parents:
            siblings = self._children.get(parent)
            if siblings is not None:
                siblings.remove(animal_id)
                if not siblings:
                    del self._children[parent]
        # Its own children keep their records, and keep naming it as a parent.
        self._children.pop(animal_id, None)

    # -- reading it

    def family_of(
        self,
        animal_id: int,
        up: int = DEFAULT_UP,
        down: int = DEFAULT_DOWN,
        limit: int = DEFAULT_LIMIT,
    ) -> FamilyView | None:
        """The animal, its ancestors ``up`` generations back and its descendants ``down``
        generations on, each once, at most ``limit`` in all (descendants are cut first); ``None``
        for an animal the book does not know."""
        centre = self._kin.get(animal_id)
        if centre is None:
            return None
        found: dict[int, Kin] = {animal_id: centre}
        ancestors = self._walk([centre], up, lambda kin: kin.parents, found, limit)
        descendants = self._walk(
            [centre], down, lambda kin: self._children.get(kin.id, ()), found, limit
        )
        order = [centre, *ancestors, *descendants]
        return FamilyView(
            animal_id,
            up,
            down,
            tuple(kin.view() for kin in order),
            truncated=descendants.truncated,
        )

    def _walk(
        self,
        start: Sequence[Kin],
        generations: int,
        step: Any,
        found: dict[int, Kin],
        limit: int,
    ) -> _Walk:
        """Breadth first from ``start``, ``generations`` deep; adds to ``found`` and returns the
        new records in order."""
        reached = _Walk()
        wave = list(start)
        for _ in range(generations):
            following: list[Kin] = []
            for kin in wave:
                for other_id in step(kin):
                    other = self._kin.get(other_id)
                    if other is None or other_id in found:
                        continue
                    if len(found) >= limit:
                        reached.truncated = True
                        continue
                    found[other_id] = other
                    reached.append(other)
                    following.append(other)
            wave = following
            if not wave:
                break
        return reached

    # -- saving it

    def to_data(self) -> list[list[Any]]:
        """Every record as ``[id, parents, sex, born, family_a, family_b, died, cause]``, by id."""
        return [
            [
                kin.id,
                list(kin.parents),
                kin.sex,
                kin.born,
                kin.family[0],
                kin.family[1],
                kin.died,
                None if kin.cause is None else kin.cause.value,
            ]
            for _, kin in sorted(self._kin.items())
        ]

    @classmethod
    def from_data(
        cls, rows: Iterable[Sequence[Any]], max_dead: int = DEFAULT_MAX_DEAD
    ) -> AncestryBook:
        """The book ``to_data`` wrote. The dead are forgotten in the order they died, as before."""
        book = cls(max_dead)
        dead: list[tuple[int, int]] = []
        for animal_id, parents, sex, born, a, b, died, cause in rows:
            kin = Kin(
                int(animal_id),
                tuple(int(p) for p in parents),
                int(sex),
                int(born),
                (float(a), float(b)),
                None if died is None else int(died),
                None if cause is None else DeathCause(cause),
            )
            book._kin[kin.id] = kin
            for parent in kin.parents:
                book._children.setdefault(parent, []).append(kin.id)
            if kin.died is not None:
                dead.append((kin.died, kin.id))
        for _, animal_id in sorted(dead):
            book._dead.append(animal_id)
        while len(book._dead) > book.max_dead:
            book._forget(book._dead.popleft())
        return book


class _Walk(list):
    """The records a walk reached, and whether it stopped short."""

    truncated: bool = False
