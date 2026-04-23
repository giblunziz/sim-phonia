"""tools_service — atelier utilitaire one-shot piloté par LLM.

Orchestre des runs ponctuels (source × subject) produisant des fichiers de
travail dans `./output/`. Hors scénario, hors session, hors bus applicatif.

Voir `documents/tools_service.md` et `documents/configuration.md`.
"""

import logging
from abc import ABC, abstractmethod

log = logging.getLogger("simphonia.tools")

_instance: "ToolsService | None" = None


class ToolsService(ABC):
    """Contrat atelier — lecture de collections mongo + CRUD `tasks` + run."""

    # ── registre task_collection + lecture documents ──────────────

    @abstractmethod
    def list_exposable_collections(self) -> list[str]:
        """Retourne la liste des `_id` de la collection `task_collection`.

        Projection `$project _id: 1` — la `description` éventuelle dans
        `task_collection` est pour l'utilisateur qui édite en direct, pas
        pour le back.
        """

    @abstractmethod
    def list_ids(self, collection_name: str) -> list[str]:
        """Liste les `_id` d'une collection autorisée (via `task_collection`).

        Lève `ValueError` si `collection_name` ne figure pas dans le registre.
        """

    @abstractmethod
    def get_document(self, collection_name: str, _id: str) -> dict | None:
        """Retourne le document complet (schemaless) ou `None`.

        Lève `ValueError` si `collection_name` ne figure pas dans le registre.
        """

    # ── tasks (collection de prompts réutilisables) ───────────────

    @abstractmethod
    def list_tasks(self) -> list[dict]:
        """Retourne toutes les tasks stockées (`{_id, prompt, temperature}`)."""

    @abstractmethod
    def get_task(self, slug: str) -> dict | None:
        """Retourne la task ou `None`."""

    @abstractmethod
    def put_task(self, slug: str, prompt: str, temperature: float) -> dict:
        """Upsert d'une task. Retourne le document complet."""

    @abstractmethod
    def delete_task(self, slug: str) -> bool:
        """Supprime une task. Retourne `True` si supprimé, `False` si absent."""


def build_tools_service(service_config: dict) -> ToolsService:
    """Instancie la stratégie configurée. Une seule stratégie pour l'instant."""
    strategy = service_config.get("strategy", "mongodb_strategy")

    if strategy == "mongodb_strategy":
        from simphonia.services.tools_service.strategies.mongodb_strategy import (
            MongoToolsService,
        )
        return MongoToolsService(
            database_uri=service_config["database_uri"],
            database_name=service_config["database_name"],
            tasks_collection=service_config.get("tasks_collection", "tasks"),
            registry_collection=service_config.get("registry_collection", "task_collection"),
        )

    raise ValueError(f"Unknown tools_service strategy: {strategy!r}")


def init(service_config: dict) -> None:
    global _instance
    _instance = build_tools_service(service_config)


def get() -> ToolsService:
    if _instance is None:
        raise RuntimeError("tools_service non initialisé — appelez init() au bootstrap")
    return _instance
