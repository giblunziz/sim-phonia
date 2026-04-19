"""MongoActivityStorage — implémentation MongoDB de ActivityStorageService.

Gère les collections `activities`, `schemas` et `scenes`.
ts_created/ts_updated auto-injectés via $setOnInsert/$set.
Tous les documents retournés sont des dict JSON-safe : datetime → ISO-8601.
"""

import logging
from datetime import datetime, timezone

from pymongo import MongoClient

from simphonia.services.activity_storage import ActivityStorageService

log = logging.getLogger("simphonia.activity_storage")


def _serialize(doc: dict) -> dict:
    return {
        k: v.isoformat() if isinstance(v, datetime) else v
        for k, v in doc.items()
    }


class MongoActivityStorage(ActivityStorageService):

    def __init__(
        self,
        *,
        database_uri: str,
        database_name: str,
        activities_collection: str = "activities",
        schemas_collection: str = "schemas",
        scenes_collection: str = "scenes",
        instances_collection: str = "activity_instances",
    ) -> None:
        self._client = MongoClient(database_uri)
        db = self._client[database_name]
        self._activities = db[activities_collection]
        self._schemas = db[schemas_collection]
        self._scenes = db[scenes_collection]
        self._instances = db[instances_collection]
        act_count = self._activities.count_documents({})
        sch_count = self._schemas.count_documents({})
        scn_count = self._scenes.count_documents({})
        ins_count = self._instances.count_documents({})
        log.info(
            "MongoActivityStorage prêt — activities(%d), schemas(%d), scenes(%d), instances(%d)",
            act_count, sch_count, scn_count, ins_count,
        )

    def list_activities(self, *, filter: dict | None = None) -> list[dict]:
        return [_serialize(doc) for doc in self._activities.find(filter or {})]

    def get_activity(self, activity_id: str) -> dict | None:
        doc = self._activities.find_one({"_id": activity_id})
        return _serialize(doc) if doc else None

    def put_activity(self, activity_id: str, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        safe = {k: v for k, v in data.items() if k not in ("_id", "ts_created", "ts_updated")}
        self._activities.update_one(
            {"_id": activity_id},
            {
                "$set": {**safe, "ts_updated": now},
                "$setOnInsert": {"ts_created": now},
            },
            upsert=True,
        )
        return _serialize(self._activities.find_one({"_id": activity_id}))

    def delete_activity(self, activity_id: str) -> bool:
        return self._activities.delete_one({"_id": activity_id}).deleted_count == 1

    # ── schemas ────────────────────────────────────────────────────

    def list_schemas(self, *, filter: dict | None = None) -> list[dict]:
        return [_serialize(doc) for doc in self._schemas.find(filter or {})]

    def get_schema(self, schema_id: str) -> dict | None:
        doc = self._schemas.find_one({"_id": schema_id})
        return _serialize(doc) if doc else None

    def put_schema(self, schema_id: str, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        safe = {k: v for k, v in data.items() if k not in ("_id", "ts_created", "ts_updated")}
        self._schemas.update_one(
            {"_id": schema_id},
            {
                "$set": {**safe, "ts_updated": now},
                "$setOnInsert": {"ts_created": now},
            },
            upsert=True,
        )
        return _serialize(self._schemas.find_one({"_id": schema_id}))

    def delete_schema(self, schema_id: str) -> bool:
        return self._schemas.delete_one({"_id": schema_id}).deleted_count == 1

    # ── scenes ─────────────────────────────────────────────────────

    def list_scenes(self, *, filter: dict | None = None) -> list[dict]:
        return [_serialize(doc) for doc in self._scenes.find(filter or {})]

    def get_scene(self, scene_id: str) -> dict | None:
        doc = self._scenes.find_one({"_id": scene_id})
        return _serialize(doc) if doc else None

    def put_scene(self, scene_id: str, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        safe = {k: v for k, v in data.items() if k not in ("_id", "ts_created", "ts_updated")}
        self._scenes.update_one(
            {"_id": scene_id},
            {
                "$set": {**safe, "ts_updated": now},
                "$setOnInsert": {"ts_created": now},
            },
            upsert=True,
        )
        return _serialize(self._scenes.find_one({"_id": scene_id}))

    def delete_scene(self, scene_id: str) -> bool:
        return self._scenes.delete_one({"_id": scene_id}).deleted_count == 1

    # ── activity_instances ─────────────────────────────────────────

    def list_instances(self, *, filter: dict | None = None) -> list[dict]:
        return [_serialize(doc) for doc in self._instances.find(filter or {})]

    def get_instance(self, instance_id: str) -> dict | None:
        doc = self._instances.find_one({"_id": instance_id})
        return _serialize(doc) if doc else None

    def put_instance(self, instance_id: str, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        safe = {k: v for k, v in data.items() if k not in ("_id", "ts_created", "ts_updated")}
        self._instances.update_one(
            {"_id": instance_id},
            {
                "$set": {**safe, "ts_updated": now},
                "$setOnInsert": {"ts_created": now},
            },
            upsert=True,
        )
        return _serialize(self._instances.find_one({"_id": instance_id}))

    def delete_instance(self, instance_id: str) -> bool:
        return self._instances.delete_one({"_id": instance_id}).deleted_count == 1
