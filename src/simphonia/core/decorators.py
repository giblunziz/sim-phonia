from collections.abc import Callable
from typing import TypeVar

from simphonia.core.command import Callback, Command
from simphonia.core.registry import default_registry

F = TypeVar("F", bound=Callback)


def command(*, bus: str, code: str, description: str) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        target_bus = default_registry().get_or_create(bus)
        target_bus.register(Command(code=code, description=description, callback=fn, bus_name=bus))
        return fn

    return decorator
