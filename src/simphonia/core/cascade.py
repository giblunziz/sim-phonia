from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

CascadeCallback = Callable[..., Any]
CascadePosition = Literal["before", "after"]


class ShortCircuit(Exception):
    """Levée par un handler `before` pour court-circuiter la commande principale.

    Le résultat encapsulé est renvoyé directement à l'appelant sans exécuter
    le `call` ni les cascades `after`.

    Usage::

        @cascade(bus="memory", code="recall", position="before")
        def cache_hit(from_char, about, context):
            hit = cache.get(from_char, about, context)
            if hit is not None:
                raise ShortCircuit(hit)
            # sinon on laisse passer
    """

    def __init__(self, result: Any) -> None:
        super().__init__(result)
        self.result = result


@dataclass(frozen=True, slots=True)
class Cascade:
    """Intercepteur déclaré sur une commande bus (before ou after)."""

    bus_name: str
    code: str
    position: CascadePosition
    callback: CascadeCallback
    priority: int = 0
    # Ordre d'enregistrement dans le bus (injection par le bus à la registration).
    discovery_order: int = field(default=0, compare=False)
