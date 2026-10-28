"""Main game loop: reads the keyboard, steps the world, and draws it.

With net=None both players share this keyboard. With a net.Host this PC runs the game
for Blue and takes Red's input from the network; with a net.Client this PC only sends
Red's input and draws the host's snapshots."""

import random

import pygame
from pygame.math import Vector2

from . import settings
from .ai import AI_VERSION, SKILLS, ComputerPilot
from .bullet import Bullet
from . import net as netplay
from . import config_screen, match_log
from .config_screen import ConfigScreen, Loadout, load_loadouts, save_loadouts
from .ship import Ship, ShipInput

MENU_ACTIONS = ("thrust", "down", "left", "right", "fire")


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


def key_actions(key: int) -> list[tuple[int, str]]:
    """Which (control set, action) pairs a key press means."""
    return [(i, action) for i, c in enumerate(settings.PLAYER_CONTROLS)
            for action in MENU_ACTIONS if getattr(c, action) == key]


def keyboard_input(controls: list[settings.Controls]) -> ShipInput:
    """Ship input from the keyboard, accepting any of the given control sets."""
    keys = pygame.key.get_pressed()
    held = lambda field: any(keys[getattr(c, field)] for c in controls)
    return ShipInput(turn=int(held("right")) - int(held("left")), thrust=held("thrust"), fire=held("fire"),
                     special=held("special"))


