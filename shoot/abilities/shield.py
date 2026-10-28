"""Shield: invulnerable while the special key is held, from limited shield time."""

from typing import TYPE_CHECKING

import pygame

from ..bullet import Bullet
from .base import SpecialAbility

if TYPE_CHECKING:
    from ..ship import Ship


class Shield(SpecialAbility):
    """Invulnerable while the key is held, from a limited supply of shield time each round."""

    key = "shield"
    name = "Shield"
    CAPACITY = 3.0  # seconds of shield per round; it does not recharge
    STATE = ("energy", "up")

    def __init__(self):
        self.energy = self.CAPACITY
        self.up = False

    def update(self, ship: "Ship", dt: float, held: bool) -> list[Bullet]:
        self.up = held and self.energy > 0
        if self.up:
            self.energy = max(0.0, self.energy - dt)
        return []

    @property
    def meter(self) -> float:
        return self.energy / self.CAPACITY

    @property
    def ready(self) -> bool:
        return self.energy > 0

    def absorbs_hit(self, ship: "Ship") -> bool:
        return self.up

    def draw(self, ship: "Ship", surface: pygame.Surface) -> None:
        if not self.up:
            return
        # Flicker in the last half second so both players can see it running out.
        if self.energy > 0.5 or int(self.energy * 20) % 2:
            pygame.draw.circle(surface, ship.color, ship.pos, ship.type.radius + 10, width=2)
