"""Base classes for special abilities."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

import pygame

from ..bullet import Bullet

if TYPE_CHECKING:
    from ..ship import Ship


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
