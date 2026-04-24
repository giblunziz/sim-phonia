"""Utilitaires d'accès aux commandes `@command(mcp=True)`.

Source unique de vérité : le décorateur. Les consommateurs (façade MCP,
context_builder, chat_service, futurs providers) passent ici au lieu de
dupliquer les définitions de tools.

Filtrage par rôle : `role=None` (défaut) retourne **toutes** les commandes MCP
quel que soit leur `mcp_role` — rétro-compat pour les consommateurs qui
n'étaient pas conscients de l'attribut. `role="player"` / `"mj"` / `"npc"` filtre.

**Groupes MCP narratifs** : chaque `(bus, role)` peut déclarer une intro/outro
via `register_mcp_group(...)`. Le helper `mcp_tool_hints(role)` compose
intro + hints des commandes + outro pour produire le bloc narratif injecté
dans le system_prompt du LLM incarné.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from string import Template

from simphonia.core.command import Command
from simphonia.core.registry import BusRegistry, default_registry

log = logging.getLogger("simphonia.mcp")


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


# ---------------------------------------------------------------------------
#  Groupes MCP narratifs — intro/outro par (bus, role)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class McpGroup:
    """Bloc narratif associé à un `(bus, role)` pour la composition du prompt.

    `reminder` : texte court ré-injecté à chaque tour via `mcp_tool_reminders`,
    placé en suffixe du user prompt (haute attention LLM). Supporte le placeholder
    Spring-style `${commands}` qui sera résolu en liste markdown des codes de
    commandes du groupe. None = pas de reminder pour ce groupe.
    """
    bus:      str
    role:     str
    intro:    str = ""
    outro:    str = ""
    reminder: str | None = None


_mcp_groups: dict[tuple[str, str], McpGroup] = {}


def register_mcp_group(
    *,
    bus: str,
    role: str,
    intro: str = "",
    outro: str = "",
    reminder: str | None = None,
) -> None:
    """Enregistre l'intro/outro/reminder narratif pour le groupe `(bus, role)`.

    Idempotent par design — un second appel **écrase** (avec warning log) ;
    utile en dev/tests. Appeler en top-level dans le module `commands/<bus>.py`
    qui héberge les commandes du groupe.
    """
    key = (bus, role)
    if key in _mcp_groups:
        log.warning("register_mcp_group: groupe %s déjà enregistré — écrasement", key)
    _mcp_groups[key] = McpGroup(
        bus=bus, role=role,
        intro=intro, outro=outro, reminder=reminder,
    )


def get_mcp_group(bus: str, role: str) -> McpGroup | None:
    """Retourne le groupe enregistré pour `(bus, role)`, ou `None`."""
    return _mcp_groups.get((bus, role))


def _reset_mcp_groups_for_tests() -> None:
    """Helper de tests — reset le registre de groupes."""
    _mcp_groups.clear()


def mcp_tool_hints(role: str, registry: BusRegistry | None = None) -> str:
    """Compose le bloc narratif des tools MCP pour un rôle donné.

    Regroupe les commandes filtrées `role=role` par leur bus, puis pour chaque
    groupe `(bus, role)` compose :
        intro (si enregistrée)
        hint1
        hint2
        ...
        outro (si enregistrée)

    Les groupes sont séparés visuellement par `\\n\\n---\\n\\n`. Retourne une
    chaîne vide si aucune commande n'a de `mcp_hint` et aucun groupe pertinent.
    """
    commands = list_mcp_commands(registry, role)
    by_bus: dict[str, list[Command]] = defaultdict(list)
    for cmd in commands:
        by_bus[cmd.bus_name].append(cmd)

    sections: list[str] = []
    for bus, cmds in by_bus.items():
        group = get_mcp_group(bus, role)
        hints = [c.mcp_hint for c in cmds if c.mcp_hint]
        if not hints and not (group and (group.intro or group.outro)):
            continue
        parts: list[str] = []
        if group and group.intro:
            parts.append(group.intro)
        parts.extend(hints)
        if group and group.outro:
            parts.append(group.outro)
        if parts:
            sections.append("\n\n".join(parts))

    return "\n\n---\n\n".join(sections)


def mcp_tool_reminders(role: str, registry: BusRegistry | None = None) -> str:
    """Compose les reminders MCP pour un rôle donné, avec résolution des placeholders.

    Pour chaque groupe `(bus, role)` qui déclare un `reminder`, le texte est
    composé en remplaçant les placeholders Spring-style :

    - `${commands}` → liste markdown des codes de commandes mcp=True du groupe,
      ordre de découverte, séparées par `, ` (ex: `` `recall`, `memorize` ``)

    Les reminders de différents groupes sont concaténés avec `\\n\\n---\\n\\n`
    (même séparateur que `mcp_tool_hints`). Retourne une chaîne vide si aucun
    groupe n'a de reminder enregistré pour ce rôle.

    Le résultat est destiné à être suffixé au dernier user prompt — pas à être
    injecté dans l'historique persisté (sinon accumulation tour après tour).
    """
    commands = list_mcp_commands(registry, role)
    by_bus: dict[str, list[Command]] = defaultdict(list)
    for cmd in commands:
        by_bus[cmd.bus_name].append(cmd)

    sections: list[str] = []
    for bus, cmds in by_bus.items():
        group = get_mcp_group(bus, role)
        if not group or not group.reminder:
            continue
        commands_md = ", ".join(f"`{c.code}`" for c in cmds)
        text = Template(group.reminder).safe_substitute(commands=commands_md)
        sections.append(text)

    return "\n\n---\n\n".join(sections)
