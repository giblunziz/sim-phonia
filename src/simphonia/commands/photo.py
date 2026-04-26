"""Commandes bus `photo` — exposition MCP des fonctions photographiques.

Deux commandes exposées au LLM-joueur (`take_shoot`, `take_selfy`), deux
commandes internes (`publish`, `get`) pour la plomberie cascades + SSE +
récupération HTTP.

Voir `documents/photo_service.md` § 3 pour le détail.
"""

from simphonia.core import command, register_mcp_group
from simphonia.services import photo_service

PHOTO_BUS = "photo"


# ─ Groupe MCP narratif pour les tools photo côté joueur ────────────────────
# Intro + outro ré-injectés par `mcp_tool_hints(role="player")` dans le
# system_prompt des LLM incarnés.
register_mcp_group(
    bus=PHOTO_BUS,
    role="player",
    intro=(
        "Tu peux prendre des photos avec ton smartphone — pour illustrer "
        "ce que tu vois, ou un autoportrait. Utilise ces outils quand un "
        "moment mérite d'être figé visuellement, pas en continu :"
    ),
    outro=(
        "Compose tes photos comme un humain : intentionnellement, avec un "
        "regard. Pas tous les tours, pas pour tout."
    ),
    reminder=(
        "Pense à tes outils photo ${commands} si un moment marquant se "
        "présente — un visage, un décor, toi-même dans une situation."
    ),
)


# ──────────────────────────────────────────────────────────────────────────
#  Commandes MCP — exposées au LLM-joueur
# ──────────────────────────────────────────────────────────────────────────

@command(
    bus=PHOTO_BUS,
    code="take_shoot",
    description="Génère une photo de scène à partir d'un prompt markdown sectionné",
    mcp=True,
    mcp_role="player",
    mcp_hint=(
        "- `take_shoot` — pour photographier une scène, un visage, un objet, "
        "un décor. Tu décris ce que tu veux capturer en sections markdown "
        "(`# style`, `# sujet`, `# tenue`, `# attitude`, `# pose`, "
        "`# arriere_plan`, `# ambiance`, etc.). Tu es libre sur toutes les "
        "sections."
    ),
    mcp_description=(
        "Prends une photo de la scène devant toi. Décris en markdown ce que "
        "tu vois et comment tu veux la cadrer, avec des sections nommées : "
        "`# style` (smartphone, contre-plongée, plan large…), `# sujet` (ce "
        "qui est photographié), `# expression`, `# tenue`, `# arriere_plan`, "
        "`# ambiance`. Toutes les sections sont libres."
    ),
    mcp_params={
        "type": "object",
        "properties": {
            "markdown": {
                "type": "string",
                "description": (
                    "Prompt markdown sectionné. Sections recommandées : "
                    "`# style`, `# sujet`, `# tenue`, `# attitude`, "
                    "`# pose`, `# arriere_plan`, `# ambiance`. Format : "
                    "`# nom_section\\ncontenu\\n\\n# autre_section\\n...`"
                ),
            },
        },
        "required": ["markdown"],
    },
)
def take_shoot_command(
    markdown: str,
    from_char: str,
    session_id: str = "",
    activity_id: str | None = None,
) -> dict:
    return photo_service.get().take_shoot(
        markdown=markdown,
        from_char=from_char,
        session_id=session_id,
        activity_id=activity_id,
    )


@command(
    bus=PHOTO_BUS,
    code="take_selfy",
    description="Génère un autoportrait — `# style` et `# sujet` injectés par le service",
    mcp=True,
    mcp_role="player",
    mcp_hint=(
        "- `take_selfy` — pour un selfie. Tu décris uniquement ce qui varie "
        "d'un selfie à l'autre : `# tenue`, `# attitude`, `# pose`, "
        "`# arriere_plan`, `# ambiance`. Le service garantit la cohérence "
        "visuelle entre tes selfies (mêmes traits, mêmes signes distinctifs) "
        "— ne décris pas ton apparence physique, c'est figé depuis ta fiche."
    ),
    mcp_description=(
        "Prends un selfie de toi. Décris en markdown ton expression, ta "
        "tenue, ta pose, où tu te trouves, l'ambiance — avec des sections "
        "nommées (`# tenue`, `# attitude`, `# pose`, `# arriere_plan`, "
        "`# ambiance`). Ne décris PAS ton apparence physique : elle est "
        "automatiquement injectée depuis ta fiche pour que tu restes "
        "visuellement cohérent d'un selfie à l'autre."
    ),
    mcp_params={
        "type": "object",
        "properties": {
            "markdown": {
                "type": "string",
                "description": (
                    "Prompt markdown sectionné — sections variables uniquement. "
                    "Recommandées : `# tenue`, `# attitude`, `# pose`, "
                    "`# arriere_plan`, `# ambiance`. Les sections `# style` "
                    "et `# sujet` sont écrasées par le service."
                ),
            },
        },
        "required": ["markdown"],
    },
)
def take_selfy_command(
    markdown: str,
    from_char: str,
    session_id: str = "",
    activity_id: str | None = None,
) -> dict:
    return photo_service.get().take_selfy(
        markdown=markdown,
        from_char=from_char,
        session_id=session_id,
        activity_id=activity_id,
    )


# ──────────────────────────────────────────────────────────────────────────
#  Commandes internes — pas de mcp=True
# ──────────────────────────────────────────────────────────────────────────

@command(
    bus=PHOTO_BUS,
    code="publish",
    description="Émet l'événement de publication d'une photo (déclenche les listeners SSE / cascades)",
)
def publish_command(photo_id: str, **payload) -> dict:
    """No-op intentionnel : la valeur sémantique du dispatch est transportée
    aux listeners via `_notify_listeners(payload)` (cf. `core/bus.py:Bus.dispatch`).
    Cette fonction accepte donc le payload complet (`session_id`, `from_char`,
    `type`, `url`...) en `**payload` sans matcher chaque clé — les listeners
    enregistrés sur ce bus (bridge SSE, futures cascades shadow_memory) y
    accèdent eux-mêmes via le payload reçu en argument."""
    return {"photo_id": photo_id, **payload}


@command(
    bus=PHOTO_BUS,
    code="get",
    description="Retourne les métadonnées d'une photo (statut, file_path, prompt résolu) ou `None`",
)
def get_command(photo_id: str) -> dict | None:
    return photo_service.get().get_photo(photo_id)


# ---------------------------------------------------------------------------
#  Formatage markdown du retour `take_shoot` / `take_selfy` pour les
#  tool_executors LLM (chat_service, activity_engine).
# ---------------------------------------------------------------------------

def format_photo_ack_markdown(result: dict, *, type_: str) -> str:
    """Formate le dict ack `{status, photo_id}` en markdown lisible par le LLM.

    Utilisé par les tool_executors pour confirmer au LLM-joueur que sa photo
    est en cours de génération (mode async — l'image arrive plus tard sur le
    bus / SSE simweb, pas dans la réponse du tool).
    """
    photo_id = result.get("photo_id") or "?"
    status = result.get("status") or "?"
    kind = "selfie" if type_ == "selfy" else "photo"
    if status == "queued":
        return (
            f"📷 {kind.capitalize()} en cours de génération "
            f"(`photo_id`: `{photo_id}`). Elle s'affichera dans quelques secondes."
        )
    if status == "failed":
        error = result.get("error") or "raison inconnue"
        return f"⚠️ Échec de la prise de {kind} : {error}"
    return f"📷 {kind.capitalize()} : statut `{status}`, `photo_id`: `{photo_id}`"
