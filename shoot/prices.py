"""Point-buy prices: the budget, and what each stat level, momentum and special ability costs.

Prices are data, not code, so they can be rebalanced from match results. The live table is
prices.json at the top of the repo, and every version is also kept in prices/ (v0001.json,
v0002.json, ...) so any change can be undone:

    python -m shoot.prices             show the live table and the saved versions
    python -m shoot.prices --use 3     make version 3 the live table again

Stat prices are per step: the list for a stat holds the cost of going from level 0 to 1, from
1 to 2, and so on, so a stat can get dearer (or cheaper) the higher it goes.
"""

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE_FILE = ROOT / "prices.json"
HISTORY_DIR = ROOT / "prices"

# Used for anything prices.json leaves out, such as a newly added special ability.
DEFAULT_BUDGET = 100
DEFAULT_SPECIAL = 8
DEFAULT_MOMENTUM = {"on": 3, "off": 0}


def default_steps(max_level: int) -> list[int]:
    """Gently rising step costs: 3, 3, 4, 4, 5, ... for a stat with 10 levels."""
    return [3 + k // 2 for k in range(max_level)]


@dataclass(frozen=True)
class PriceTable:
    version: int
    budget: int
    stats: dict[str, tuple[int, ...]]  # stat key -> cost of each level step, from level 0 up
    momentum: dict[str, int]           # "on" / "off" -> cost of that choice
    specials: dict[str, int]           # ability key -> cost
    note: str = ""                     # why this version exists, e.g. what a rebalance changed

    def stat_cost(self, key: str, level: int) -> int:
        """Total cost of a stat at this level."""
        return sum(self.stats[key][:level])

    def step_cost(self, key: str, level: int) -> int:
        """Cost of going from this level to the next one."""
        return self.stats[key][level]

    def momentum_cost(self, on: bool) -> int:
        return self.momentum["on" if on else "off"]

    def special_cost(self, key: str | None) -> int:
        return self.specials[key] if key else 0

    def to_dict(self) -> dict:
        return {"version": self.version, "budget": self.budget, "note": self.note,
                "stats": {k: list(v) for k, v in self.stats.items()},
                "momentum": dict(self.momentum), "specials": dict(self.specials)}

    @classmethod
    def from_dict(cls, data: dict, stat_levels: dict[str, int], special_keys: list[str]) -> "PriceTable":
        """Build a table for these stats (key -> number of levels) and specials, filling gaps
        with defaults. Raises ValueError if the data is malformed."""
        def price(v) -> int:
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError(f"bad price {v!r}")
            return v

        try:
            stats = {}
            for key, levels in stat_levels.items():
                steps = [price(c) for c in data.get("stats", {}).get(key, default_steps(levels))]
                if len(steps) != levels:
                    raise ValueError(f"{key} needs {levels} step prices, got {len(steps)}")
                stats[key] = tuple(steps)
            momentum = {k: price(data.get("momentum", {}).get(k, v)) for k, v in DEFAULT_MOMENTUM.items()}
            specials = {k: price(data.get("specials", {}).get(k, DEFAULT_SPECIAL)) for k in special_keys}
            return cls(version=int(data.get("version", 0)), budget=price(data.get("budget", DEFAULT_BUDGET)),
                       stats=stats, momentum=momentum, specials=specials, note=str(data.get("note", "")))
        except (TypeError, AttributeError) as e:
            raise ValueError(f"bad price table: {e}") from None


def load(stat_levels: dict[str, int], special_keys: list[str]) -> PriceTable:
    """The live table, or all defaults if prices.json is missing or broken."""
    try:
        return PriceTable.from_dict(json.loads(LIVE_FILE.read_text()), stat_levels, special_keys)
    except (OSError, ValueError):
        return PriceTable.from_dict({}, stat_levels, special_keys)


def history_file(version: int) -> Path:
    return HISTORY_DIR / f"v{version:04d}.json"


def versions() -> list[int]:
    return sorted(int(p.stem[1:]) for p in HISTORY_DIR.glob("v[0-9]*.json"))


def _write(path: Path, table: dict) -> None:
    path.parent.mkdir(exist_ok=True)
    text = json.dumps(table, indent=2)
    text = re.sub(r"\[[\d,\s]*\]", lambda m: json.dumps(json.loads(m.group())), text)  # one line per list
    path.write_text(text + "\n")


def publish(table: PriceTable) -> PriceTable:
    """Save a new version (numbered after the newest one) and make it live."""
    new = PriceTable(**{**table.__dict__, "version": max(versions(), default=0) + 1})
    _write(history_file(new.version), new.to_dict())
    _write(LIVE_FILE, new.to_dict())
    return new


def use_version(version: int) -> None:
    """Make an old version live again, e.g. to undo a rebalance."""
    _write(LIVE_FILE, json.loads(history_file(version).read_text()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Show or roll back the point-buy price table.")
    parser.add_argument("--use", type=int, metavar="VERSION", help="make this saved version the live table")
    args = parser.parse_args()
    if args.use is not None:
        if args.use not in versions():
            raise SystemExit(f"No version {args.use}. Saved versions: {versions()}")
        use_version(args.use)
    live = json.loads(LIVE_FILE.read_text()) if LIVE_FILE.exists() else None
    print(f"Live: version {live['version']}  {live.get('note', '')}" if live else "Live: built-in defaults")
    for v in versions():
        note = json.loads(history_file(v).read_text()).get("note", "")
        print(f"  v{v}  {note}")


if __name__ == "__main__":
    main()
