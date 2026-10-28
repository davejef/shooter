"""Rebalancing: work out from logged rounds which upgrades win more than their price says,
then make those dearer and the others cheaper.

    python -m shoot.balance            report what each upgrade is worth, and rebalance if due
    python -m shoot.balance --report   only report

Every priced choice is an "item": each level step of each stat, momentum (on rather than off)
and each special. A logistic regression on the difference between the two ships' items
estimates how much each one adds to the chance of winning:

    P(Blue wins) = sigmoid(side bias for the mode + sum of w_i * (Blue has i - Red has i))

When prices are right, each w_i is the same multiple (theta) of its price, so w_i / theta is the
item's fair price in points. Every ship spends the whole budget, so theta can't be read off
directly; it is set so that the items ships actually buy are, on average, worth what they cost.

To stay stable with little data, the fit pulls each w_i towards theta * price and neighbouring
level steps of a stat towards each other (L2 penalties), and each rebalance moves a price only
part of the way to its fair price, at most 15% (or 1 point), and only when the data is clear enough.
"""

import argparse
import math
from dataclasses import dataclass

import numpy as np

from . import config_screen, match_log, prices
from .abilities import ABILITIES
from .config_screen import STATS

MIN_NEW_ROUNDS = 1000  # rounds played on the current prices before the next rebalance
MAX_ROUNDS = 30000     # only the most recent rounds are used
HUMAN_WEIGHT = 2.0     # a round people played counts as this many self-play rounds
PRIOR_STRENGTH = 20.0  # L2 pull towards the current prices; higher = slower to believe the data
SMOOTHING = 40.0       # L2 pull between neighbouring level steps of the same stat
DAMPING = 0.3          # fraction of the way to the fair price each rebalance moves
MAX_CHANGE = 0.15      # largest fraction a price can move in one rebalance (at least 1 point)
MIN_Z = 1.0            # only move a price if it is this many standard errors from fair
MODES = ("selfplay", "ai", "local", "lan")


@dataclass(frozen=True)
class Item:
    kind: str      # "stat", "momentum" or "special"
    key: str = ""  # stat or ability key
    step: int = 0  # for stats: the step from level `step` to `step + 1`

    def label(self) -> str:
        if self.kind == "stat":
            stat = next(s for s in STATS if s.key == self.key)
            return f"{stat.label} level {self.step + 1}"
        if self.kind == "momentum":
            return "Momentum on"
        return ABILITIES[self.key].name

    def has(self, ship: dict) -> bool:
        if self.kind == "stat":
            return ship["levels"][self.key] > self.step
        if self.kind == "momentum":
            return bool(ship["momentum"])
        return ship.get("special") == self.key

    def price(self, table: prices.PriceTable) -> int:
        if self.kind == "stat":
            return table.step_cost(self.key, self.step)
        if self.kind == "momentum":
            return table.momentum_cost(True) - table.momentum_cost(False)
        return table.special_cost(self.key)


def items() -> list[Item]:
    return ([Item("stat", s.key, j) for s in STATS for j in range(s.max_level)]
            + [Item("momentum")] + [Item("special", k) for k in ABILITIES])


@dataclass
class Estimate:
    item: Item
    price: int
    fair: float     # fair price in points by the data
    error: float    # standard error of `fair`


@dataclass
class Fit:
    estimates: list[Estimate]
    side_bias: dict[str, float]  # per mode: > 0 means Blue wins more than the ships explain
    rounds: int
    draws: int


def load_rounds() -> list[dict]:
    rounds = match_log.read(match_log.SELFPLAY_FILE) + match_log.read(match_log.MATCHES_FILE)
    rounds.sort(key=lambda r: r.get("time", ""))
    return rounds[-MAX_ROUNDS:]


