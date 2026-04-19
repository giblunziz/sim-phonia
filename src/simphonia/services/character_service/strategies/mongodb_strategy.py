"""MongoCharacterService — stratégie character_service s'appuyant sur character_storage.

Délègue la lecture MongoDB à `character_storage.get()`.
Maintient un cache mémoire local pour la résolution fuzzy (`_resolve_identifier`).
"""

import logging

from simphonia.core.errors import CharacterNotFound
from simphonia.services.character_service import CharacterService, _resolve_identifier

log = logging.getLogger("simphonia.character")


class MongoCharacterService(CharacterService):
    """Stratégie MongoDB — lit les fiches via character_storage, cache en mémoire."""

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        from simphonia.services import character_storage  # import lazy (évite cycle)

        self._cache.clear()
        for doc in character_storage.get().list_characters():
            _id = doc.get("_id")
            if not isinstance(_id, str) or not _id:
                log.warning("Fiche sans `_id` string valide (ignorée) : %r", _id)
                continue
            if _id in self._cache:
                log.warning("Doublon d'`_id` %r — document ignoré", _id)
                continue
            self._cache[_id] = doc

        log.info("MongoCharacterService prêt — %d fiche(s) chargée(s)", len(self._cache))

    def get_character_list(self) -> list[str]:
        return sorted(self._cache)

    def get_character(self, name: str) -> dict:
        try:
            return self._cache[name]
        except KeyError as exc:
            raise CharacterNotFound(name) from exc

    def get_identifier(self, name: str) -> str | None:
        return _resolve_identifier(name, self._cache)

    def reset(self) -> int:
        self._load()
        return len(self._cache)
