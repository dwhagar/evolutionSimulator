"""History and the run through the process host (UX.31): the recorder's news, the run folder."""

import time

import pytest

from evolution_simulator.history import HistoryMirror, Recorder
from evolution_simulator.runs import RunStore
from evolution_simulator.session import (
    Ack,
    CommandRejected,
    FakeSimulation,
    HistoryBatch,
    Host,
    HostRules,
    InProcessClient,
    NewRunSpec,
    Prepared,
    ProcessClient,
    RequestHistory,
    ResumeSpec,
    RunNotice,
    SaveNow,
    Session,
    SessionRules,
    Shutdown,
    StartRun,
    Step,
    Stopped,
    make_host,
)
from evolution_simulator.world import World, WorldConfig

DAY = 24  # ticks (the default tick is an hour)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make(host_rules=None, recorder=None, sim=None):
    clock = Clock()
    sim = sim if sim is not None else FakeSimulation(30, 40, seed=2)
    session = Session(
        sim, rules=SessionRules(max_ticks_per_update=DAY, max_elapsed=10.0), clock=clock
    )
    return Host(session, host_rules, clock, recorder=recorder), clock, sim


def history_batches(messages):
    return [m for m in messages if isinstance(m, HistoryBatch)]


def settle(host, clock, days, ack=True):
    """Run ``days`` simulated days, a day per host step, acknowledging everything unless told not
    to. (A fake world has no step listener, so the host samples once per step.)"""
    out = []
    for _ in range(days):
        host.receive(Step(DAY))
        clock.advance(0.3)
        out.extend(host.step())
        if ack:
            host.receive(Ack(host._sent))
    return out


class Viewer:
    """What a window does with the history messages: keep a mirror."""

    def __init__(self) -> None:
        self.mirror = HistoryMirror()
        self.fulls = 0

    def take(self, messages):
        for batch in history_batches(messages):
            if batch.full is not None:
                self.fulls += 1
                self.mirror.reset(batch.rules, batch.full)
            else:
                self.mirror.push(batch.samples)


# --- the host keeps a recorder and tells the viewer -----------------------------------


def test_the_first_step_sends_the_whole_history_even_when_it_is_empty():
    host, clock, _ = make()
    host.first_message()
    clock.advance(0.3)
    [batch] = history_batches(host.step())
    assert batch.full is not None and len(batch.full) == 0
    assert batch.rules == host.recorder.rules
    assert batch.samples == ()


def test_new_samples_follow_and_the_viewers_mirror_equals_the_recorder():
    host, clock, _ = make()
    host.first_message()
    viewer = Viewer()
    out = settle(host, clock, 120)  # past the day tier's 90 samples, so days merge into weeks
    viewer.take(out)
    assert viewer.fulls == 1
    assert len(host.recorder.history()) > 90
    assert viewer.mirror.history() == host.recorder.history()
    assert all(b.full is None for b in history_batches(out)[1:])


def test_samples_are_sent_a_few_at_a_time_not_one_message_each():
    host, clock, _ = make(HostRules(history_interval=1.0))
    host.first_message()
    out = settle(host, clock, 10)
    clock.advance(2.0)
    out.extend(host.step())  # the last few were waiting for the interval
    batches = history_batches(out)
    assert len(batches) < 10
    assert batches[0].full is not None  # the first day was already in the first, full, history
    assert sum(len(b.samples) for b in batches[1:]) + len(batches[0].full) == 10


def test_a_viewer_that_is_behind_loses_nothing():
    host, clock, _ = make(HostRules(max_in_flight=2))
    host.first_message()
    viewer = Viewer()
    held = settle(host, clock, 15, ack=False)  # nothing acknowledged: sending stops at two
    assert len(history_batches(held)) <= 1
    viewer.take(held)
    caught_up = []
    host.receive(Ack(host._sent))
    for _ in range(6):
        clock.advance(0.3)
        caught_up.extend(host.step())
        host.receive(Ack(host._sent))
    viewer.take(caught_up)
    assert viewer.mirror.history() == host.recorder.history()
    assert viewer.fulls == 1


def test_a_viewer_too_far_behind_is_sent_the_whole_history_instead_of_every_sample():
    host, clock, _ = make(HostRules(max_in_flight=2, max_pending_samples=3))
    host.first_message()
    held = settle(host, clock, 20, ack=False)  # twenty days; only three samples are ever held
    assert history_batches(held) == []
    after = []
    for _ in range(4):
        host.receive(Ack(host._sent))
        clock.advance(0.3)
        after.extend(host.step())
    [batch] = history_batches(after)
    assert batch.full == host.recorder.history() and len(batch.full) == 20
    assert batch.samples == ()


