from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Callback = Callable[..., Any]

# Rôles MCP — détermine l'audience qui voit le tool dans sa façade dédiée :
#   player : joueurs humains/LLM incarnant un personnage (façade `/sse`)
#   mj     : agent LLM MJ autonome (façade `/sse/mj`)
#   npc    : futurs PNJ intelligents (backlog — Aurore, Lorenzo)
# Valeur par défaut `"player"` = rétro-compat.
MCP_ROLES = frozenset({"player", "mj", "npc"})


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
    # Texte narratif injecté dans le system_prompt du LLM incarné pour lui
    # indiquer **quand** activer ce tool depuis son expérience subjective.
    # Composé côté consumer via `core.mcp.mcp_tool_hints(role)`. Optionnel —
    # une commande MCP sans hint reste légitime (le `mcp_description` suffit).
    mcp_hint: str | None = None
