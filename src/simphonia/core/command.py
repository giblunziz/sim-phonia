from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Callback = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class Command:
    code: str
    description: str
    callback: Callback
    bus_name: str
    mcp: bool = False
    mcp_description: str | None = None
    mcp_params: dict[str, Any] | None = field(default=None)
