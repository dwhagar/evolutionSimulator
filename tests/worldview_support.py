"""Builders shared by the world view tests: animals, statuses and frames of known content."""

from evolution_simulator.session import Frame, Status
from evolution_simulator.session.snapshot import pack_animals, pack_corpses, pack_plants
from evolution_simulator.world.views import AnimalView

WORLD = (100.0, 100.0)


def animal(id=1, x=50.0, y=50.0, heading=0.0, radius=10.0, **kw):
    fields = {
        "energy_ratio": 0.5,
        "health_ratio": 1.0,
        "age_ratio": 0.2,
        "diet": 1.0,
        "asleep": False,
        "pregnant": False,
        "ready_to_mate": False,
        "wandering": False,
        "sex": 0,
    }
    fields.update(kw)
    return AnimalView(id, x, y, heading, radius, **fields)


def status(**kw):
    fields = {
        "running": False,
        "steps_left": 0,
        "speed_asked": 3600.0,
        "speed_preset": "hour",
        "speed_achieved": None,
        "behind": False,
        "ticks_dropped": 0,
        "selected": None,
    }
    fields.update(kw)
    return Status(**fields)


def make_frame(animals=(), plants=None, corpses=(), tick=0, seconds=0.0, daylight=1.0, **kw):
    return Frame(
        format=1,
        seq=tick + 1,
        tick=tick,
        simulated_seconds=seconds,
        elapsed="0",
        day=0,
        daylight=daylight,
        is_night=daylight < 0.5,
        world_size=WORLD,
        status=kw.get("status", status()),
        animal_count=len(animals),
        plant_count=len(plants or ()),
        corpse_count=len(corpses),
        animals=pack_animals(list(animals)),
        corpses=pack_corpses(list(corpses)),
        plants=None if plants is None else pack_plants(list(plants)),
    )


def luminance(rgb):
    r, g, b = (float(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
