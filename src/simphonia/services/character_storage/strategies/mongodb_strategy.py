"""MongoCharacterStorage — implémentation MongoDB de CharacterStorageService.

Gère les collections `characters` (upsert) et `knowledge` (CRUD, tri anti-chrono).
Tous les documents retournés sont des dict JSON-safe : _id → str, datetime → ISO-8601.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import MongoClient, ReturnDocument, DESCENDING

from simphonia.services.character_storage import CharacterStorageService

log = logging.getLogger("simphonia.character_storage")


def _serialize(doc: dict) -> dict:
    """Convertit ObjectId → str et datetime → ISO-8601 dans un document MongoDB."""
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


class MongoCharacterStorage(CharacterStorageService):

    def __init__(
        self,
        *,
        database_uri: str,
        database_name: str,
        characters_collection: str = "characters",
        knowledge_collection: str = "knowledge",
    ) -> None:
        self._client: MongoClient = MongoClient(database_uri)
        db = self._client[database_name]
        self._characters = db[characters_collection]
        self._knowledge = db[knowledge_collection]
        self._database_name = database_name

        char_count = self._characters.count_documents({})
        know_count = self._knowledge.count_documents({})
        log.info(
            "MongoCharacterStorage prêt — %s.%s (%d), %s.%s (%d)",
            database_name, characters_collection, char_count,
            database_name, knowledge_collection, know_count,
        )

    # ── characters ────────────────────────────────────────────────

    def list_characters(self, *, filter: dict | None = None) -> list[dict]:
        return [_serialize(doc) for doc in self._characters.find(filter or {})]

    def get_character(self, character_id: str) -> dict | None:
        doc = self._characters.find_one({"_id": character_id})
        return _serialize(doc) if doc else None

    def put_character(self, character: dict) -> dict:
        if not character.get("_id") or not isinstance(character["_id"], str):
            raise ValueError("put_character : `_id` (str) obligatoire")
        self._characters.replace_one(
            {"_id": character["_id"]},
            character,
            upsert=True,
        )
        return _serialize(character)

    def delete_character(self, character_id: str) -> bool:
        return self._characters.delete_one({"_id": character_id}).deleted_count == 1

    # ── knowledge ─────────────────────────────────────────────────

    def list_knowledge(self, *, filter: dict | None = None) -> list[dict]:
        cursor = self._knowledge.find(filter or {}).sort("ts", DESCENDING)
        return [_serialize(doc) for doc in cursor]

    def get_knowledge(self, knowledge_id: str) -> dict | None:
        try:
            oid = ObjectId(knowledge_id)
        except Exception:
            return None
        doc = self._knowledge.find_one({"_id": oid})
        return _serialize(doc) if doc else None

    def push_knowledge(self, entry: dict) -> dict:
        doc = {k: v for k, v in entry.items() if k not in ("_id", "ts")}
        doc["_id"] = ObjectId()
        doc["ts"] = datetime.now(timezone.utc)
        self._knowledge.insert_one(doc)
        return _serialize(doc)

    def update_knowledge(self, knowledge_id: str, patch: dict) -> dict | None:
        try:
            oid = ObjectId(knowledge_id)
        except Exception:
            return None
        safe_patch = {k: v for k, v in patch.items() if k not in ("_id", "ts")}
        doc = self._knowledge.find_one_and_update(
            {"_id": oid},
            {"$set": safe_patch},
            return_document=ReturnDocument.AFTER,
        )
        return _serialize(doc) if doc else None

    def delete_knowledge(self, knowledge_id: str) -> bool:
        try:
            oid = ObjectId(knowledge_id)
        except Exception:
            return False
        return self._knowledge.delete_one({"_id": oid}).deleted_count == 1
