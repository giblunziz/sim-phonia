"""shadow_storage — capture passive du subconscient des joueurs.

Service d'administration : alimente une collection MongoDB + un index ChromaDB
dédiés (`subconscient`) à partir des sorties LLM republiées sur le bus
`messages`. Aucune analyse, aucune interprétation — juste de la matière brute
sémantiquement indexée, prête à être consommée par Tobias (le futur
shadow_memory_service).

Spec : `documents/shadow_storage.md`.
"""

import logging
from abc import ABC, abstractmethod

log = logging.getLogger("simphonia.shadow_storage")

_instance: "ShadowStorageService | None" = None


class ShadowStorageService(ABC):

    # ── ingestion (listener bus messages) ─────────────────────────

    @abstractmethod
    def feed(self, message: dict) -> None:
        """Listener générique branché sur le bus `messages`.

        Filtre interne : ignore si pas de `from_char`, ou si tous les champs
        du payload sont exclus par `excluded_keys`. Push atomique Mongo + Chroma."""

    # ── lecture / pagination ──────────────────────────────────────

    @abstractmethod
    def list_entries(
        self,
        *,
        filter: dict | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Liste paginée triée anti-chrono par défaut."""

    @abstractmethod
    def count_entries(self, *, filter: dict | None = None) -> int:
        """Pour la pagination UI."""

    @abstractmethod
    def get_entry(self, entry_id: str) -> dict | None:
        """Retourne None si absent."""

    # ── mutation ──────────────────────────────────────────────────

    @abstractmethod
    def update_entry(self, entry_id: str, doc: dict) -> dict | None:
        """Update intégral du document. Retourne le doc mis à jour, None si absent.
        Resync Chroma à faire séparément via `resync_chroma()`."""

    @abstractmethod
    def delete_entry(self, entry_id: str) -> bool:
        """Suppression Mongo + Chroma. True si supprimé, False si absent."""

    # ── maintenance ───────────────────────────────────────────────

    @abstractmethod
    def resync_chroma(self) -> int:
        """Reconstruit l'index ChromaDB depuis Mongo. Retourne le count indexé."""


def build_shadow_storage_service(service_config: dict) -> ShadowStorageService:
    strategy = service_config.get("strategy", "mongodb_strategy")

    if strategy == "mongodb_strategy":
        from simphonia.services.shadow_storage.strategies.mongodb_strategy import (
            MongoShadowStorage,
        )
        return MongoShadowStorage(
            database_uri=service_config["database_uri"],
            database_name=service_config["database_name"],
            collection=service_config.get("collection", "subconscient"),
            chroma_collection=service_config.get("chroma_collection", "subconscient"),
            excluded_keys=set(service_config.get("excluded_keys") or ()),
        )

    raise ValueError(f"Unknown shadow_storage strategy: {strategy!r}")


def init(service_config: dict) -> None:
    """Initialise le service et l'abonne aux bus listés dans `subscriptions`."""
    global _instance
    _instance = build_shadow_storage_service(service_config)

    # Auto-subscribe sur les bus déclarés dans le YAML — délégué au bootstrap
    # pour respecter l'ordre d'init (le bus `messages` doit exister avant).
    from simphonia.core import default_registry
    from simphonia.core.errors import BusNotFound

    for bus_name in service_config.get("subscriptions") or []:
        try:
            default_registry().get(bus_name).subscribe(_instance.feed)
            log.info("shadow_storage abonné au bus %r", bus_name)
        except BusNotFound:
            log.warning("subscription bus %r introuvable — ignorée", bus_name)


def get() -> ShadowStorageService:
    if _instance is None:
        raise RuntimeError("shadow_storage non initialisé — appelez init() au bootstrap")
    return _instance
