"""Computer-vs-computer matches between two pilots, to measure whether a change to the AI helps.

    python -m shoot.arena                      the current pilot (hard) against the first one
    python -m shoot.arena --a normal --b easy  any two of: hard, normal, easy, baseline
    python -m shoot.arena --scenarios          also a few fixed match-ups, pilot A against itself
    python -m shoot.arena --b hard --set PREFERRED_RANGE=350   try a setting on pilot A only
    python -m shoot.arena --a normal --set aim_error=10        or a skill value

Ships are random builds from self-play. Each build pair is played twice with the pilots
swapping ships and sides, and in half the pairs both ships are the same build, so neither
pilot gets the better ship. Nothing is logged and prices aren't touched.
"""

import argparse
import math
import multiprocessing
import os
import random
import time
from collections import Counter

from . import selfplay
from .config_screen import STATS, Loadout


def _play(game, loadouts: list[Loadout], stats: Counter, a_side: int) -> None:
    """One round; counts into stats from pilot A's point of view (A flies ship a_side)."""
    game.loadouts = loadouts
    for ship, loadout in zip(game.ships, loadouts):
        ship.type = loadout.ship_type()
    game.new_round()
    while game.winner is None and game.round_time < selfplay.ROUND_LIMIT:
        hp = [s.hp for s in game.ships]
        game.update(1 / selfplay.FPS)
        for b in game.bullets:
            if not getattr(b, "counted", False):
                b.counted = True
                if not b.fake:
                    stats["shots_a" if game.ships.index(b.owner) == a_side else "shots_b"] += 1
        lost = [before - s.hp for before, s in zip(hp, game.ships)]
        if max(lost) >= 2:
            stats["rams"] += 1  # a ram costs 2 at once (a bullet only 1); not counted as a hit
            continue
        for i, n in enumerate(lost):
            stats["hits_on_b" if i != a_side else "hits_on_a"] += n
    stats["rounds"] += 1
    stats["seconds"] += game.round_time
    if game.winner is None:
        stats["timeouts"] += 1
    elif game.winner < 0:
        stats["both_died"] += 1
    else:
        stats["a_won" if game.winner == a_side else "b_won"] += 1


def _worker(args) -> Counter:
    seed, pairs, a, b, fixed, tweaks = args
    rng = random.Random(seed)
    random.seed(seed)
    ta, tb = tweaks
    games = [selfplay._make_game((a, b), (ta, tb)), selfplay._make_game((b, a), (tb, ta))]  # A flies Blue, then Red
    stats = Counter()
    for _ in range(pairs):
        if fixed:
            loadouts = [Loadout.from_dict(d, check_budget=False) for d in fixed]
        else:
            first = selfplay.random_loadout(rng, rng.uniform(selfplay.MIN_SPEND, 1.0))
            second = first if rng.random() < 0.5 else selfplay.random_loadout(rng, rng.uniform(selfplay.MIN_SPEND, 1.0))
            loadouts = [first, second]
        _play(games[0], loadouts, stats, a_side=0)
        # Random builds: A also flies the other ship. Fixed match-ups: A keeps the first one.
        _play(games[1], loadouts[::-1] if fixed else loadouts, stats, a_side=1)
    return stats


def run(a: str, b: str, rounds: int, workers: int | None = None, fixed: list[dict] | None = None,
        tweaks: tuple[dict, dict] = ({}, {})) -> Counter:
    workers = workers or os.cpu_count() or 1
    pairs = max(1, rounds // 2)
    batch = 10
    jobs = [(random.randrange(2**31), min(batch, pairs - i), a, b, fixed, tweaks) for i in range(0, pairs, batch)]
    total = Counter()
    with multiprocessing.Pool(workers) as pool:
        for stats in pool.imap_unordered(_worker, jobs):
            total.update(stats)
    return total


def summary(s: Counter) -> str:
    decided = s["a_won"] + s["b_won"]
    p = s["a_won"] / decided if decided else 0.5
    ci = 1.96 * math.sqrt(p * (1 - p) / decided) if decided else 0.5
    acc = lambda hits, shots: f"{hits / shots:.0%}" if shots else "-"
    return (f"A wins {p:.1%} ± {ci:.1%} of {decided} decided | both died {s['both_died'] / s['rounds']:.0%}, "
            f"timeouts {s['timeouts'] / s['rounds']:.0%}, rams {s['rams'] / s['rounds']:.2f}/round | hit rate A {acc(s['hits_on_b'], s['shots_a'])}, "
            f"B {acc(s['hits_on_a'], s['shots_b'])} | {s['seconds'] / s['rounds']:.1f} s/round")


def _ship(momentum: bool, special: str | None = None, **levels) -> dict:
    l = {st.key: st.start_level for st in STATS}
    l.update(levels)
    return {"levels": l, "momentum": momentum, "special": special}


SCENARIOS = {
    "Momentum vs momentum": [_ship(True), _ship(True)],
    "No momentum vs no momentum": [_ship(False), _ship(False)],
    "Momentum vs no momentum": [_ship(True), _ship(False)],
    "Fast momentum vs momentum": [_ship(True, speed=10), _ship(True)],
    "Cloak vs plain": [_ship(False, "cloak"), _ship(False)],
    "Mirror image vs plain": [_ship(False, "mirror"), _ship(False)],
    "Shield vs plain": [_ship(False, "shield"), _ship(False)],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Pit two computer pilots against each other.")
    parser.add_argument("--a", default="hard", help="pilot A (default hard)")
    parser.add_argument("--b", default="baseline", help="pilot B (default baseline, the first AI)")
    parser.add_argument("--games", type=int, default=2000, help="rounds to play (default 2000)")
    parser.add_argument("--workers", type=int, help="processes to use (default: one per CPU core)")
    parser.add_argument("--scenarios", action="store_true", help="also play fixed match-ups, A against A")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                        help="give pilot A another value for one of ComputerPilot's settings or its "
                             "skill's, e.g. --set PREFERRED_RANGE=350 or --set reaction=0.15")
    args = parser.parse_args()
    import dataclasses
    from .ai import ComputerPilot, Skill
    tweaks = {name: float(value) for name, value in (t.split("=", 1) for t in args.set)}
    skill_fields = {f.name for f in dataclasses.fields(Skill)} - {"name"}
    for name in tweaks:
        if not (name.isupper() and hasattr(ComputerPilot, name)) and name not in skill_fields:
            parser.error(f"ComputerPilot and its skill have no setting {name}")

    start = time.time()
    s = run(args.a, args.b, args.games, args.workers, tweaks=(tweaks, {}))
    print(f"{args.a} (A) vs {args.b} (B), random ships: {summary(s)}")
    print(f"  {s['rounds'] / (time.time() - start):.0f} rounds/s")
    if args.scenarios:
        print(f"\n{args.a} against itself (only A gets --set); A flies the first ship named:")
        for name, ships in SCENARIOS.items():
            print(f"  {name:28} {summary(run(args.a, args.a, max(100, args.games // 5), args.workers, ships, (tweaks, {})))}")


if __name__ == "__main__":
    main()
