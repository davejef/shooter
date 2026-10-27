"""Spread shot: fires a fan of bullets."""

from typing import TYPE_CHECKING

from ..bullet import Bullet
from .base import TriggeredAbility

if TYPE_CHECKING:
    from ..ship import Ship


class SpreadShot(TriggeredAbility):
    key = "spread"
    name = "Spread shot"
    cost = 2
    cooldown = 5.0
    ANGLES = (-24, -12, 0, 12, 24)

    def activate(self, ship: "Ship") -> list[Bullet]:
        bullets = []
        for offset in self.ANGLES:
            direction = ship.forward().rotate(offset)
            nose = ship.pos + direction * (ship.type.radius + 6)
            bullets.append(Bullet(ship, nose, ship.vel + direction * ship.type.bullet_speed))
        return bullets
