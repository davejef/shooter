"""Special abilities: an optional extra power a ship uses with its special key.

To add one, create a module here with a subclass of SpecialAbility (or TriggeredAbility for
a press-to-fire power with a recharge), fill in the class attributes and abstract methods,
and add the class to ABILITIES below. It then shows up on the setup screen and works over LAN.
"""

from .base import SpecialAbility, TriggeredAbility
from .cloak import Cloak
from .hyperspace import Hyperspace
from .shield import Shield
from .spread_shot import SpreadShot

ABILITIES: dict[str, type[SpecialAbility]] = {cls.key: cls for cls in (Shield, SpreadShot, Hyperspace, Cloak)}


def make_ability(key: str | None) -> SpecialAbility | None:
    return ABILITIES[key]() if key else None


__all__ = ["ABILITIES", "Cloak", "Hyperspace", "Shield", "SpecialAbility", "SpreadShot", "TriggeredAbility",
           "make_ability"]
