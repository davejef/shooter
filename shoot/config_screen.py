"""Pre-match setup screen: each player buys their ship's stats from a point budget.

Each stat has levels from 0 up to its own cap, at a fixed cost per level. Both players get the same
budget, so a ship can be great at a few things or decent at everything, but not both.
Up/down (thrust/down key) picks a row, left/right sells or buys a level, fire toggles ready.
The match starts when both players are ready. Choices are saved to players.json.
"""

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pygame

from . import settings
from .abilities import ABILITIES
from .settings import ShipType

SAVE_FILE = Path(__file__).resolve().parent.parent / "players.json"

BUDGET = 24  # points per player; exactly what a fresh ship (every stat at its start level) costs


@dataclass(frozen=True)
class Stat:
    key: str
    label: str
    lo: float  # value at level 0
    hi: float  # value at max_level
    apply: Callable[[ShipType, float], ShipType]
    fmt: Callable[[float], str]
    max_level: int = 10
    start_level: int = 5  # level of a fresh ship; matches DEFAULT_SHIP
    cost: int = 1         # points per level

    def value(self, level: int) -> float:
        return self.lo + (self.hi - self.lo) * level / self.max_level


def _set_speed(t: ShipType, v: float) -> ShipType:
    # Keep acceleration in proportion so faster ships also feel punchier.
    return dataclasses.replace(t, max_speed=v, thrust=v * 0.75)


STATS = [
    # Each hit point matters a lot at this scale, so it costs 2 points per level.
    Stat("hit_points", "Hit points", 1, 5,
         lambda t, v: dataclasses.replace(t, hit_points=round(v)), lambda v: f"{round(v)}",
         max_level=4, start_level=2, cost=2),
    Stat("speed", "Speed", 200, 600, _set_speed, lambda v: f"{round(v)}"),
    Stat("turn_speed", "Turn speed", 120, 320,
         lambda t, v: dataclasses.replace(t, turn_speed=v), lambda v: f"{round(v)}°/s"),
    Stat("bullet_speed", "Bullet speed", 300, 800,
         lambda t, v: dataclasses.replace(t, bullet_speed=v), lambda v: f"{round(v)}"),
    Stat("fire_rate", "Fire rate", 2, 6,
         lambda t, v: dataclasses.replace(t, fire_cooldown=1 / v), lambda v: f"{v:.1f} shots/s"),
]
MOMENTUM_ROW = len(STATS)  # momentum is a free on/off choice after the stats
SPECIAL_ROW = len(STATS) + 1  # then the optional special ability, which costs points
ROWS = len(STATS) + 2
SPECIAL_OPTIONS: list[str | None] = [None, *ABILITIES]


def special_cost(key: str | None) -> int:
    return ABILITIES[key].cost if key else 0


def special_options(networked: bool) -> list[str | None]:
    """Specials on offer: network-only ones (like Cloak) need two screens."""
    return [k for k in SPECIAL_OPTIONS if k is None or networked or not ABILITIES[k].network_only]


@dataclass
class Loadout:
    levels: dict[str, int] = field(default_factory=lambda: {s.key: s.start_level for s in STATS})
    momentum: bool = True
    special: str | None = None

    @property
    def points_left(self) -> int:
        return BUDGET - sum(s.cost * self.levels[s.key] for s in STATS) - special_cost(self.special)

    def ship_type(self) -> ShipType:
        t = settings.DEFAULT_SHIP
        for stat in STATS:
            t = stat.apply(t, stat.value(self.levels[stat.key]))
        return dataclasses.replace(t, momentum=self.momentum, special=self.special)

    def cycle_special(self, step: int, options: list[str | None]) -> None:
        """Move to the next special in that direction that the remaining points can pay for."""
        affordable = self.points_left + special_cost(self.special)
        i = options.index(self.special)
        for _ in options:
            i = (i + step) % len(options)
            if special_cost(options[i]) <= affordable:
                self.special = options[i]
                return

    def to_dict(self) -> dict:
        return {"levels": dict(self.levels), "momentum": self.momentum, "special": self.special}

    @classmethod
    def from_dict(cls, data: dict) -> "Loadout":
        """Build a loadout, raising ValueError unless it is within the rules."""
        try:
            levels = {s.key: int(data["levels"][s.key]) for s in STATS}
            momentum = bool(data["momentum"])
            special = data.get("special")
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise ValueError(f"bad loadout: {e}") from None
        if special not in SPECIAL_OPTIONS:
            raise ValueError(f"unknown special ability: {special!r}")
        loadout = cls(levels, momentum, special)
        if any(not 0 <= levels[s.key] <= s.max_level for s in STATS) or loadout.points_left < 0:
            raise ValueError("loadout breaks the point-buy rules")
        return loadout


def load_loadouts() -> list[Loadout]:
    loadouts = [Loadout(), Loadout()]
    try:
        data = json.loads(SAVE_FILE.read_text())
        for i, d in enumerate(data[:2]):
            loadouts[i] = Loadout.from_dict(d)
    except (OSError, ValueError, TypeError, KeyError):
        pass  # missing, old-format or tampered file: use fresh ships
    return loadouts


def save_loadouts(loadouts: list[Loadout]) -> None:
    try:
        SAVE_FILE.write_text(json.dumps([l.to_dict() for l in loadouts], indent=2))
    except OSError:
        pass


