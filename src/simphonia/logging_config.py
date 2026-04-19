"""Chargement de la configuration de logging depuis logging.yaml.

Résout les chemins de fichiers log relatifs vers PROJECT_ROOT/logs/
et crée le dossier logs/ si nécessaire.
"""
import logging.config
from pathlib import Path

import yaml

from simphonia.config import PROJECT_ROOT

_LOGGING_YAML = Path(__file__).parent / "logging.yaml"


def setup_logging(config_path: Path | None = None) -> None:
    path = config_path or _LOGGING_YAML
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    for handler in config.get("handlers", {}).values():
        if "filename" in handler:
            filename = Path(handler["filename"])
            if not filename.is_absolute():
                handler["filename"] = str(PROJECT_ROOT / filename)

    logging.config.dictConfig(config)
