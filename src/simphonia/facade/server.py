"""Façade MCP — expose les @command(mcp=True) comme tools MCP.

Un serveur MCP par personnage actif : from_char est injecté au démarrage,
le LLM ne le voit pas. Résultats formatés en markdown.
"""
import logging
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

from simphonia.core import default_registry
from simphonia.services import memory_service

log = logging.getLogger("simphonia.mcp")


def _format_memories(about_display: str, memories: list[dict]) -> str:
    if not memories:
        return f"Je n'ai aucun souvenir de {about_display}."
    lines = [f"# Vos souvenirs à propos de {about_display}"]
    for m in memories:
        lines.append(f"- {m['value']}")
    return "\n".join(lines)


def build_mcp_app(from_char: str | None) -> Starlette:
    """Construit l'app ASGI MCP.

    Si `from_char` est fourni, il est injecté automatiquement (invisible du LLM).
    Sinon, `from_char` est ajouté comme paramètre requis dans le schema du tool.
    """
    if from_char:
        log.info("MCP : personnage actif = %s", from_char)
    else:
        log.info("MCP : mode générique — from_char requis dans les appels")

    server = Server("simphonia")
    sse = SseServerTransport("/messages/")

    registry = default_registry()
    mcp_commands = [
        cmd
        for bus in registry.all().values()
        for cmd in bus.list()
        if cmd.mcp
    ]
    log.info("MCP : %d tool(s) exposé(s) — %s", len(mcp_commands), [c.code for c in mcp_commands])

    def _build_input_schema(base_params: dict) -> dict:
        """Ajoute `from_char` au schema si le personnage n'est pas injecté."""
        if from_char:
            return base_params
        schema = {**base_params, "properties": dict(base_params.get("properties", {}))}
        schema["properties"]["from_char"] = {
            "type": "string",
            "description": "Slug du personnage qui consulte ses souvenirs",
        }
        schema["required"] = list(base_params.get("required", [])) + ["from_char"]
        return schema

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=cmd.code,
                description=cmd.mcp_description or cmd.description,
                inputSchema=_build_input_schema(cmd.mcp_params or {"type": "object", "properties": {}}),
            )
            for cmd in mcp_commands
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        cmd = next((c for c in mcp_commands if c.code == name), None)
        if cmd is None:
            log.warning("MCP : tool inconnu '%s'", name)
            return [types.TextContent(type="text", text=f"Outil inconnu : {name}")]

        from simphonia.services import character_service
        raw_from = from_char or arguments.get("from_char", "").strip()
        effective_from_char = character_service.get().get_identifier(raw_from) or raw_from.lower()
        about_raw = arguments.get("about", "").strip()
        about_slug = character_service.get().get_identifier(about_raw) or about_raw.lower()
        context = arguments.get("context", "").strip()

        log.info("MCP recall : from=%s about=%s context=%.80s", effective_from_char, about_slug, context)

        memories = memory_service.get().recall(
            from_char=effective_from_char,
            context=context,
            about=about_slug or None,
        )
        text = _format_memories(about_raw or "cette personne", memories)
        return [types.TextContent(type="text", text=text)]

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )
