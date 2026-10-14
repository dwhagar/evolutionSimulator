"""The viewer's copy of the recorder's history (UX.31): sample listeners and ``HistoryMirror``."""

import pytest

from evolution_simulator.history import (
    HistoryMirror,
    Recorder,
    RecorderRules,
    TierRule,
)
from evolution_simulator.session import FakeSimulation

TINY = RecorderRules(
    tiers=(TierRule("day", 1, 3), TierRule("week", 7, 2), TierRule("month", 30, 2)),
    histogram_every=2,
)
"""Small enough that every tier overflows, including the last one that merges its oldest."""


def fake_days(recorder, sim, days, hook=None):
    """Step a fake world ``days`` days, sampling after every step (it has no step listener)."""
    for _ in range(days * 24):
        sim.step()
        if recorder.observe() and hook is not None:
            hook()


def test_a_sample_listener_hears_each_new_single_day_sample():
    sim = FakeSimulation(20, 30, seed=1)
    recorder = Recorder(sim)
    heard = []
    recorder.add_sample_listener(heard.append)
    fake_days(recorder, sim, 5)
    assert [s.day for s in heard] == [1, 2, 3, 4, 5]
    assert all(s.span == 1 for s in heard)
    recorder.remove_sample_listener(heard.append)
    recorder.remove_sample_listener(heard.append)  # not there: nothing happens
    fake_days(recorder, sim, 1)
    assert len(heard) == 5


@pytest.mark.parametrize("rules", [None, TINY], ids=["default tiers", "tiny tiers"])
def test_a_mirror_fed_the_new_samples_equals_the_recorder(rules):
    sim = FakeSimulation(20, 30, seed=2)
    recorder = Recorder(sim, rules)
    mirror = HistoryMirror()
    assert not mirror.ready
    mirror.reset(recorder.rules, recorder.history())
    assert mirror.ready
    recorder.add_sample_listener(lambda sample: mirror.push([sample]))
    for day in range(1, 160):
        fake_days(recorder, sim, 1)
        assert mirror.history() == recorder.history(), f"differs on day {day}"
    assert len(recorder.history()) == recorder.sample_count


def test_a_mirror_started_late_is_reset_by_a_full_history():
    sim = FakeSimulation(20, 30, seed=3)
    recorder = Recorder(sim, TINY)
    fake_days(recorder, sim, 40)
    mirror = HistoryMirror()
    mirror.reset(recorder.rules, recorder.history())
    recorder.add_sample_listener(lambda sample: mirror.push([sample]))
    fake_days(recorder, sim, 40)
    assert mirror.history() == recorder.history()


def test_a_mirror_refuses_samples_before_it_has_a_history():
    sim = FakeSimulation(5, 5)
    recorder = Recorder(sim)
    fake_days(recorder, sim, 2)
    mirror = HistoryMirror()
    with pytest.raises(ValueError, match="full history"):
        mirror.push(recorder.history().samples())
    with pytest.raises(ValueError, match="no history"):
        mirror.history()


def test_a_mirror_refuses_a_history_that_does_not_fit_the_rules():
    sim = FakeSimulation(5, 5)
    recorder = Recorder(sim)
    with pytest.raises(ValueError, match="tiers"):
        HistoryMirror().reset(TINY, recorder.history())
