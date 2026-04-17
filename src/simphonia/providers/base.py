"""Interface commune pour les providers LLM."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMStats:
    """Statistiques d'un appel LLM."""
    prompt_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMProvider(ABC):
    """Interface abstraite pour un provider LLM (Ollama, Anthropic, etc.)."""

    def __init__(self, model: str, max_tokens: int = 1024,
                 temperature: float = 0.8, **kwargs):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    def call(self, system_prompt: str, messages: list,
             identity: str = "", temperature: float = None) -> tuple[str | None, LLMStats]:
        """
        Appelle le LLM et retourne (réponse_texte, stats).

        Args:
            system_prompt: le system prompt (fiche + règles)
            messages: l'historique [{role, content}, ...]
            identity: rappel d'identité ("you are Théo")
            temperature: override de la température (optionnel)

        Returns:
            (reply_text, LLMStats) ou (None, LLMStats) en cas d'erreur
        """
        pass

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__.lower().replace("provider", "")
