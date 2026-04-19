from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Callback = Callable[..., Any]

# Rôles MCP — détermine si la commande est exposée au joueur (via la façade
# `/sse`) ou au MJ autonome (via `/sse/mj`). Valeur par défaut `"player"` =
# rétro-compat : toutes les commandes MCP existantes restent côté joueur.
MCP_ROLES = frozenset({"player", "mj"})


@dataclass(frozen=True, slots=True)
class Command:
    code: str
    description: str
    callback: Callback
    bus_name: str
    mcp: bool = False
    mcp_description: str | None = None
    mcp_params: dict[str, Any] | None = field(default=None)
    mcp_role: str = "player"
