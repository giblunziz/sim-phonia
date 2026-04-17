"""CharacterService — accès aux fiches de personnages.

Interface + factory qui instancie la stratégie (`json_strategy`, `mongodb_strategy`, …)
sélectionnée via la configuration YAML (`services.character_service`).

Voir `documents/character_service.md` et `documents/configuration.md`.
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


def build_character_service(service_config: dict) -> CharacterService:
    """Instancie la stratégie configurée (`services.character_service` section).

    Import dynamique pour éviter de charger toutes les stratégies
    (et leurs dépendances) à l'import du package.
    """
    strategy = service_config.get("strategy", "json_strategy")

    if strategy == "json_strategy":
        from simphonia.services.character_service.strategies.json_strategy import (
            JsonCharacterService,
        )

        return JsonCharacterService()

    if strategy == "mongodb_strategy":
        from simphonia.services.character_service.strategies.mongodb_strategy import (
            MongoCharacterService,
        )

        database_uri = service_config.get("database_uri")
        database_name = service_config.get("database_name")
        if not isinstance(database_uri, str) or not database_uri:
            raise RuntimeError(
                "mongodb_strategy: `services.character_service.database_uri` manquant ou vide "
                "(vérifier le YAML et l'interpolation ${MONGO_URI})"
            )
        if not isinstance(database_name, str) or not database_name:
            raise RuntimeError(
                "mongodb_strategy: `services.character_service.database_name` manquant ou vide "
                "(vérifier le YAML et l'interpolation ${MONGO_DATABASE})"
            )
        return MongoCharacterService(database_uri=database_uri, database_name=database_name)

    raise ValueError(f"Unknown character_service strategy: {strategy!r}")


_instance: CharacterService | None = None


def init(service_config: dict) -> None:
    """Construit l'instance du service selon la config donnée. Idempotent."""
    global _instance
    if _instance is None:
        _instance = build_character_service(service_config)


def get() -> CharacterService:
    """Retourne l'instance du service. `init()` doit avoir été appelé auparavant."""
    if _instance is None:
        raise RuntimeError("character_service not initialized — call init() first")
    return _instance
