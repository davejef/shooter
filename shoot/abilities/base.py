"""Base classes for special abilities."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

import pygame
from pygame.math import Vector2

from ..bullet import Bullet

if TYPE_CHECKING:
    from ..ship import Ship


class SpecialAbility(ABC):
    key: ClassVar[str]    # id used in saves and over the network
    name: ClassVar[str]   # shown on the setup screen and HUD
    cost: ClassVar[int]   # setup points
    network_only: ClassVar[bool] = False  # True to offer it only in LAN play
    passive: ClassVar[bool] = False       # True if it works without the special key
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

    def visibility(self, ship: "Ship", own_view: bool) -> float:
        """How visible the ship is, from 0 (hidden) to 1, on its own player's screen
        (own_view True) or the opponent's. Only differs from 1 in LAN play."""
        return 1.0

    def images(self, ship: "Ship", own_view: bool) -> list[tuple[Vector2, float]]:
        """Where to draw the ship, as (position, visibility) pairs. Usually just one."""
        return [(ship.pos, self.visibility(ship, own_view))]

    def extra_shots(self, ship: "Ship", shots: list[Bullet]) -> list[Bullet]:
        """More bullets to add whenever the ship fires its normal gun."""
        return []

    def intercept(self, ship: "Ship", pos: Vector2, radius: float, destroy: bool) -> bool:
        """Return True if something at pos hits a part of the ship other than the real one
        (it is then stopped there and does no damage). destroy: whether it was a real hit."""
        return False

    def public_positions(self, ship: "Ship") -> list[Vector2] | None:
        """Where the opponent's PC should draw this ship when it must not be told the real
        position, or None to send the real position as usual."""
        return None

    def state(self, own_view: bool) -> dict:
        """What to send over LAN; own_view says whether it goes to this ship's own player."""
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
