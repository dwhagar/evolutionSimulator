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


class TickCounter:
    """A big made-up world that writes its tick into shared memory, so a test can see the
    simulation move without reading from the pipe. Frames of this world are about 390 KB, more than
    a pipe holds."""

    def __init__(self, value) -> None:
        self.value = value

    def __call__(self):
        return _CountingSimulation(self.value)


class _CountingSimulation(FakeSimulation):
    def __init__(self, value) -> None:
        super().__init__(3000, 12000, seed=1)
        self._value = value

    def step(self):
        report = super().step()
        self._value.value = self.tick
        return report
