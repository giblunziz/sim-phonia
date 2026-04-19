from simphonia.core import command
from simphonia.services import memory_service

MEMORY_BUS = "memory"


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
