"""ChromaMemoryService — RAG contextuel sur vector store local ChromaDB.

Port simplifié de `symphonie.services.memory_service` :
- pas de synchronisation MongoDB
- pas de push / drop / reset (la mutation sera gérée par ailleurs, via cascades)
- seul `recall` est exposé sur le bus (plus `stats` en observabilité)
"""

import json
import logging

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from simphonia.config import CHROMA_DIR, COLLECTION_NAME, DEFAULT_MEMORY_SLOTS, EMBEDDING_MODEL
from simphonia.core.errors import CharacterNotFound
from simphonia.services.memory_service import MemoryService

log = logging.getLogger("simphonia.memory")
log_chroma = logging.getLogger("simphonia.chromadb")


class ChromaMemoryService(MemoryService):
    """RAG contextuel — vector store local ChromaDB."""

    def __init__(self, load_factor: float = 1.0, min_distance: float = 1.0, force_cpu: bool = False) -> None:
        self._load_factor = load_factor
        self._min_distance = min_distance
        log.info("Initialisation ChromaMemoryService...")

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self._client: chromadb.ClientAPI = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection: chromadb.Collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("ChromaDB : %s (%d documents)", CHROMA_DIR, self._collection.count())

        device = "cpu" if force_cpu else None
        log.info("Chargement du modèle d'embedding : %s", EMBEDDING_MODEL)
        self._embedder: SentenceTransformer = SentenceTransformer(EMBEDDING_MODEL, device=device)
        log.info("ChromaMemoryService prêt — %d documents indexés", self._collection.count())

    def _embed(self, text: str) -> list[float]:
        return self._embedder.encode(text, normalize_embeddings=True).tolist()

    def recall(
        self,
        from_char: str,
        context: str,
        about: str | None = None,
        participants: list[str] | None = None,
    ) -> list[dict]:
        from simphonia.services import character_service

        try:
            char = character_service.get().get_character(from_char)
            slots = int(char.get("memory", {}).get("slots", DEFAULT_MEMORY_SLOTS))
        except CharacterNotFound:
            slots = DEFAULT_MEMORY_SLOTS

        n_results = max(int(slots * self._load_factor), DEFAULT_MEMORY_SLOTS)

        if about:
            where: dict = {"$and": [{"from": from_char}, {"about": about}]}
        elif participants:
            targets = list(participants)
            if from_char not in targets:
                targets.append(from_char)
            where = {"$and": [{"from": from_char}, {"about": {"$in": targets}}]}
        else:
            where = {"from": from_char}

        count = self._collection.count()
        if count == 0:
            return []

        query_embedding = self._embed(context)

        log_chroma.debug("=" * 60)
        log_chroma.debug("RECALL REQUEST")
        log_chroma.debug(
            json.dumps(
                {
                    "from_char": from_char,
                    "context": context,
                    "slots": slots,
                    "load_factor": self._load_factor,
                    "n_results": n_results,
                    "min_distance": self._min_distance,
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
            if distance < self._min_distance:
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
            "%s recall (%d candidats → %d retenus, slots=%d, load_factor=%.1f, min_dist=%.2f)",
            from_char,
            len(results["documents"][0]),
            len(memories),
            slots,
            self._load_factor,
            self._min_distance,
        )
        return memories

    def stats(self) -> dict:
        return {
            "status": "ready",
            "documents": self._collection.count(),
            "embedding_model": EMBEDDING_MODEL,
            "chroma_dir": str(CHROMA_DIR),
        }
