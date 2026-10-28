"""The computer pilot for single-player games and self-play.

It produces the same ShipInput a player's keyboard would. Several times a second it tries a
handful of short plans (turn left, right, not at all or towards its aim, with or without
thrust), plays each one forward with the real ship movement against the bullets it can see
and where the enemy is heading, and flies the one that scores best: no hits taken, a shot
that would land, a good distance from the enemy, and no losing rams. Between plans it fires
whenever a bullet leaving the nose now would meet the enemy.

It only knows what a person on the opponent's screen would: a cloaked ship is out of sight
(it guesses from where it was last seen and from the bullets it fires), and against Mirror
image it can't tell the identical ships apart.

The strongest play is the "hard" skill; "normal" and "easy" are the same pilot with slower
reactions, worse aim and a shorter look-ahead.
"""

import math
import random
from dataclasses import dataclass

from pygame.math import Vector2

from . import settings
from .bullet import Bullet
from .ship import Ship, ShipInput

AI_VERSION = 2  # bump when the pilot changes, so self-play prices only use rounds it played


@dataclass(frozen=True)
class Skill:
    name: str
    think_interval: float  # s between plans: its reaction time
    aim_error: float       # degrees its aim can be off, chosen afresh with each plan
    horizon: float         # s it looks ahead when comparing plans


SKILLS = {s.name: s for s in (
    # Easy and normal are tuned against the first AI (ai_baseline.py) in the arena: easy wins
    # about 30% against it, normal about 50%, hard about 90%.
    Skill("easy", think_interval=0.7, aim_error=30.0, horizon=0.2),
    Skill("normal", think_interval=0.4, aim_error=18.0, horizon=0.3),
    Skill("hard", think_interval=0.1, aim_error=0.0, horizon=0.6),
)}
DEFAULT_SKILL = "hard"

STEP = 0.1              # s per step when playing a plan forward
BLIND_FIRE_TIME = 1.5   # s it keeps shooting at where it guesses an unseen enemy is
AIM = 2                 # a plan's turn value meaning "turn towards the aim point"
OFF, ON, BURST = 0, 1, 2  # a plan's thrust: none, all the way, or only while it holds its turn
PLANS = [(turn, thrust) for turn in (AIM, -1, 0, 1) for thrust in (OFF, ON, BURST)]


def wrapped_delta(src: Vector2, dst: Vector2) -> Vector2:
    """Shortest vector from src to dst, going across the screen edge when wraparound is on."""
    d = dst - src
    if settings.WRAPAROUND:
        w, h = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        d.x = (d.x + w / 2) % w - w / 2
        d.y = (d.y + h / 2) % h - h / 2
    return d


def _wrap(dx: float, dy: float) -> tuple[float, float]:
    if settings.WRAPAROUND:
        w, h = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        dx = (dx + w / 2) % w - w / 2
        dy = (dy + h / 2) % h - h / 2
    return dx, dy


def angle_diff(a: float, b: float) -> float:
    """Signed difference b - a in degrees, in (-180, 180]."""
    return (b - a + 180) % 360 - 180


def intercept_time(dx: float, dy: float, wx: float, wy: float, speed: float) -> float | None:
    """When a bullet at this speed, fired now from the origin, can meet a target at (dx, dy)
    moving at (wx, wy) relative to the gun. None if it can't catch it."""
    a = wx * wx + wy * wy - speed * speed
    b = 2 * (dx * wx + dy * wy)
    c = dx * dx + dy * dy
    if abs(a) < 1e-6:
        return -c / b if b < 0 else None
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    root = math.sqrt(disc)
    times = [t for t in ((-b - root) / (2 * a), (-b + root) / (2 * a)) if t > 0]
    return min(times) if times else None


