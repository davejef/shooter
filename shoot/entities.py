"""Ships and bullets. These know nothing about the keyboard: they act on a ShipInput,
so the same code can later be driven by a network peer or an AI."""

from dataclasses import dataclass

import pygame
from pygame.math import Vector2

from . import settings
from .settings import ShipType

# Ship outline in local space, nose pointing along +x.
SHIP_SHAPE = [Vector2(18, 0), Vector2(-12, -11), Vector2(-6, 0), Vector2(-12, 11)]
FLAME_SHAPE = [Vector2(-8, -5), Vector2(-20, 0), Vector2(-8, 5)]


@dataclass
class ShipInput:
    turn: int = 0        # -1 left, 0 none, +1 right
    thrust: bool = False
    fire: bool = False


def wrap_or_clamp(pos: Vector2, vel: Vector2, radius: float) -> None:
    """Keep pos on screen, either by wrapping or by bouncing off the edges."""
    w, h = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
    if settings.WRAPAROUND:
        pos.x %= w
        pos.y %= h
        return
    if pos.x < radius:
        pos.x, vel.x = radius, abs(vel.x) * 0.5
    elif pos.x > w - radius:
        pos.x, vel.x = w - radius, -abs(vel.x) * 0.5
    if pos.y < radius:
        pos.y, vel.y = radius, abs(vel.y) * 0.5
    elif pos.y > h - radius:
        pos.y, vel.y = h - radius, -abs(vel.y) * 0.5


class Bullet:
    RADIUS = 2.5

    def __init__(self, owner: "Ship", pos: Vector2, vel: Vector2):
        self.owner = owner
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


class Ship:
    def __init__(self, ship_type: ShipType, color, pos: Vector2, angle: float):
        self.type = ship_type
        self.color = color
        self.spawn_pos = Vector2(pos)
        self.spawn_angle = angle
        self.reset()

    def reset(self) -> None:
        self.pos = Vector2(self.spawn_pos)
        self.vel = Vector2()
        self.angle = self.spawn_angle  # degrees, 0 = facing right
        self.hp = self.type.hit_points
        self.cooldown = 0.0
        self.thrusting = False
        self.hit_flash = 0.0

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def forward(self) -> Vector2:
        return Vector2(1, 0).rotate(self.angle)

    def update(self, dt: float, ctrl: ShipInput) -> list[Bullet]:
        """Advance one frame and return any bullets fired."""
        t = self.type
        self.angle = (self.angle + ctrl.turn * t.turn_speed * dt) % 360
        self.thrusting = ctrl.thrust

        if t.momentum:
            if ctrl.thrust:
                self.vel += self.forward() * t.thrust * dt
        else:
            self.vel = self.forward() * t.max_speed if ctrl.thrust else Vector2()
        if self.vel.length() > t.max_speed:
            self.vel.scale_to_length(t.max_speed)

        self.pos += self.vel * dt
        wrap_or_clamp(self.pos, self.vel, t.radius)

        self.cooldown = max(0.0, self.cooldown - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)

        if ctrl.fire and self.cooldown == 0.0:
            self.cooldown = t.fire_cooldown
            nose = self.pos + self.forward() * (t.radius + 6)
            return [Bullet(self, nose, self.vel + self.forward() * t.bullet_speed)]
        return []

    def take_hit(self, damage: int) -> None:
        self.hp = max(0, self.hp - damage)
        self.hit_flash = 0.12

    def draw(self, surface: pygame.Surface) -> None:
        if not self.alive:
            return
        color = (255, 255, 255) if self.hit_flash > 0 else self.color
        points = [self.pos + p.rotate(self.angle) for p in SHIP_SHAPE]
        pygame.draw.polygon(surface, color, points, width=2)
        if self.thrusting:
            flame = [self.pos + p.rotate(self.angle) for p in FLAME_SHAPE]
            pygame.draw.lines(surface, (255, 200, 60), False, flame, width=2)
