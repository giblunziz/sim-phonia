from simphonia.core import command
from simphonia.services import character_service

CHARACTER_BUS = "character"


@command(
    bus=CHARACTER_BUS,
    code="list",
    description="Retourne la liste des identifiants des personnages connus",
)
def list_command() -> list[str]:
    return character_service.get().get_character_list()


@command(
    bus=CHARACTER_BUS,
    code="get",
    description="Retourne la fiche complète d'un personnage",
)
def get_command(name: str) -> dict:
    return character_service.get().get_character(name)


@command(
    bus=CHARACTER_BUS,
    code="reset",
    description="Recharge toutes les fiches depuis la source de données",
)
def reset_command() -> int:
    return character_service.get().reset()
