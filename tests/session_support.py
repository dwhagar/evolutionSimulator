"""Recipes that fail on purpose, importable by a spawned simulation process."""

from evolution_simulator.session import FakeSimulation


class BrokenRecipe:
    """A recipe that cannot build its simulation."""

    def __call__(self):
        raise RuntimeError("the world would not build")


class FailsAtTick:
    """A made-up world whose step fails at the given tick."""

    def __init__(self, tick: int = 3) -> None:
        self.tick = tick

    def __call__(self):
        return _FailingSimulation(self.tick)


class _FailingSimulation(FakeSimulation):
    def __init__(self, fail_at: int) -> None:
        super().__init__(10, 10)
        self._fail_at = fail_at

    def step(self):
        if self.tick + 1 >= self._fail_at:
            raise ValueError(f"the simulation broke at tick {self._fail_at}")
        return super().step()
