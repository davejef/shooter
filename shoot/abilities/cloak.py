"""Cloak: invisible to the opponent while the special key is held, from limited cloak time.

Only offered in LAN play: on a shared screen both players would see where the ship is.
"""

from typing import TYPE_CHECKING

from ..bullet import Bullet
from .base import SpecialAbility

if TYPE_CHECKING:
    from ..ship import Ship


class Cloak(SpecialAbility):
    key = "cloak"
    name = "Cloak"
    network_only = True
    CAPACITY = 5.0     # seconds of cloak per round; it does not recharge
    OWN_ALPHA = 0.3    # how visible the ship is on its own player's screen while cloaked
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

    def visibility(self, ship: "Ship", own_view: bool) -> float:
        if not self.up:
            return 1.0
        return self.OWN_ALPHA if own_view else 0.0
