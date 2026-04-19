"""Provider Ollama — modèles locaux avec tool use."""
import json
import logging
import time

import httpx

from simphonia.providers.base import LLMProvider, LLMStats, ToolExecutor

log = logging.getLogger("simphonia.providers.ollama")

MAX_TOOL_ITERATIONS = 5


class OllamaProvider(LLMProvider):
    """Connecteur Ollama pour modèles locaux avec support tool use."""

    def __init__(self, model: str, url: str = "http://localhost:11434/api/chat",
                 max_tokens: int = 1024, temperature: float = 0.8,
                 keep_alive: str = "-1", **kwargs):
        super().__init__(model, max_tokens, temperature)
        self.url = url
        self.keep_alive = keep_alive

    def _http_call(self, payload: dict) -> dict | None:
        """Envoie une requête à Ollama. Retourne le JSON ou None."""
        try:
            t0 = time.time()
            response = httpx.post(self.url, json=payload, timeout=300)
            data = response.json()

            if "error" in data:
                log.warning("Ollama erreur: %s", data["error"])
                return None
            if "message" not in data:
                log.warning("Réponse Ollama inattendue")
                log.info("raw: %s", json.dumps(data, ensure_ascii=False, default=str)[:500])
                return None

            data["_elapsed_ms"] = (time.time() - t0) * 1000
            return data

        except httpx.TimeoutException:
            log.error("Timeout Ollama (300s)")
            return None
        except httpx.ConnectError:
            log.error("Ollama injoignable — le service tourne ?")
            return None
        except Exception as e:
            log.error("Erreur Ollama inattendue: %s", e)
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

        temp = temperature if temperature is not None else self.temperature

        ollama_tools = None
        if tools:
            ollama_tools = [
                {"type": "function", "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                }}
                for t in tools
            ]

        all_messages = [{"role": "system", "content": system_prompt}]
        all_messages.extend(messages)
        if identity:
            all_messages.append({"role": "user", "content": f"you are {identity}"})

        cumulative_stats = LLMStats()

        for _ in range(MAX_TOOL_ITERATIONS):
            payload: dict = {
                "model": self.model,
                "messages": all_messages,
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": {"num_predict": self.max_tokens, "temperature": temp},
            }
            if ollama_tools:
                payload["tools"] = ollama_tools

            data = self._http_call(payload)
            if data is None:
                return None, cumulative_stats

            cumulative_stats.prompt_tokens += data.get("prompt_eval_count", 0)
            cumulative_stats.output_tokens += data.get("eval_count", 0)
            cumulative_stats.duration_ms += data.get("_elapsed_ms", 0)

            message = data["message"]
            tool_calls = message.get("tool_calls") or []

            if tool_calls and tool_executor:
                all_messages.append({
                    "role": "assistant",
                    "content": message.get("content", ""),
                    "tool_calls": tool_calls,
                })
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    log.info("Tool call : %s(%s)", fn.get("name"), fn.get("arguments"))
                    try:
                        result = tool_executor(fn["name"], fn.get("arguments") or {})
                    except Exception as exc:
                        result = f"Erreur lors de l'exécution de {fn.get('name')} : {exc}"
                        log.warning("tool_executor error: %s", exc)
                    all_messages.append({"role": "tool", "content": result})
                continue

            content = message.get("content", "")
            if not content or not content.strip():
                log.warning("Ollama content vide pour %s", identity)
                log.info("message raw: %s", json.dumps(message, ensure_ascii=False, default=str)[:500])

            return content, cumulative_stats

        log.warning("Tool use loop : max iterations (%d) atteint", MAX_TOOL_ITERATIONS)
        return None, cumulative_stats

    @property
    def provider_name(self) -> str:
        return "ollama"
