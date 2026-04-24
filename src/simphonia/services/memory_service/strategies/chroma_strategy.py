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

    def __init__(
        self,
        load_factor: float = 1.0,
        min_distance: float = 1.0,
        dedup_threshold: float = 0.2,
        force_cpu: bool = False,
    ) -> None:
        self._load_factor     = load_factor
        self._min_distance    = min_distance
        self._dedup_threshold = dedup_threshold
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

        log_chroma.info("=" * 60)
        log_chroma.info("RECALL REQUEST")
        log_chroma.info(
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

        log_chroma.info("RECALL RESPONSE")
        log_chroma.info(
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
            if distance > self._min_distance:
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

        log.info(
            "%s recall (%d candidats → %d retenus, slots=%d, load_factor=%.1f, min_dist=%.2f)",
            from_char,
            len(results["documents"][0]),
            len(memories),
            slots,
            self._load_factor,
            self._min_distance,
        )
        return memories

    def memorize(
        self,
        from_char: str,
        notes: list[dict],
        activity: str = "",
        scene: str = "",
    ) -> dict:
        """Push live Mongo + Chroma avec dédup sémantique.

        Voir docstring de l'ABC pour le contrat. Aucune exception levée :
        chaque note est traitée indépendamment, les erreurs et skips sont
        reportés dans le `details`.
        """
        from simphonia.services import character_service, character_storage

        added:   int = 0
        skipped: int = 0
        details: list[dict] = []

        char_svc = character_service.get()
        store    = character_storage.get()

        for note in notes or []:
            raw_about = (note.get("about") or "").strip()
            category  = (note.get("category") or "").strip()
            value     = (note.get("value") or "").strip()

            # Aucune validation côté serveur — la commande RPC `memory/memorize`
            # porte les contraintes (JSONSchema mcp_params : `required` + `enum`).
            # Tout passe par elle, donc on fait confiance au payload reçu.

            # Résolution about (self / from_char / autre)
            if raw_about.lower() == "self":
                about_slug = from_char
            else:
                about_slug = char_svc.get_identifier(raw_about) or raw_about.lower()

            # Embed (réutilisé pour dédup query + insert)
            embedding = self._embed(value)

            # Dédup sémantique
            if self._collection.count() > 0:
                where = {"$and": [
                    {"from":     from_char},
                    {"about":    about_slug},
                    {"category": category},
                ]}
                try:
                    existing = self._collection.query(
                        query_embeddings=[embedding],
                        where=where,
                        n_results=1,
                        include=["distances"],
                    )
                    distances = existing.get("distances") or [[]]
                    if distances and distances[0]:
                        d = float(distances[0][0])
                        if d < self._dedup_threshold:
                            log.info(
                                "memorize: skip semantic duplicate from=%s about=%s "
                                "category=%s distance=%.3f value=%.60r",
                                from_char, about_slug, category, d, value,
                            )
                            details.append({
                                "about": about_slug, "category": category, "value": value,
                                "status": "skipped", "reason": "semantic_duplicate",
                                "distance": round(d, 4),
                            })
                            skipped += 1
                            continue
                except Exception as exc:
                    log.warning("memorize: dedup query a échoué — insertion forcée : %s", exc)

            # Insert MongoDB (source de vérité — _id et ts auto-injectés)
            try:
                entry_in = {
                    "from":     from_char,
                    "about":    about_slug,
                    "category": category,
                    "value":    value,
                    "activity": activity,
                    "scene":    scene,
                }
                inserted = store.push_knowledge(entry_in)
            except Exception as exc:
                log.warning("memorize: push_knowledge Mongo a échoué : %s", exc)
                details.append({
                    "about": about_slug, "category": category,
                    "status": "error", "reason": f"mongo_push_failed: {exc}",
                })
                continue

            # Insert ChromaDB (réutilise embedding pré-calculé)
            try:
                self._collection.add(
                    ids=[str(inserted.get("_id", ""))],
                    documents=[value],
                    metadatas=[{
                        "from":     from_char,
                        "about":    about_slug,
                        "category": category,
                        "activity": activity,
                        "scene":    scene,
                        "ts":       str(inserted.get("ts", "")),
                    }],
                    embeddings=[embedding],
                )
            except Exception as exc:
                log.warning("memorize: chroma.add a échoué (Mongo OK) : %s", exc)
                details.append({
                    "about": about_slug, "category": category,
                    "status": "partial", "reason": f"chroma_add_failed: {exc}",
                })
                added += 1
                continue

            details.append({
                "about": about_slug, "category": category, "value": value, "status": "added",
            })
            added += 1
            log.info("memorize: from=%s about=%s category=%s value=%.60r",
                     from_char, about_slug, category, value)

        return {"added": added, "skipped": skipped, "details": details}

    def stats(self) -> dict:
        return {
            "status": "ready",
            "documents": self._collection.count(),
            "embedding_model": EMBEDDING_MODEL,
            "chroma_dir": str(CHROMA_DIR),
        }

    def resync(self) -> dict:
        from simphonia.services import character_storage  # import lazy

        entries = character_storage.get().list_knowledge()
        if not entries:
            log.info("resync : aucune entrée knowledge à indexer")
            return {"reindexed": 0}

        log.info("resync : suppression collection '%s'...", COLLECTION_NAME)
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        ids, documents, metadatas = [], [], []
        for entry in entries:
            value = entry.get("value", "")
            if not value:
                continue
            ids.append(str(entry.get("_id", "")))
            documents.append(value)
            metadatas.append({
                "about":    entry.get("about", ""),
                "activity": entry.get("activity", ""),
                "category": entry.get("category", ""),
                "from":     entry.get("from", ""),
                "scene":    entry.get("scene", ""),
                "ts":       str(entry.get("ts", "")),
            })

        BATCH = 100
        for i in range(0, len(ids), BATCH):
            batch_ids  = ids[i:i + BATCH]
            batch_docs = documents[i:i + BATCH]
            batch_meta = metadatas[i:i + BATCH]
            embeddings = [self._embed(d) for d in batch_docs]
            self._collection.add(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta,
                embeddings=embeddings,
            )

        log.info("resync terminé — %d documents indexés", len(ids))
        return {"reindexed": len(ids)}
