"""MongoCharacterService — fiches lues depuis une collection MongoDB `characters`.

Chargement eager au démarrage, cache mémoire indexé par le champ `_id` de
chaque document (les documents MongoDB utilisent des `_id` de type `str` —
mêmes valeurs que les noms de fichier `.json` côté `json_strategy`).

Paramètres de connexion injectés par la factory à partir de la config :

- `database_uri`  — URI de connexion MongoDB
- `database_name` — nom de la base

Collection cible fixée : `characters`.
"""

import logging

from pymongo import MongoClient

from simphonia.core.errors import CharacterNotFound
from simphonia.services.character_service import CharacterService

log = logging.getLogger("simphonia.character")

CHARACTERS_COLLECTION = "characters"


class MongoCharacterService(CharacterService):
    """Stratégie MongoDB — charge toutes les fiches de `<db>.characters` au startup."""

    def __init__(self, database_uri: str, database_name: str) -> None:
        self._client: MongoClient = MongoClient(database_uri)
        self._database_name: str = database_name
        self._collection = self._client[database_name][CHARACTERS_COLLECTION]
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        for doc in self._collection.find():
            _id = doc.get("_id")
            if not isinstance(_id, str) or not _id:
                log.warning(
                    "Fiche MongoDB sans `_id` string valide (ignorée) : %r",
                    _id,
                )
                continue

            if _id in self._cache:
                log.warning("Doublon d'`_id` %r — document ignoré", _id)
                continue

            self._cache[_id] = doc

        log.info(
            "MongoCharacterService prêt — %d fiche(s) chargée(s) depuis %s.%s",
            len(self._cache),
            self._database_name,
            CHARACTERS_COLLECTION,
        )

    def get_character_list(self) -> list[str]:
        return sorted(self._cache)

    def get_character(self, name: str) -> dict:
        try:
            return self._cache[name]
        except KeyError as exc:
            raise CharacterNotFound(name) from exc

    def reset(self) -> int:
        self._cache.clear()
        self._load()
        return len(self._cache)
