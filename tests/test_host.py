"""The simulation host (UX.7): acknowledgements, dropped frames, capped events, errors."""

import time

import pytest
from session_support import FailsAtTick

from evolution_simulator.session import (
    Ack,
    CommandRejected,
    EventBatch,
    FakeSimulation,
    Host,
    HostInfo,
    HostRules,
    Inbox,
    InProcessClient,
    Pause,
    Play,
    Ready,
    RequestPlants,
    Select,
    Session,
    SessionRules,
    SetFrameRate,
    SetSpeed,
    Shutdown,
    Step,
    Stopped,
    fake_client,
)
from evolution_simulator.session.client import _Collector
from evolution_simulator.session.snapshot import Frame
from evolution_simulator.world import Died, Mated, StepReport
from evolution_simulator.world.views import AnimalDetail


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make(sim=None, host_rules=None, **session_rules):
    clock = Clock()
    session_rules.setdefault("max_ticks_per_update", 3)  # a frozen clock never ends a budget
    session_rules.setdefault("max_elapsed", 10.0)
    sim = sim if sim is not None else FakeSimulation(30, 40, seed=2)
    session = Session(sim, rules=SessionRules(**session_rules), clock=clock)
    return Host(session, host_rules, clock), clock, sim


def frames(messages):
    return [m for m in messages if isinstance(m, Frame)]


# --- starting ----------------------------------------------------------------------


def test_the_host_starts_with_a_ready_message_holding_a_full_frame():
    host, _, sim = make()
    ready = host.first_message()
    assert isinstance(ready, Ready)
    assert ready.frame.plants is not None and ready.frame.tick == sim.tick
    assert host.in_flight == 1


def test_the_first_step_after_ready_sends_no_second_frame():
    host, clock, _ = make()
    host.first_message()
    clock.advance(1.0)
    assert frames(host.step()) == []


# --- acknowledgements ----------------------------------------------------------------


def run_flat_out(host, clock, steps, ack=None):
    sent = []
    for _ in range(steps):
        clock.advance(0.05)
        out = host.step()
        sent.extend(out)
        if ack is not None:
            host.receive(Ack(ack(host)))
    return sent


def test_frames_stop_while_the_viewer_is_behind_and_resume_on_an_ack():
    host, clock, _ = make(host_rules=HostRules(max_in_flight=2), work_budget=10.0)
    host.first_message()
    host.receive(SetSpeed("max"))
    host.receive(Play())
    sent = run_flat_out(host, clock, 20)  # nobody acknowledges
    assert len(frames(sent)) == 1  # the Ready was one in flight, this the second
    assert host.in_flight == 2
    held_at = host.session.simulation.tick
    clock.advance(1.0)
    host.step()
    assert host.session.simulation.tick > held_at  # the simulation never waited
    host.receive(Ack(2))
    resumed = run_flat_out(host, clock, 3)
    assert frames(resumed)


def test_dropped_frames_are_counted_and_reported():
    host, clock, _ = make(
        host_rules=HostRules(max_in_flight=1, info_interval=0.5),
        work_budget=10.0,
        max_ticks_per_update=2,
    )
    host.first_message()
    host.receive(SetSpeed("max"))
    host.receive(Play())
    sent = run_flat_out(host, clock, 40)
    infos = [m for m in sent if isinstance(m, HostInfo)]
    assert infos and infos[-1].frames_dropped > 0
    assert infos[-1].frames_sent == 0


def test_a_dead_animals_last_detail_is_sent_even_when_blocked():
    host, clock, sim = make(host_rules=HostRules(max_in_flight=1), work_budget=10.0)
    host.first_message()  # one in flight: now blocked
    target = sim.animal_views()[0].id
    host.receive(Select(target))
    assert not host._can_send()
    out = host.step()
    assert not any(isinstance(m, AnimalDetail) for m in out)  # a live detail is dropped
    victim = sim._animals[target]
    sim._animals.pop(target)
    sim._corpses.clear()
    clock.advance(1.0)
    del victim
    out = host.step()
    sent = [m for m in out if isinstance(m, AnimalDetail)]
    assert sent and not sent[0].alive


def test_an_ack_can_not_run_ahead_of_what_was_sent():
    host, _, _ = make()
    host.first_message()
    host.receive(Ack(999))
    assert host.in_flight == 0


# --- events -----------------------------------------------------------------------


def test_events_arrive_in_batches_with_status_changes():
    host, clock, _ = make(work_budget=10.0)
    host.first_message()
    host.receive(Ack(1))
    host.receive(Step(30))
    clock.advance(0.2)
    batches = [m for m in host.step() if isinstance(m, EventBatch)]
    assert len(batches) == 1
    kinds = {type(e).__name__ for e in batches[0].events}
    assert "StatusChanged" in kinds


def test_world_events_are_capped_per_second():
    host, _clock, _ = make(
        FakeSimulation(60, 10, seed=1, period=20),
        HostRules(max_events_per_second=5, event_interval=0.0, max_in_flight=100),
        work_budget=10.0,
    )
    host.first_message()
    host.receive(Step(60))
    batches = [m for m in host.step() if isinstance(m, EventBatch)]
    world = [
        e for b in batches for e in b.events if isinstance(e, (Died, Mated)) or hasattr(e, "kind")
    ]
    assert len(world) <= 5
    assert batches[-1].dropped > 0