def test_request_history_sends_everything_again():
    host, clock, _ = make()
    host.first_message()
    viewer = Viewer()
    viewer.take(settle(host, clock, 5))
    host.receive(RequestHistory())
    clock.advance(0.3)
    out = host.step()
    [batch] = history_batches(out)
    assert batch.full == host.recorder.history()
    assert len(batch.full) == 5


def test_a_host_told_not_to_record_sends_no_history_and_refuses_the_request():
    host, clock, _ = make(HostRules(record=False))
    host.first_message()
    out = settle(host, clock, 3)
    assert history_batches(out) == [] and host.recorder is None
    host.receive(RequestHistory())
    clock.advance(0.3)
    [rejected] = [m for m in host.step() if isinstance(m, CommandRejected)]
    assert "history" in rejected.reason


def test_a_recorder_made_by_hand_is_the_one_the_host_uses():
    sim = FakeSimulation(10, 10, seed=4)
    mine = Recorder(sim)
    host, clock, _ = make(recorder=mine, sim=sim)
    host.first_message()
    assert host.recorder is mine
    viewer = Viewer()
    viewer.take(settle(host, clock, 4))
    assert viewer.mirror.history() == mine.history()


def test_make_host_takes_a_bare_simulation_or_a_prepared_one():
    bare = make_host(FakeSimulation(5, 5))
    assert bare.recorder is not None and bare.run is None
    sim = FakeSimulation(5, 5)
    mine = Recorder(sim)
    assert make_host(Prepared(sim, mine)).recorder is mine


# --- the run ---------------------------------------------------------------------------


def small_world_spec(tmp_path, **more):
    return NewRunSpec(tmp_path, WorldConfig(seed=5), animals=8, plants=30, **more)


class Watch:
    """Polls a client and remembers the newest of everything it hears."""

    def __init__(self, client) -> None:
        self.client = client
        self.first = None
        self.frame = self.history = self.run = None
        self.rejected = []

    def until(self, done, polls=2000):
        for _ in range(polls):
            time.sleep(0.002)  # frames are paced by real time
            inbox = self.client.poll()
            assert inbox.crash is None, inbox.crash
            self.first = inbox if inbox.ready and self.first is None else self.first
            self.frame = inbox.frame or self.frame
            self.history = inbox.history or self.history
            self.run = inbox.run or self.run
            self.rejected.extend(inbox.rejected)
            if done(self):
                return self
        raise AssertionError("never happened")

    def ticks(self, tick):
        return self.until(lambda w: w.frame is not None and w.frame.tick >= tick)


def test_a_host_with_a_run_says_so_and_saves_when_asked_and_when_it_stops(tmp_path):
    watch = Watch(InProcessClient(small_world_spec(tmp_path, name="trial")))
    notice = watch.until(lambda w: w.run is not None).run
    assert (notice.name, notice.checkpoints, notice.saved) == ("trial", 1, 0)
    assert notice.resumed_from is None and notice.path.startswith(str(tmp_path))

    watch.client.send(Step(3 * DAY))
    watch.ticks(3 * DAY)
    watch.client.send(SaveNow())
    saved = watch.until(lambda w: w.run.saved == 1).run
    assert saved.checkpoints == 2
    assert saved.last_checkpoint.endswith(f"{3 * DAY:012d}")

    watch.client.send(Step(DAY))
    watch.ticks(4 * DAY)
    tick = watch.client.host.session.simulation.tick
    watch.client.close()  # a last checkpoint at this very tick

    resumed = RunStore(tmp_path).open(notice.run_id).resume()
    assert resumed.world.tick == tick
    assert len(resumed.recorder.history()) == 4  # four days recorded and saved with it


def test_autosave_checkpoints_through_the_host(tmp_path):
    client = InProcessClient(small_world_spec(tmp_path))
    rules = client.host.run.store.rules
    client.host.run.store.rules = type(rules)(checkpoint_every_days=1.0, min_wall_seconds=0.0)
    watch = Watch(client)
    client.send(Step(3 * DAY))
    watch.ticks(3 * DAY)
    assert watch.until(lambda w: w.run is not None and w.run.saved >= 2).run.checkpoints >= 2
    client.close()


def test_save_now_is_refused_without_a_run():
    watch = Watch(InProcessClient(FakeSimulation(5, 5)))
    watch.client.send(SaveNow())
    watch.until(lambda w: bool(w.rejected))
    assert isinstance(watch.rejected[0].command, SaveNow)


