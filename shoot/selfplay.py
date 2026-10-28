"""Computer-vs-computer games with random ships, to find out which upgrades win.

    python -m shoot.selfplay --games 2000
    python -m shoot.selfplay --games 2000 --cycles 5   play, rebalance, and repeat 5 times

Runs without a window, as fast as the PC allows, on all CPU cores. Every round gives both
ships a random build that spends the whole budget, and is logged to selfplay.jsonl. After
each batch the prices are rebalanced if there is enough new data (see balance.py), so the
next batch plays on the new prices.
"""

import argparse
import multiprocessing
import os
import random
import time

from . import config_screen, match_log
from .config_screen import STATS, Loadout, special_options

FPS = 60
ROUND_LIMIT = 60.0  # seconds of game time before a round counts as a draw


def random_loadout(rng: random.Random) -> Loadout:
    """A random build that spends (nearly) the whole budget. Each stat gets a random weight,
    so builds range from all-rounders to ships that pour everything into one or two stats."""
    prices = config_screen.PRICES
    loadout = Loadout(levels={s.key: 0 for s in STATS}, momentum=rng.random() < 0.5,
                      special=rng.choice(special_options(networked=True)))
    if loadout.points_left < 0:
        loadout.special = None
    weights = {s.key: rng.expovariate(1.0) for s in STATS}
    while True:
        options = [s for s in STATS if loadout.levels[s.key] < s.max_level
                   and prices.step_cost(s.key, loadout.levels[s.key]) <= loadout.points_left]
        if not options:
            return loadout
        stat = rng.choices(options, [weights[s.key] for s in options])[0]
        loadout.levels[stat.key] += 1


def _make_game():
    os.environ["SDL_VIDEODRIVER"] = "dummy"  # no window
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    from .ai import SimpleAI
    from .game import Game

    class SelfPlayGame(Game):
        def __init__(self):
            super().__init__(ai=True)
            self.setup = None
            self.blue_ai = SimpleAI(self.ships[0], self.ships[1])

        def read_inputs(self):
            return [self.blue_ai.decide(self.bullets, self.frame_dt), self.ai.decide(self.bullets, self.frame_dt)]

        def round_finished(self):
            pass  # logged by the runner

        def play(self, loadouts: list[Loadout]) -> tuple[int, float]:
            self.loadouts = loadouts
            for ship, loadout in zip(self.ships, loadouts):
                ship.type = loadout.ship_type()
            self.new_round()
            while self.winner is None and self.round_time < ROUND_LIMIT:
                self.update(1 / FPS)
            return (-1 if self.winner is None else self.winner), self.round_time

    return SelfPlayGame()


def _worker(args: tuple[int, int]) -> list[dict]:
    seed, count = args
    rng = random.Random(seed)
    random.seed(seed)  # the game and AI use the global generator
    game = _make_game()
    rounds = []
    for _ in range(count):
        loadouts = [random_loadout(rng), random_loadout(rng)]
        winner, seconds = game.play(loadouts)
        rounds.append(match_log.entry("selfplay", loadouts, winner, seconds, config_screen.PRICES.version))
    return rounds


def run(games: int, workers: int | None = None, quiet: bool = False) -> int:
    """Play and log this many rounds. Returns how many were logged."""
    workers = workers or os.cpu_count() or 1
    batch = 25
    jobs = [(random.randrange(2**31), min(batch, games - i)) for i in range(0, games, batch)]
    done, start = 0, time.time()
    with multiprocessing.Pool(workers) as pool:
        for rounds in pool.imap_unordered(_worker, jobs):
            match_log.append(rounds, match_log.SELFPLAY_FILE)
            done += len(rounds)
            if not quiet:
                print(f"\r{done}/{games} rounds  ({done / (time.time() - start):.0f}/s)", end="", flush=True)
    if not quiet:
        print()
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description="Computer-vs-computer games to rebalance prices.")
    parser.add_argument("--games", type=int, default=2000, help="rounds to play (default 2000)")
    parser.add_argument("--workers", type=int, help="processes to use (default: one per CPU core)")
    parser.add_argument("--cycles", type=int, default=1, help="batches to play, rebalancing after each")
    parser.add_argument("--no-rebalance", action="store_true", help="only collect data")
    args = parser.parse_args()
    from . import balance
    for cycle in range(args.cycles):
        if args.cycles > 1:
            print(f"Batch {cycle + 1} of {args.cycles}, prices v{config_screen.PRICES.version}")
        run(args.games, args.workers)
        if not args.no_rebalance:
            balance.auto_rebalance(verbose=True)


if __name__ == "__main__":
    main()
