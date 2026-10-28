"""Mirror image: the ship starts each round as three identical ships flying in formation.

Only one is real, picked at random. Its own player sees which (the decoys are drawn
faintly); the opponent sees three identical ships. Decoys copy every move, fire harmless
bullets when the real ship fires, and vanish when hit by a real bullet or rammed.
Passive: the special key does nothing. Only offered in LAN play, and the opponent's PC is
never sent which ship is real.
"""

import random
from typing import TYPE_CHECKING

from pygame.math import Vector2

from .. import settings
from ..bullet import Bullet
from .base import SpecialAbility

if TYPE_CHECKING:
    from ..ship import Ship


class MirrorImage(SpecialAbility):
    key = "mirror"
    name = "Mirror image"
    network_only = True
    passive = True
    SLOTS = 3
    SPACING = 70     # px between ships in the formation, side by side
    DECOY_ALPHA = 0.4  # how decoys look on their own player's screen

    def __init__(self):
        self.real = random.randrange(self.SLOTS)  # which formation slot the real ship flies in
        self.alive = [True] * self.SLOTS          # the real slot stays True; the ship itself has hp
        # Set on the opponent's PC instead of the above: just where to draw identical ships.
        self.disguised: list[Vector2] | None = None

    def update(self, ship: "Ship", dt: float, held: bool) -> list[Bullet]:
        return []

    @property
    def decoys_left(self) -> int:
        if self.disguised is not None:
            return len(self.disguised) - 1
        return sum(self.alive) - 1

    @property
    def meter(self) -> float:
        return self.decoys_left / (self.SLOTS - 1)

    @property
    def ready(self) -> bool:
        return self.decoys_left > 0

    def decoy_positions(self, ship: "Ship") -> list[Vector2]:
        return [self._slot_pos(ship, k) for k in self._decoy_slots()]

    def _decoy_slots(self) -> list[int]:
        return [k for k in range(self.SLOTS) if k != self.real and self.alive[k]]

    def _slot_pos(self, ship: "Ship", slot: int) -> Vector2:
        pos = ship.pos + Vector2(0, (slot - self.real) * self.SPACING).rotate(ship.angle)
        if settings.WRAPAROUND:
            pos.x %= settings.SCREEN_WIDTH
            pos.y %= settings.SCREEN_HEIGHT
        return pos

    def images(self, ship: "Ship", own_view: bool) -> list[tuple[Vector2, float]]:
        if self.disguised is not None:
            return [(p, 1.0) for p in self.disguised]
        decoy_alpha = self.DECOY_ALPHA if own_view else 1.0
        return [(ship.pos, 1.0)] + [(p, decoy_alpha) for p in self.decoy_positions(ship)]

    def extra_shots(self, ship: "Ship", shots: list[Bullet]) -> list[Bullet]:
        fakes = []
        for decoy in self.decoy_positions(ship):
            for shot in shots:
                fakes.append(Bullet(ship, decoy + (shot.pos - ship.pos), shot.vel, fake=True))
        return fakes

    def intercept(self, ship: "Ship", pos: Vector2, radius: float, destroy: bool) -> bool:
        for k in self._decoy_slots():
            if self._slot_pos(ship, k).distance_to(pos) < ship.type.radius + radius:
                if destroy:
                    self.alive[k] = False
                return True
        return False

    # Over LAN the opponent gets nothing here, only public_positions() in place of the ship's.
    def state(self, own_view: bool) -> dict:
        return {"real": self.real, "alive": self.alive} if own_view else {}

    def load_state(self, state: dict) -> None:
        if "real" in state:
            self.real, self.alive, self.disguised = state["real"], state["alive"], None

    def public_positions(self, ship: "Ship") -> list[Vector2]:
        positions = [Vector2(ship.pos)] + self.decoy_positions(ship)
        random.shuffle(positions)
        return positions
