"""LAN play: one PC hosts and runs the whole game, the other joins.

The joining PC (always Red) sends its inputs and menu actions to the host, and the
host sends back a snapshot of the world every frame, which the joiner just draws.
Messages are JSON objects, one per line, over a single TCP connection.

Host -> client: {"t": "prices", "table": {...}}  the host's price table, sent on connect
                {"t": "snapshot", ...}         see snapshot()
Client -> host: {"t": "hello", "loadout": {...}}  the joiner's saved ship, sent once
                {"t": "input", "turn", "thrust", "fire", "special"}
                {"t": "action", "a": <Controls field>}   setup screen
                {"t": "cmd", "c": "rematch" | "setup"}
"""

import dataclasses
import json
import socket

from pygame.math import Vector2

from . import settings
from .abilities import make_ability
from .bullet import Bullet
from .config_screen import Loadout
from .settings import ShipType
from .ship import ShipInput

DEFAULT_PORT = 50007
MAX_BACKLOG = 64 * 1024  # stop queueing snapshots if the other side falls this far behind


def lan_ip() -> str:
    """Best guess at this PC's address on the home network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.0.1", 1))  # UDP connect sends nothing; it just picks a route
            return s.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())


class Connection:
    """Non-blocking line-based JSON over a TCP socket."""

    def __init__(self, sock: socket.socket):
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = sock
        self.inbox = b""
        self.outbox = b""
        self.closed = False

    def send(self, msg: dict, droppable: bool = False) -> None:
        if self.closed or (droppable and len(self.outbox) > MAX_BACKLOG):
            return
        self.outbox += json.dumps(msg, separators=(",", ":")).encode() + b"\n"
        self.flush()

    def flush(self) -> None:
        try:
            while self.outbox:
                sent = self.sock.send(self.outbox)
                self.outbox = self.outbox[sent:]
        except BlockingIOError:
            pass
        except OSError:
            self.close()

    def receive(self) -> list[dict]:
        self.flush()
        while not self.closed:
            try:
                data = self.sock.recv(65536)
            except BlockingIOError:
                break
            except OSError:
                self.close()
                break
            if not data:
                self.close()
                break
            self.inbox += data
        *lines, self.inbox = self.inbox.split(b"\n")
        messages = []
        for line in lines:
            try:
                messages.append(json.loads(line))
            except ValueError:
                pass
        return messages

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class Host:
    local_player = 0

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self.address = lan_ip()
        self.listener = socket.create_server(("", port))
        self.listener.setblocking(False)
        self.conn: Connection | None = None
        self.remote_input = ShipInput()

    @property
    def connected(self) -> bool:
        return self.conn is not None and not self.conn.closed

    def poll(self) -> list[dict]:
        """Accept a joiner if none yet, and return its messages. Inputs are kept in
        remote_input; a {"t": "connect"} or {"t": "disconnect"} marks a change."""
        events = []
        if self.conn is not None and self.conn.closed:
            self.conn = None
            self.remote_input = ShipInput()
            events.append({"t": "disconnect"})
        if self.conn is None:
            try:
                sock, _ = self.listener.accept()
            except BlockingIOError:
                return events
            self.conn = Connection(sock)
            events.append({"t": "connect"})
        for msg in self.conn.receive():
            if msg.get("t") == "input":
                turn = max(-1, min(1, int(msg.get("turn", 0))))
                self.remote_input = ShipInput(turn, bool(msg.get("thrust")), bool(msg.get("fire")),
                                              bool(msg.get("special")))
            else:
                events.append(msg)
        return events

    def send(self, msg: dict, droppable: bool = True) -> None:
        """Send to the joiner. Droppable messages (snapshots) are skipped if it falls behind."""
        if self.connected:
            self.conn.send(msg, droppable=droppable)


class Client:
    local_player = 1

    def __init__(self, host: str, port: int = DEFAULT_PORT):
        sock = socket.create_connection((host, port), timeout=5)
        self.conn = Connection(sock)

    @property
    def connected(self) -> bool:
        return not self.conn.closed

    def poll(self) -> list[dict]:
        return self.conn.receive()

    def send(self, msg: dict) -> None:
        self.conn.send(msg)


def _vec(v: Vector2) -> list[float]:
    return [round(v.x, 1), round(v.y, 1)]


def _ship_snapshot(ship, own_view: bool) -> dict:
    snap = {
        "type": dataclasses.asdict(ship.type),
        "pos": _vec(ship.pos), "vel": _vec(ship.vel), "angle": round(ship.angle, 1),
        "hp": ship.hp, "thrusting": ship.thrusting, "flash": ship.hit_flash,
        "ability": ship.ability.state(own_view) if ship.ability else None,
    }
    if ship.ability and not own_view and ship.alive:
        disguise = ship.ability.public_positions(ship)
        if disguise is not None:
            # Mirror image: the real position must not reach the opponent's PC at all.
            snap["images"] = [_vec(p) for p in disguise]
            snap["pos"] = snap["images"][0]
    return snap


def snapshot(game, viewer: int = 1) -> dict:
    """Everything the joiner (player `viewer`) needs to draw the current frame."""
    setup = None
    if game.setup is not None:
        setup = [{"loadout": p.loadout.to_dict(), "row": p.row, "ready": p.ready}
                 for p in game.setup.panels]
    return {
        "t": "snapshot",
        "wrap": settings.WRAPAROUND,
        "setup": setup,
        "ships": [_ship_snapshot(s, own_view=i == viewer) for i, s in enumerate(game.ships)],
        "bullets": [[game.ships.index(b.owner), *_vec(b.pos)] for b in game.bullets],
        "winner": game.winner,
        "wins": game.wins,
    }


def apply_snapshot(game, snap: dict) -> None:
    settings.WRAPAROUND = snap["wrap"]
    if snap["setup"] is not None:
        if game.setup is None:
            game.open_setup()
        for panel, p in zip(game.setup.panels, snap["setup"]):
            panel.loadout = Loadout.from_dict(p["loadout"], check_budget=False)  # the host checked it
            panel.row = p["row"]
            panel.ready = p["ready"]
    elif game.setup is not None:
        game.close_setup()
    for ship, s in zip(game.ships, snap["ships"]):
        was_alive = ship.alive
        ship.type = ShipType(**s["type"])
        ship.pos = Vector2(s["pos"])
        ship.vel = Vector2(s["vel"])
        ship.angle = s["angle"]
        ship.hp = s["hp"]
        ship.thrusting = s["thrusting"]
        ship.hit_flash = s["flash"]
        if ship.ability is None or ship.ability.key != ship.type.special:
            ship.ability = make_ability(ship.type.special)
        if ship.ability and s["ability"]:
            ship.ability.load_state(s["ability"])
        if ship.ability and "images" in s:
            ship.ability.disguised = [Vector2(p) for p in s["images"]]
        if was_alive and not ship.alive:
            game.explode(ship)
    game.bullets = [Bullet(game.ships[owner], Vector2(x, y), Vector2()) for owner, x, y in snap["bullets"]]
    if game.winner is not None and snap["winner"] is None:
        game.particles = []  # new round
    game.winner = snap["winner"]
    game.wins = snap["wins"]
