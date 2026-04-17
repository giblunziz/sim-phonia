from collections.abc import Callable
from typing import Any, TypeVar

from simphonia.core.cascade import Cascade, CascadeCallback, CascadePosition
from simphonia.core.command import Callback, Command
from simphonia.core.errors import CommandContractError
from simphonia.core.registry import default_registry

F = TypeVar("F", bound=Callback)
G = TypeVar("G", bound=CascadeCallback)


def command(
    *,
    bus: str,
    code: str,
    description: str,
    mcp: bool = False,
    mcp_description: str | None = None,
    mcp_params: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    _validate_mcp_contract(
        bus_name=bus,
        code=code,
        mcp=mcp,
        mcp_description=mcp_description,
        mcp_params=mcp_params,
    )

    def decorator(fn: F) -> F:
        target_bus = default_registry().get_or_create(bus)
        target_bus.register(
            Command(
                code=code,
                description=description,
                callback=fn,
                bus_name=bus,
                mcp=mcp,
                mcp_description=mcp_description,
                mcp_params=mcp_params,
            )
        )
        return fn

    return decorator


def cascade(
    *,
    bus: str,
    code: str,
    position: CascadePosition,
    priority: int = 0,
) -> Callable[[G], G]:
    """Décore une fonction comme intercepteur de commande bus.

    Args:
        bus: Nom du bus cible.
        code: Code de la commande ciblée.
        position: ``"before"`` (avant le call) ou ``"after"`` (après).
        priority: Ordre relatif entre cascades — plus petit = plus tôt.
                  En cas d'égalité, l'ordre de discovery est utilisé.

    La cascade ``before`` reçoit les mêmes kwargs que la commande.
    Elle peut lever :class:`~simphonia.core.cascade.ShortCircuit` pour
    court-circuiter la commande principale et renvoyer un résultat immédiat.

    La cascade ``after`` reçoit les mêmes kwargs que la commande **plus**
    un kwarg ``result`` contenant la valeur retournée par le call.
    """

    def decorator(fn: G) -> G:
        target_bus = default_registry().get_or_create(bus)
        target_bus.register_cascade(
            Cascade(
                bus_name=bus,
                code=code,
                position=position,
                callback=fn,
                priority=priority,
            )
        )
        return fn

    return decorator


def _validate_mcp_contract(
    *,
    bus_name: str,
    code: str,
    mcp: bool,
    mcp_description: str | None,
    mcp_params: dict[str, Any] | None,
) -> None:
    if not mcp:
        if mcp_description is not None or mcp_params is not None:
            raise CommandContractError(
                bus_name,
                code,
                "mcp_description/mcp_params provided but mcp=False",
            )
        return

    if not (isinstance(mcp_description, str) and mcp_description.strip()):
        raise CommandContractError(
            bus_name,
            code,
            "mcp=True requires a non-empty mcp_description",
        )
    if not isinstance(mcp_params, dict):
        raise CommandContractError(
            bus_name,
            code,
            "mcp=True requires mcp_params as a JSONSchema dict",
        )
    if mcp_params.get("type") != "object":
        raise CommandContractError(
            bus_name,
            code,
            "mcp_params must be a JSONSchema object (type='object')",
        )
    properties = mcp_params.get("properties")
    if not isinstance(properties, dict):
        raise CommandContractError(
            bus_name,
            code,
            "mcp_params must declare a 'properties' dict",
        )
