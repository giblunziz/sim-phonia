from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Callback = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class Command:
    code: str
    description: str
    callback: Callback
    bus_name: str
