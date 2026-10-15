"""Times genome distance, the digit-by-digit loop of before ``DNA.17`` against the packed integer.

Run ``python -m evolution_tools.bench_dna_distance [genomes] [seed]``. It builds that many random animal
genomes, times every pair with each method (the first call of the packed method also makes each
genome's packed integer, so that cost is included), times a single comparison, and checks that both
methods give the same answers.
"""

from __future__ import annotations

import random
import sys
import timeit
from itertools import combinations
from operator import ne
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from evolution_simulator.dna import DNA
from evolution_simulator.layouts import ANIMAL_LAYOUT


def digit_loop_distance(a: DNA, b: DNA) -> float:
    """The implementation before ``DNA.17``: compare the digits one by one."""
    return sum(map(ne, a.sequence, b.sequence)) / a.length


def main(count: int = 300, seed: int = 1) -> None:
    rng = random.Random(seed)
    genomes = [DNA.random(ANIMAL_LAYOUT, rng) for _ in range(count)]
    pairs = list(combinations(genomes, 2))
    old = timeit.timeit(lambda: [digit_loop_distance(a, b) for a, b in pairs], number=1)
    fresh = [DNA(ANIMAL_LAYOUT, g.sequence) for g in genomes]  # nothing packed yet
    first = timeit.timeit(lambda: [a.distance(b) for a, b in combinations(fresh, 2)], number=1)
    again = timeit.timeit(lambda: [a.distance(b) for a, b in pairs], number=3) / 3
    a, b = genomes[0], genomes[1]
    one_old = timeit.timeit(lambda: digit_loop_distance(a, b), number=2000) / 2000
    one_new = timeit.timeit(lambda: a.distance(b), number=20000) / 20000
    same = all(digit_loop_distance(a, b) == a.distance(b) for a, b in pairs)
    print(f"{count} genomes of {ANIMAL_LAYOUT.length} digits, {len(pairs):,} pairs")
    print(f"  digit loop           {old * 1000:9.1f} ms")
    print(f"  packed, first pass   {first * 1000:9.1f} ms  (includes packing each genome once)")
    print(f"  packed, packed      {again * 1000:9.1f} ms")
    print(f"  one comparison       {one_old * 1e6:9.2f} us -> {one_new * 1e6:.2f} us")
    print(f"  identical answers: {same}")


if __name__ == "__main__":
    main(*(int(arg) for arg in sys.argv[1:3]))
