"""Utilitaires d'accès aux commandes `@command(mcp=True)`.

Source unique de vérité : le décorateur. Les consommateurs (façade MCP,
context_builder, chat_service, futurs providers) passent ici au lieu de
dupliquer les définitions de tools.

Filtrage par rôle : `role=None` (défaut) retourne **toutes** les commandes MCP
quel que soit leur `mcp_role` — rétro-compat pour les consommateurs qui
n'étaient pas conscients de l'attribut. `role="player"` ou `role="mj"` filtre.
"""
from __future__ import annotations

from simphonia.core.command import Command
from simphonia.core.registry import BusRegistry, default_registry


def list_mcp_commands(
    registry: BusRegistry | None = None,
    role: str | None = None,
) -> list[Command]:
    """Commandes du registry avec `mcp=True`, optionnellement filtrées par `mcp_role`.

    - `role=None` : pas de filtre — rétro-compat
    - `role="player"` : uniquement les tools exposés au joueur
    - `role="mj"` : uniquement les tools exposés au MJ autonome
    """
    reg = registry or default_registry()
    commands = [cmd for bus in reg.all().values() for cmd in bus.list() if cmd.mcp]
    if role is None:
        return commands
    return [cmd for cmd in commands if cmd.mcp_role == role]


def to_tool_definitions(commands: list[Command]) -> list[dict]:
    """Convertit des `Command` en tool definitions provider-agnostic.

    Format : `{name, description, parameters}` — consommé tel quel par les
    providers LLM (Anthropic, Ollama) et par la façade MCP.
    """
    return [
        {
            "name":        cmd.code,
            "description": cmd.mcp_description or cmd.description,
            "parameters":  cmd.mcp_params or {"type": "object", "properties": {}},
        }
        for cmd in commands
    ]


def mcp_tool_definitions(
    registry: BusRegistry | None = None,
    role: str | None = None,
) -> list[dict]:
    """Raccourci : `list_mcp_commands(registry, role)` puis `to_tool_definitions`."""
    return to_tool_definitions(list_mcp_commands(registry, role))
