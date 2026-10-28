"""Command line entry point: local play, or host/join a LAN game."""

import argparse
import sys

from . import net
from .game import Game


def main() -> None:
    parser = argparse.ArgumentParser(description="Two-player ship duel.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--host", action="store_true", help="host a LAN game (you play Blue)")
    mode.add_argument("--join", metavar="HOST_IP", help="join a LAN game at this address (you play Red)")
    mode.add_argument("--ai", action="store_true", help="play alone against the computer (it flies Red)")
    parser.add_argument("--port", type=int, default=net.DEFAULT_PORT, help=f"default {net.DEFAULT_PORT}")
    args = parser.parse_args()

    if not args.join:  # a joiner uses the host's prices
        try:
            from . import balance
            balance.auto_rebalance()
        except ImportError:
            pass  # numpy not installed: keep the current prices

    connection = None
    try:
        if args.host:
            connection = net.Host(args.port)
        elif args.join:
            print(f"Connecting to {args.join}:{args.port}...")
            connection = net.Client(args.join, args.port)
    except OSError as e:
        sys.exit(f"Network error: {e}")
    Game(connection, ai=args.ai).run()
