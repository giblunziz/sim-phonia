"""MongoToolsService — implémentation MongoDB de ToolsService.

Gère :
  - `tasks`            : prompts réutilisables `{_id, prompt, temperature}`
  - `task_collection`  : registre en lecture seule des collections exposables
  - collections référencées par le registre : lecture seule des documents

Les documents sont retournés schemaless (mongo natif → dict), sans filtrage
ni transformation autre que la normalisation `datetime → ISO-8601`.
"""

import logging
from datetime import datetime, timezone

from pymongo import MongoClient

from simphonia.services.tools_service import ToolsService

log = logging.getLogger("simphonia.tools")


def _serialize(doc: dict) -> dict:
    return {
        k: v.isoformat() if isinstance(v, datetime) else v
        for k, v in doc.items()
    }


class MongoToolsService(ToolsService):

    def __init__(
        self,
        *,
        database_uri: str,
        database_name: str,
        tasks_collection: str = "tasks",
        registry_collection: str = "task_collection",
    ) -> None:
        self._client = MongoClient(database_uri)
        self._db = self._client[database_name]
        self._tasks = self._db[tasks_collection]
        self._registry = self._db[registry_collection]
        tasks_count = self._tasks.count_documents({})
        reg_count = self._registry.count_documents({})
        log.info(
            "MongoToolsService prêt — tasks(%d), registry(%d) [%s]",
            tasks_count, reg_count, registry_collection,
        )

    # ── registre + lecture documents ──────────────────────────────

    def list_exposable_collections(self) -> list[str]:
        return [doc["_id"] for doc in self._registry.find({}, {"_id": 1})]

    def _assert_exposable(self, collection_name: str) -> None:
        if not self._registry.count_documents({"_id": collection_name}, limit=1):
            raise ValueError(
                f"Collection {collection_name!r} non exposable — absente du registre task_collection"
            )

    def list_ids(self, collection_name: str) -> list[str]:
        self._assert_exposable(collection_name)
        return [
            doc["_id"]
            for doc in self._db[collection_name].find({}, {"_id": 1}).sort("_id", 1)
        ]

    def get_document(self, collection_name: str, _id: str) -> dict | None:
        self._assert_exposable(collection_name)
        doc = self._db[collection_name].find_one({"_id": _id})
        return _serialize(doc) if doc else None

    # ── tasks ─────────────────────────────────────────────────────

    def list_tasks(self) -> list[dict]:
        return [_serialize(doc) for doc in self._tasks.find({})]

    def get_task(self, slug: str) -> dict | None:
        doc = self._tasks.find_one({"_id": slug})
        return _serialize(doc) if doc else None

    def put_task(self, slug: str, prompt: str, temperature: float) -> dict:
        now = datetime.now(timezone.utc)
        self._tasks.update_one(
            {"_id": slug},
            {
                "$set": {
                    "prompt":      prompt,
                    "temperature": temperature,
                    "ts_updated":  now,
                },
                "$setOnInsert": {"ts_created": now},
            },
            upsert=True,
        )
        return _serialize(self._tasks.find_one({"_id": slug}))

    def delete_task(self, slug: str) -> bool:
        return self._tasks.delete_one({"_id": slug}).deleted_count == 1
