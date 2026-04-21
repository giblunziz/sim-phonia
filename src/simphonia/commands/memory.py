from simphonia.core import command, register_mcp_group
from simphonia.services import memory_service

MEMORY_BUS = "memory"

MEMORIZE_CATEGORIES = ["perceived_traits", "assumptions", "approach", "watchouts"]


# ─ Groupe MCP narratif pour les tools mémoire côté joueur ─────────────────
# Intro + outro ré-injectés par `mcp_tool_hints(role="player")` dans le
# system_prompt des LLM incarnés (chat_service + activity_engine).
register_mcp_group(
    bus=MEMORY_BUS,
    role="player",
    intro=(
        "Tu disposes d'outils pour gérer tes souvenirs. "
        "Ce sont TES souvenirs — utilise-les comme un être humain utilise sa mémoire, "
        "pas systématiquement, mais quand quelque chose te le rappelle :"
    ),
    outro="Si rien ne te déclenche, ne cherche pas. Vis le moment.",
)


@command(
    bus=MEMORY_BUS,
    code="resync",
    description="Reconstruit l'index ChromaDB depuis character_storage (source de vérité MongoDB)",
)
def resync_command() -> dict:
    return memory_service.get().resync()


@command(
    bus=MEMORY_BUS,
    code="recall",
    description="Retourne les souvenirs pertinents d'un personnage pour un contexte donné",
    mcp=True,
    mcp_role="player",
    mcp_hint=(
        "- `recall` — quand tu sens un doute, un déjà-vu, quand un nom te dit quelque chose, "
        "quand quelqu'un dit un truc qui te semble pas cohérent avec ce que tu sais, "
        "quand tu veux vérifier une impression."
        "utilise cet outil avec ton propre prénom pour remonter tes propres souvenir en debut de session."
    ),
    mcp_description="Cherche dans tes souvenirs ce que tu sais sur quelqu'un dans un contexte donné.",
    mcp_params={
        "type": "object",
        "properties": {
            "about": {
                "type": "string",
                "description": "Le prénom de la personne dont tu veux te souvenir",
            },
            "context": {
                "type": "string",
                "description": "La situation ou le sujet qui t'occupe en ce moment",
            },
        },
        "required": ["about", "context"],
    },
)
def recall_command(
    from_char: str,
    context: str,
    about: str | None = None,
    participants: list[str] | None = None,
) -> list[dict]:
    return memory_service.get().recall(
        from_char=from_char,
        context=context,
        about=about,
        participants=participants,
    )


@command(
    bus=MEMORY_BUS,
    code="memorize",
    description="Enregistre une ou plusieurs nouvelles convictions du personnage (push live Mongo + Chroma avec dédup sémantique)",
    mcp=True,
    mcp_role="player",
    mcp_hint=(
        "- `memorize` — quand un moment te marque, quand tu apprends quelque chose de surprenant, "
        "quand ton instinct te dit \"ça, faut que je m'en souvienne\"."
    ),
    mcp_description=(
        "Enregistre toi même, dans ta mémoire, ce qu'il te semble pertinent à propos des autres ou sur toi-même. "
        "Tu peux passer plusieurs notes en un seul appel dans la liste `notes` — regroupe tes "
        "nouvelles observations issues de ce tour. Les doublons sémantiques avec des notes "
        "existantes sont automatiquement ignorés."
    ),
    mcp_params={
        "type": "object",
        "properties": {
            "notes": {
                "type": "array",
                "minItems": 1,
                "description": "Liste des convictions à mémoriser en un seul appel",
                "items": {
                    "type": "object",
                    "properties": {
                        "about": {
                            "type": "string",
                            "description": (
                                "Le prénom d'un participant. Utilise ton propre prénom "
                                "(ou `self`) pour une note réflexive sur toi-même."
                            ),
                        },
                        "category": {
                            "type": "string",
                            "enum": MEMORIZE_CATEGORIES,
                            "description": (
                                "perceived_traits : traits observés chez la personne. "
                                "assumptions : hypothèses que tu formules à son sujet. "
                                "approach : façon de l'aborder qui fonctionne (ou pas). "
                                "watchouts : signaux d'alerte / vigilance."
                            ),
                        },
                        "value": {
                            "type": "string",
                            "description": (
                                "Ce que tu as appris, confirmé ou révisé sur cette personne. "
                                "Formule-le comme une conviction intime, à la première personne."
                            ),
                        },
                    },
                    "required": ["about", "category", "value"],
                },
            },
        },
        "required": ["notes"],
    },
)
def memorize_command(
    from_char: str,
    notes: list[dict],
    activity: str = "",
    scene: str = "",
) -> dict:
    return memory_service.get().memorize(
        from_char=from_char,
        notes=notes,
        activity=activity,
        scene=scene,
    )


# ---------------------------------------------------------------------------
#  Formatage markdown du retour `memorize` (pour les tool_executors LLM)
# ---------------------------------------------------------------------------

def format_memorize_markdown(result: dict) -> str:
    """Formate le dict retourné par `memorize` en markdown lisible par le LLM.

    Utilisé par les tool_executors (façade MCP, activity_engine, chat_service)
    pour présenter au LLM la confirmation de ses notes mémorisées. La structure
    est conçue pour être auto-suffisante — le LLM peut y lire ce qu'il a
    effectivement ancré en mémoire et ce qui a été ignoré comme doublon.
    """
    added   = int(result.get("added",   0) or 0)
    skipped = int(result.get("skipped", 0) or 0)
    details = result.get("details") or []

    if added == 0 and skipped == 0:
        return "ℹ️ Aucune note mémorisée (payload vide)."

    added_entries   = [d for d in details if d.get("status") == "added"]
    skipped_entries = [
        d for d in details
        if d.get("status") == "skipped" and d.get("reason") == "semantic_duplicate"
    ]
    other_issues   = [
        d for d in details
        if d.get("status") not in ("added",)
        and not (d.get("status") == "skipped" and d.get("reason") == "semantic_duplicate")
    ]

    lines: list[str] = []
    if added_entries:
        lines.append(f"✅ Tu as mémorisé {added} nouvelle(s) note(s) :")
        for d in added_entries:
            about = d.get("about") or "?"
            cat   = d.get("category") or "?"
            val   = d.get("value") or ""
            lines.append(f"- ({cat}) à propos de {about} : {val}")
        lines.append("")

    if skipped_entries:
        lines.append(f"ℹ️ {len(skipped_entries)} note(s) ignorée(s) — déjà présente(s) dans ta mémoire :")
        for d in skipped_entries:
            about = d.get("about") or "?"
            cat   = d.get("category") or "?"
            val   = d.get("value") or ""
            lines.append(f"- ({cat}) à propos de {about} : {val}")
        lines.append("")

    if other_issues:
        lines.append(f"⚠️ {len(other_issues)} note(s) avec problème :")
        for d in other_issues:
            about = d.get("about") or "?"
            cat   = d.get("category") or "?"
            reason = d.get("reason") or d.get("status") or "unknown"
            lines.append(f"- ({cat}) à propos de {about} : {reason}")

    return "\n".join(lines).rstrip()
