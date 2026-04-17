from simphonia.core import command
from simphonia.services import memory_service

MEMORY_BUS = "memory"


@command(
    bus=MEMORY_BUS,
    code="recall",
    description="Retourne les souvenirs pertinents d'un personnage pour un contexte donné",
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
