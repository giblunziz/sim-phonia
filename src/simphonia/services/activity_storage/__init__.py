"""activity_storage — référentiel MongoDB pour les activités, schémas, scènes et instances.

Gère les collections `activities`, `schemas`, `scenes` et `activity_instances` :
CRUD complet, ts_created/ts_updated auto-gérés.
"""

import logging
from abc import ABC, abstractmethod

log = logging.getLogger("simphonia.activity_storage")

_instance: "ActivityStorageService | None" = None


class ActivityStorageService(ABC):

    @abstractmethod
    def list_activities(self, *, filter: dict | None = None) -> list[dict]: ...

    @abstractmethod
    def get_activity(self, activity_id: str) -> dict | None:
        """Retourne None si absent."""

    @abstractmethod
    def put_activity(self, activity_id: str, data: dict) -> dict:
        """Upsert sur _id (slug). ts_created/ts_updated auto-gérés. Retourne le document."""

    @abstractmethod
    def delete_activity(self, activity_id: str) -> bool:
        """Retourne True si supprimé, False si absent."""

    # ── schemas ───────────────────────────────────────────────────

    @abstractmethod
    def list_schemas(self, *, filter: dict | None = None) -> list[dict]: ...

    @abstractmethod
    def get_schema(self, schema_id: str) -> dict | None:
        """Retourne None si absent."""

    @abstractmethod
    def put_schema(self, schema_id: str, data: dict) -> dict:
        """Upsert sur _id (slug). ts_created/ts_updated auto-gérés. Retourne le document."""

    @abstractmethod
    def delete_schema(self, schema_id: str) -> bool:
        """Retourne True si supprimé, False si absent."""

    # ── scenes ────────────────────────────────────────────────────

    @abstractmethod
    def list_scenes(self, *, filter: dict | None = None) -> list[dict]: ...

    @abstractmethod
    def get_scene(self, scene_id: str) -> dict | None:
        """Retourne None si absent."""

    @abstractmethod
    def put_scene(self, scene_id: str, data: dict) -> dict:
        """Upsert sur _id (slug). ts_created/ts_updated auto-gérés. Retourne le document."""

    @abstractmethod
    def delete_scene(self, scene_id: str) -> bool:
        """Retourne True si supprimé, False si absent."""

    # ── activity_instances ────────────────────────────────────────

    @abstractmethod
    def list_instances(self, *, filter: dict | None = None) -> list[dict]: ...

    @abstractmethod
    def get_instance(self, instance_id: str) -> dict | None:
        """Retourne None si absent."""

    @abstractmethod
    def put_instance(self, instance_id: str, data: dict) -> dict:
        """Upsert sur _id (slug). ts_created/ts_updated auto-gérés. Retourne le document."""

    @abstractmethod
    def delete_instance(self, instance_id: str) -> bool:
        """Retourne True si supprimé, False si absent."""


def build_activity_storage_service(service_config: dict) -> ActivityStorageService:
    strategy = service_config.get("strategy", "mongodb_strategy")

    if strategy == "mongodb_strategy":
        from simphonia.services.activity_storage.strategies.mongodb_strategy import (
            MongoActivityStorage,
        )
        collections = service_config.get("collections", {})
        return MongoActivityStorage(
            database_uri=service_config["database_uri"],
            database_name=service_config["database_name"],
            activities_collection=collections.get("activities", "activities"),
            schemas_collection=collections.get("schemas", "schemas"),
            scenes_collection=collections.get("scenes", "scenes"),
            instances_collection=collections.get("activity_instances", "activity_instances"),
        )

    raise ValueError(f"Unknown activity_storage strategy: {strategy!r}")


def init(service_config: dict) -> None:
    global _instance
    _instance = build_activity_storage_service(service_config)


def get() -> ActivityStorageService:
    if _instance is None:
        raise RuntimeError("activity_storage non initialisé — appelez init() au bootstrap")
    return _instance