def test_a_resumed_run_brings_back_the_world_its_history_and_its_folder(tmp_path):
    first = Watch(InProcessClient(small_world_spec(tmp_path)))
    first.client.send(Step(3 * DAY))
    first.ticks(3 * DAY)
    run_id = first.until(lambda w: w.run is not None).run.run_id
    sim = first.client.host.session.simulation
    tick, digest = sim.tick, sim.state_digest()
    first.client.close()

    again = Watch(InProcessClient(ResumeSpec(tmp_path)))
    again.until(lambda w: w.history is not None and w.run is not None)
    assert again.first.frame.tick == tick
    assert again.client.host.session.simulation.state_digest() == digest
    assert len(again.history) == 3
    assert again.run.run_id == run_id and again.run.resumed_from.endswith(f"{tick:012d}")

    again.client.send(Step(2 * DAY))
    again.until(lambda w: len(w.history) == 5)
    assert again.history == again.client.host.recorder.history()
    again.client.close()


def test_resuming_with_no_runs_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no runs"):
        ResumeSpec(tmp_path)()


def test_a_shutdown_message_saves_the_run_before_stopping(tmp_path):
    prepared = small_world_spec(tmp_path)()
    host = make_host(prepared)
    host.first_message()
    host.receive(Step(DAY))
    for _ in range(6):
        host.step()
    host.receive(Shutdown())
    assert [type(m) for m in host.step()] == [Stopped]
    assert host.run.checkpoints()[-1].tick == host.session.simulation.tick
    assert host.step() == [Stopped()] or host.stopped  # stopped is final


# --- over a real process --------------------------------------------------------------


def test_history_and_the_run_cross_a_real_pipe(tmp_path):
    client = ProcessClient(small_world_spec(tmp_path, name="piped"))
    try:
        client.send(Step(2 * DAY))
        history = notice = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and (history is None or len(history) < 2 or not notice):
            inbox = client.poll()
            assert inbox.crash is None, inbox.crash
            history = inbox.history if inbox.history is not None else history
            notice = inbox.run if inbox.run is not None else notice
            time.sleep(0.01)
        assert history is not None and len(history) == 2
        assert notice.name == "piped"
        client.send(RequestHistory())
        again = None
        while time.monotonic() < deadline and again is None:
            again = client.poll().history
            time.sleep(0.01)
        assert again == history
    finally:
        client.close()
    runs = RunStore(tmp_path).list_runs()
    assert [r.name for r in runs] == ["piped"]
    assert RunStore(tmp_path).open(runs[0].id).resume().world.tick >= 2 * DAY


def test_the_new_messages_pickle():
    import pickle

    sim = World(WorldConfig(seed=1))
    sim.populate(3, 5)
    recorder = Recorder(sim)
    sim.run(2 * DAY)
    batch = HistoryBatch(recorder.rules, (), recorder.history())
    assert pickle.loads(pickle.dumps(batch)) == batch
    notice = RunNotice("id", "name", "/x", 1, "checkpoint-1", 0)
    assert pickle.loads(pickle.dumps(notice)) == notice
    assert pickle.loads(pickle.dumps(SaveNow())) == SaveNow()


def test_start_run_saves_a_real_world_into_a_run_and_refuses_a_made_up_one(tmp_path):
    world = World(WorldConfig(seed=4))
    world.populate(5, 20)
    host, clock, _ = make(sim=world)
    host.first_message()
    host.receive(StartRun(str(tmp_path), "later"))
    clock.advance(0.3)
    [notice] = [m for m in host.step() if isinstance(m, RunNotice)]
    assert (notice.name, notice.checkpoints) == ("later", 1) and host.run is not None
    assert notice.answers == 0
    host.receive(StartRun(str(tmp_path), "again", token=7))  # already in a run: it is checkpointed
    clock.advance(0.3)
    [again] = [m for m in host.step() if isinstance(m, RunNotice)]
    assert (again.run_id, again.name, again.answers, again.saved) == (notice.run_id, "later", 7, 1)
    host.receive(Shutdown(save=False))
    host.receive(Shutdown())  # the first word is the one that counts
    assert host.step() == [Stopped()]
    assert [c.tick for c in host.run.checkpoints()] == [0]  # no last checkpoint

    fake_host, fake_clock, _ = make()
    fake_host.first_message()
    fake_host.receive(StartRun(str(tmp_path)))
    fake_clock.advance(0.3)
    [rejected] = [m for m in fake_host.step() if isinstance(m, CommandRejected)]
    assert "not a real world" in rejected.reason
