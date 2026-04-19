"""Provider Anthropic — Claude API avec prompt caching et tool use."""
import json
import logging
import time

import httpx

from simphonia.providers.base import LLMProvider, LLMStats, ToolExecutor

log = logging.getLogger("simphonia.providers.anthropic")

THROTTLE_TIERS = {
    10000: 0,
    20000: 10,
    30000: 30,
}

MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 30
MAX_TOOL_ITERATIONS = 5


class AnthropicProvider(LLMProvider):
    """Connecteur API Anthropic avec prompt caching, throttle progressif et tool use."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str, max_tokens: int = 1024,
                 temperature: float = 0.8, api_key: str = "", **kwargs):
        super().__init__(model, max_tokens, temperature)
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("api_key non fournie pour AnthropicProvider")
        self._total_output_tokens = 0

    def _throttle(self):
        pause = 0
        for threshold, delay in sorted(THROTTLE_TIERS.items()):
            if self._total_output_tokens < threshold:
                break
            pause = delay
        if pause > 0:
            log.warning("Throttle — %d output tokens cumulés → pause %ds",
                        self._total_output_tokens, pause)
            time.sleep(pause)

    def _http_call(self, payload: dict) -> dict | None:
        """Envoie une requête à l'API Anthropic avec retry 429/529. Retourne le JSON ou None."""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        for attempt in range(MAX_RETRIES + 1):
            try:
                t0 = time.time()
                response = httpx.post(self.API_URL, headers=headers, json=payload, timeout=120)
                elapsed = (time.time() - t0) * 1000

                if response.status_code in (429, 529):
                    code = response.status_code
                    retry_after = int(response.headers.get("retry-after", DEFAULT_RETRY_DELAY))
                    if attempt < MAX_RETRIES:
                        log.warning("HTTP %d — tentative %d/%d → pause %ds",
                                    code, attempt + 1, MAX_RETRIES, retry_after)
                        time.sleep(retry_after)
                        continue
                    log.error("HTTP %d — %d tentatives épuisées", code, MAX_RETRIES)
                    return None

                data = response.json()
                if "error" in data:
                    log.error("Anthropic erreur: %s", data["error"].get("message", str(data["error"])))
                    return None
                if "content" not in data:
                    log.error("Réponse Anthropic inattendue")
                    log.info("raw: %s", json.dumps(data, ensure_ascii=False, default=str)[:500])
                    return None

                usage = data.get("usage", {})
                self._total_output_tokens += usage.get("output_tokens", 0)
                data["_elapsed_ms"] = elapsed
                return data

            except httpx.TimeoutException:
                log.error("Timeout Anthropic (120s)")
                return None
            except httpx.ConnectError:
                log.error("API Anthropic injoignable")
                return None
            except Exception as e:
                log.error("Erreur Anthropic inattendue: %s", e)
                return None
        return None

    def call(
        self,
        system_prompt: str,
        messages: list,
        identity: str = "",
        temperature: float = None,
        tools: list[dict] | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> tuple[str | None, LLMStats]:

        self._throttle()

        temp = temperature if temperature is not None else self.temperature
        system_block = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

        anthropic_tools = None
        if tools:
            anthropic_tools = [
                {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                for t in tools
            ]

        all_messages = list(messages)
        if identity:
            all_messages.append({"role": "user", "content": f"you are {identity}"})

        cumulative_stats = LLMStats()

        for _ in range(MAX_TOOL_ITERATIONS):
            payload: dict = {
                "model": self.model,
                "system": system_block,
                "messages": all_messages,
                "max_tokens": self.max_tokens,
                "temperature": temp,
            }
            if anthropic_tools:
                payload["tools"] = anthropic_tools

            data = self._http_call(payload)
            if data is None:
                return None, cumulative_stats

            usage = data.get("usage", {})
            cumulative_stats.prompt_tokens += usage.get("input_tokens", 0)
            cumulative_stats.output_tokens += usage.get("output_tokens", 0)
            cumulative_stats.duration_ms += data.get("_elapsed_ms", 0)
            cumulative_stats.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            cumulative_stats.cache_write_tokens += usage.get("cache_creation_input_tokens", 0)

            if cumulative_stats.cache_read_tokens > 0 or cumulative_stats.cache_write_tokens > 0:
                log.info("Cache: %d read / %d write",
                         cumulative_stats.cache_read_tokens, cumulative_stats.cache_write_tokens)

            content_blocks = data.get("content", [])
            tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]

            if tool_use_blocks and tool_executor:
                all_messages.append({"role": "assistant", "content": content_blocks})
                tool_results = []
                for block in tool_use_blocks:
                    log.info("Tool call : %s(%s)", block["name"], block["input"])
                    try:
                        result = tool_executor(block["name"], block["input"])
                    except Exception as exc:
                        result = f"Erreur lors de l'exécution de {block['name']} : {exc}"
                        log.warning("tool_executor error: %s", exc)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result,
                    })
                all_messages.append({"role": "user", "content": tool_results})
                continue

            reply_text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
            return reply_text, cumulative_stats

        log.warning("Tool use loop : max iterations (%d) atteint", MAX_TOOL_ITERATIONS)
        return None, cumulative_stats

    @property
    def provider_name(self) -> str:
        return "anthropic"
