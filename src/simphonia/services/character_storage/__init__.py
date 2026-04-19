"""character_storage — accès structuré aux collections MongoDB `characters` et `knowledge`.

Service d'administration : source de vérité pour les données persistées.
Aucune connaissance de ses consommateurs (character_service, memory_service, simweb).
"""

import logging
from abc import ABC, abstractmethod

log = logging.getLogger("simphonia.character_storage")

_instance: "CharacterStorageService | None" = None


class CharacterStorageService(ABC):

    # ── characters ────────────────────────────────────────────────

    @abstractmethod
    def list_characters(self, *, filter: dict | None = None) -> list[dict]: ...

    @abstractmethod
    def get_character(self, character_id: str) -> dict | None:
        """Retourne None si absent."""

    @abstractmethod
    def put_character(self, character: dict) -> dict:
        """Upsert sur `_id` (str obligatoire). Retourne le document stocké."""

    @abstractmethod
    def delete_character(self, character_id: str) -> bool:
        """Retourne True si supprimé, False si absent."""

    # ── knowledge ─────────────────────────────────────────────────

    @abstractmethod
    def list_knowledge(self, *, filter: dict | None = None) -> list[dict]:
        """Tri anti-chronologique par défaut. Consommé par memory/resync."""

    @abstractmethod
    def get_knowledge(self, knowledge_id: str) -> dict | None:
        """Retourne None si absent."""

    @abstractmethod
    def push_knowledge(self, entry: dict) -> dict:
        """INSERT — injecte `_id` (str) et `ts` (ISO-8601 UTC) si absents."""

    @abstractmethod
    def update_knowledge(self, knowledge_id: str, patch: dict) -> dict | None:
        """Mise à jour partielle. Retourne le document mis à jour, None si absent."""

    @abstractmethod
    def delete_knowledge(self, knowledge_id: str) -> bool:
        """Retourne True si supprimé, False si absent."""

    @abstractmethod
    def delete_knowledge_by_activity(self, activity_id: str) -> int:
        """Supprime toutes les entrées knowledge liées à activity_id. Retourne le nombre supprimé."""


def build_character_storage_service(service_config: dict) -> CharacterStorageService:
    strategy = service_config.get("strategy", "mongodb_strategy")

    if strategy == "mongodb_strategy":
        from simphonia.services.character_storage.strategies.mongodb_strategy import (
            MongoCharacterStorage,
        )
        collections = service_config.get("collections", {})
        return MongoCharacterStorage(
            database_uri=service_config["database_uri"],
            database_name=service_config["database_name"],
            characters_collection=collections.get("characters", "characters"),
            knowledge_collection=collections.get("knowledge", "knowledge"),
        )

    raise ValueError(f"Unknown character_storage strategy: {strategy!r}")


def init(service_config: dict) -> None:
    global _instance
    _instance = build_character_storage_service(service_config)


def get() -> CharacterStorageService:
    if _instance is None:
        raise RuntimeError("character_storage non initialisé — appelez init() au bootstrap")
    return _instance
