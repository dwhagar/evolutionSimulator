"""The brain as part of an animal: read from DNA at birth, costs energy, answers `think`."""

import random

import pytest
from genome_support import dna_from_v5

from evolution_simulator import traits as traits_module
from evolution_simulator.brain import DEFAULT_BLUEPRINT, DEFAULT_SHAPE, Brain
from evolution_simulator.brain_adapter import (
    INPUT_NAMES,
    BrainDecision,
    Percepts,
    Temperament,
    build_inputs,
    decode_outputs,
)
from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT, PLANT_LAYOUT
from evolution_simulator.traits import (
    BRAIN_CONNECTION_COST,
    BRAIN_DEAD_ZONE,
    BRAIN_NEURON_COST,
    AnimalTraits,
    PlantTraits,
)

OLD_BODY = ("0123" * 18)[:70]
BODY = (
    OLD_BODY[:65] + "000000" + OLD_BODY[65:]
)  # fertility and recovery at zero, the rest as before
OPERATING = (
    "0" * 16
)  # brain_gain, reaction_time, curiosity, learning_rate: gain 0.5, think every tick
BRAIN = "".join(str((i * 7 + i // 5) % 4) for i in range(908))  # fixed, varied, not saturated
PINNED = dna_from_v5(BODY + OPERATING, BRAIN)
FAINT = (
    "13" * 454
)  # every value is level 7 of 16: -0.133, so every gate is off and weights are dead
STRONG = "3" * 908  # every value is +2.0: every gate on, every weight live

SEEN = Percepts(
    plant_direction=-0.5, plant_closeness=0.8, threat_direction=0.2, threat_closeness=0.1
)


def with_brain(digits: str) -> DNA:
    return PINNED.replaced("brain", [int(d) for d in digits])


# --- reading the brain from the genome ---------------------------------------


def test_the_brain_is_built_from_the_genome_at_birth():
    traits = AnimalTraits(PINNED)
    expected = DEFAULT_BLUEPRINT.build(
        PINNED.values("brain"), dead_zone=BRAIN_DEAD_ZONE, gain=traits.brain.gain
    )
    assert traits.brain == expected
    assert traits.brain.shape.inputs == DEFAULT_SHAPE.inputs == 20
    assert traits.brain.shape.hidden == len(DEFAULT_BLUEPRINT.slots_on(PINNED.values("brain")))
    assert len(traits.brain.to_values()) == traits.brain.shape.weight_count


def test_different_genomes_give_different_brains_and_the_same_genome_the_same():
    other = DNA.random(ANIMAL_LAYOUT, random.Random(4))
    assert AnimalTraits(other).brain != AnimalTraits(PINNED).brain
    assert AnimalTraits(PINNED).brain == AnimalTraits(PINNED).brain


def test_the_brain_does_not_change_the_body():
    a, b = AnimalTraits(with_brain(FAINT)), AnimalTraits(with_brain(STRONG))
    assert dict(a.phenotype) == dict(b.phenotype)
    assert a.mass == b.mass and a.max_energy == b.max_energy
    assert a.base_max_speed == b.base_max_speed


def test_plants_have_no_brain():
    assert not hasattr(PlantTraits(DNA.random(PLANT_LAYOUT, random.Random(1))), "brain")


# --- what thinking costs -----------------------------------------------------


def test_upkeep_charges_per_neuron_and_per_active_connection():
    faint, strong = AnimalTraits(with_brain(FAINT)), AnimalTraits(with_brain(STRONG))
    # every gate off keeps one hidden neuron, whose weights are all inside the dead zone
    assert faint.brain.shape.hidden == 1 and faint.brain.active_connections() == 0
    assert faint.brain_upkeep == pytest.approx(BRAIN_NEURON_COST * 7)
    # every gate on: 16 hidden neurons, each with 20 inputs and 6 outputs, all live
    assert strong.brain.shape.hidden == 16
    assert strong.brain.active_connections() == 16 * (20 + 6)
    assert strong.brain_upkeep == pytest.approx(
        BRAIN_NEURON_COST * 22 + BRAIN_CONNECTION_COST * 416
    )


def test_the_cost_threshold_is_the_brains_dead_zone():
    """BRAIN.21: a weight that costs nothing also does nothing, and one that acts also pays."""
    for seed in range(5):
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(seed)))
        brain = traits.brain
        shape = brain.shape
        assert brain.dead_zone == BRAIN_DEAD_ZONE
        values = list(brain.to_values())
        size = shape.neuron_size
        weight_positions = [
            j * size + i
            for j in range(shape.hidden)
            for i in range(1, size)  # everything in a neuron block but its bias
        ]
        live = [i for i in weight_positions if abs(values[i]) > BRAIN_DEAD_ZONE]
        assert brain.active_connections() == len(live)
        # switching off every weight that costs nothing changes nothing the creature does
        cut = [0.0 if i in weight_positions and i not in live else v for i, v in enumerate(values)]
        plain = Brain.from_values(shape, cut, gain=brain.gain)
        inputs = [random.Random(seed).uniform(-1, 1) for _ in range(shape.inputs)]
        assert brain.decide(inputs) == plain.decide(inputs)
        assert plain.active_connections(BRAIN_DEAD_ZONE) == len(live)


def test_a_faint_brain_acts_only_through_its_biases():
    faint = AnimalTraits(with_brain(FAINT))
    assert faint.brain.active_connections() == 0
    inputs = [0.9] * DEFAULT_SHAPE.inputs
    assert faint.brain.decide(inputs) == faint.brain.decide([0.0] * DEFAULT_SHAPE.inputs)


def test_upkeep_is_part_of_basal_metabolism():
    faint, strong = AnimalTraits(with_brain(FAINT)), AnimalTraits(with_brain(STRONG))
    assert strong.basal_metabolism - faint.basal_metabolism == pytest.approx(
        strong.brain_upkeep - faint.brain_upkeep
    )
    assert strong.basal_metabolism > faint.basal_metabolism


def test_a_heavily_wired_brain_drains_energy_faster():
    def energy_after_ten_ticks(dna: DNA) -> float:
        traits = AnimalTraits(dna)
        for _ in range(10):
            traits.update_metabolism_and_aging(0.0)
        return traits.current_energy

    assert energy_after_ten_ticks(with_brain(STRONG)) < energy_after_ten_ticks(with_brain(FAINT))


def test_a_typical_random_brain_costs_a_few_percent_of_the_basal_budget():
    ratios = []
    for seed in range(100):
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(seed)))
        ratios.append(traits.brain_upkeep / traits.basal_metabolism)
    assert 0.01 < sum(ratios) / len(ratios) < 0.08
    assert max(ratios) < 0.15