class Game:
    def __init__(self, net: "netplay.Host | netplay.Client | None" = None, ai: str | None = None):
        """ai: the computer's skill level ("easy", "normal" or "hard") to play against it."""
        self.net = net
        # In LAN play, or against the computer, this PC's player uses whichever keys they like.
        self.local_player = net.local_player if net else (0 if ai else None)
        pygame.init()
        pygame.display.set_caption("Shoot")
        self.screen = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 22)
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
        self.ai = ComputerPilot(self.ships[1], self.ships[0], ai) if ai else None  # flies Red
        self.wins = [0, 0]
        self.loadouts: list[Loadout] | None = None  # last ships bought; None = load saved
        self.new_round()
        self.open_setup()

    def open_setup(self) -> None:
        self.setup: ConfigScreen | None = ConfigScreen(self.font, self.big_font, self.loadouts,
                                                       networked=self.net is not None)
        if self.net:
            self.setup.panels[1 - self.local_player].remote = True
        if self.ai:
            # The computer keeps Red's last ship (the default at first) and is always ready.
            red = self.setup.panels[1]
            red.remote, red.ready = True, True
            self.show_skill()
        pygame.key.set_repeat(300, 60)

    def show_skill(self) -> None:
        self.setup.panels[1].remote_text = f"computer player: {self.ai.skill.name}    F2: change"

    def change_skill(self) -> None:
        names = list(SKILLS)
        skill = names[(names.index(self.ai.skill.name) + 1) % len(names)]
        self.ai = ComputerPilot(self.ships[1], self.ships[0], skill)
        self.ai.new_round()
        self.show_skill()

    def close_setup(self) -> None:
        self.loadouts = self.setup.loadouts()
        config_screen.prices.mark_seen(config_screen.PRICES.version)  # the players have seen the notice
        if self.net:
            # Only remember this PC's own ship; the other PC remembers its own.
            saved = load_loadouts()
            saved[self.local_player] = self.loadouts[self.local_player]
            save_loadouts(saved)
        else:
            save_loadouts(self.loadouts)
        for ship, loadout in zip(self.ships, self.loadouts):
            ship.type = loadout.ship_type()
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
        self.round_time = 0.0
        if self.ai:
            self.ai.new_round()

    def read_inputs(self) -> list[ShipInput]:
        if isinstance(self.net, netplay.Host):
            return [keyboard_input(settings.PLAYER_CONTROLS), self.net.remote_input]
        if self.ai:
            return [keyboard_input(settings.PLAYER_CONTROLS), self.ai.decide(self.bullets, self.frame_dt)]
        return [keyboard_input([c]) for c in settings.PLAYER_CONTROLS]

    def menu_action(self, player: int, action: str) -> None:
        if self.setup is None:
            return
        self.setup.handle_action(player, action)
        if self.setup.done:
            self.close_setup()

    def command(self, cmd: str) -> None:
        if self.winner is None:
            return
        if cmd == "rematch":
            self.new_round()
        elif cmd == "setup":
            self.open_setup()

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                self.handle_key(event.key)
        return True

    def handle_key(self, key: int) -> None:
        cmd = {pygame.K_r: "rematch", pygame.K_c: "setup"}.get(key)
        if isinstance(self.net, netplay.Client):
            if not self.net.connected:
                return
            if self.setup is not None:
                for _, action in key_actions(key)[:1]:
                    self.net.send({"t": "action", "a": action})
            elif cmd:
                self.net.send({"t": "cmd", "c": cmd})
            return
        if isinstance(self.net, netplay.Host) and not self.net.connected:
            cmd = None  # nobody to play against yet
        if self.setup is not None and self.ai and key == pygame.K_F2:
            self.change_skill()
        elif self.setup is not None:
            for control_set, action in key_actions(key)[:1]:
                player = control_set if self.local_player is None else self.local_player
                self.menu_action(player, action)
        elif key == pygame.K_F1:
            settings.WRAPAROUND = not settings.WRAPAROUND
        elif cmd:
            self.command(cmd)

    def handle_network(self) -> None:
        if isinstance(self.net, netplay.Host):
            for msg in self.net.poll():
                kind = msg.get("t")
                if kind == "connect":
                    # Both PCs must buy ships from the same price list: this one's.
                    self.net.send({"t": "prices", "table": config_screen.PRICES.to_dict()}, droppable=False)
                if kind in ("connect", "disconnect"):
                    # Back to setup for a fresh match; Blue keeps any choices already made.
                    self.wins = [0, 0]
                    if self.setup is None:
                        self.new_round()
                        self.open_setup()
                    self.setup.panels[1].ready = False
                elif kind == "hello" and self.setup is not None:
                    try:
                        loadout = Loadout.from_dict(msg.get("loadout"), check_budget=False)
                        loadout.fit_budget()  # Red may have saved it under other prices
                        self.setup.panels[1].loadout = loadout
                    except ValueError:
                        pass  # broken: Red starts from a fresh ship
                elif kind == "action" and msg.get("a") in MENU_ACTIONS:
                    self.menu_action(1, msg["a"])
                elif kind == "cmd":
                    self.command(msg.get("c"))
            if self.setup is not None:
                self.setup.banner = ("" if self.net.connected else
                                     f"Waiting for Red to join: python main.py --join {self.net.address}")
        elif isinstance(self.net, netplay.Client):
            messages = self.net.poll()
            for m in messages:
                if m.get("t") == "prices":
                    config_screen.use_prices(m["table"])
            snapshots = [m for m in messages if m.get("t") == "snapshot"]
            if snapshots:
                netplay.apply_snapshot(self, snapshots[-1])  # only the latest matters
            if self.net.connected:
                i = keyboard_input(settings.PLAYER_CONTROLS)
                self.net.send({"t": "input", "turn": i.turn, "thrust": i.thrust, "fire": i.fire,
                               "special": i.special})
            elif self.setup is not None:
                self.setup.banner = "Lost connection to the host. Esc to quit."

    def update(self, dt: float) -> None:
        self.frame_dt = dt
        if self.winner is None:
            self.round_time += dt
        for ship, ctrl in zip(self.ships, self.read_inputs()):
            if ship.alive:
                self.bullets.extend(ship.update(dt, ctrl))

        for bullet in self.bullets:
            bullet.update(dt)
            for ship in self.ships:
                if ship is bullet.owner or not ship.alive or not bullet.alive:
                    continue
                # Decoys (Mirror image) stop bullets; only real bullets destroy them.
                if ship.ability and ship.ability.intercept(ship, bullet.pos, Bullet.RADIUS,
                                                           destroy=not bullet.fake):
                    bullet.alive = False
                elif ship.pos.distance_to(bullet.pos) < ship.type.radius + Bullet.RADIUS:
                    bullet.alive = False
                    if not bullet.fake:
                        ship.take_hit(bullet.owner.type.bullet_damage)
                        if not ship.alive:
                            self.explode(ship)
        self.bullets = [b for b in self.bullets if b.alive]

        a, b = self.ships
        # Ramming a decoy destroys it harmlessly.
        for ship, other in ((a, b), (b, a)):
            if ship.ability and ship.alive and other.alive:
                ship.ability.intercept(ship, other.pos, other.type.radius, destroy=True)
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

        self.update_particles(dt)

        if self.winner is None:
            alive = [i for i, s in enumerate(self.ships) if s.alive]
            if len(alive) < 2:
                self.winner = alive[0] if alive else -1
                if self.winner >= 0:
                    self.wins[self.winner] += 1
                self.round_finished()

    def round_finished(self) -> None:
        """Log the round for rebalancing. In LAN play only the host logs it."""
        mode = "lan" if self.net else ("ai" if self.ai else "local")
        match_log.append([match_log.entry(mode, self.loadouts, self.winner, self.round_time,
                                          config_screen.PRICES.version, ai=AI_VERSION if self.ai else None)])

    def update_particles(self, dt: float) -> None:
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

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

    def draw_ability_meter(self, x: int, y: int, ship: Ship, color) -> None:
        """Special ability name with its meter: recharge progress, or shield time left."""
        ability = ship.ability
        key = pygame.key.name(settings.PLAYER_CONTROLS[self.ships.index(ship)].special)
        if self.local_player is not None:
            key = "shift"  # in LAN play either shift key works
        # Lit in the player's colour when usable, grey when recharging or used up.
        label = self.small_font.render(ability.name if ability.passive else f"{ability.name} ({key})", True,
                                       color if ability.ready else (120, 120, 140))
        bar_w = 200
        if ship is self.ships[0]:
            self.screen.blit(label, (x, y))
        else:
            self.screen.blit(label, label.get_rect(topright=(x + bar_w, y)))
        fill = bar_w * ability.meter
        pygame.draw.rect(self.screen, tuple(c // 2 for c in color), (x, y + 18, bar_w, 4), width=1)
        pygame.draw.rect(self.screen, color, (x, y + 18, fill, 4))

    def draw_hud(self) -> None:
        for i, ship in enumerate(self.ships):
            color = settings.PLAYER_COLORS[i]
            x = 20 if i == 0 else settings.SCREEN_WIDTH - 220
            you = "  (you)" if i == self.local_player else (f"  (computer, {self.ai.skill.name})" if self.ai and i == 1 else "")
            label = self.font.render(f"{settings.PLAYER_NAMES[i]}{you}  wins: {self.wins[i]}", True, color)
            self.screen.blit(label, (x, 16))
            self.draw_health_bar(x, 44, ship, color)
            if ship.ability:
                self.draw_ability_meter(x, 62, ship, color)

        if isinstance(self.net, netplay.Client):
            mode = "Esc quit" if self.net.connected else "Lost connection to the host. Esc to quit."
        else:
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
        for i, ship in enumerate(self.ships):
            # On a shared screen every ship counts as the viewer's own.
            ship.draw(self.screen, own_view=self.local_player in (None, i))
        for p in self.particles:
            p.draw(self.screen)
        self.draw_hud()
        pygame.display.flip()

    def tick(self, dt: float) -> bool:
        """One frame. Returns False when the player quits."""
        running = self.handle_events()
        self.handle_network()
        if isinstance(self.net, netplay.Client):
            self.update_particles(dt)  # the host simulates everything else
        elif self.setup is None:
            self.update(dt)
        if isinstance(self.net, netplay.Host):
            self.net.send(netplay.snapshot(self))
        self.draw()
        return running

    def run(self) -> None:
        if isinstance(self.net, netplay.Client):
            self.net.send({"t": "hello", "loadout": load_loadouts()[1].to_dict()})
        while self.tick(min(self.clock.tick(settings.FPS) / 1000.0, 0.05)):
            pass
        pygame.quit()
