"""Commandes bus `activity_storage` — référentiel des activités et des schémas."""

from simphonia.core import command
from simphonia.services import activity_storage

ACTIVITY_STORAGE_BUS = "activity_storage"


@command(bus=ACTIVITY_STORAGE_BUS, code="activities.list",
         description="Liste toutes les activités du référentiel")
def activities_list(filter: dict | None = None) -> list[dict]:
    return activity_storage.get().list_activities(filter=filter)


@command(bus=ACTIVITY_STORAGE_BUS, code="activities.get",
         description="Retourne une activité par son slug (_id)")
def activities_get(activity_id: str) -> dict | None:
    return activity_storage.get().get_activity(activity_id)


@command(bus=ACTIVITY_STORAGE_BUS, code="activities.put",
         description="Upsert d'une activité (activity_id = slug, ts auto-gérés)")
def activities_put(activity_id: str, data: dict) -> dict:
    return activity_storage.get().put_activity(activity_id, data)


@command(bus=ACTIVITY_STORAGE_BUS, code="activities.delete",
         description="Supprime une activité par son slug")
def activities_delete(activity_id: str) -> bool:
    return activity_storage.get().delete_activity(activity_id)


# ── schemas ────────────────────────────────────────────────────────────────────

@command(bus=ACTIVITY_STORAGE_BUS, code="schemas.list",
         description="Liste tous les schémas du référentiel")
def schemas_list(filter: dict | None = None) -> list[dict]:
    return activity_storage.get().list_schemas(filter=filter)


@command(bus=ACTIVITY_STORAGE_BUS, code="schemas.get",
         description="Retourne un schéma par son slug (_id)")
def schemas_get(schema_id: str) -> dict | None:
    return activity_storage.get().get_schema(schema_id)


@command(bus=ACTIVITY_STORAGE_BUS, code="schemas.put",
         description="Upsert d'un schéma (schema_id = slug, ts auto-gérés)")
def schemas_put(schema_id: str, data: dict) -> dict:
    return activity_storage.get().put_schema(schema_id, data)


@command(bus=ACTIVITY_STORAGE_BUS, code="schemas.delete",
         description="Supprime un schéma par son slug")
def schemas_delete(schema_id: str) -> bool:
    return activity_storage.get().delete_schema(schema_id)


# ── scenes ─────────────────────────────────────────────────────────────────────

@command(bus=ACTIVITY_STORAGE_BUS, code="scenes.list",
         description="Liste toutes les scènes du référentiel")
def scenes_list(filter: dict | None = None) -> list[dict]:
    return activity_storage.get().list_scenes(filter=filter)


@command(bus=ACTIVITY_STORAGE_BUS, code="scenes.get",
         description="Retourne une scène par son slug (_id)")
def scenes_get(scene_id: str) -> dict | None:
    return activity_storage.get().get_scene(scene_id)


@command(bus=ACTIVITY_STORAGE_BUS, code="scenes.put",
         description="Upsert d'une scène (scene_id = slug, ts auto-gérés)")
def scenes_put(scene_id: str, data: dict) -> dict:
    return activity_storage.get().put_scene(scene_id, data)


@command(bus=ACTIVITY_STORAGE_BUS, code="scenes.delete",
         description="Supprime une scène par son slug")
def scenes_delete(scene_id: str) -> bool:
    return activity_storage.get().delete_scene(scene_id)


# ── activity_instances ─────────────────────────────────────────────────────────

@command(bus=ACTIVITY_STORAGE_BUS, code="instances.list",
         description="Liste toutes les instances d'activité")
def instances_list(filter: dict | None = None) -> list[dict]:
    return activity_storage.get().list_instances(filter=filter)


@command(bus=ACTIVITY_STORAGE_BUS, code="instances.get",
         description="Retourne une instance par son slug (_id)")
def instances_get(instance_id: str) -> dict | None:
    return activity_storage.get().get_instance(instance_id)


@command(bus=ACTIVITY_STORAGE_BUS, code="instances.put",
         description="Upsert d'une instance (instance_id = slug, ts auto-gérés)")
def instances_put(instance_id: str, data: dict) -> dict:
    return activity_storage.get().put_instance(instance_id, data)


@command(bus=ACTIVITY_STORAGE_BUS, code="instances.delete",
         description="Supprime une instance par son slug")
def instances_delete(instance_id: str) -> bool:
    return activity_storage.get().delete_instance(instance_id)
