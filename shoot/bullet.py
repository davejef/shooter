"""Bullets fired by ships."""

from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from . import settings

if TYPE_CHECKING:
    from .ship import Ship


class Bullet:
    RADIUS = 2.5

    def __init__(self, owner: "Ship", pos: Vector2, vel: Vector2, fake: bool = False):
        self.owner = owner
        self.fake = fake  # fired by a decoy: looks real but does no damage
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.age = 0.0
        self.alive = True

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.age += dt
        if self.age >= self.owner.type.bullet_lifetime:
            self.alive = False
            return
        if settings.WRAPAROUND:
            self.pos.x %= settings.SCREEN_WIDTH
            self.pos.y %= settings.SCREEN_HEIGHT
        elif not (0 <= self.pos.x <= settings.SCREEN_WIDTH and 0 <= self.pos.y <= settings.SCREEN_HEIGHT):
            self.alive = False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.circle(surface, self.owner.color, self.pos, self.RADIUS)