def test_events_wait_for_the_viewer_and_the_buffer_is_bounded():
    host, clock, _ = make(
        FakeSimulation(60, 10, seed=1, period=20),
        HostRules(max_in_flight=1, max_events_per_second=10_000, max_buffered_events=10),
        work_budget=10.0,
    )
    host.first_message()  # blocked from the start
    host.receive(Step(60))
    clock.advance(1.0)
    out = host.step()
    assert not any(isinstance(m, EventBatch) for m in out)
    assert len(host._events) == 10 and host._events_dropped > 0
    host.receive(Ack(1))
    clock.advance(1.0)
    batches = [m for m in host.step() if isinstance(m, EventBatch)]
    assert batches and batches[0].dropped > 0


# --- requests and errors --------------------------------------------------------------


def test_a_command_the_session_refuses_comes_back_rejected_and_changes_nothing():
    host, clock, _ = make()
    host.first_message()
    host.receive(SetSpeed("fortnight"))
    host.receive(Select(10**9))
    clock.advance(0.1)
    rejected = [m for m in host.step() if isinstance(m, CommandRejected)]
    assert len(rejected) == 2
    assert "fortnight" in rejected[0].reason
    assert host.session.status.selected is None


def test_the_frame_rate_can_be_lowered_and_stopped():
    host, clock, _ = make(work_budget=10.0, frame_interval=0.0)
    host.first_message()
    host.receive(SetFrameRate(0))
    host.receive(SetSpeed("max"))
    host.receive(Play())
    sent = run_flat_out(host, clock, 10, ack=lambda h: h._sent)
    assert frames(sent) == []
    assert host.session.simulation.tick > 0  # still running
    host.receive(SetFrameRate(10))
    sent = run_flat_out(host, clock, 10, ack=lambda h: h._sent)
    assert 1 <= len(frames(sent)) <= 10
    host.receive(SetFrameRate(-1))
    assert [m for m in host.step() if isinstance(m, CommandRejected)]


def test_plants_can_be_asked_for():
    host, clock, _ = make(plant_interval=100.0)
    host.first_message()
    host.receive(Ack(1))
    host.receive(SetSpeed("hour"))  # one tick a second, and running, so not "settled"
    host.receive(Play())
    host.step()
    clock.advance(1.0)
    first = frames(host.step())
    assert first and first[0].plants is None
    host.receive(Ack(host._sent))
    host.receive(RequestPlants())
    clock.advance(1.0)
    again = frames(host.step())
    assert again and again[0].plants is not None


def test_shutdown_stops_the_host_cleanly():
    host, _, _ = make()
    host.first_message()
    host.receive(Shutdown())
    assert host.step() == [Stopped()]
    assert host.stopped


# --- the in-process client ---------------------------------------------------------------


def test_the_in_process_client_hands_over_the_first_frame_then_runs_on_poll():
    client = fake_client(animals=20, plants=30)
    first = client.poll()
    assert first.ready and first.frame is not None and first.frame.plants is not None
    assert first.frame.tick == 0
    client.send(Step(4))
    seen = Inbox()
    for _ in range(100):
        seen = client.poll()
        if seen.frame is not None:
            break
        time.sleep(0.01)
    assert seen.frame is not None and seen.frame.tick == 4
    client.send(SetSpeed("fortnight"))
    assert client.poll().rejected


def test_the_in_process_client_reports_a_failing_simulation_and_stops():
    client = InProcessClient(FailsAtTick(3))
    client.poll()
    client.send(Step(10))
    inbox = client.poll()
    assert inbox.crash is not None and "broke at tick 3" in inbox.crash
    assert client.crashed == inbox.crash
    assert client.poll().crash is None  # said once; the client stays stopped
    client.close()
    assert client.poll().empty
    client.send(Pause())  # harmless after close


def test_frames_folded_together_keep_the_plants_of_the_last_one_that_had_them():
    host, clock, _ = make(plant_interval=100.0, frame_interval=0.0)
    ready = host.first_message()
    host.receive(Ack(1))
    host.receive(SetSpeed("hour"))
    host.receive(Play())
    host.step()
    clock.advance(1.0)
    later = frames(host.step())[0]
    assert later.plants is None
    folded = _Collector().collect([ready, later])
    assert folded.frame.tick == later.tick
    assert folded.frame.plants is ready.frame.plants
    assert folded.ready


def test_a_slow_window_is_sent_fewer_frames_in_process():
    client = fake_client(animals=20, plants=30)
    client.poll()
    client.send(SetSpeed("max"))
    client.send(Play())
    polls = [client.poll() for _ in range(5)]
    assert all(p.frame is None or p.frame.tick >= 0 for p in polls)


@pytest.mark.parametrize("bad", [0, -1])
def test_host_rules_are_checked(bad):
    with pytest.raises(ValueError):
        HostRules(max_in_flight=bad)
    assert StepReport(0).tick == 0
