"""Pre-match setup screen: each player tunes their own ship with their own keys.

Up/down (thrust/down key) picks a stat, left/right changes it, fire toggles ready.
The match starts when both players are ready. Choices are saved to players.json.
"""

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pygame

from . import settings
from .settings import ShipType

SAVE_FILE = Path(__file__).resolve().parent.parent / "players.json"


@dataclass(frozen=True)
class Stat:
    label: str
    min: float
    max: float
    step: float
    get: Callable[[ShipType], float]
    set: Callable[[ShipType, float], ShipType]
    fmt: Callable[[float], str] = lambda v: f"{v:g}"


def _set_speed(t: ShipType, v: float) -> ShipType:
    # Keep acceleration in proportion so faster ships also feel punchier.
    return dataclasses.replace(t, max_speed=v, thrust=v * 0.75)


STATS = [
    Stat("Hit points", 1, 50, 1,
         lambda t: t.hit_points,
         lambda t, v: dataclasses.replace(t, hit_points=int(v)),
         lambda v: f"{int(v)}"),
    Stat("Speed", 100, 800, 25,
         lambda t: t.max_speed, _set_speed,
         lambda v: f"{int(v)}"),
    Stat("Turn speed", 60, 480, 20,
         lambda t: t.turn_speed,
         lambda t, v: dataclasses.replace(t, turn_speed=v),
         lambda v: f"{int(v)}°/s"),
    Stat("Bullet speed", 200, 1200, 50,
         lambda t: t.bullet_speed,
         lambda t, v: dataclasses.replace(t, bullet_speed=v),
         lambda v: f"{int(v)}"),
    Stat("Fire rate", 1, 15, 0.5,
         lambda t: round(1 / t.fire_cooldown, 1),
         lambda t, v: dataclasses.replace(t, fire_cooldown=1 / v),
         lambda v: f"{v:g} shots/s"),
    Stat("Momentum", 0, 1, 1,
         lambda t: int(t.momentum),
         lambda t, v: dataclasses.replace(t, momentum=bool(v)),
         lambda v: "on" if v else "off"),
]

SAVED_FIELDS = ["hit_points", "max_speed", "thrust", "turn_speed", "bullet_speed", "fire_cooldown", "momentum"]


def load_ship_types() -> list[ShipType]:
    types = [settings.DEFAULT_SHIP, settings.DEFAULT_SHIP]
    try:
        data = json.loads(SAVE_FILE.read_text())
        types = [dataclasses.replace(settings.DEFAULT_SHIP, **{k: d[k] for k in SAVED_FIELDS if k in d})
                 for d in data[:2]]
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return types


def save_ship_types(types: list[ShipType]) -> None:
    data = [{k: getattr(t, k) for k in SAVED_FIELDS} for t in types]
    try:
        SAVE_FILE.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


class PlayerPanel:
    def __init__(self, index: int, ship_type: ShipType):
        self.index = index
        self.controls = settings.PLAYER_CONTROLS[index]
        self.ship_type = ship_type
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
            self.row = (self.row - 1) % len(STATS)
        elif action == "down":
            self.row = (self.row + 1) % len(STATS)
        elif action in ("left", "right"):
            stat = STATS[self.row]
            delta = stat.step if action == "right" else -stat.step
            value = min(stat.max, max(stat.min, stat.get(self.ship_type) + delta))
            self.ship_type = stat.set(self.ship_type, value)

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, font, big_font) -> None:
        color = settings.PLAYER_COLORS[self.index]
        pygame.draw.rect(surface, color, rect, width=2, border_radius=8)
        title = big_font.render(settings.PLAYER_NAMES[self.index], True, color)
        surface.blit(title, title.get_rect(midtop=(rect.centerx, rect.top + 20)))

        y = rect.top + 100
        for i, stat in enumerate(STATS):
            selected = i == self.row and not self.ready
            text_color = (255, 255, 255) if selected else (170, 170, 185)
            if selected:
                pygame.draw.rect(surface, (40, 40, 60), (rect.left + 16, y - 6, rect.width - 32, 36),
                                 border_radius=4)
            surface.blit(font.render(stat.label, True, text_color), (rect.left + 32, y))
            value = stat.get(self.ship_type)
            value_color = color if selected else text_color
            val = font.render(stat.fmt(value), True, value_color)
            surface.blit(val, val.get_rect(midtop=(rect.right - 115, y)))
            if value > stat.min:
                surface.blit(font.render("<", True, value_color), (rect.right - 200, y))
            if value < stat.max:
                arrow = font.render(">", True, value_color)
                surface.blit(arrow, arrow.get_rect(topright=(rect.right - 32, y)))
            y += 48

        c = self.controls
        name = pygame.key.name
        if self.remote:
            help_lines = ["set up on the other PC"]
        else:
            help_lines = [
                f"{name(c.thrust)} / {name(c.down)}: choose    {name(c.left)} / {name(c.right)}: change",
                f"{name(c.fire)}: {'not ready' if self.ready else 'ready'}",
            ]
        for j, line in enumerate(help_lines):
            text = font.render(line, True, (120, 120, 140))
            surface.blit(text, text.get_rect(midtop=(rect.centerx, rect.bottom - 110 + j * 30)))

        status = "READY" if self.ready else "setting up..."
        s = big_font.render(status, True, color if self.ready else (90, 90, 110))
        surface.blit(s, s.get_rect(midbottom=(rect.centerx, rect.bottom - 120)))


class ConfigScreen:
    def __init__(self, font, big_font):
        self.font = font
        self.big_font = big_font
        self.panels = [PlayerPanel(i, t) for i, t in enumerate(load_ship_types())]
        self.banner = ""  # extra line under the title, e.g. LAN connection status

    def handle_action(self, player: int, action: str) -> None:
        self.panels[player].handle_action(action)

    @property
    def done(self) -> bool:
        return all(p.ready for p in self.panels)

    def ship_types(self) -> list[ShipType]:
        return [p.ship_type for p in self.panels]

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
