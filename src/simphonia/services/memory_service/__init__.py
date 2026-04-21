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
        about: str | None = None,
        participants: list[str] | None = None,
    ) -> list[dict]:
        """Retourne les souvenirs pertinents d'un personnage pour un contexte donné."""

    @abstractmethod
    def memorize(
        self,
        from_char: str,
        notes: list[dict],
        activity: str = "",
        scene: str = "",
    ) -> dict:
        """Enregistre une ou plusieurs nouvelles convictions du personnage.

        Push live MongoDB + ChromaDB. Dédup sémantique (cosine `where=
        (from, about, category)`, seuil `dedup_threshold`) — les notes proches
        d'une existante sont skippées et reportées dans le retour.

        `notes` est une liste de dicts `{about, category, value}` :
          - `about`    : slug de personnage (résolu via fuzzy match), `from_char`
                         ou `"self"` autorisés pour l'introspection
          - `category` : un parmi `perceived_traits | assumptions | approach | watchouts`
          - `value`    : texte de la conviction (formulation à la 1re personne)

        `activity` et `scene` sont injectés par le tool_executor depuis la session
        en cours — ils tracent l'origine du souvenir dans les metadatas Chroma.

        Retourne :
          ```
          {
            "added":   int,    # notes effectivement insérées
            "skipped": int,    # notes skippées par dédup
            "details": [{about, category, status, reason?, distance?}, ...],
          }
          ```
        """

    @abstractmethod
    def stats(self) -> dict:
        """Retourne un instantané de l'état du service (observabilité)."""

    @abstractmethod
    def resync(self) -> dict:
        """Reconstruit l'index ChromaDB depuis character_storage.list_knowledge().

        Retourne {"reindexed": N}.
        """


def build_memory_service(service_config: dict) -> MemoryService:
    """Instancie la stratégie configurée (`services.memory_service` section)."""
    strategy = service_config.get("strategy", "chroma_strategy")

    if strategy == "chroma_strategy":
        from simphonia.services.memory_service.strategies.chroma_strategy import (
            ChromaMemoryService,
        )

        load_factor     = float(service_config.get("load_factor", 1.0))
        min_distance    = float(service_config.get("min_distance", 1.0))
        dedup_threshold = float(service_config.get("dedup_threshold", 0.2))
        return ChromaMemoryService(
            load_factor=load_factor,
            min_distance=min_distance,
            dedup_threshold=dedup_threshold,
        )

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
