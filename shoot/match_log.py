"""Match history for rebalancing: one JSON line per finished round, with both ships.

matches.jsonl holds games people played (local, LAN and against the computer), and
selfplay.jsonl holds computer-vs-computer games from `python -m shoot.selfplay`.
Both stay on this PC (they are gitignored); only the prices they lead to are committed.
"""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATCHES_FILE = ROOT / "matches.jsonl"
SELFPLAY_FILE = ROOT / "selfplay.jsonl"


def entry(mode: str, loadouts, winner: int, seconds: float, prices_version: int) -> dict:
    """One round. mode: "local", "lan", "ai" (person vs computer) or "selfplay".
    winner: 0 Blue, 1 Red, -1 draw."""
    return {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": mode, "prices": prices_version,
            "ships": [l.to_dict() for l in loadouts], "winner": winner, "seconds": round(seconds, 1)}


def append(entries: list[dict], path: Path = MATCHES_FILE) -> None:
    try:
        with path.open("a") as f:
            for e in entries:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
    except OSError:
        pass  # a read-only folder shouldn't stop the game


def read(path: Path) -> list[dict]:
    """Every round in a log, skipping lines that are cut off or broken."""
    rounds = []
    try:
        with path.open() as f:
            for line in f:
                try:
                    rounds.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rounds
