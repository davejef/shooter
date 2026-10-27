"""Special abilities: an optional extra power a ship uses with its special key.

To add one, subclass SpecialAbility (or TriggeredAbility for a press-to-fire power with a
recharge), fill in the class attributes and abstract methods, and add the class to
ABILITIES. It then shows up on the setup screen and works over LAN.
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
    key: ClassVar[str]    # id used in saves and over the network
    name: ClassVar[str]   # shown on the setup screen and HUD
    cost: ClassVar[int]   # setup points
    # Attributes sent over LAN every frame so the other PC can draw this ability.
    STATE: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def update(self, ship: "Ship", dt: float, held: bool) -> list[Bullet]:
        """Called every frame with whether the special key is held. Returns any bullets fired."""

    @property
    @abstractmethod
    def meter(self) -> float:
        """How full the HUD bar under the health bar is, from 0 to 1."""

    @property
    def ready(self) -> bool:
        """Whether the ability can be used right now (the HUD shows READY)."""
        return self.meter >= 1.0

    def absorbs_hit(self, ship: "Ship") -> bool:
        """Return True to cancel incoming damage."""
        return False

    def draw(self, ship: "Ship", surface: pygame.Surface) -> None:
        """Draw any visible effect around the ship."""

    def state(self) -> dict:
        return {name: getattr(self, name) for name in self.STATE}

    def load_state(self, state: dict) -> None:
        for name in self.STATE:
            setattr(self, name, state[name])


class TriggeredAbility(SpecialAbility):
    """Fires once when the key is pressed, then recharges for `cooldown` seconds."""

    cooldown: ClassVar[float]        # seconds from one use to the next
    duration: ClassVar[float] = 0.0  # seconds the visible effect lasts after use
    STATE = ("recharge", "active_left")

    def __init__(self):
        self.recharge = 0.0
        self.active_left = 0.0

    @abstractmethod
    def activate(self, ship: "Ship") -> list[Bullet]:
        """Apply the ability's effect to ship; return any bullets it fires."""

    def update(self, ship: "Ship", dt: float, held: bool) -> list[Bullet]:
        self.recharge = max(0.0, self.recharge - dt)
        self.active_left = max(0.0, self.active_left - dt)
        if held and self.recharge == 0.0:
            self.recharge = self.cooldown
            self.active_left = self.duration
            return self.activate(ship)
        return []

    @property
    def meter(self) -> float:
        return 1.0 - self.recharge / self.cooldown


class Shield(SpecialAbility):
    """Invulnerable while the key is held, from a limited supply of shield time each round."""

    key = "shield"
    name = "Shield"
    cost = 2
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


class Hyperspace(TriggeredAbility):
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
        if self.active_left > 0:
            radius = ship.type.radius + 30 * self.active_left / self.duration
            pygame.draw.circle(surface, ship.color, ship.pos, radius, width=1)


ABILITIES: dict[str, type[SpecialAbility]] = {cls.key: cls for cls in (Shield, SpreadShot, Hyperspace)}


def make_ability(key: str | None) -> SpecialAbility | None:
    return ABILITIES[key]() if key else None
