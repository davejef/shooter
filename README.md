# Shoot

A two-player, Asteroids-style ship duel written in Python with pygame.

## Setup (Windows)

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Controls

| Action | Blue (left) | Red (right) |
|--------|-------------|-------------|
| Turn   | A / D       | Left / Right |
| Thrust | W           | Up           |
| Fire   | Space       | Enter        |

- **F1** toggles screen wraparound
- **F2** toggles momentum (drift vs. direct movement)
- **R** starts a new round after someone wins
- **Esc** quits

Ramming the other ship damages both of you.

## Tuning

Ship stats (thrust, turn speed, fire rate, bullet speed, hit points, momentum) are in
`DEFAULT_SHIP` in `shoot/settings.py`. Screen size and wraparound default are there too.
