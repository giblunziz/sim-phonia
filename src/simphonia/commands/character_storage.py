"""Commandes bus `character_storage` — administration MongoDB.

Expose les opérations CRUD sur les collections `characters` et `knowledge`.
Aucune façade MCP : ces commandes sont réservées à l'administration (simweb / CLI).
"""

from simphonia.core import command
from simphonia.services import character_storage

CHARACTER_STORAGE_BUS = "character_storage"


# ── characters ────────────────────────────────────────────────────────────────

@command(bus=CHARACTER_STORAGE_BUS, code="characters.list",
         description="Liste toutes les fiches personnages (dict bruts)")
def characters_list(filter: dict | None = None) -> list[dict]:
    return character_storage.get().list_characters(filter=filter)


@command(bus=CHARACTER_STORAGE_BUS, code="characters.get",
         description="Retourne la fiche d'un personnage par son _id")
def characters_get(character_id: str) -> dict | None:
    return character_storage.get().get_character(character_id)


@command(bus=CHARACTER_STORAGE_BUS, code="characters.put",
         description="Upsert d'une fiche personnage (champ _id obligatoire)")
def characters_put(character: dict) -> dict:
    return character_storage.get().put_character(character)


@command(bus=CHARACTER_STORAGE_BUS, code="characters.delete",
         description="Supprime une fiche personnage par son _id")
def characters_delete(character_id: str) -> bool:
    return character_storage.get().delete_character(character_id)


# ── knowledge ─────────────────────────────────────────────────────────────────

@command(bus=CHARACTER_STORAGE_BUS, code="knowledge.list",
         description="Liste toutes les entrées knowledge (tri anti-chronologique)")
def knowledge_list(filter: dict | None = None) -> list[dict]:
    return character_storage.get().list_knowledge(filter=filter)


@command(bus=CHARACTER_STORAGE_BUS, code="knowledge.get",
         description="Retourne une entrée knowledge par son _id")
def knowledge_get(knowledge_id: str) -> dict | None:
    return character_storage.get().get_knowledge(knowledge_id)


@command(bus=CHARACTER_STORAGE_BUS, code="knowledge.push",
         description="Insère une nouvelle entrée knowledge (append — _id et ts injectés)")
def knowledge_push(entry: dict) -> dict:
    return character_storage.get().push_knowledge(entry)


@command(bus=CHARACTER_STORAGE_BUS, code="knowledge.update",
         description="Mise à jour partielle d'une entrée knowledge par son _id")
def knowledge_update(knowledge_id: str, patch: dict) -> dict | None:
    return character_storage.get().update_knowledge(knowledge_id, patch)


@command(bus=CHARACTER_STORAGE_BUS, code="knowledge.delete",
         description="Supprime une entrée knowledge par son _id")
def knowledge_delete(knowledge_id: str) -> bool:
    return character_storage.get().delete_knowledge(knowledge_id)
