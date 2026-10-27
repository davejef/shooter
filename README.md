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
each player has **24 points** to spend on hit points, speed, turn speed, bullet speed and
fire rate, which is exactly what the default ship costs. Momentum is a free on/off choice.
An optional special ability costs 2 points, so you sell some stats to afford one.

| Stat         | Range        | Default | Cost              |
|--------------|--------------|---------|-------------------|
| Hit points   | 1 to 5       | 3       | 2 points per HP   |
| Speed        | 200 to 600   | 400     | 1 point per 40    |
| Turn speed   | 120 to 320°/s| 220°/s  | 1 point per 20°/s |
| Bullet speed | 300 to 800   | 550     | 1 point per 50    |
| Fire rate    | 2 to 6/s     | 4/s     | 1 point per 0.4/s |

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
loaded next time.

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
shots, closes to about 300 px, sidesteps incoming bullets and uses Shield, Spread shot or
Hyperspace when they help. To make it easier or harder, change `AIM_ERROR` and
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

## Tuning

The point budget (`BUDGET`) and each stat's range, levels, default and cost (`STATS`) are
in `shoot/config_screen.py`. Screen size and the
wraparound default are in `shoot/settings.py`.

To add a special ability, subclass `SpecialAbility` in a new module in the `shoot/abilities/` package: set `key`,
`name` and `cost`, implement `update(ship, dt, held)` and `meter`, and override
`absorbs_hit()`, `draw()` or `visibility()` if needed. Set `network_only = True` for an
ability that only makes sense with two screens. Other hooks: `images()`, `extra_shots()`, `intercept()`
and `public_positions()` (see `mirror_image.py`). For a press-to-fire power with a recharge, subclass
`TriggeredAbility` instead and just set `cooldown` and implement `activate()`. Add the class
to `ABILITIES` in `shoot/abilities/__init__.py`. It then appears on the
setup screen and works in LAN play. Delete `players.json` to reset both ships.