def fit(rounds: list[dict], table: prices.PriceTable) -> Fit | None:
    """Fit the model to decided rounds. None if there is too little to go on."""
    all_items = items()
    n = len(all_items)
    p = np.array([it.price(table) for it in all_items], dtype=float)
    rows, ys, weights, mode_rows, usage = [], [], [], [], np.zeros(n)
    draws = 0
    for r in rounds:
        try:
            if r["winner"] not in (0, 1):
                draws += 1
                continue
            blue, red = r["ships"]
            has = [[it.has(ship) for it in all_items] for ship in (blue, red)]
            mode = r.get("mode") if r.get("mode") in MODES else "local"
        except (KeyError, TypeError, ValueError, AttributeError):
            continue  # a round logged by an older version, or a broken line
        rows.append([a - b for a, b in zip(*has)])
        usage += np.array(has[0], dtype=float) + np.array(has[1], dtype=float)
        mode_rows.append([m == mode for m in MODES])
        ys.append(1.0 if r["winner"] == 0 else 0.0)
        weights.append(1.0 if mode == "selfplay" else HUMAN_WEIGHT)
    if len(rows) < 100:
        return None
    x = np.hstack([np.array(rows, dtype=float), np.array(mode_rows, dtype=float)])
    y, sw = np.array(ys), np.array(weights)
    usage /= 2 * len(rows)  # how often a ship has each item

    # Penalty matrix on the item weights: towards the prior, and neighbouring steps together.
    penalty = np.zeros((x.shape[1], x.shape[1]))
    penalty[:n, :n] = np.eye(n)
    for i in range(n - 1):
        a, b = all_items[i], all_items[i + 1]
        if a.kind == b.kind == "stat" and a.key == b.key:
            diff = np.zeros(x.shape[1])
            diff[i], diff[i + 1] = 1, -1
            penalty += SMOOTHING / PRIOR_STRENGTH * np.outer(diff, diff)
    penalty *= PRIOR_STRENGTH
    penalty[n:, n:] = np.eye(len(MODES)) * 1e-3  # unused modes would otherwise make the fit singular

    def solve(prior: np.ndarray, pen: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        beta = np.zeros(x.shape[1])
        for _ in range(50):  # Newton's method
            prob = 1 / (1 + np.exp(-(x @ beta)))
            grad = x.T @ (sw * (y - prob)) - pen @ (beta - prior)
            hess = (x * (sw * prob * (1 - prob))[:, None]).T @ x + pen
            step = np.linalg.solve(hess, grad)
            beta += step
            if np.abs(step).max() < 1e-8:
                break
        return beta, hess

    def value_per_point(w: np.ndarray) -> float:
        return float(usage @ w) / float(usage @ p)

    # First a loose fit to find the scale, then the real one pulled towards prices at that scale.
    loose, _ = solve(np.zeros(x.shape[1]), penalty * 0.05)
    theta = value_per_point(loose[:n])
    if theta <= 0:
        return None  # the data doesn't even say upgrades help: don't touch prices
    beta, hess = solve(np.concatenate([theta * p, np.zeros(len(MODES))]), penalty)
    theta = value_per_point(beta[:n])
    if theta <= 0:
        return None
    cov = np.linalg.inv(hess)
    estimates = [Estimate(it, int(p[i]), beta[i] / theta, math.sqrt(max(cov[i, i], 0.0)) / theta)
                 for i, it in enumerate(all_items)]
    bias = {m: float(beta[n + k]) for k, m in enumerate(MODES)}
    return Fit(estimates, bias, len(rows), draws)


def damped(old: int, fair: float, error: float, floor: int) -> int:
    """The new price: part of the way to fair, by at most MAX_CHANGE (or 1 point)."""
    if abs(fair - old) < MIN_Z * error:
        return old  # not clear enough yet
    target = old + DAMPING * (fair - old)
    limit = max(MAX_CHANGE * abs(old), 1.0)
    target = max(old - limit, min(old + limit, target))
    new = round(target)
    if new == old and abs(target - old) >= 0.5:
        new = old + (1 if target > old else -1)
    return max(floor, new)


def repriced(table: prices.PriceTable, result: Fit) -> tuple[prices.PriceTable, list[str]]:
    """A new table from the fit, and a line for each price that changed."""
    stats = {k: list(v) for k, v in table.stats.items()}
    specials = dict(table.specials)
    momentum = dict(table.momentum)
    changes = []
    for e in result.estimates:
        it = e.item
        if it.kind == "momentum":
            # One number for the difference: whichever of on/off is stronger costs it.
            new = damped(e.price, e.fair, e.error, floor=-10**6)
            momentum = {"on": max(new, 0), "off": max(-new, 0)}
            if momentum != table.momentum:
                changes.append((abs(new - e.price), f"Momentum on {table.momentum['on']}->{momentum['on']}, "
                                                    f"off {table.momentum['off']}->{momentum['off']}"))
            continue
        new = damped(e.price, e.fair, e.error, floor=1)
        if new == e.price:
            continue
        if it.kind == "stat":
            stats[it.key][it.step] = new
        else:
            specials[it.key] = new
        changes.append((abs(new - e.price), f"{it.label()} {e.price}->{new}"))
    new_table = prices.PriceTable(version=table.version, budget=table.budget,
                                  stats={k: tuple(v) for k, v in stats.items()},
                                  momentum=momentum, specials=specials, note="")
    changes.sort(key=lambda c: -c[0])  # biggest changes first
    return new_table, [text for _, text in changes]


def rounds_on_current_prices(rounds: list[dict], table: prices.PriceTable) -> float:
    return sum(1.0 if r.get("mode") == "selfplay" else HUMAN_WEIGHT
               for r in rounds if r.get("prices") == table.version)


def auto_rebalance(verbose: bool = False) -> list[str] | None:
    """Rebalance if enough rounds were played on the current prices. Returns the changes
    (possibly none) if it rebalanced, else None."""
    table = config_screen.PRICES
    rounds = load_rounds()
    new_rounds = rounds_on_current_prices(rounds, table)
    if new_rounds < MIN_NEW_ROUNDS:
        if verbose:
            print(f"Not rebalancing yet: {new_rounds:.0f} of {MIN_NEW_ROUNDS} rounds on prices v{table.version}.")
        return None
    result = fit(rounds, table)
    if result is None:
        if verbose:
            print("Not rebalancing: the data doesn't give a usable fit yet.")
        return None
    new_table, changes = repriced(table, result)
    if not changes:
        if verbose:
            print(f"Prices v{table.version} look balanced on {result.rounds} rounds: no changes.")
        return changes
    summary = "; ".join(changes)
    note = f"Rebalanced from {result.rounds} rounds"
    new_table = prices.publish(prices.PriceTable(**{**new_table.__dict__, "note": note,
                                                    "changes": tuple(changes)}))
    config_screen.use_prices(new_table.to_dict())
    if verbose:
        print(f"New prices v{new_table.version}: {summary}")
    return changes


def report(result: Fit) -> str:
    lines = [f"{result.rounds} decided rounds, {result.draws} draws.",
             "Side bias (Blue's edge beyond the ships): "
             + ", ".join(f"{m} {b:+.2f}" for m, b in result.side_bias.items()), "",
             f"{'Item':28} {'price':>5} {'fair':>6} {'+/-':>5}"]
    for e in result.estimates:
        flag = "  dearer" if e.fair - e.price > MIN_Z * e.error else (
            "  cheaper" if e.price - e.fair > MIN_Z * e.error else "")
        lines.append(f"{e.item.label():28} {e.price:5d} {e.fair:6.1f} {e.error:5.1f}{flag}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate what each upgrade is worth and rebalance prices.")
    parser.add_argument("--report", action="store_true", help="only report, don't change prices")
    args = parser.parse_args()
    result = fit(load_rounds(), config_screen.PRICES)
    if result is None:
        print("Not enough rounds logged yet. Run python -m shoot.selfplay to make some.")
        return
    print(report(result))
    print()
    if not args.report:
        auto_rebalance(verbose=True)


if __name__ == "__main__":
    main()
