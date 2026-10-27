"""Hyperspace: jumps to a random spot on the screen."""

import random
from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from .. import settings
from ..bullet import Bullet
from .base import TriggeredAbility

if TYPE_CHECKING:
    from ..ship import Ship


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
