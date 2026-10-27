"""Game-wide settings. Ship stats live on ShipType so they can later come from config."""

from dataclasses import dataclass

import pygame

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
FPS = 60

# Screen edge behaviour: True wraps ships and bullets around, False makes the edge a wall.
WRAPAROUND = True

BACKGROUND = (5, 5, 15)
STAR_COUNT = 120


@dataclass(frozen=True)
class ShipType:
    name: str
    # Movement
    momentum: bool          # True: Asteroids-style drift. False: moves only while thrusting.
    thrust: float           # px/s^2 when momentum is on
    max_speed: float        # px/s
    turn_speed: float       # degrees/s
    # Weapons
    fire_cooldown: float    # seconds between shots
    bullet_speed: float     # px/s, added to the ship's own velocity
    bullet_lifetime: float  # seconds
    bullet_damage: int
    # Durability
    hit_points: int
    radius: float           # collision radius in px
    # Extra
    special: str | None = None  # key into abilities.ABILITIES, or None for no special


DEFAULT_SHIP = ShipType(
    name="Fighter",
    momentum=True,
    thrust=300.0,
    max_speed=400.0,
    turn_speed=220.0,
    fire_cooldown=0.25,
    bullet_speed=550.0,
    bullet_lifetime=1.4,
    bullet_damage=1,
    hit_points=3,
    radius=14.0,
)


@dataclass(frozen=True)
class Controls:
    left: int
    right: int
    thrust: int  # also "up" in menus
    down: int    # menus only
    fire: int
    special: int  # triggers the ship's special ability


PLAYER_CONTROLS = [
    Controls(left=pygame.K_a, right=pygame.K_d, thrust=pygame.K_w, down=pygame.K_s, fire=pygame.K_SPACE,
             special=pygame.K_LSHIFT),
    Controls(left=pygame.K_LEFT, right=pygame.K_RIGHT, thrust=pygame.K_UP, down=pygame.K_DOWN, fire=pygame.K_RETURN,
             special=pygame.K_RSHIFT),
]

PLAYER_COLORS = [(80, 200, 255), (255, 120, 80)]
PLAYER_NAMES = ["Blue", "Red"]
