"""MemoryService — RAG contextuel.

Interface + factory qui instancie la stratégie (`chroma_strategy`, …) sélectionnée
via la configuration YAML (`services.memory_service`). Pour l'instant,
seule `chroma_strategy` est disponible — l'abstraction est en place pour
permettre un provider alternatif le jour où ChromaDB ne suffit plus.
"""

from abc import ABC, abstractmethod


class MemoryService(ABC):
    """Contrat du service de mémoire contextuelle (RAG)."""

    @abstractmethod
    def recall(
        self,
        from_char: str,
        context: str,
        top_k: int | None = None,
        about: str | None = None,
        participants: list[str] | None = None,
        factor: float = 1.0,
        max_distance: float | None = None,
    ) -> list[dict]:
        """Retourne les souvenirs pertinents d'un personnage pour un contexte donné."""

    @abstractmethod
    def stats(self) -> dict:
        """Retourne un instantané de l'état du service (observabilité)."""


def build_memory_service(service_config: dict) -> MemoryService:
    """Instancie la stratégie configurée (`services.memory_service` section)."""
    strategy = service_config.get("strategy", "chroma_strategy")

    if strategy == "chroma_strategy":
        from simphonia.services.memory_service.strategies.chroma_strategy import (
            ChromaMemoryService,
        )

        return ChromaMemoryService()

    raise ValueError(f"Unknown memory_service strategy: {strategy!r}")


_instance: MemoryService | None = None


def init(service_config: dict) -> None:
    """Construit l'instance du service selon la config donnée. Idempotent."""
    global _instance
    if _instance is None:
        _instance = build_memory_service(service_config)


def get() -> MemoryService:
    """Retourne l'instance du service. `init()` doit avoir été appelé auparavant."""
    if _instance is None:
        raise RuntimeError("memory_service not initialized — call init() first")
    return _instance
