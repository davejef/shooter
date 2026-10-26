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

The game opens on a setup screen with one panel per player. Each player tunes their own ship:
hit points, speed, turn speed, bullet speed, fire rate and momentum.

| Action       | Blue    | Red           |
|--------------|---------|---------------|
| Choose stat  | W / S   | Up / Down     |
| Change value | A / D   | Left / Right  |
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

Default ship stats are in `DEFAULT_SHIP` in `shoot/settings.py`, and the setup screen's
ranges and step sizes are in `STATS` in `shoot/config_screen.py`. Screen size and the
wraparound default are in `shoot/settings.py`. Delete `players.json` to reset both ships.
