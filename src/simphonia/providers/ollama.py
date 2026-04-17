"""Provider Ollama — modèles locaux."""
import json
import logging
import time

import httpx

from simphonia.providers.base import LLMProvider, LLMStats

log = logging.getLogger("simphonia.providers.ollama")


class OllamaProvider(LLMProvider):
    """Connecteur Ollama pour modèles locaux."""

    def __init__(self, model: str, url: str = "http://localhost:11434/api/chat",
                 max_tokens: int = 1024, temperature: float = 0.8,
                 keep_alive: str = "-1", **kwargs):
        super().__init__(model, max_tokens, temperature)
        self.url = url
        self.keep_alive = keep_alive

    def call(self, system_prompt: str, messages: list,
             identity: str = "", temperature: float = None) -> tuple[str | None, LLMStats]:

        all_messages = [{"role": "system", "content": system_prompt}]
        all_messages.extend(messages)
        if identity:
            all_messages.append({"role": "user", "content": f"you are {identity}"})

        temp = temperature if temperature is not None else self.temperature

        try:
            t0 = time.time()
            response = httpx.post(self.url, json={
                "model": self.model,
                "messages": all_messages,
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": {
                    "num_predict": self.max_tokens,
                    "temperature": temp
                }
            }, timeout=300)

            data = response.json()

            if "error" in data:
                log.warning("Ollama erreur: %s", data["error"])
                return None, LLMStats()

            if "message" not in data:
                log.warning("Réponse Ollama inattendue")
                log.debug("raw: %s", json.dumps(data, ensure_ascii=False, default=str)[:500])
                return None, LLMStats()

            content = data["message"]["content"]
            # Gemma4: si le content est vide, le modèle a peut-être tout mis dans le thinking
            if not content or not content.strip():
                raw = json.dumps(data["message"], ensure_ascii=False, default=str)
                log.warning("Ollama content vide pour %s", identity)
                log.debug("message raw: %s", raw[:500])

            stats = LLMStats(
                prompt_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                duration_ms=data.get("total_duration", 0) / 1_000_000,
            )
            return content, stats

        except httpx.TimeoutException:
            log.error("Timeout Ollama (300s)")
            return None, LLMStats()
        except httpx.ConnectError:
            log.error("Ollama injoignable — le service tourne ?")
            return None, LLMStats()
        except Exception as e:
            log.error("Erreur Ollama inattendue: %s", e)
            return None, LLMStats()

    @property
    def provider_name(self) -> str:
        return "ollama"
