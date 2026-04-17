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
    top_k: int | None = None,
    about: str | None = None,
    participants: list[str] | None = None,
    factor: float = 1.0,
    max_distance: float | None = None,
) -> list[dict]:
    return memory_service.get().recall(
        from_char=from_char,
        context=context,
        top_k=top_k,
        about=about,
        participants=participants,
        factor=factor,
        max_distance=max_distance,
    )