class PlayerPanel:
    def __init__(self, index: int, loadout: Loadout, networked: bool = False):
        self.index = index
        self.controls = settings.PLAYER_CONTROLS[index]
        self.specials = special_options(networked)
        if loadout.special not in self.specials:
            loadout.special = None  # e.g. a saved Cloak in a local game; refunds its points
        self.loadout = loadout
        self.row = 0
        self.ready = False
        self.remote = False  # True when this panel is driven from the other PC

    def handle_action(self, action: str) -> None:
        """Apply one menu action: a Controls field name ("thrust" is up)."""
        if action == "fire":
            self.ready = not self.ready
            return
        if self.ready:
            return
        if action == "thrust":
            self.row = (self.row - 1) % ROWS
        elif action == "down":
            self.row = (self.row + 1) % ROWS
        elif action in ("left", "right"):
            if self.row == SPECIAL_ROW:
                self.loadout.cycle_special(1 if action == "right" else -1, self.specials)
                return
            if self.row == MOMENTUM_ROW:
                self.loadout.momentum = not self.loadout.momentum
                return
            stat = STATS[self.row]
            key = stat.key
            level = self.loadout.levels[key]
            if action == "right" and level < stat.max_level and self.loadout.points_left >= stat.cost:
                self.loadout.levels[key] = level + 1
            elif action == "left" and level > 0:
                self.loadout.levels[key] = level - 1

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, font, big_font) -> None:
        color = settings.PLAYER_COLORS[self.index]
        dim = tuple(c // 3 for c in color)
        pygame.draw.rect(surface, color, rect, width=2, border_radius=8)
        title = big_font.render(settings.PLAYER_NAMES[self.index], True, color)
        surface.blit(title, title.get_rect(midtop=(rect.centerx, rect.top + 20)))

        left = self.loadout.points_left
        points = font.render(f"Points left: {left} / {BUDGET}", True,
                             color if left else (170, 170, 185))
        surface.blit(points, points.get_rect(midtop=(rect.centerx, rect.top + 78)))

        y = rect.top + 120
        pip_x, pip_w, pip_gap = rect.left + 190, 14, 4
        for i in range(ROWS):
            selected = i == self.row and not self.ready
            text_color = (255, 255, 255) if selected else (170, 170, 185)
            if selected:
                pygame.draw.rect(surface, (40, 40, 60), (rect.left + 16, y - 6, rect.width - 32, 36),
                                 border_radius=4)
            if i == MOMENTUM_ROW:
                label, value = "Momentum", ("on" if self.loadout.momentum else "off") + "  (free)"
            elif i == SPECIAL_ROW:
                special = self.loadout.special
                label = "Special"
                value = f"{ABILITIES[special].name}  ({special_cost(special)} pts)" if special else "none"
            else:
                stat = STATS[i]
                level = self.loadout.levels[stat.key]
                label, value = stat.label, stat.fmt(stat.value(level))
                # A pip per level, wider for stats that cost more per level.
                w = stat.cost * pip_w + (stat.cost - 1) * pip_gap
                for k in range(stat.max_level):
                    pip = (pip_x + k * (w + pip_gap), y + 2, w, 16)
                    pygame.draw.rect(surface, color if k < level else dim, pip,
                                     width=0 if k < level else 1, border_radius=2)
            surface.blit(font.render(label, True, text_color), (rect.left + 32, y))
            val = font.render(value, True, color if selected else text_color)
            surface.blit(val, val.get_rect(topright=(rect.right - 32, y)))
            y += 48

        c = self.controls
        name = pygame.key.name
        if self.remote:
            help_lines = ["set up on the other PC"]
        else:
            help_lines = [
                f"{name(c.thrust)} / {name(c.down)}: choose    {name(c.left)} / {name(c.right)}: sell / buy",
                f"{name(c.fire)}: {'not ready' if self.ready else 'ready'}    "
                f"{name(c.special)}: use special in game",
            ]
        for j, line in enumerate(help_lines):
            text = font.render(line, True, (120, 120, 140))
            surface.blit(text, text.get_rect(midtop=(rect.centerx, rect.bottom - 110 + j * 30)))

        status = "READY" if self.ready else "setting up..."
        s = big_font.render(status, True, color if self.ready else (90, 90, 110))
        surface.blit(s, s.get_rect(midbottom=(rect.centerx, rect.bottom - 120)))


class ConfigScreen:
    def __init__(self, font, big_font, loadouts: list[Loadout] | None = None, networked: bool = False):
        self.font = font
        self.big_font = big_font
        if loadouts is None:
            loadouts = load_loadouts()
        self.panels = [PlayerPanel(i, Loadout.from_dict(l.to_dict()), networked) for i, l in enumerate(loadouts)]
        self.banner = ""  # extra line under the title, e.g. LAN connection status

    def handle_action(self, player: int, action: str) -> None:
        self.panels[player].handle_action(action)

    @property
    def done(self) -> bool:
        return all(p.ready for p in self.panels)

    def loadouts(self) -> list[Loadout]:
        return [p.loadout for p in self.panels]

    def draw(self, surface: pygame.Surface) -> None:
        w, h = surface.get_size()
        title = self.big_font.render("Ship setup", True, (230, 230, 230))
        surface.blit(title, title.get_rect(midtop=(w / 2, 20)))
        if self.banner:
            banner = self.font.render(self.banner, True, (230, 210, 120))
            surface.blit(banner, banner.get_rect(midtop=(w / 2, 72)))
        margin, gap = 40, 40
        panel_w = (w - 2 * margin - gap) / 2
        for i, panel in enumerate(self.panels):
            rect = pygame.Rect(margin + i * (panel_w + gap), 100, panel_w, h - 160)
            panel.draw(surface, rect, self.font, self.big_font)
        hint = self.font.render("Both players press fire to start    Esc quit", True, (110, 110, 130))
        surface.blit(hint, hint.get_rect(midbottom=(w / 2, h - 16)))