class SimShip:
    """A ship's movement, cut down for playing plans forward quickly."""

    __slots__ = ("x", "y", "vx", "vy", "angle", "t")

    def __init__(self, ship: Ship):
        self.x, self.y = ship.pos.x, ship.pos.y
        self.vx, self.vy = ship.vel.x, ship.vel.y
        self.angle = ship.angle
        self.t = ship.type

    def copy(self) -> "SimShip":
        c = SimShip.__new__(SimShip)
        c.x, c.y, c.vx, c.vy, c.angle, c.t = self.x, self.y, self.vx, self.vy, self.angle, self.t
        return c

    def step(self, turn: int, thrust: bool, dt: float) -> None:
        t = self.t
        self.angle = (self.angle + turn * t.turn_speed * dt) % 360
        rad = math.radians(self.angle)
        fx, fy = math.cos(rad), math.sin(rad)
        if t.momentum:
            if thrust:
                self.vx += fx * t.thrust * dt
                self.vy += fy * t.thrust * dt
                speed = math.hypot(self.vx, self.vy)
                if speed > t.max_speed:
                    self.vx *= t.max_speed / speed
                    self.vy *= t.max_speed / speed
        elif thrust:
            self.vx, self.vy = fx * t.max_speed, fy * t.max_speed
        else:
            self.vx = self.vy = 0.0
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not settings.WRAPAROUND:
            w, h, r = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT, t.radius
            if self.x < r:
                self.x, self.vx = r, abs(self.vx) * 0.5
            elif self.x > w - r:
                self.x, self.vx = w - r, -abs(self.vx) * 0.5
            if self.y < r:
                self.y, self.vy = r, abs(self.vy) * 0.5
            elif self.y > h - r:
                self.y, self.vy = h - r, -abs(self.vy) * 0.5


