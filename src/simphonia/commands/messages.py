"""Bus `messages` — canal de fan-out pour la republication des sorties LLM parsées.

Spec : `documents/shadow_storage.md` — section *Bus `messages` — canal pub/sub central*.

Ce module ne porte qu'une seule commande no-op `published`. Le travail réel est
fait par les listeners enregistrés via `Bus.subscribe(...)` (cf. core/bus.py).

Producteurs (services qui dispatchent sur ce bus) :
- `activity_service.engine` — après _build_exchange (par tour de joueur)
- `chat_service.default_strategy` — après parse_llm_json (par réponse)
- … (extensible — futurs modes)

Consommateurs (services qui s'abonnent) :
- `shadow_storage` — capture du subconscient des joueurs
- … (extensible — futurs metrics_service, audit_log, etc.)

Schéma du payload (convention, non enforcée — schemaless) :
    {
        "bus_origin": str,       # "activity" | "chat" | …
        "from_char":  str | None,# slug du locuteur, None si non applicable
        "payload":    dict,      # contenu brut tel que produit par la source
    }
"""
from simphonia.core import command


MESSAGES_BUS = "messages"


@command(
    bus=MESSAGES_BUS,
    code="published",
    description=(
        "Canal de fan-out — republication des sorties LLM parsées. "
        "Callback no-op : le travail est fait par les listeners du bus."
    ),
)
def published_command(**kwargs) -> None:
    """No-op intentionnel — voir docstring du module."""
    return None
