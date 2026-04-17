"""ConfigurationService — loader + accesseur de la configuration simphonia.

Charge le fichier YAML `simphonia.yaml` au startup, résout les interpolations
d'environnement (`${VAR}` / `$VAR`) puis expose un snapshot immuable via `get()`
et `section()`. Les services consommateurs **ne lisent jamais le fichier
eux-mêmes** — ils passent toujours par ce service.

Localisation du fichier :

- défaut : `src/simphonia/simphonia.yaml` (racine du module)
- override : flag CLI `--configuration <path>` (via `SIMPHONIA_CONFIG_PATH`)

L'interpolation `${VAR}` est faite via `os.path.expandvars` (appliqué
récursivement sur tous les scalaires string de l'arbre). Si une variable
n'existe pas dans l'environnement, elle reste littérale dans la config —
c'est au consommateur de détecter l'absence et de remonter une erreur
explicite au startup.
"""

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from simphonia.config import PROJECT_ROOT

log = logging.getLogger("simphonia.configuration")

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "src" / "simphonia" / "simphonia.yaml"

_config: dict[str, Any] | None = None


def init(path: Path | None = None) -> None:
    """Charge la configuration. Idempotent."""
    global _config
    if _config is not None:
        return

    config_path = path or _resolve_path()
    if not config_path.is_file():
        raise RuntimeError(f"configuration_service: fichier introuvable : {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"configuration_service: la racine de {config_path} doit être un mapping YAML"
        )

    _config = _expand_env(raw)
    log.info("Configuration chargée depuis %s", config_path)


def _resolve_path() -> Path:
    override = os.environ.get("SIMPHONIA_CONFIG_PATH")
    if override:
        return Path(override)
    return DEFAULT_CONFIG_PATH


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


def get(path: str, default: Any = None) -> Any:
    """Lecture par chemin pointé (ex: `services.character_service.strategy`).

    Retourne `default` si le chemin n'existe pas. Les valeurs dict / list
    retournées sont des copies défensives (deepcopy).
    """
    if _config is None:
        raise RuntimeError("configuration_service not initialized — call init() first")

    node: Any = _config
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]

    if isinstance(node, (dict, list)):
        return copy.deepcopy(node)
    return node


def section(path: str) -> dict:
    """Retourne une sous-section dict (copie défensive). `{}` si absente."""
    value = get(path, default={})
    return value if isinstance(value, dict) else {}


def as_dict() -> dict:
    """Snapshot complet de la configuration (copie défensive deepcopy)."""
    if _config is None:
        raise RuntimeError("configuration_service not initialized — call init() first")
    return copy.deepcopy(_config)
