"""ChatService — orchestration des dialogues entre personnages.

Interface + factory qui instancie la stratégie (`default_strategy`, …)
sélectionnée via la configuration YAML (`services.chat_service`).

Voir `documents/simphonia.md` et `documents/configuration.md`.
"""

import logging
from abc import ABC, abstractmethod

from simphonia.providers.base import LLMProvider


class ChatService(ABC):
    """Contrat minimal : démarrer, poursuivre et clore un dialogue."""

    @abstractmethod
    def start(self, from_char: str, to: str, say: str, human: bool = False) -> dict:
        """Démarre une nouvelle session de dialogue.

        Retourne `{"session_id": ..., "from_char": ..., "to": ..., "reply": None}`.
        """

    @abstractmethod
    def reply(self, session_id: str, from_char: str, say: str, human: bool = False) -> dict:
        """Ajoute un tour à une session existante.

        Retourne `{"reply": None}`.
        """

    @abstractmethod
    def stop(self, session_id: str) -> dict:
        """Clôt une session.

        Retourne `{"session_id": ..., "status": "closed"}`.
        """

    @abstractmethod
    def auto_reply(self, session_id: str, speaker: str) -> None:
        """Tour autonome LLM : `speaker` génère sa réplique, l'autre répond.

        Appelé en arrière-plan depuis `chat.said` quand `human=False`.
        Ne retourne rien — les effets passent par le log et le bus.
        """


def _build_chat_logger(log_config: dict) -> logging.Logger:
    return logging.getLogger("simphonia.chat")


def build_chat_service(
    service_config: dict,
    provider: LLMProvider,
    provider_name: str,
    logger: logging.Logger,
) -> ChatService:
    """Instancie la stratégie configurée (`services.chat_service` section).

    Import dynamique pour éviter de charger toutes les stratégies
    (et leurs dépendances) à l'import du package.
    """
    strategy = service_config.get("strategy", "default_strategy")

    if strategy == "default_strategy":
        from simphonia.services.chat_service.strategies.default_strategy import (
            DefaultChatService,
        )

        return DefaultChatService(provider=provider, provider_name=provider_name, logger=logger)

    raise ValueError(f"Unknown chat_service strategy: {strategy!r}")


_instance: ChatService | None = None


def init(service_config: dict) -> None:
    """Construit l'instance du service selon la config donnée. Idempotent."""
    global _instance
    if _instance is not None:
        return

    from simphonia.services import provider_registry

    provider_name = service_config["model"]
    provider = provider_registry.get(provider_name)
    logger = _build_chat_logger(service_config.get("log", {}))
    _instance = build_chat_service(service_config, provider, provider_name, logger)


def get() -> ChatService:
    """Retourne l'instance du service. `init()` doit avoir été appelé auparavant."""
    if _instance is None:
        raise RuntimeError("chat_service not initialized — call init() first")
    return _instance
