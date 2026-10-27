"""Special abilities: an optional extra power a ship triggers with its special key.

To add one, subclass SpecialAbility, fill in the class attributes and activate(), and
add the class to ABILITIES. It then shows up on the setup screen and works over LAN.
"""

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

import pygame
from pygame.math import Vector2

from . import settings
from .bullet import Bullet

if TYPE_CHECKING:
    from .ship import Ship


class SpecialAbility(ABC):
    key: ClassVar[str]          # id used in saves and over the network
    name: ClassVar[str]         # shown on the setup screen and HUD
    cost: ClassVar[int]         # setup points
    cooldown: ClassVar[float]   # seconds from one use to the next
    duration: ClassVar[float] = 0.0  # seconds the effect lasts; 0 for instant abilities

    def __init__(self):
        self.recharge = 0.0     # seconds until it can be used again
        self.active_left = 0.0  # seconds of effect remaining

    @property
    def ready(self) -> bool:
        return self.recharge <= 0.0

    @property
    def active(self) -> bool:
        return self.active_left > 0.0

    def try_trigger(self, ship: "Ship") -> list[Bullet]:
        """Use the ability if it has recharged. Returns any bullets it fires."""
        if not self.ready:
            return []
        self.recharge = self.cooldown
        self.active_left = self.duration
        return self.activate(ship)

    @abstractmethod
    def activate(self, ship: "Ship") -> list[Bullet]:
        """Apply the ability's effect to ship; return any bullets it fires."""

    def update(self, ship: "Ship", dt: float) -> None:
        self.recharge = max(0.0, self.recharge - dt)
        self.active_left = max(0.0, self.active_left - dt)

    def absorbs_hit(self, ship: "Ship") -> bool:
        """Return True to cancel incoming damage."""
        return False

    def draw(self, ship: "Ship", surface: pygame.Surface) -> None:
        """Draw any visible effect around the ship."""

    # Everything the other PC needs to draw this ability in LAN play.
    def state(self) -> dict:
        return {"recharge": round(self.recharge, 2), "active": round(self.active_left, 2)}

    def load_state(self, state: dict) -> None:
        self.recharge = state["recharge"]
        self.active_left = state["active"]


class Shield(SpecialAbility):
    key = "shield"
    name = "Shield"
    cost = 2
    cooldown = 8.0
    duration = 1.5

    def activate(self, ship: "Ship") -> list[Bullet]:
        return []

    def absorbs_hit(self, ship: "Ship") -> bool:
        return self.active

    def draw(self, ship: "Ship", surface: pygame.Surface) -> None:
        if self.active:
            # Flicker in the last half second so the other player can see it ending.
            if self.active_left > 0.5 or int(self.active_left * 20) % 2:
                pygame.draw.circle(surface, ship.color, ship.pos, ship.type.radius + 10, width=2)


class SpreadShot(SpecialAbility):
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


class Hyperspace(SpecialAbility):
    key = "hyperspace"
    name = "Hyperspace"
    cost = 2
    cooldown = 6.0
    duration = 0.4  # how long the arrival flash shows

    MARGIN = 60

    def activate(self, ship: "Ship") -> list[Bullet]:
        ship.pos = Vector2(random.uniform(self.MARGIN, settings.SCREEN_WIDTH - self.MARGIN),
                           random.uniform(self.MARGIN, settings.SCREEN_HEIGHT - self.MARGIN))
        return []

    def draw(self, ship: "Ship", surface: pygame.Surface) -> None:
        if self.active:
            radius = ship.type.radius + 30 * self.active_left / self.duration
            pygame.draw.circle(surface, ship.color, ship.pos, radius, width=1)


ABILITIES: dict[str, type[SpecialAbility]] = {cls.key: cls for cls in (Shield, SpreadShot, Hyperspace)}


def make_ability(key: str | None) -> SpecialAbility | None:
    return ABILITIES[key]() if key else None
