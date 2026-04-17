"""MemoryService — RAG contextuel (vector store local ChromaDB).

Usage interne uniquement. Accessible via la commande bus `memory/recall`.
Pas d'import direct hors du module `simphonia.commands.memory` tant que la
contrainte d'exposition n'est pas levée.

Port simplifié de `symphonie.services.memory_service` :
- pas de synchronisation MongoDB
- pas de push / drop / reset (la mutation sera gérée par ailleurs, via cascades)
- seul `recall` est exposé sur le bus
"""

import json
import logging

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from simphonia.config import CHROMA_DIR, COLLECTION_NAME, DEFAULT_MEMORY_SLOTS, EMBEDDING_MODEL

log = logging.getLogger("simphonia.memory")
log_chroma = logging.getLogger("simphonia.chromadb")


class MemoryService:
    """RAG contextuel — vector store local ChromaDB."""

    def __init__(self) -> None:
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None
        self._embedder: SentenceTransformer | None = None
        self._ready = False

    def init(self, force_cpu: bool = False) -> None:
        """Initialise ChromaDB + modèle d'embedding. Idempotent."""
        if self._ready:
            return

        log.info("Initialisation MemoryService...")

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("ChromaDB : %s (%d documents)", CHROMA_DIR, self._collection.count())

        device = "cpu" if force_cpu else None
        log.info("Chargement du modèle d'embedding : %s", EMBEDDING_MODEL)
        self._embedder = SentenceTransformer(EMBEDDING_MODEL, device=device)
        log.info("MemoryService prêt — %d documents indexés", self._collection.count())

        self._ready = True

    @property
    def ready(self) -> bool:
        return self._ready

    def embed(self, text: str) -> list[float]:
        assert self._embedder is not None, "MemoryService non initialisé"
        return self._embedder.encode(text, normalize_embeddings=True).tolist()

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
        """Récupère les souvenirs pertinents d'un personnage pour un contexte donné.

        Args:
            from_char: personnage qui se souvient (filtre metadata `from`)
            context: texte de contexte (événement, affirmation, situation)
            top_k: nombre max de résultats (défaut: DEFAULT_MEMORY_SLOTS)
            about: filtre sur une cible unique
            participants: filtre sur les participants de l'activité (+ soi-même)
            factor: multiplicateur sur top_k pour élargir la fenêtre de recherche
            max_distance: distance cosine max pour filtrer le bruit

        Returns:
            Liste de dicts {value, about, category, activity, scene, distance}
            triés par pertinence (distance croissante).
        """
        if not self._ready:
            log.warning("MemoryService non initialisé")
            return []

        k = top_k or DEFAULT_MEMORY_SLOTS
        n_results = max(int(k * factor), 1)

        if about:
            where: dict = {"$and": [{"from": from_char}, {"about": about}]}
        elif participants:
            targets = list(participants)
            if from_char not in targets:
                targets.append(from_char)
            where = {"$and": [{"from": from_char}, {"about": {"$in": targets}}]}
        else:
            where = {"from": from_char}

        assert self._collection is not None
        count = self._collection.count()
        if count == 0:
            return []

        query_embedding = self.embed(context)

        log_chroma.debug("=" * 60)
        log_chroma.debug("RECALL REQUEST")
        log_chroma.debug(
            json.dumps(
                {
                    "from_char": from_char,
                    "context": context[:200],
                    "top_k": k,
                    "factor": factor,
                    "n_results": n_results,
                    "max_distance": max_distance,
                    "where": where,
                    "collection_count": count,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        results = self._collection.query(
            query_embeddings=[query_embedding],
            where=where,
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )

        log_chroma.debug("RECALL RESPONSE")
        log_chroma.debug(
            json.dumps(
                {
                    "documents": results.get("documents", []),
                    "metadatas": results.get("metadatas", []),
                    "distances": results.get("distances", []),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        memories: list[dict] = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i]
            if max_distance is not None and distance > max_distance:
                continue
            memories.append(
                {
                    "value": doc,
                    "about": meta.get("about", ""),
                    "category": meta.get("category", ""),
                    "activity": meta.get("activity", ""),
                    "scene": meta.get("scene", ""),
                    "distance": round(distance, 4),
                }
            )

        log.debug(
            "%s recall (%d candidats → %d retenus, factor=%.1f, max_dist=%s)",
            from_char,
            len(results["documents"][0]),
            len(memories),
            factor,
            max_distance,
        )
        return memories

    def stats(self) -> dict:
        if not self._ready:
            return {"status": "not_initialized"}
        assert self._collection is not None
        return {
            "status": "ready",
            "documents": self._collection.count(),
            "embedding_model": EMBEDDING_MODEL,
            "chroma_dir": str(CHROMA_DIR),
        }


memory_service = MemoryService()
