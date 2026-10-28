"""The first computer pilot, kept unchanged as a yardstick for the current one (see arena.py).

It produces the same ShipInput a player's keyboard would, from what it can see: it turns
to lead its shots at the opponent, closes in when far away, fires when lined up, and
sidesteps bullets that are about to hit it. It uses its special ability when it helps.

It only knows what a person on the opponent's screen would: a cloaked ship is out of sight
(it guesses where it went from where it was last seen), and against Mirror image it picks
one of the identical ships at random to chase.
"""

import random

from pygame.math import Vector2

from . import settings
from .bullet import Bullet
from .ship import Ship, ShipInput

AIM_TOLERANCE = 8       # degrees off target at which it will fire
PREFERRED_RANGE = 300   # px it tries to keep from the opponent
DANGER_TIME = 0.5       # s ahead it looks for incoming bullets
DANGER_RADIUS = 40      # px; a bullet passing closer than this is a threat
THINK_INTERVAL = 0.12   # s between decisions, so it reacts like a person, not instantly
AIM_ERROR = 5           # degrees of random aim error per decision
BLIND_FIRE_TIME = 1.5   # s it keeps shooting at where it guesses an unseen enemy is


def wrapped_delta(src: Vector2, dst: Vector2) -> Vector2:
    """Shortest vector from src to dst, going across the screen edge when wraparound is on."""
    d = dst - src
    if settings.WRAPAROUND:
        w, h = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        d.x = (d.x + w / 2) % w - w / 2
        d.y = (d.y + h / 2) % h - h / 2
    return d


def angle_diff(a: float, b: float) -> float:
    """Signed difference b - a in degrees, in (-180, 180]."""
    return (b - a + 180) % 360 - 180


class SimpleAI:
    def __init__(self, me: Ship, enemy: Ship):
        self.me = me
        self.enemy = enemy
        self.think_timer = 0.0
        self.aim_error = 0.0
        self.dodge: int = 0  # -1/+1 turn direction while dodging, 0 when not
        # What it believes about the enemy: last seen position and velocity.
        self.seen_pos = Vector2(enemy.pos)
        self.seen_vel = Vector2()
        self.unseen_time = 0.0
        self.pick: int | None = None     # which look-alike it is chasing
        self.sightings_count = 0
        self.watched_ability = None      # the enemy ability the above belongs to (new each round)

    def _perceive(self, dt: float) -> None:
        """Update seen_pos and seen_vel from what is visible this frame."""
        enemy = self.enemy
        if enemy.ability is not self.watched_ability:  # new round
            self.watched_ability, self.pick, self.sightings_count = enemy.ability, None, 0
            self.unseen_time = 0.0
        sightings = enemy.ability.sightings(enemy) if enemy.ability else [enemy.pos]
        if sightings:
            if self.pick is None or len(sightings) != self.sightings_count:
                self.pick = random.randrange(len(sightings))  # a look-alike vanished: choose again
                self.sightings_count = len(sightings)
            self.seen_pos = Vector2(sightings[self.pick])
            self.seen_vel = Vector2(enemy.vel)
            self.unseen_time = 0.0
        else:
            # Out of sight: assume it carried on the way it was going.
            self.unseen_time += dt
            self.seen_pos += self.seen_vel * dt
            if settings.WRAPAROUND:
                self.seen_pos.x %= settings.SCREEN_WIDTH
                self.seen_pos.y %= settings.SCREEN_HEIGHT

    def decide(self, bullets: list[Bullet], dt: float) -> ShipInput:
        me, enemy = self.me, self.enemy
        if not me.alive or not enemy.alive:
            return ShipInput()
        self._perceive(dt)

        self.think_timer -= dt
        if self.think_timer <= 0:
            self.think_timer = THINK_INTERVAL
            self.aim_error = random.uniform(-AIM_ERROR, AIM_ERROR)
            self.dodge = self._dodge_direction(bullets)

        to_enemy = wrapped_delta(me.pos, self.seen_pos)
        distance = to_enemy.length()
        aim = self._lead(to_enemy)
        error = angle_diff(me.angle, Vector2(1, 0).angle_to(aim) + self.aim_error)
        in_range = (distance < me.type.bullet_speed * me.type.bullet_lifetime * 0.9
                    and self.unseen_time < BLIND_FIRE_TIME)

        if self.dodge:
            # Turn across the bullet's path and burn.
            turn, thrust = self.dodge, True
        else:
            turn = 0 if abs(error) < 3 else (1 if error > 0 else -1)
            facing = abs(error) < 30
            thrust = facing and distance > PREFERRED_RANGE
            if me.type.momentum and me.vel.length() > me.type.max_speed * 0.6 and not facing:
                thrust = False  # don't build up speed in the wrong direction
        fire = in_range and abs(error) < AIM_TOLERANCE

        return ShipInput(turn=turn, thrust=thrust, fire=fire,
                         special=self._use_special(error, in_range))

    def _lead(self, to_enemy: Vector2) -> Vector2:
        """Where to aim so a bullet meets the enemy, assuming it keeps its velocity."""
        speed = self.me.type.bullet_speed
        rel_vel = self.seen_vel - self.me.vel
        t = to_enemy.length() / max(speed, 1)
        for _ in range(2):  # refine the time to impact twice; plenty for a game AI
            t = (to_enemy + rel_vel * t).length() / max(speed, 1)
        aim = to_enemy + rel_vel * t
        return aim if aim.length() > 0 else Vector2(1, 0)

    def _incoming(self, bullets: list[Bullet]) -> Bullet | None:
        """The enemy bullet that will pass closest to us within DANGER_TIME, if any."""
        threat, closest = None, DANGER_RADIUS
        for b in bullets:
            if b.owner is self.me:
                continue
            rel_pos = wrapped_delta(self.me.pos, b.pos)
            rel_vel = b.vel - self.me.vel
            speed2 = rel_vel.length_squared()
            if speed2 == 0:
                continue
            t = -rel_pos.dot(rel_vel) / speed2  # time of closest approach
            if 0 < t < DANGER_TIME:
                miss = (rel_pos + rel_vel * t).length()
                if miss < closest:
                    threat, closest = b, miss
        return threat

    def _dodge_direction(self, bullets: list[Bullet]) -> int:
        threat = self._incoming(bullets)
        if threat is None:
            return 0
        # Turn so the nose points across the bullet's path, whichever way is quicker.
        across = Vector2(1, 0).angle_to(threat.vel) + 90
        error = angle_diff(self.me.angle, across)
        if abs(error) > 90:
            error = angle_diff(self.me.angle, across + 180)
        return 1 if error > 0 else -1

    def _use_special(self, aim_error: float, in_range: bool) -> bool:
        ability = self.me.ability
        if ability is None or not ability.ready or ability.passive:
            return False
        key = ability.key
        if key == "shield":
            return self.dodge != 0  # hold it while a bullet is about to hit
        if key == "spread":
            return in_range and abs(aim_error) < 20
        if key == "hyperspace":
            return self.dodge != 0 and self.me.hp == 1
        if key == "cloak":
            return in_range  # vanish while attacking, so the enemy can't aim back
        return False
