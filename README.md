# Shoot

A two-player, Asteroids-style ship duel written in Python with pygame.

## Setup (Windows)

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Ship setup

The game opens on a setup screen with one panel per player. Ships are built with point buy:
each player has **100 points** to spend on hit points, speed, turn speed, bullet speed and
fire rate, momentum (on or off) and an optional special ability. A fresh ship costs exactly 100.

Prices come from `prices.json` (see [Prices](#prices) below), so they can change as the game is
rebalanced. Each level of a stat has its own price, and higher levels cost more. On the setup
screen the selected stat shows what the next level costs and what selling one gives back.

| Stat         | Range        | Default | Price per level (v1)            |
|--------------|--------------|---------|---------------------------------|
| Hit points   | 1 to 5       | 3       | 9, 12, 15, 18                   |
| Speed        | 200 to 600   | 400     | 3, 3, 4, 4, 5, 5, 6, 6, 7, 7    |
| Turn speed   | 120 to 320°/s| 220°/s  | as speed                        |
| Bullet speed | 300 to 800   | 550     | as speed                        |
| Fire rate    | 2 to 6/s     | 4/s     | as speed                        |
| Momentum     | on / off     | on      | on 3, off 0                     |
| Special      |              | none    | 8 each                          |

| Special      | Effect                                              | Recharge |
|--------------|-----------------------------------------------------|----------|
| Shield       | Hold the key to stay invulnerable (even to ramming). 3 s of shield per round | none |
| Spread shot  | Fires a fan of 5 bullets                            | 5 s      |
| Hyperspace   | Jumps to a random spot on the screen                | 6 s      |
| Cloak        | Hold the key to vanish from the opponent's screen (you see a faint outline). 5 s per round. LAN play only | none |
| Mirror image | Passive. Each round you fly as 3 identical ships in formation; only one (random) is real. You see which, your opponent doesn't. Decoys fire harmless bullets and vanish when shot or rammed. LAN play only | none |

| Action       | Blue    | Red           |
|--------------|---------|---------------|
| Choose stat  | W / S   | Up / Down     |
| Sell / buy   | A / D   | Left / Right  |
| Ready        | Space   | Enter         |

The match starts when both players are ready. Choices are saved to `players.json` and
loaded next time. If prices have changed since, a saved ship that no longer fits the budget
has levels sold until it does.

## Controls

| Action | Blue (left) | Red (right) |
|--------|-------------|-------------|
| Turn   | A / D       | Left / Right |
| Thrust | W           | Up           |
| Fire   | Space       | Enter        |
| Special | Left Shift | Right Shift  |

- **F1** toggles screen wraparound
- **R** starts a new round after someone wins, **C** goes back to ship setup
- **Esc** quits

Ramming the other ship damages both of you.

## Playing against the computer

Run `python main.py --ai`. You fly Blue with either WASD + Space + Left Shift or the arrow
keys + Enter + Right Shift; the computer flies Red with Red's last saved ship. It leads its
shots, closes to about 300 px, sidesteps incoming bullets and uses Shield, Spread shot,
Hyperspace or Cloak when they help. It only sees what a person would: it loses track of a
cloaked ship and can't tell a Mirror image decoy from the real ship. To make it easier or harder, change `AIM_ERROR` and
`THINK_INTERVAL` at the top of `shoot/ai.py`.

## LAN play (two PCs)

Both PCs need this folder and the setup steps above, and they must be on the same network.

1. On the first PC run `python main.py --host`. It plays Blue, and the setup screen shows
   the exact command for the other PC, including this PC's IP address.
2. On the second PC run `python main.py --join <that IP>`. It plays Red.
3. The first time you host, Windows Firewall asks whether Python may accept connections.
   Allow it on **Private networks**.

Each player can use either WASD + Space + Left Shift or the arrow keys + Enter + Right Shift. Either player can press
**R** for a rematch or **C** to change ships, and only the host can toggle wraparound with F1.
The host runs the game, so Red may feel a few milliseconds of lag on wifi.
If port 50007 is taken, pick another with `--port` on both PCs.

## Prices

`prices.json` holds the live price table: the budget, the price of every level step of each
stat, momentum on and off, and each special. Every version is also kept in `prices/`
(`v0001.json`, `v0002.json`, ...), so any change can be undone:

```
python -m shoot.prices           show the live version and the saved ones
python -m shoot.prices --use 1   bring back version 1's prices (saved as a new version)
```

In LAN play the host's prices are used: the host sends its table to the joiner when it
connects. The setup screen shows which version is in use.

### Automatic rebalancing

The game keeps prices balanced by itself. Every finished round is logged with both ships:
games people play go to `matches.jsonl` (in LAN play the host logs them), and
computer-vs-computer games go to `selfplay.jsonl`. Both logs stay on this PC (gitignored).

Once 1000 rounds have been played on the current prices (a round people played counts
double), the next start of the game fits a model of how much each level step, momentum and
each special adds to the chance of winning. Anything that wins more than its price says gets
dearer, and anything that wins less gets cheaper. Each rebalance moves a price only part of
the way, by at most 15% (or 1 point), and only where the data is clear. The new prices are
saved as a new version, and the setup screen shows what changed until the next match starts.
Commit `prices.json` and `prices/` to share them.

People can't play enough games for this on their own, so the computer plays itself:

```
python -m shoot.selfplay --games 2000              about 10 s per 1000 rounds on 4 cores
python -m shoot.selfplay --games 1500 --cycles 5   play, rebalance, repeat
python -m shoot.balance --report                   what each upgrade is worth by the data so far
```

Self-play uses random builds that spend the whole budget, so every upgrade gets tried in
many combinations. Prices end up balanced for how the computer plays, which is not quite
how people play: human rounds count double to pull them back towards that.

## Tuning

Each stat's range, number of levels and default (`STATS`) are in `shoot/config_screen.py`,
and its prices are in `prices.json`. Screen size and the wraparound default are in `shoot/settings.py`.

To add a special ability, subclass `SpecialAbility` in a new module in the `shoot/abilities/` package: set `key`
and `name` (its price goes in `prices.json`; until then it costs 8, and rebalancing will price it), implement `update(ship, dt, held)` and `meter`, and override
`absorbs_hit()`, `draw()` or `visibility()` if needed. Set `network_only = True` for an
ability that only makes sense with two screens. Other hooks: `images()`, `extra_shots()`, `intercept()`
and `public_positions()` (see `mirror_image.py`). For a press-to-fire power with a recharge, subclass
`TriggeredAbility` instead and just set `cooldown` and implement `activate()`. Add the class
to `ABILITIES` in `shoot/abilities/__init__.py`. It then appears on the
setup screen and works in LAN play. Delete `players.json` to reset both ships.