def test_the_cost_constants_are_module_level_so_they_can_move_to_config():
    assert traits_module.BRAIN_NEURON_COST > 0
    assert traits_module.BRAIN_CONNECTION_COST > 0
    assert 0 < traits_module.BRAIN_DEAD_ZONE < 2.0


# --- thinking ---------------------------------------------------------------
def adult(dna: DNA, **kwargs) -> AnimalTraits:
    """An animal past its juvenile period, so it is ready to mate (a newborn waits one birth
    interval, `REPRO.5`)."""
    traits = AnimalTraits(dna, **kwargs)
    traits.mating_cooldown = 0
    traits._update_needs_and_drives()
    return traits


def test_think_runs_the_brain_on_the_animals_state_and_the_percepts():
    traits = adult(PINNED)
    expected = decode_outputs(
        traits.brain.decide(
            build_inputs(
                SEEN,
                energy_ratio=traits.current_energy / traits.max_energy,
                health_ratio=traits.current_health / traits.max_damage_capacity,
                vitality=traits.vitality,
                ready_to_mate=True,
                pain=0.0,
                temperament=Temperament(
                    traits.current_aggression,
                    traits._effective_fear(),
                    traits.phenotype["repro_drive"],
                ),
            )
        )
    )
    assert traits.think(SEEN) == expected


# Re-pinned for the animal layout with the three reproduction genes (REPRO.5): the body digits of
# this genome now spell different genes.
def test_pinned_decision_for_a_fixed_genome():
    # Checked against a separate forward pass written from the genome values (gates, dead zone, gain).
    decision = adult(PINNED).think(SEEN)
    assert decision.turn == pytest.approx(0.928239061)
    assert decision.speed == pytest.approx(0.476344698)
    assert decision.eat_or_attack == pytest.approx(0.911143506)
    assert decision.seek_mating == pytest.approx(0.127545809)
    assert decision.alarm_call == pytest.approx(0.719130673)
    assert decision.mating_call == pytest.approx(0.838283436)
    assert decision.eats_or_attacks is True and decision.seeks_mating is False


