"""Assemblage du contexte LLM (system prompt + messages) pour chaque tour d'activité."""
import json
import logging
from collections import defaultdict

from simphonia.core.mcp import mcp_tool_definitions
from simphonia.utils.parser import parse_llm_json

log = logging.getLogger("simphonia.activity.context")

PRIVATE_FIELDS = {"inner_thought", "inner", "expected", "noticed", "memory"}
PUBLIC_FIELDS  = {"from", "to", "talk", "message", "action", "actions", "body", "mood"}


# ======================================================================
#  TOOLS
# ======================================================================

def get_tools(activity: dict | None = None) -> list[dict]:
    """Retourne les tool definitions à passer au provider **joueur**.

    Source de vérité : le décorateur `@command(mcp=True, mcp_role="player", ...)`.
    Filtre explicite sur `role="player"` — les tools MJ (`give_turn`, etc.) ne
    sont pas exposés aux LLM joueurs.

    Le paramètre `activity` est réservé pour un futur filtrage par allowlist
    (`activity['tools_allowed']`).
    """
    return mcp_tool_definitions(role="player")


# ======================================================================
#  FORMAT EXCHANGE
# ======================================================================

def format_exchange(speaker: str, raw_response: str) -> str:
    """Formate un échange brut en markdown distributable aux autres joueurs.

    Seuls les champs publics sont inclus (talk, actions, body, mood).
    Les champs privés (inner_thought, inner, expected, noticed, memory) sont ignorés.
    """
    data = parse_llm_json(raw_response)
    if not data:
        return f"{speaker} prend la parole : {raw_response}"

    lines = []
    from_char = data.get("from", speaker)
    to_char   = data.get("to", "all")

    if to_char == "all":
        lines.append(f"### {from_char} s'adresse à tous")
    else:
        lines.append(f"### {from_char} s'adresse à {to_char}")

    talk = data.get("talk") or data.get("message")
    if talk:
        if isinstance(talk, list):
            for line in talk:
                lines.append(f"- {line}")
        else:
            lines.append(f"- {talk}")

    actions = data.get("actions") or data.get("action")
    if actions:
        lines.append(f"### {from_char} a agi ainsi:")
        if isinstance(actions, list):
            for line in actions:
                lines.append(f"- {line}")
        else:
            lines.append(f"- {actions}")

    body = data.get("body")
    if body:
        lines.append(f"### le corps de {from_char} réagit ainsi:")
        lines.append(f"- {body}")

    mood = data.get("mood")
    if mood:
        lines.append(f"### l'humeur de {from_char}:")
        lines.append(f"- {mood}")

    return "\n".join(lines)


# ======================================================================
#  SYSTEM PROMPT
# ======================================================================

def build_system_prompt(
    player: str,
    instance: dict,
    activity: dict,
    scene: dict,
    character: dict,
    knowledge_entries: list[dict],
    system_schemas: list[dict] | None = None,
) -> str:
    """Assemble le system prompt complet pour un joueur à un tour donné.

    Ordre strict :
      1. Schema JSON (si défini dans l'activité)
      2. Scène
      3. Règles joueur
      4. Impressions sur les autres (knowledge, presentation)
      5. Fiche personnage
    """
    parts = []

    # 1. Schemas system activés (résolus par l'engine depuis activity.system[enabled])
    for schema in (system_schemas or []):
        lines = ["Réponds UNIQUEMENT en JSON valide respectant ce schéma. Ne l'encadre pas de bloc de code markdown."]
        prompt_text = schema.get("prompt", "").strip()
        if prompt_text:
            lines.append(prompt_text)
        payload = schema.get("payload")
        if payload:
            lines.append(json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload)
        parts.append("\n".join(lines))

    # 2. Scène
    scene_content = scene.get("content", "")
    if scene_content:
        parts.append(f"## Scène\n{scene_content}")

    # 3. Règles joueur
    rules = activity.get("rules") or {}
    if not isinstance(rules, dict):
        log.warning("[build_system_prompt] activity.rules n'est pas un dict (%r) pour %r",
                    type(rules).__name__, activity.get("_id", "?"))
        rules = {}

    player_rules = rules.get("players", "")
    if player_rules:
        parts.append(f"## Règles du jeu\n{player_rules}")
    else:
        log.warning("[build_system_prompt] rules.players absent ou vide pour l'activité %r",
                    activity.get("_id", "?"))

    # 4. Impressions sur les autres (knowledge)
    if knowledge_entries:
        by_about: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for entry in knowledge_entries:
            about    = entry.get("about", "?")
            category = entry.get("category", "?")
            value    = entry.get("value") or entry.get("content", "")
            if value:
                by_about[about][category].append(value)

        if by_about:
            lines = [
                "## Tes impressions sur les autres participants",
                "Ces analyses reflètent tes premières impressions. "
                "Elles guident ta manière d'interagir avec chacun.",
            ]
            for about, categories in by_about.items():
                lines.append(f"### Ce que tu sais à propos de {about}")
                for category, values in categories.items():
                    for value in values:
                        lines.append(f"- **{category}** : {value}")
            parts.append("\n".join(lines))

    # 5. Fiche personnage
    char_json = json.dumps(character, ensure_ascii=False, indent=2)
    parts.append(f"## Ta fiche personnage\n{char_json}")

    return "\n\n".join(parts)


# ======================================================================
#  MESSAGES
# ======================================================================

def build_messages(
    player: str,
    instance: dict,
    exchange_history: list[dict],
    current_round_event: dict | None = None,
    whisper: str | None = None,
    mj_instruction: dict | None = None,
    amorce: str | None = None,
) -> list[dict]:
    """Assemble la liste de messages pour un joueur à un tour donné.

    Ordre strict :
      1. Amorce MJ (réservée au MJ, jamais aux joueurs)
      2. Événement de round (déjà résolu par le caller)
      3. Whisper (message privé)
      4. Historique des échanges publics
      5. Instruction MJ (déjà résolue par le caller)
    """
    messages = []

    # 1. Amorce MJ
    if amorce is not None:
        messages.append({"role": "user", "content": amorce})

    # 2. Événement de round
    if current_round_event is not None:
        content = (
            current_round_event.get("content")
            or current_round_event.get("instruction")
            or json.dumps(current_round_event, ensure_ascii=False)
        )
        messages.append({"role": "user", "content": content})

    # 3. Whisper
    if whisper is not None:
        messages.append({"role": "user", "content": whisper})

    # 4. Historique des échanges publics
    for entry in exchange_history:
        from_char = entry.get("from")
        role      = "assistant" if from_char == player else "user"
        raw       = entry.get("raw_response") or entry.get("content", "")
        messages.append({"role": role, "content": format_exchange(from_char or "?", raw)})

    # 5. Instruction MJ
    if mj_instruction is not None:
        content = (
            mj_instruction.get("instruction")
            or mj_instruction.get("content")
            or json.dumps(mj_instruction, ensure_ascii=False)
        )
        messages.append({"role": "user", "content": content})

    return messages
