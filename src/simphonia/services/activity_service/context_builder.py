"""Assemblage du contexte LLM (system prompt + messages) pour chaque tour d'activité."""
import json
import logging
from collections import defaultdict

from simphonia.core.mcp import mcp_tool_definitions, mcp_tool_reminders
from simphonia.utils.parser import parse_llm_json

log = logging.getLogger("simphonia.activity.context")

PRIVATE_FIELDS = {"inner_thought", "inner", "expected", "noticed", "memory"}
PUBLIC_FIELDS  = {"from", "to", "talk", "message", "action", "actions", "body", "mood"}


# ======================================================================
#  TOOLS
# ======================================================================

def get_tools(activity: dict | None = None, role: str = "player") -> list[dict]:
    """Retourne les tool definitions à passer au provider pour un rôle donné.

    Source de vérité : le décorateur `@command(mcp=True, mcp_role=..., ...)`.
    Le `role` est habituellement dérivé via `character_service.get().get_type(speaker)` —
    un `npc` ou `human` recevra l'ensemble de tools correspondant (pouvant être vide).

    Le paramètre `activity` est réservé pour un futur filtrage par allowlist
    (`activity['tools_allowed']`).
    """
    return mcp_tool_definitions(role=role)


# ======================================================================
#  FORMAT EXCHANGE
# ======================================================================


def _synthesize_raw_from_public(from_char: str, public: dict) -> str:
    """Génère un JSON équivalent à un `raw_response` LLM à partir d'un `public`
    d'exchange — utilisé pour les tours HITL (humain) qui n'ont pas de raw.

    Filtre les valeurs vides pour produire un JSON minimal, équivalent à ce
    qu'un LLM aurait produit pour le même `public`.
    """
    payload = {"from": from_char}
    for k, v in public.items():
        if v in (None, "", [], {}):
            continue
        payload[k] = v
    return json.dumps(payload, ensure_ascii=False)

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
    instance: dict | None,
    activity: dict | None,
    scene: dict | None,
    character: dict,
    knowledge_entries: list[dict],
    system_schemas: list[dict] | None = None,
) -> str:
    """Assemble le system prompt complet pour un joueur à un tour donné.

    Ordre strict :
      1. Schema JSON (si défini dans l'activité)
      2. Scène
      3. Règles joueur (skippé si `activity is None`)
      4. Impressions sur les autres (knowledge, presentation)
      5. Fiche personnage

    `instance` et `activity` peuvent être `None` pour un usage hors activity_engine
    (ex: chat_service simple). Dans ce cas, la section "Règles du jeu" est
    entièrement omise — pas de warning.
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
    scene_content = scene.get("content", "") if scene else ""
    if scene_content:
        parts.append(f"## Scène\n{scene_content}")

    # 3. Règles joueur (uniquement si une activité est fournie)
    if activity is not None:
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
    memorize_log: list[str] | None = None,
    role: str = "player",
) -> list[dict]:
    """Assemble la liste de messages pour un joueur à un tour donné.

    Ordre strict :
      1. Amorce MJ (réservée au MJ, jamais aux joueurs)
      2. Événement de round (déjà résolu par le caller)
      3. Whisper (message privé)
      4. Mémorisations récentes du joueur (cohérence narrative memorize)
      5. Historique des échanges publics
      6. Instruction MJ (déjà résolue par le caller)
      7. Reminder MCP — suffixé au dernier message user, jamais persisté
         (régénéré à chaque tour pour combattre la dilution du system prompt
         sur conversations longues).
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

    # 4. Mémorisations récentes — ré-injection des confirmations `memorize` du
    # joueur pour garantir la cohérence narrative (sinon le LLM « mémorise puis
    # oublie au prochain give_turn »). Overlap léger accepté avec ce que `recall`
    # peut remonter — renforce l'ancrage.
    if memorize_log:
        content = "## Tes mémorisations récentes\n\n" + "\n\n---\n\n".join(memorize_log)
        messages.append({"role": "user", "content": content})

    # 5. Historique des échanges publics
    for entry in exchange_history:
        from_char = entry.get("from")
        role      = "assistant" if from_char == player else "user"
        raw       = entry.get("raw_response") or entry.get("content")
        if not raw:
            # Exchange sans raw_response (typiquement un tour HITL — l'humain
            # n'a pas produit de JSON LLM brut). On synthétise un JSON équivalent
            # depuis le `public` pour que `format_exchange` le rende comme un
            # tour LLM normal côté contexte des autres joueurs.
            raw = _synthesize_raw_from_public(from_char or "?", entry.get("public") or {})
        messages.append({"role": role, "content": format_exchange(from_char or "?", raw)})

    # 5. Instruction MJ
    if mj_instruction is not None:
        content = (
            mj_instruction.get("instruction")
            or mj_instruction.get("content")
            or json.dumps(mj_instruction, ensure_ascii=False)
        )
        messages.append({"role": "user", "content": content})

    # 6. Reminder MCP — suffixé au dernier message user (haute attention LLM,
    # placeholders ${commands} résolus). Jamais ré-injecté dans l'historique
    # persisté : régénéré à chaque tour à partir des mcp groups vivants.
    reminder = mcp_tool_reminders(role)
    if reminder:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                messages[i] = {
                    **messages[i],
                    "content": messages[i]["content"] + f"\n\n---\n{reminder}",
                }
                break

    return messages
