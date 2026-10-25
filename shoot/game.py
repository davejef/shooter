"""Main game loop: reads the keyboard, steps the world, and draws it."""

import random

import pygame
from pygame.math import Vector2

from . import settings
from .config_screen import ConfigScreen, save_ship_types
from .entities import Bullet, Ship, ShipInput


class Particle:
    def __init__(self, pos: Vector2, color):
        self.pos = Vector2(pos)
        self.vel = Vector2(random.uniform(40, 220), 0).rotate(random.uniform(0, 360))
        self.life = random.uniform(0.4, 1.0)
        self.color = color

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.circle(surface, self.color, self.pos, 1.5)


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Shoot")
        self.screen = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 28)
        self.big_font = pygame.font.Font(None, 72)
        self.stars = [
            (random.randrange(settings.SCREEN_WIDTH), random.randrange(settings.SCREEN_HEIGHT),
             random.choice((60, 100, 160)))
            for _ in range(settings.STAR_COUNT)
        ]
        w, h = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        self.ships = [
            Ship(settings.DEFAULT_SHIP, settings.PLAYER_COLORS[0], Vector2(w * 0.2, h / 2), 0),
            Ship(settings.DEFAULT_SHIP, settings.PLAYER_COLORS[1], Vector2(w * 0.8, h / 2), 180),
        ]
        self.wins = [0, 0]
        self.new_round()
        self.open_setup()

    def open_setup(self) -> None:
        self.setup: ConfigScreen | None = ConfigScreen(self.font, self.big_font)
        pygame.key.set_repeat(300, 60)

    def close_setup(self) -> None:
        types = self.setup.ship_types()
        save_ship_types(types)
        for ship, ship_type in zip(self.ships, types):
            ship.type = ship_type
        self.setup = None
        pygame.key.set_repeat()
        self.wins = [0, 0]
        self.new_round()

    def new_round(self) -> None:
        for ship in self.ships:
            ship.reset()
        self.bullets: list[Bullet] = []
        self.particles: list[Particle] = []
        self.winner: int | None = None  # index of winning player, -1 for a draw
        self.round_over_time = 0.0

    def read_inputs(self) -> list[ShipInput]:
        keys = pygame.key.get_pressed()
        inputs = []
        for c in settings.PLAYER_CONTROLS:
            inputs.append(ShipInput(
                turn=int(keys[c.right]) - int(keys[c.left]),
                thrust=keys[c.thrust],
                fire=keys[c.fire],
            ))
        return inputs

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if self.setup is not None:
                    self.setup.handle_key(event.key)
                    if self.setup.done:
                        self.close_setup()
                elif event.key == pygame.K_F1:
                    settings.WRAPAROUND = not settings.WRAPAROUND
                elif event.key == pygame.K_r and self.winner is not None:
                    self.new_round()
                elif event.key == pygame.K_c and self.winner is not None:
                    self.open_setup()
        return True

    def update(self, dt: float) -> None:
        for ship, ctrl in zip(self.ships, self.read_inputs()):
            if ship.alive:
                self.bullets.extend(ship.update(dt, ctrl))

        for bullet in self.bullets:
            bullet.update(dt)
            for ship in self.ships:
                if ship is bullet.owner or not ship.alive or not bullet.alive:
                    continue
                if ship.pos.distance_to(bullet.pos) < ship.type.radius + Bullet.RADIUS:
                    bullet.alive = False
                    ship.take_hit(bullet.owner.type.bullet_damage)
                    if not ship.alive:
                        self.explode(ship)
        self.bullets = [b for b in self.bullets if b.alive]

        a, b = self.ships
        if a.alive and b.alive and a.pos.distance_to(b.pos) < a.type.radius + b.type.radius:
            # Ramming hurts both ships and knocks them apart.
            for ship in (a, b):
                ship.take_hit(2)
            push = (a.pos - b.pos)
            if push.length() == 0:
                push = Vector2(1, 0)
            push.scale_to_length(150)
            a.vel += push
            b.vel -= push
            for ship in (a, b):
                if not ship.alive:
                    self.explode(ship)

        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

        if self.winner is None:
            alive = [i for i, s in enumerate(self.ships) if s.alive]
            if len(alive) < 2:
                self.winner = alive[0] if alive else -1
                if self.winner >= 0:
                    self.wins[self.winner] += 1

    def explode(self, ship: Ship) -> None:
        self.particles.extend(Particle(ship.pos, ship.color) for _ in range(60))

    def draw_health_bar(self, x: int, y: int, ship: Ship, color) -> None:
        """Bar split into one segment per hit point, with a tick between each segment."""
        bar_w, bar_h = 200, 12
        max_hp = ship.type.hit_points
        seg_w = bar_w / max_hp
        pygame.draw.rect(self.screen, color, (x, y, round(seg_w * ship.hp), bar_h))
        pygame.draw.rect(self.screen, color, (x, y, bar_w, bar_h), width=1)
        dim = tuple(c // 2 for c in color)
        for k in range(1, max_hp):
            tx = x + round(k * seg_w)
            # Dark gaps cut the filled part; dim ticks mark the lost points.
            tick_color = settings.BACKGROUND if k < ship.hp else dim
            pygame.draw.line(self.screen, tick_color, (tx, y + 1), (tx, y + bar_h - 2))

    def draw_hud(self) -> None:
        for i, ship in enumerate(self.ships):
            color = settings.PLAYER_COLORS[i]
            x = 20 if i == 0 else settings.SCREEN_WIDTH - 220
            label = self.font.render(f"{settings.PLAYER_NAMES[i]}  wins: {self.wins[i]}", True, color)
            self.screen.blit(label, (x, 16))
            self.draw_health_bar(x, 44, ship, color)

        mode = f"F1 wrap: {'on' if settings.WRAPAROUND else 'off'}   Esc quit"
        text = self.font.render(mode, True, (110, 110, 130))
        self.screen.blit(text, text.get_rect(midbottom=(settings.SCREEN_WIDTH / 2, settings.SCREEN_HEIGHT - 10)))

        if self.winner is not None:
            msg = "Draw!" if self.winner < 0 else f"{settings.PLAYER_NAMES[self.winner]} wins!"
            color = (230, 230, 230) if self.winner < 0 else settings.PLAYER_COLORS[self.winner]
            title = self.big_font.render(msg, True, color)
            center = (settings.SCREEN_WIDTH / 2, settings.SCREEN_HEIGHT / 2)
            self.screen.blit(title, title.get_rect(center=center))
            hint = self.font.render("R: play again    C: change ships", True, (200, 200, 200))
            self.screen.blit(hint, hint.get_rect(center=(center[0], center[1] + 50)))

    def draw(self) -> None:
        self.screen.fill(settings.BACKGROUND)
        for x, y, c in self.stars:
            self.screen.set_at((x, y), (c, c, c))
        if self.setup is not None:
            self.setup.draw(self.screen)
            pygame.display.flip()
            return
        for bullet in self.bullets:
            bullet.draw(self.screen)
        for ship in self.ships:
            ship.draw(self.screen)
        for p in self.particles:
            p.draw(self.screen)
        self.draw_hud()
        pygame.display.flip()

    def run(self) -> None:
        running = True
        while running:
            dt = min(self.clock.tick(settings.FPS) / 1000.0, 0.05)
            running = self.handle_events()
            if self.setup is None:
                self.update(dt)
            self.draw()
        pygame.quit()
