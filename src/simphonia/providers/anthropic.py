"""Provider Anthropic — Claude API avec prompt caching."""
import json
import logging
import time

import httpx

from simphonia.providers.base import LLMProvider, LLMStats

log = logging.getLogger("simphonia.providers.anthropic")

# Throttle progressif basé sur les output tokens cumulés
# Ralentit les appels à mesure que le budget est consommé
THROTTLE_TIERS = {
    10000: 0,    # 0-10K  → pas de pause
    20000: 10,   # 10K-20K → pause 10s
    30000: 30,   # 20K-30K → pause 30s
}

# Retry sur 429 (rate limit)
MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 30


class AnthropicProvider(LLMProvider):
    """Connecteur API Anthropic avec prompt caching, throttle progressif et retry 429."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str, max_tokens: int = 1024,
                 temperature: float = 0.8, api_key: str = "", **kwargs):
        super().__init__(model, max_tokens, temperature)
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("api_key non fournie pour AnthropicProvider")
        self._total_output_tokens = 0

    def _throttle(self):
        """Applique un délai progressif selon les output tokens cumulés."""
        pause = 0
        for threshold, delay in sorted(THROTTLE_TIERS.items()):
            if self._total_output_tokens < threshold:
                break
            pause = delay

        if pause > 0:
            log.warning("Throttle — %d output tokens cumulés → pause %ds",
                        self._total_output_tokens, pause)
            time.sleep(pause)

    def call(self, system_prompt: str, messages: list,
             identity: str = "", temperature: float = None) -> tuple[str | None, LLMStats]:

        # Throttle avant l'appel
        self._throttle()

        all_messages = list(messages)
        if identity:
            all_messages.append({"role": "user", "content": f"you are {identity}"})

        temp = temperature if temperature is not None else self.temperature

        # System prompt avec cache_control (5min ephemeral)
        system_block = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }
        ]

        payload = {
            "model": self.model,
            "system": system_block,
            "messages": all_messages,
            "max_tokens": self.max_tokens,
            "temperature": temp,
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Boucle retry pour les 429
        for attempt in range(MAX_RETRIES + 1):
            try:
                t0 = time.time()
                response = httpx.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                elapsed = (time.time() - t0) * 1000

                # Rate limit — retry avec délai
                if response.status_code == 429:
                    retry_after = int(response.headers.get("retry-after", DEFAULT_RETRY_DELAY))
                    if attempt < MAX_RETRIES:
                        log.warning("Rate limit 429 — tentative %d/%d → pause %ds",
                                    attempt + 1, MAX_RETRIES, retry_after)
                        time.sleep(retry_after)
                        continue
                    else:
                        log.error("Rate limit 429 — %d tentatives épuisées", MAX_RETRIES)
                        return None, LLMStats()

                # Overloaded — même traitement
                if response.status_code == 529:
                    retry_after = int(response.headers.get("retry-after", DEFAULT_RETRY_DELAY))
                    if attempt < MAX_RETRIES:
                        log.warning("API overloaded 529 — tentative %d/%d → pause %ds",
                                    attempt + 1, MAX_RETRIES, retry_after)
                        time.sleep(retry_after)
                        continue
                    else:
                        log.error("API overloaded 529 — %d tentatives épuisées", MAX_RETRIES)
                        return None, LLMStats()

                data = response.json()

                if "error" in data:
                    error_msg = data["error"].get("message", str(data["error"]))
                    log.error("Anthropic erreur: %s", error_msg)
                    return None, LLMStats()

                if "content" not in data:
                    log.error("Réponse Anthropic inattendue")
                    log.debug("raw: %s", json.dumps(data, ensure_ascii=False, default=str)[:500])
                    return None, LLMStats()

                # Extraire le texte
                reply_text = ""
                for block in data["content"]:
                    if block.get("type") == "text":
                        reply_text += block["text"]

                # Stats avec cache
                usage = data.get("usage", {})
                stats = LLMStats(
                    prompt_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    duration_ms=elapsed,
                    cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                    cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
                )

                # Compteur cumulé pour le throttle
                self._total_output_tokens += stats.output_tokens

                if stats.cache_read_tokens > 0 or stats.cache_write_tokens > 0:
                    log.info("Cache: %d read / %d write",
                             stats.cache_read_tokens, stats.cache_write_tokens)

                return reply_text, stats

            except httpx.TimeoutException:
                log.error("Timeout Anthropic (120s)")
                return None, LLMStats()
            except httpx.ConnectError:
                log.error("API Anthropic injoignable")
                return None, LLMStats()
            except Exception as e:
                log.error("Erreur Anthropic inattendue: %s", e)
                return None, LLMStats()

        return None, LLMStats()

    @property
    def provider_name(self) -> str:
        return "anthropic"
