"""Commandes bus `shadow_storage` — admin/UI uniquement, aucun MCP exposé.

Spec : `documents/shadow_storage.md`.
"""
from simphonia.core import command
from simphonia.services import shadow_storage


SHADOW_BUS = "shadow_storage"


@command(
    bus=SHADOW_BUS,
    code="entries.list",
    description=(
        "Liste paginée des entrées du subconscient. "
        "Retourne `{entries: list[dict], total: int}`."
    ),
)
def entries_list_command(
    filter: dict | None = None,
    skip: int = 0,
    limit: int = 50,
) -> dict:
    svc = shadow_storage.get()
    return {
        "entries": svc.list_entries(filter=filter, skip=skip, limit=limit),
        "total":   svc.count_entries(filter=filter),
    }


@command(
    bus=SHADOW_BUS,
    code="entries.get",
    description="Récupère une entrée par _id (str). Retourne None si absente.",
)
def entries_get_command(entry_id: str) -> dict | None:
    return shadow_storage.get().get_entry(entry_id)


@command(
    bus=SHADOW_BUS,
    code="entries.update",
    description=(
        "Update intégral d'une entrée. Le _id présent dans `doc` est ignoré. "
        "Retourne le doc mis à jour, None si absent. "
        "Resync Chroma à faire séparément via `chroma.resync`."
    ),
)
def entries_update_command(entry_id: str, doc: dict) -> dict | None:
    return shadow_storage.get().update_entry(entry_id, doc)


@command(
    bus=SHADOW_BUS,
    code="entries.delete",
    description="Supprime une entrée Mongo + Chroma. Retourne True si supprimée.",
)
def entries_delete_command(entry_id: str) -> bool:
    return shadow_storage.get().delete_entry(entry_id)


@command(
    bus=SHADOW_BUS,
    code="chroma.resync",
    description="Reconstruit l'index ChromaDB du subconscient depuis Mongo. Retourne le count indexé.",
)
def chroma_resync_command() -> int:
    return shadow_storage.get().resync_chroma()
