"""Façade MCP — expose les `@command(mcp=True)` comme tools MCP.

Deux endpoints distincts dans une seule app Starlette :
- `/sse`     → tools `mcp_role="player"` (recall, memorize à venir…)
- `/sse/mj`  → tools `mcp_role="mj"` (give_turn, next_round, end)

Le flag CLI `--character <slug>` injecte `from_char` côté joueur uniquement.
Le MJ n'a pas de `from_char` (il n'est pas un personnage).

Pour `recall` (player) : formatage markdown spécifique conservé (meilleur pour
le LLM joueur). Pour les autres tools (notamment MJ) : dispatch bus générique,
résultat sérialisé JSON. La généralisation des formatters est un ticket séparé.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

from simphonia.core import default_registry
from simphonia.core.command import Command
from simphonia.core.mcp import list_mcp_commands

log = logging.getLogger("simphonia.mcp")


def _format_memories(about_display: str, memories: list[dict]) -> str:
    """Formatage markdown spécifique aux résultats de `recall`."""
    if not memories:
        return f"Je n'ai aucun souvenir de {about_display}."
    lines = [f"# Vos souvenirs à propos de {about_display}"]
    for m in memories:
        lines.append(f"- {m['value']}")
    return "\n".join(lines)


def _serialize_result(result: Any) -> str:
    """Sérialise un résultat de commande bus en texte pour le LLM.

    Dict/list → JSON indenté. Scalaires → str(). Utilisé pour tous les tools
    sauf `recall` qui a son formatage markdown dédié.
    """
    if result is None:
        return "ok"
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return str(result)


def _build_mcp_server(
    *,
    role: str,
    from_char: str | None,
) -> tuple[Server, SseServerTransport, list[Command], str]:
    """Construit un `Server` MCP + transport SSE filtrés sur `role`.

    Args:
        role: `"player"` ou `"mj"`.
        from_char: Slug à injecter (joueur uniquement). Ignoré pour `role="mj"`.

    Returns:
        (server, sse_transport, mcp_commands, messages_path)
    """
    messages_path = "/messages/" if role == "player" else "/mj/messages/"
    server = Server(f"simphonia-{role}")
    sse = SseServerTransport(messages_path)

    mcp_commands = list_mcp_commands(role=role)
    log.info("MCP [%s] : %d tool(s) — %s", role, len(mcp_commands), [c.code for c in mcp_commands])

    # `from_char` n'a de sens que pour le rôle joueur
    effective_from_char = from_char if role == "player" else None

    def _build_input_schema(base_params: dict) -> dict:
        """Ajoute `from_char` au schema si le joueur n'est pas injecté."""
        if effective_from_char or role != "player":
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
            log.warning("MCP [%s] : tool inconnu '%s'", role, name)
            return [types.TextContent(type="text", text=f"Outil inconnu : {name}")]

        # Cas spécial : tool `recall` (player) — formatage markdown custom pour le LLM joueur.
        if cmd.code == "recall" and role == "player":
            from simphonia.services import character_service, memory_service
            raw_from             = effective_from_char or arguments.get("from_char", "").strip()
            effective_slug       = character_service.get().get_identifier(raw_from) or raw_from.lower()
            about_raw            = arguments.get("about", "").strip()
            about_slug           = character_service.get().get_identifier(about_raw) or about_raw.lower()
            context              = arguments.get("context", "").strip()

            log.info("MCP recall : from=%s about=%s context=%.80s",
                     effective_slug, about_slug, context)

            memories = memory_service.get().recall(
                from_char=effective_slug,
                context=context,
                about=about_slug or None,
            )
            return [types.TextContent(type="text", text=_format_memories(about_raw or "cette personne", memories))]

        # Cas générique : dispatch via le bus, sérialisation JSON du résultat.
        # Pour role="player" avec from_char injecté, on l'ajoute aux args si la commande
        # en a besoin (convention `from_char` — cf. futur `memory/memorize`).
        call_args = dict(arguments)
        if role == "player" and effective_from_char:
            # Si la commande déclare `from_char` dans sa signature, on l'injecte.
            # Détection naïve : via le callback.__code__.co_varnames.
            varnames = getattr(cmd.callback, "__code__", None)
            if varnames and "from_char" in varnames.co_varnames:
                call_args.setdefault("from_char", effective_from_char)

        try:
            result = default_registry().get(cmd.bus_name).dispatch(cmd.code, call_args)
        except Exception as exc:
            log.warning("MCP [%s] dispatch %s/%s a échoué : %s",
                        role, cmd.bus_name, cmd.code, exc)
            return [types.TextContent(type="text", text=f"Erreur : {exc}")]

        log.info("MCP [%s] %s/%s → %s", role, cmd.bus_name, cmd.code,
                 str(result)[:120])
        return [types.TextContent(type="text", text=_serialize_result(result))]

    return server, sse, mcp_commands, messages_path


def build_mcp_app(from_char: str | None) -> Starlette:
    """Construit l'app ASGI MCP avec ses deux endpoints (player + mj).

    `from_char` s'applique uniquement au serveur joueur. Le serveur MJ n'a pas
    de `from_char` (le MJ n'est pas un personnage).
    """
    if from_char:
        log.info("MCP : personnage joueur actif = %s", from_char)
    else:
        log.info("MCP : mode générique joueur — from_char requis dans les appels")

    player_server, player_sse, _, _ = _build_mcp_server(role="player", from_char=from_char)
    mj_server,     mj_sse,     _, _ = _build_mcp_server(role="mj",     from_char=None)

    async def handle_player_sse(request: Request) -> None:
        async with player_sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await player_server.run(streams[0], streams[1], player_server.create_initialization_options())

    async def handle_mj_sse(request: Request) -> None:
        async with mj_sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mj_server.run(streams[0], streams[1], mj_server.create_initialization_options())

    return Starlette(
        routes=[
            Route("/sse",    endpoint=handle_player_sse),
            Mount("/messages/", app=player_sse.handle_post_message),
            Route("/sse/mj", endpoint=handle_mj_sse),
            Mount("/mj/messages/", app=mj_sse.handle_post_message),
        ]
    )