def test_think_is_repeatable_and_changes_nothing():
    traits = adult(PINNED)
    before = (traits.current_energy, traits.age_ticks, traits.flag_wants_mate, traits.vitality)
    assert traits.think(SEEN) == traits.think(SEEN)
    assert (
        traits.current_energy,
        traits.age_ticks,
        traits.flag_wants_mate,
        traits.vitality,
    ) == before


def test_think_sees_hunger_health_and_readiness_to_mate():
    fed = adult(PINNED).think(Percepts())
    hungry = adult(PINNED)
    hungry.current_energy *= 0.2
    assert hungry.think(Percepts()) != fed
    hurt = adult(PINNED)
    hurt.apply_damage(hurt.max_damage_capacity * 0.5)
    assert hurt.think(Percepts()) != fed
    resting = adult(PINNED)
    resting.mating_cooldown = 5
    assert resting.think(Percepts()) != fed


def test_think_sees_the_world():
    traits = adult(PINNED)
    assert traits.think(SEEN) != traits.think(Percepts())
    assert traits.think(Percepts(touching=True)) != traits.think(Percepts())


def test_decisions_over_a_run_are_deterministic():
    def run() -> list[BrainDecision]:
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(9)))
        r = random.Random(3)
        decisions = []
        for _ in range(50):
            percepts = Percepts(plant_closeness=r.random(), plant_direction=r.uniform(-1, 1))
            decisions.append(traits.think(percepts))
            traits.update_metabolism_and_aging(0.5)
        return decisions

    assert run() == run()


def test_random_animals_always_decide_inside_the_output_ranges():
    r = random.Random(12)
    for seed in range(60):
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(seed)))
        percepts = Percepts(
            plant_direction=r.uniform(-1, 1),
            plant_closeness=r.random(),
            threat_direction=r.uniform(-1, 1),
            threat_closeness=r.random(),
            touching=r.random() < 0.5,
            crowding=r.random(),
        )
        d = traits.think(percepts)
        assert -1.0 <= d.turn <= 1.0
        assert all(0.0 <= v <= 1.0 for v in (d.speed, d.eat_or_attack, d.seek_mating))
        assert all(0.0 <= v <= 1.0 for v in (d.alarm_call, d.mating_call))


# --- behaviour genes (BRAIN.14) ----------------------------------------------

THREAT = Percepts(threat_closeness=0.5, threat_direction=0.3)
PREY = Percepts(prey_closeness=0.5, prey_direction=-0.3)


def with_genes(**genes: str) -> AnimalTraits:
    """The pinned animal with the named body genes replaced."""
    dna = PINNED
    for name, digits in genes.items():
        dna = dna.replaced(name, [int(d) for d in digits])
    return AnimalTraits(dna)


def test_the_fear_gene_changes_the_reaction_to_a_threat_only():
    timid, bold = with_genes(fear="3333"), with_genes(fear="0000")
    assert timid.think(THREAT) != bold.think(THREAT)
    assert timid.think(Percepts()) == bold.think(Percepts())
    assert timid.think(PREY) == bold.think(PREY)


def test_the_aggression_gene_changes_the_reaction_to_prey_only():
    fierce, meek = with_genes(aggression="3333"), with_genes(aggression="0000")
    assert fierce.think(PREY) != meek.think(PREY)
    assert fierce.think(Percepts()) == meek.think(Percepts())
    assert fierce.think(THREAT) == meek.think(THREAT)


def test_the_temperament_given_to_the_brain_follows_the_animals_current_drives():
    traits = with_genes(aggression="2000", fear="1000")
    calm = traits.think(PREY)
    traits.current_energy = traits.max_energy * 0.1  # starving: aggression boosts
    assert traits.current_aggression > 0.0
    assert traits.think(PREY) != calm


def test_fear_as_the_fixed_rule_uses_it_comes_from_one_place():
    traits = with_genes(fear="3000")
    traits.set_environmental_stimuli(threat_detected=True)
    assert traits.flag_in_fear == (traits._effective_fear() > traits.current_aggression)
    traits.vitality = 0.2
    assert traits._effective_fear() == pytest.approx(traits.base_fear_weight * (1.2 - 0.1))


# --- decision interval (BRAIN.11) --------------------------------------------


class CountingBrain:
    """Wraps a brain and counts how often it actually decides."""

    def __init__(self, brain):
        self.brain = brain
        self.calls = 0

    def decide(self, inputs):
        return self.decide_with_hidden(inputs)[1]

    def decide_with_hidden(self, inputs):
        self.calls += 1
        return self.brain.decide_with_hidden(inputs)

    def __getattr__(self, name):
        return getattr(self.brain, name)


