"""MongoShadowStorage — implémentation MongoDB + ChromaDB du shadow_storage.

Spec : `documents/shadow_storage.md`.

Stocke le payload complet en Mongo (sans appliquer `excluded_keys`) et indexe
sémantiquement la concaténation des champs admis dans une collection ChromaDB
dédiée (`subconscient`, séparée du `knowledge` joueur).
"""

import logging
from datetime import datetime, timezone
from typing import Any

import chromadb
from bson import ObjectId
from chromadb.config import Settings
from pymongo import DESCENDING, MongoClient
from sentence_transformers import SentenceTransformer

from simphonia.config import CHROMA_DIR, EMBEDDING_MODEL
from simphonia.services.shadow_storage import ShadowStorageService

log = logging.getLogger("simphonia.shadow_storage")


def _serialize(doc: dict) -> dict:
    """Convertit ObjectId → str et datetime → ISO-8601."""
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = _serialize(v)
        else:
            result[k] = v
    return result


class MongoShadowStorage(ShadowStorageService):

    def __init__(
        self,
        *,
        database_uri: str,
        database_name: str,
        collection: str = "subconscient",
        chroma_collection: str = "subconscient",
        excluded_keys: set[str] | None = None,
    ) -> None:
        self._excluded_keys = set(excluded_keys or ())
        self._database_name = database_name
        self._collection_name = collection
        self._chroma_collection_name = chroma_collection

        # Mongo
        self._client: MongoClient = MongoClient(database_uri)
        self._collection = self._client[database_name][collection]
        mongo_count = self._collection.count_documents({})

        # Chroma
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self._chroma: chromadb.ClientAPI = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._chroma_col: chromadb.Collection = self._chroma.get_or_create_collection(
            name=chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        chroma_count = self._chroma_col.count()

        # Embedder (instance dédiée — mutualisable plus tard avec memory_service)
        log.info("Chargement embedder shadow_storage : %s", EMBEDDING_MODEL)
        self._embedder: SentenceTransformer = SentenceTransformer(EMBEDDING_MODEL)

        log.info(
            "MongoShadowStorage prêt — mongo=%s.%s (%d), chroma=%s (%d)",
            database_name, collection, mongo_count,
            chroma_collection, chroma_count,
        )

    # ── helpers internes ──────────────────────────────────────────

    def _extract_candidates(self, payload: dict) -> dict[str, Any]:
        """Récolte les champs feuilles non exclus, en aplatissant les wrappers
        connus (`public`, `private`).

        - Wrappers `public`/`private` déballés automatiquement (conteneurs)
        - Champs vides ignorés
        - Excluded_keys (denylist) filtre les métadonnées structurelles
        - En cas de collision entre niveaux, la première occurrence gagne
          (priorité private > public > flat)"""
        found: dict[str, Any] = {}
        for source in (
            payload.get("private") or {},
            payload.get("public")  or {},
            payload,
        ):
            if not isinstance(source, dict):
                continue
            for k, v in source.items():
                if k in ("private", "public"):
                    continue
                if k in self._excluded_keys:
                    continue
                if not v:
                    continue
                if k not in found:
                    found[k] = v
        return found

    def _embedding_text(self, candidates: dict[str, Any]) -> str:
        """Concaténation déterministe (ordre alphabétique des clés)."""
        parts = []
        for k in sorted(candidates):
            v = candidates[k]
            if isinstance(v, (dict, list)):
                import json
                v = json.dumps(v, ensure_ascii=False)
            parts.append(f"{k}: {v}")
        return "\n".join(parts)

    def _embed(self, text: str) -> list[float]:
        return self._embedder.encode(text, normalize_embeddings=True).tolist()

    # ── ingestion ─────────────────────────────────────────────────

    def feed(self, message: dict) -> None:
        """Listener bus `messages`. Filtre + push atomique Mongo+Chroma.

        Best-effort : exceptions logguées, n'impactent pas l'appelant."""
        try:
            from_char = message.get("from_char")
            if not from_char:
                return

            payload = message.get("payload") or {}
            candidates = self._extract_candidates(payload)
            if not candidates:
                return

            doc = {
                "from":       from_char,
                "bus_origin": message.get("bus_origin", "unknown"),
                "payload":    payload,
                "ts":         datetime.now(timezone.utc),
            }
            result = self._collection.insert_one(doc)
            entry_id = str(result.inserted_id)

            # Push Chroma (best-effort, indépendant de Mongo)
            try:
                self._chroma_col.add(
                    ids=[entry_id],
                    embeddings=[self._embed(self._embedding_text(candidates))],
                    metadatas=[{
                        "from":       from_char,
                        "bus_origin": doc["bus_origin"],
                        "ts":         doc["ts"].isoformat(),
                    }],
                    documents=[self._embedding_text(candidates)],
                )
            except Exception as exc:
                log.warning(
                    "[feed] push Chroma échoué pour _id=%s : %s",
                    entry_id, exc,
                )

            log.info(
                "[feed] entry %s stored — from=%s bus_origin=%s candidates=%d",
                entry_id, from_char, doc["bus_origin"], len(candidates),
            )

        except Exception as exc:
            log.warning("[feed] erreur globale : %s", exc, exc_info=True)

    # ── lecture / pagination ──────────────────────────────────────

    def list_entries(
        self,
        *,
        filter: dict | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        cursor = (self._collection
                  .find(filter or {})
                  .sort("ts", DESCENDING)
                  .skip(skip)
                  .limit(limit))
        return [_serialize(doc) for doc in cursor]

    def count_entries(self, *, filter: dict | None = None) -> int:
        return self._collection.count_documents(filter or {})

    def get_entry(self, entry_id: str) -> dict | None:
        doc = self._collection.find_one({"_id": ObjectId(entry_id)})
        return _serialize(doc) if doc else None

    # ── mutation ──────────────────────────────────────────────────

    def update_entry(self, entry_id: str, doc: dict) -> dict | None:
        # Préserve l'_id Mongo (interdit en replace_one body)
        clean = {k: v for k, v in doc.items() if k != "_id"}
        result = self._collection.replace_one(
            {"_id": ObjectId(entry_id)},
            clean,
        )
        if result.matched_count == 0:
            return None
        return self.get_entry(entry_id)

    def delete_entry(self, entry_id: str) -> bool:
        deleted = self._collection.delete_one({"_id": ObjectId(entry_id)}).deleted_count == 1
        if deleted:
            try:
                self._chroma_col.delete(ids=[entry_id])
            except Exception as exc:
                log.warning("[delete] suppression Chroma échouée pour %s : %s", entry_id, exc)
        return deleted

    # ── maintenance ───────────────────────────────────────────────

    def resync_chroma(self) -> int:
        """Reconstruit l'index ChromaDB depuis Mongo en repartant de zéro.

        Drop + recreate la collection Chroma, puis re-push tout en lot."""
        log.info("[resync] début — drop collection chroma %r", self._chroma_collection_name)
        self._chroma.delete_collection(self._chroma_collection_name)
        self._chroma_col = self._chroma.get_or_create_collection(
            name=self._chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict] = []
        documents: list[str] = []

        BATCH = 100
        indexed = 0
        for doc in self._collection.find({}):
            payload = doc.get("payload") or {}
            candidates = self._extract_candidates(payload)
            if not candidates:
                continue

            text = self._embedding_text(candidates)
            ids.append(str(doc["_id"]))
            embeddings.append(self._embed(text))
            ts = doc.get("ts")
            metadatas.append({
                "from":       doc.get("from", ""),
                "bus_origin": doc.get("bus_origin", "unknown"),
                "ts":         ts.isoformat() if isinstance(ts, datetime) else str(ts),
            })
            documents.append(text)

            if len(ids) >= BATCH:
                self._chroma_col.add(
                    ids=ids, embeddings=embeddings,
                    metadatas=metadatas, documents=documents,
                )
                indexed += len(ids)
                ids, embeddings, metadatas, documents = [], [], [], []

        if ids:
            self._chroma_col.add(
                ids=ids, embeddings=embeddings,
                metadatas=metadatas, documents=documents,
            )
            indexed += len(ids)

        log.info("[resync] terminé — %d entrées indexées", indexed)
        return indexed
