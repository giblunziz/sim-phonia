"""CharacterService — accès aux fiches de personnages.

Interface + factory qui instancie la stratégie (`json_strategy`, `mongodb_strategy`, …)
sélectionnée via la configuration YAML (`services.character_service.strategy`).

Voir `documents/character_service.md`.
"""

from abc import ABC, abstractmethod


class CharacterService(ABC):
    """Contrat schemaless : les fiches circulent en `dict` brut."""

    @abstractmethod
    def get_character_list(self) -> list[str]:
        """Retourne la liste des identifiants (`_id`) des personnages connus."""

    @abstractmethod
    def get_character(self, name: str) -> dict:
        """Retourne la fiche complète d'un personnage (`dict` brut)."""

    @abstractmethod
    def reset(self) -> int:
        """Recharge toutes les fiches depuis la source de données.

        Retourne le nombre de fiches disponibles après rechargement.
        La sémantique du rechargement dépend de la stratégie active
        (rescan de répertoire pour `json_strategy`, `find()` pour
        `mongodb_strategy`, etc.).
        """


def build_character_service(strategy: str) -> CharacterService:
    """Instancie la stratégie configurée.

    Import dynamique pour éviter de charger toutes les stratégies
    (et leurs dépendances) à l'import du package.
    """
    if strategy == "json_strategy":
        from simphonia.services.character_service.strategies.json_strategy import (
            JsonCharacterService,
        )

        return JsonCharacterService()

    raise ValueError(f"Unknown character_service strategy: {strategy!r}")


_instance: CharacterService | None = None


def init(strategy: str) -> None:
    """Construit l'instance du service selon la stratégie donnée. Idempotent."""
    global _instance
    if _instance is None:
        _instance = build_character_service(strategy)


def get() -> CharacterService:
    """Retourne l'instance du service. `init()` doit avoir été appelé auparavant."""
    if _instance is None:
        raise RuntimeError("character_service not initialized — call init() first")
    return _instance