class ComputerPilot:
    # How it plays; class attributes so the arena can try other values (arena.py --set).
    FIRST_PHASE = 0.25      # s a plan holds its turn before turning back to aim
    PREFERRED_RANGE = 280   # px it likes to keep from the enemy
    HIT_COST = 100.0        # per hit point lost (three times that for the last one)
    SHOT_VALUE = 60.0       # best shot on offer during the plan
    RANGE_COST = 15.0       # at double or zero the preferred range
    FACING_COST = 10.0      # ending the plan facing directly away from the enemy
    RAM_RISK = 50.0         # a ram that trades hit points evenly is still a gamble
    BLIND_SPREAD = 0.3      # how widely it sprays at a hidden enemy, per s since the last clue
    CLOAK_HOLD = 0.6        # s it keeps a cloak up once it goes on
    EXPOSURE_TIME = 0.6     # s; it cloaks if the enemy could aim and hit it quicker than this

    def __init__(self, me: Ship, enemy: Ship, skill: str = DEFAULT_SKILL):
        self.me = me
        self.enemy = enemy
        self.skill = SKILLS[skill]
        self.think_timer = random.uniform(0, self.skill.think_interval)  # so two pilots don't move in step
        self.aim_error = 0.0
        self.plan: tuple[int, int] = (AIM, OFF)
        self.plan_age = 0.0
        self.danger = math.inf   # how soon the best plan still gets hit (inf if never)
        self.ram_time = math.inf  # how soon the best plan rams the enemy (inf if never)
        self.cloak_time = 0.0     # s our cloak has been up
        # What it believes about the enemy: where it is and how it is moving.
        self.seen_pos = Vector2(enemy.pos)
        self.seen_vel = Vector2()
        self.sightings: list[Vector2] = [enemy.pos]  # everywhere the enemy appears to be
        self.unseen_time = 0.0
        self.clue_pos: Vector2 | None = None  # where a bullet showed the hidden enemy to be
        self.clue_age = 0.0                   # s since then (or since last seen)
        self.pick: int | None = None     # which look-alike it is chasing
        self.sightings_count = 0
        self.watched_ability = None      # the enemy ability the above belongs to (new each round)

    # Perception

    def _perceive(self, bullets: list[Bullet], dt: float) -> None:
        """Update what it believes about the enemy from what is visible this frame."""
        enemy = self.enemy
        if enemy.ability is not self.watched_ability:  # new round
            self.watched_ability, self.pick, self.sightings_count = enemy.ability, None, 0
            self.unseen_time = self.clue_age = 0.0
            self.clue_pos = None
        sightings = enemy.ability.sightings(enemy) if enemy.ability else [enemy.pos]
        if sightings:
            if self.pick is None or len(sightings) != self.sightings_count:
                self.pick = random.randrange(len(sightings))  # a look-alike vanished: choose again
                self.sightings_count = len(sightings)
            if len(sightings) > 1 and self.think_timer <= dt:
                self.pick = self._easiest_target(sightings)
            self.sightings = sightings
            self.seen_pos = Vector2(sightings[self.pick])
            self.seen_vel = Vector2(enemy.vel)
            self.unseen_time = self.clue_age = 0.0
            self.clue_pos = None
            return
        # Out of sight: assume it carried on the way it was going, unless it gives itself away
        # by firing. A new bullet shows where its gun was a moment ago, and two of them how fast
        # it is moving.
        self.unseen_time += dt
        self.clue_age += dt
        self.sightings = []
        self.seen_pos += self.seen_vel * dt
        for b in bullets:
            if b.owner is enemy and b.age <= dt * 1.5:
                direction = (b.vel - self.seen_vel)
                nose = direction.normalize() * (enemy.type.radius + 6) if direction.length() > 0 else Vector2()
                origin = b.pos - b.vel * b.age - nose
                if self.clue_pos is not None and self.clue_age > 0.1:
                    self.seen_vel = wrapped_delta(self.clue_pos, origin) / self.clue_age
                self.seen_pos, self.clue_pos, self.clue_age = origin, origin, 0.0
                break
        if settings.WRAPAROUND:
            self.seen_pos.x %= settings.SCREEN_WIDTH
            self.seen_pos.y %= settings.SCREEN_HEIGHT

    def _easiest_target(self, sightings: list[Vector2]) -> int:
        """Which of several look-alikes it could aim at soonest."""
        me = self.me
        def time_to_shoot(pos: Vector2) -> float:
            d = wrapped_delta(me.pos, pos)
            off = abs(angle_diff(me.angle, Vector2(1, 0).angle_to(d))) if d.length() else 0.0
            return off / me.type.turn_speed + d.length() / me.type.bullet_speed
        times = [time_to_shoot(p) for p in sightings]
        best = min(range(len(sightings)), key=times.__getitem__)
        # Only switch for a clearly easier one, so it doesn't flit between them.
        return best if times[best] < times[self.pick] - 0.1 else self.pick

    # Deciding

    def decide(self, bullets: list[Bullet], dt: float) -> ShipInput:
        me = self.me
        if not me.alive or not self.enemy.alive:
            return ShipInput()
        self._perceive(bullets, dt)

        self.think_timer -= dt
        self.plan_age += dt
        if self.think_timer <= 0:
            self.think_timer = self.skill.think_interval
            self.aim_error = random.uniform(-self.skill.aim_error, self.skill.aim_error)
            self.plan, self.danger, self.ram_time = self._choose_plan(bullets)
            self.plan_age = 0.0

        turn, thrust = self.plan
        first_phase = self.plan_age < self.FIRST_PHASE
        if turn == AIM or not first_phase:
            ex, ey = self._near(self.seen_pos)
            turn = self._aim_turn(SimShip(me), ex, ey, self.seen_vel.x, self.seen_vel.y, 1 / settings.FPS,
                                  self.aim_error)
        fire = me.cooldown == 0 and self._fire_now()
        cloak = me.ability if me.ability and me.ability.key == "cloak" else None
        self.cloak_time = self.cloak_time + dt if cloak and cloak.up else 0.0
        return ShipInput(turn=turn, thrust=thrust == ON or (thrust == BURST and first_phase), fire=fire,
                         special=self._use_special(fire))

    def _fire_now(self) -> bool:
        """Whether a bullet fired now would hit any ship it can see, or where it guesses a hidden
        one is (while the guess is fresh)."""
        s = SimShip(self.me)
        vx, vy = self.seen_vel.x, self.seen_vel.y
        if self.sightings:
            return any(self._would_hit(s, self.aim_error, *self._near(p), vx, vy) is not None
                       for p in self.sightings)
        # Hidden: the longer since the last clue, the wider the area it might be in.
        slack = self.clue_age * self.enemy.type.max_speed * self.BLIND_SPREAD
        return (self.clue_age < BLIND_FIRE_TIME
                and self._would_hit(s, self.aim_error, *self._near(self.seen_pos), vx, vy, slack) is not None)

    def _near(self, pos: Vector2) -> tuple[float, float]:
        """pos, moved across the screen edge if that is shorter, so that from here on plain
        differences give the shortest way to it."""
        d = wrapped_delta(self.me.pos, pos)
        return self.me.pos.x + d.x, self.me.pos.y + d.y

    def _aim_turn(self, s: SimShip, ex: float, ey: float, evx: float, evy: float, dt: float,
                  error: float = 0.0) -> int:
        """Which way to turn so a bullet from s meets an enemy at (ex, ey) moving at (evx, evy).
        Positions here and in the look-ahead are as from _near: no wrapping needed."""
        dx, dy = ex - s.x, ey - s.y
        wx, wy = evx - s.vx, evy - s.vy
        t = intercept_time(dx, dy, wx, wy, s.t.bullet_speed)
        if t is None:
            t = math.hypot(dx, dy) / s.t.bullet_speed
        aim = math.degrees(math.atan2(dy + wy * t, dx + wx * t)) + error
        diff = (aim - s.angle + 180) % 360 - 180
        if abs(diff) < s.t.turn_speed * dt * 0.5:
            return 0
        return 1 if diff > 0 else -1

    def _would_hit(self, s: SimShip, error: float, ex: float, ey: float, evx: float, evy: float,
                   slack: float = 0.0) -> float | None:
        """Time for a bullet fired from s now to reach an enemy at (ex, ey) moving at (evx, evy),
        if it would hit (or pass within slack px of hitting); else None."""
        t = s.t
        rad = math.radians(s.angle + error)
        fx, fy = math.cos(rad), math.sin(rad)
        nose = t.radius + 6
        dx, dy = ex - (s.x + fx * nose), ey - (s.y + fy * nose)
        rvx = evx - (s.vx + fx * t.bullet_speed)
        rvy = evy - (s.vy + fy * t.bullet_speed)
        a = rvx * rvx + rvy * rvy
        tc = -(dx * rvx + dy * rvy) / a if a > 0 else 0.0
        if tc < 0.0:
            tc = 0.0
        elif tc > t.bullet_lifetime:
            tc = t.bullet_lifetime
        mx, my = dx + rvx * tc, dy + rvy * tc
        reach = self.enemy.type.radius + Bullet.RADIUS + slack
        return tc if mx * mx + my * my < reach * reach else None

    def _threats(self, bullets: list[Bullet], horizon: float) -> list[tuple[float, float, float, float, float]]:
        """Enemy bullets that could reach us within the horizon: (x, y, vx, vy, time left),
        with positions as from _near."""
        me = self.me
        reach = me.type.radius + Bullet.RADIUS + me.type.max_speed * horizon + 10
        out = []
        for b in bullets:
            if b.owner is me:
                continue
            life = min(b.owner.type.bullet_lifetime - b.age, horizon)
            dx, dy = _wrap(b.pos.x - me.pos.x, b.pos.y - me.pos.y)
            rvx, rvy = b.vel.x - me.vel.x, b.vel.y - me.vel.y
            a = rvx * rvx + rvy * rvy
            tc = min(max(-(dx * rvx + dy * rvy) / a, 0.0), life) if a > 0 else 0.0
            if math.hypot(dx + rvx * tc, dy + rvy * tc) < reach:
                out.append((me.pos.x + dx, me.pos.y + dy, b.vel.x, b.vel.y, life))
        return out

    def _choose_plan(self, bullets: list[Bullet]) -> tuple[tuple[int, int], float, float]:
        """The best plan, how soon it gets hit and how soon it rams (inf for never)."""
        horizon = self.skill.horizon
        threats = self._threats(bullets, horizon)
        start = SimShip(self.me)
        ram = self._ram_value()
        best, best_score, best_danger, best_ram = self.plan, -math.inf, math.inf, math.inf
        for plan in PLANS:
            score, danger, ram_time = self._score(plan, start.copy(), threats, horizon, ram)
            if plan == self.plan:
                score += 1.0  # a little loyalty, so it doesn't dither between equal plans
            score += random.uniform(0, 0.5)  # and no two rounds play out quite the same
            if score > best_score:
                best, best_score, best_danger, best_ram = plan, score, danger, ram_time
        return best, best_danger, best_ram

    def _ram_value(self) -> float:
        """What ramming the enemy now would be worth: both ships lose 2 hit points, except
        one behind a shield."""
        me, enemy = self.me, self.enemy
        mine = 0 if self._shield_left() > 0.3 else 2
        theirs = 0 if (enemy.ability and enemy.ability.key == "shield" and enemy.ability.up) else 2
        if mine >= me.hp:
            return -self._loss(mine, me.hp)  # even taking the enemy along is only a draw
        return self._loss(theirs, enemy.hp) - self._loss(mine, me.hp) - self.RAM_RISK

    def _loss(self, points: int, hp: int) -> float:
        """How bad losing this many hit points is, for a ship that has hp of them."""
        if points <= 0:
            return 0.0
        return self.HIT_COST * (hp + 2 if points >= hp else points)

    def _shield_left(self) -> float:
        ability = self.me.ability
        return ability.energy if ability and ability.key == "shield" else 0.0

    def _score(self, plan: tuple[int, int], s: SimShip, threats, horizon: float,
               ram: float) -> tuple[float, float, float]:
        me, enemy = self.me, self.enemy
        turn, thrust_mode = plan
        (ex, ey), evx, evy = self._near(self.seen_pos), self.seen_vel.x, self.seen_vel.y
        hit_reach = me.type.radius + Bullet.RADIUS + 3
        hit_reach2 = hit_reach * hit_reach
        ram_reach = me.type.radius + enemy.type.radius + 4
        ram_reach2 = ram_reach * ram_reach
        rammed = self.unseen_time > 0  # can't plan a ram on a ship it can't see
        ram_time = math.inf
        hits_left = me.hp
        score, danger, best_shot = 0.0, math.inf, 0.0
        cooldown = me.cooldown
        t = 0.0
        steps = max(1, round(horizon / STEP))
        live = threats
        for _ in range(steps):
            first = t < self.FIRST_PHASE
            step_turn = turn if (turn != AIM and first) else self._aim_turn(
                s, ex + evx * t, ey + evy * t, evx, evy, STEP)
            x0, y0 = s.x, s.y
            s.step(step_turn, thrust_mode == ON or (thrust_mode == BURST and first), STEP)
            svx, svy = (s.x - x0) / STEP, (s.y - y0) / STEP
            # Bullets: closest approach during this step, with both moving in straight lines.
            survivors = []
            for bullet in live:
                bx, by, bvx, bvy, life = bullet
                if life <= t:
                    continue
                dx, dy = bx + bvx * t - x0, by + bvy * t - y0
                rvx, rvy = bvx - svx, bvy - svy
                a = rvx * rvx + rvy * rvy
                tc = -(dx * rvx + dy * rvy) / a if a > 0 else 0.0
                if tc < 0.0:
                    tc = 0.0
                elif tc > STEP or tc > life - t:
                    tc = STEP if STEP < life - t else life - t
                mx, my = dx + rvx * tc, dy + rvy * tc
                if mx * mx + my * my < hit_reach2:
                    when = t + tc
                    danger = min(danger, when)
                    score -= self._loss(1, hits_left) * (1.0 - 0.4 * when / horizon)
                    hits_left -= 1
                else:
                    survivors.append(bullet)
            live = survivors
            # Ramming: closest approach to the enemy during this step.
            if not rammed:
                dx, dy = ex + evx * t - x0, ey + evy * t - y0
                rvx, rvy = evx - svx, evy - svy
                a = rvx * rvx + rvy * rvy
                tc = -(dx * rvx + dy * rvy) / a if a > 0 else 0.0
                tc = 0.0 if tc < 0.0 else (STEP if tc > STEP else tc)
                mx, my = dx + rvx * tc, dy + rvy * tc
                if mx * mx + my * my < ram_reach2:
                    rammed, ram_time = True, t + tc
                    score += ram * (1.0 - 0.4 * (t + tc) / horizon)
            t += STEP
            # The best shot this plan offers once the gun has reloaded.
            if t >= cooldown and best_shot < 1.0:
                tof = self._would_hit(s, 0.0, ex + evx * t, ey + evy * t, evx, evy)
                if tof is not None:
                    best_shot = max(best_shot, (1.0 - 0.5 * t / horizon) / (1.0 + tof / 0.4))
        score += self.SHOT_VALUE * best_shot
        # Where it ends up: near the preferred range, and facing the enemy (beyond the horizon
        # turning round is what leads to a shot).
        dx, dy = ex + evx * t - s.x, ey + evy * t - s.y
        dist = math.hypot(dx, dy)
        score -= self.RANGE_COST * ((dist - self.PREFERRED_RANGE) / self.PREFERRED_RANGE) ** 2
        off = abs((math.degrees(math.atan2(dy, dx)) - s.angle + 180) % 360 - 180)
        score -= self.FACING_COST * off / 180
        return score, danger, ram_time

    # Specials

    def _use_special(self, firing: bool) -> bool:
        ability = self.me.ability
        if ability is None or not ability.ready or ability.passive:
            return False
        key = ability.key
        if key == "shield":
            return min(self.danger, self.ram_time) < 0.25  # hold it while a hit or ram is coming
        if key == "spread":
            return firing
        if key == "hyperspace":
            return self.danger < 0.2 or (self.ram_time < 0.2 and self._ram_value() < 0)
        if key == "cloak":
            # Vanish while the enemy has us in its sights, and stay hidden long enough to slip away.
            if ability.up and self.cloak_time < self.CLOAK_HOLD:
                return True
            return self._enemy_aim_time() < self.EXPOSURE_TIME
        return False

    def _enemy_aim_time(self) -> float:
        """How long the enemy (any of its look-alikes) needs to turn to us and have a bullet
        arrive; inf if out of range or out of sight."""
        me, enemy = self.me, self.enemy
        best = math.inf
        for pos in self.sightings:
            d = wrapped_delta(pos, me.pos)
            if d.length() < enemy.type.bullet_speed * enemy.type.bullet_lifetime:
                off = abs(angle_diff(enemy.angle, Vector2(1, 0).angle_to(d)))
                best = min(best, off / enemy.type.turn_speed + d.length() / enemy.type.bullet_speed)
        return best
