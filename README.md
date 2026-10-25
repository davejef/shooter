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

## Tuning

Default ship stats are in `DEFAULT_SHIP` in `shoot/settings.py`, and the setup screen's
ranges and step sizes are in `STATS` in `shoot/config_screen.py`. Screen size and the
wraparound default are in `shoot/settings.py`. Delete `players.json` to reset both ships.
