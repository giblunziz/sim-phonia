"""CharacterService — accès aux fiches de personnages.

Interface + factory qui instancie la stratégie (`json_strategy`, `mongodb_strategy`, …)
sélectionnée via la configuration YAML (`services.character_service`).

Voir `documents/character_service.md` et `documents/configuration.md`.
"""

import logging
import unicodedata
from abc import ABC, abstractmethod

log = logging.getLogger("simphonia.character")


def _normalize(s: str) -> str:
    """Lowercase + suppression des accents (NFD, catégorie Mn)."""
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _resolve_identifier(name: str, cache: dict) -> str | None:
    """Résout un nom LLM vers un _id canonique du cache.

    Stratégie :
      1. Match exact sur le nom normalisé
      2. Split sur espaces / underscores, match sur chaque token
      3. Match partiel (token contenu dans un _id ou inversement, min 3 chars)
    """
    if not name or not name.strip():
        return None

    normalized_ids = {_normalize(cid): cid for cid in cache}
    norm = _normalize(name)

    # 1. Exact
    if norm in normalized_ids:
        return normalized_ids[norm]

    # 2. Token
    tokens = norm.replace("_", " ").split()
    for token in tokens:
        if token in normalized_ids:
            return normalized_ids[token]

    # 3. Partiel
    for token in tokens:
        if len(token) < 3:
            continue
        for norm_id, canonical in normalized_ids.items():
            if token in norm_id or norm_id in token:
                log.info("get_identifier partiel : '%s' → '%s' (token '%s')", name, canonical, token)
                return canonical

    log.info("get_identifier non résolu : '%s' (tokens: %s)", name, tokens)
    return None


class CharacterService(ABC):
    """Contrat schemaless : les fiches circulent en `dict` brut."""

    @abstractmethod
    def get_character_list(self) -> list[str]:
        """Retourne la liste des identifiants (`_id`) des personnages connus."""

    @abstractmethod
    def get_character(self, name: str) -> dict:
        """Retourne la fiche complète d'un personnage (`dict` brut)."""

    @abstractmethod
    def get_identifier(self, name: str) -> str | None:
        """Retourne le slug canonique (`_id`) correspondant à `name`, ou `None`.

        Résolution : correspondance exacte sur `_id`, puis correspondance
        normalisée (lowercase + sans accents).
        """

    @abstractmethod
    def reset(self) -> int:
        """Recharge toutes les fiches depuis la source de données.

        Retourne le nombre de fiches disponibles après rechargement.
        La sémantique du rechargement dépend de la stratégie active
        (rescan de répertoire pour `json_strategy`, `find()` pour
        `mongodb_strategy`, etc.).
        """


def build_character_service(service_config: dict) -> CharacterService:
    """Instancie la stratégie configurée (`services.character_service` section).

    Import dynamique pour éviter de charger toutes les stratégies
    (et leurs dépendances) à l'import du package.
    """
    strategy = service_config.get("strategy", "json_strategy")

    if strategy == "json_strategy":
        from simphonia.services.character_service.strategies.json_strategy import (
            JsonCharacterService,
        )

        return JsonCharacterService()

    if strategy == "mongodb_strategy":
        from simphonia.services.character_service.strategies.mongodb_strategy import (
            MongoCharacterService,
        )
        return MongoCharacterService()

    raise ValueError(f"Unknown character_service strategy: {strategy!r}")


_instance: CharacterService | None = None


def init(service_config: dict) -> None:
    """Construit l'instance du service selon la config donnée. Idempotent."""
    global _instance
    if _instance is None:
        _instance = build_character_service(service_config)


def get() -> CharacterService:
    """Retourne l'instance du service. `init()` doit avoir été appelé auparavant."""
    if _instance is None:
        raise RuntimeError("character_service not initialized — call init() first")
    return _instance
