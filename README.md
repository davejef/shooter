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
each player has **25 points** to spend on hit points, speed, turn speed, bullet speed and
fire rate. Each stat goes from level 0 to 10 at one point per level, and a fresh ship puts
5 points in every stat. Momentum is a free on/off choice.

| Stat         | Level 0 | Level 5 | Level 10 |
|--------------|---------|---------|----------|
| Hit points   | 5       | 10      | 15       |
| Speed        | 200     | 400     | 600      |
| Turn speed   | 120°/s  | 220°/s  | 320°/s   |
| Bullet speed | 300     | 550     | 800      |
| Fire rate    | 2/s     | 4/s     | 6/s      |

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

- **F1** toggles screen wraparound
- **R** starts a new round after someone wins, **C** goes back to ship setup
- **Esc** quits

Ramming the other ship damages both of you.

## LAN play (two PCs)

Both PCs need this folder and the setup steps above, and they must be on the same network.

1. On the first PC run `python main.py --host`. It plays Blue, and the setup screen shows
   the exact command for the other PC, including this PC's IP address.
2. On the second PC run `python main.py --join <that IP>`. It plays Red.
3. The first time you host, Windows Firewall asks whether Python may accept connections.
   Allow it on **Private networks**.

Each player can use either WASD + Space or the arrow keys + Enter. Either player can press
**R** for a rematch or **C** to change ships, and only the host can toggle wraparound with F1.
The host runs the game, so Red may feel a few milliseconds of lag on wifi.
If port 50007 is taken, pick another with `--port` on both PCs.

## Tuning

The point budget (`BUDGET`), the level cap and each stat's level 0 and level 10 values
(`STATS`) are in `shoot/config_screen.py`. Screen size and the
wraparound default are in `shoot/settings.py`. Delete `players.json` to reset both ships.