def counted(interval: int) -> tuple[AnimalTraits, CountingBrain]:
    traits = adult(PINNED, decision_interval=interval)
    counter = CountingBrain(traits.brain)
    traits.brain = counter
    return traits, counter


def test_the_default_interval_decides_every_tick():
    traits, counter = counted(1)
    for _ in range(6):
        traits.think(SEEN)
    assert counter.calls == 6
    assert traits.decision_interval == 1


@pytest.mark.parametrize("interval", [2, 3, 4])
def test_the_brain_runs_once_every_n_ticks(interval):
    traits, counter = counted(interval)
    for _ in range(12):
        traits.think(SEEN)
    assert counter.calls == 12 // interval


def test_ticks_between_decisions_keep_the_last_decision_even_if_the_world_changes():
    traits, _ = counted(3)
    first = traits.think(SEEN)
    assert traits.think(Percepts()) == first
    assert traits.think(PREY) == first
    assert traits.think(Percepts()) != first  # the fourth call decides afresh


def test_decisions_follow_the_same_schedule_every_run():
    def run() -> list[BrainDecision]:
        traits = AnimalTraits(DNA.random(ANIMAL_LAYOUT, random.Random(2)), decision_interval=4)
        r = random.Random(1)
        out = []
        for i in range(20):
            out.append(traits.think(Percepts(plant_closeness=(i % 5) / 5), r))
        return out

    assert run() == run()


def test_wandering_only_draws_randomness_when_a_decision_is_made():
    traits = adult(PINNED, decision_interval=5)
    r = random.Random(4)
    traits.think(Percepts(), r)  # blind: wanders, draws
    state = r.getstate()
    for _ in range(4):
        assert traits.think(Percepts(), r).wandering
    assert r.getstate() == state


def test_a_slower_thinker_pays_proportionally_less_upkeep():
    every = adult(PINNED)
    fourth = adult(PINNED, decision_interval=4)
    assert fourth.brain_upkeep == pytest.approx(every.brain_upkeep / 4)
    assert every.basal_metabolism - fourth.basal_metabolism == pytest.approx(
        every.brain_upkeep * 0.75
    )


def test_the_interval_must_be_at_least_one_tick():
    with pytest.raises(ValueError):
        adult(PINNED, decision_interval=0)
    assert traits_module.DECISION_INTERVAL >= 1


# --- the reproduction drive (REPRO.5) -----------------------------------------


def mate_input(percepts: Percepts, drive: float) -> float:
    inputs = build_inputs(
        percepts,
        energy_ratio=0.5,
        health_ratio=1.0,
        vitality=1.0,
        ready_to_mate=True,
        pain=0.0,
        temperament=Temperament(repro_drive=drive),
    )
    return inputs[INPUT_NAMES.index("mate_closeness")]


def test_the_drive_bends_how_close_a_possible_mate_looks():
    seen = Percepts(mate_direction=0.2, mate_closeness=0.5)
    assert mate_input(seen, 0.5) == pytest.approx(0.5)  # neutral
    assert mate_input(seen, 1.0) == pytest.approx(0.8)  # x1.6
    assert mate_input(seen, 0.0) == pytest.approx(0.2)  # x0.4
    assert mate_input(Percepts(), 1.0) == 0.0  # nothing sensed stays unsensed


def test_the_temperament_drive_must_be_a_gene_level():
    with pytest.raises(ValueError):
        Temperament(repro_drive=1.5)


def test_a_possible_mate_does_not_pull_on_an_animal_in_cooldown():
    seen = Percepts(mate_direction=0.4, mate_closeness=0.7, plant_closeness=0.3)
    resting = adult(PINNED)
    resting.mating_cooldown = 7
    blind = adult(PINNED)
    blind.mating_cooldown = 7
    assert resting.think(seen) == blind.think(Percepts(plant_closeness=0.3))
    ready = adult(PINNED)
    assert ready.think(seen) != adult(PINNED).think(Percepts(plant_closeness=0.3))


def test_think_gives_the_brain_the_animals_own_drive():
    low = adult(with_body_gene("repro_drive", "000"))
    high = adult(with_body_gene("repro_drive", "333"))
    seen = Percepts(mate_direction=0.2, mate_closeness=0.5)
    assert low.think(seen) != high.think(seen)


def with_body_gene(gene_id: str, digits: str) -> DNA:
    return PINNED.replaced(gene_id, [int(d) for d in digits])
