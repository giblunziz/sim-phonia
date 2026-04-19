"""JsonCharacterService — fiches lues depuis `./resources/characters/*.json`.

Chargement eager au démarrage, cache mémoire indexé par le champ `_id` de
chaque fiche (normalisation "à la MongoDB") — pas par le nom de fichier.
"""

import json
import logging

from simphonia.config import CHARACTERS_DIR
from simphonia.core.errors import CharacterNotFound
from simphonia.services.character_service import CharacterService, _resolve_identifier

log = logging.getLogger("simphonia.character")


class JsonCharacterService(CharacterService):
    """Stratégie par défaut — un fichier JSON par personnage, indexé par `_id`."""

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not CHARACTERS_DIR.is_dir():
            log.warning("Répertoire des personnages introuvable : %s", CHARACTERS_DIR)
            return

        for path in sorted(CHARACTERS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Fiche personnage illisible (%s) : %s", path.name, exc)
                continue

            _id = data.get("_id")
            if not isinstance(_id, str) or not _id:
                log.warning("Fiche personnage sans `_id` valide : %s", path.name)
                continue

            if _id in self._cache:
                log.warning("Doublon d'`_id` %r — fiche ignorée : %s", _id, path.name)
                continue

            self._cache[_id] = data

        log.info(
            "JsonCharacterService prêt — %d fiche(s) chargée(s) depuis %s",
            len(self._cache),
            CHARACTERS_DIR,
        )

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
        self._cache.clear()
        self._load()
        return len(self._cache)
