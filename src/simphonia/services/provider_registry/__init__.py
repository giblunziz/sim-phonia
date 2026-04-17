"""provider_registry — registre des providers LLM.

Lit la section `providers` du YAML (déjà interpolée par `configuration_service`),
instancie chaque provider par dispatch sur `protocol`, et expose un accès nommé
thread-safe en lecture (dictionnaire module-level, rempli une seule fois au boot).

Usage :
    from simphonia.services import provider_registry
    provider_registry.init(configuration_service.section("providers"))
    p = provider_registry.get("gemma4")
    reply, stats = p.call(system_prompt, messages)
"""

import logging
from typing import Any

from simphonia.core.errors import ProviderNotFound
from simphonia.providers.base import LLMProvider

log = logging.getLogger("simphonia.provider_registry")

_instances: dict[str, LLMProvider] = {}


def init(providers_config: dict) -> None:
    """Instancie tous les providers déclarés dans la section `providers:` du YAML.

    Fail-fast si :
    - la section est vide ou absente
    - un protocol est inconnu

    Idempotent : un second appel est ignoré si le registre est déjà peuplé.
    """
    global _instances
    if _instances:
        return

    if not providers_config:
        raise RuntimeError(
            "provider_registry: la section `providers` est absente ou vide dans la configuration"
        )

    built: dict[str, LLMProvider] = {}
    for name, cfg in providers_config.items():
        if not isinstance(cfg, dict):
            raise RuntimeError(
                f"provider_registry: entrée `providers.{name}` invalide (dict attendu)"
            )
        built[name] = _build_provider(name, cfg)
        log.info("Provider %r chargé (%s / %s)", name, cfg.get("protocol"), cfg.get("model"))

    _instances = built
    log.info("provider_registry prêt : %d provider(s) — %s", len(_instances), list(_instances))


def get(name: str) -> LLMProvider:
    """Retourne le provider nommé. Lève `ProviderNotFound` si inconnu."""
    if name not in _instances:
        raise ProviderNotFound(name)
    return _instances[name]


def list_names() -> list[str]:
    """Retourne la liste des noms de providers enregistrés."""
    return list(_instances.keys())


# ---------------------------------------------------------------------------
# Factory interne
# ---------------------------------------------------------------------------

def _build_provider(name: str, cfg: dict[str, Any]) -> LLMProvider:
    """Instancie un provider à partir de sa config brute.

    Dispatch sur `cfg["protocol"]`. Fail-fast si protocol inconnu.
    """
    protocol = cfg.get("protocol")

    if protocol == "ollama":
        from simphonia.providers.ollama import OllamaProvider
        return OllamaProvider(
            model=cfg["model"],
            url=cfg.get("url", "http://localhost:11434/api/chat"),
            max_tokens=int(cfg.get("max_tokens", 1024)),
            temperature=float(cfg.get("temperature", 0.8)),
            keep_alive=str(cfg.get("keep_alive", "-1")),
        )

    if protocol == "anthropic":
        from simphonia.services import configuration_service
        from simphonia.providers.anthropic import AnthropicProvider
        api_key = configuration_service.get(f"providers.{name}.api_key", default="")
        if not isinstance(api_key, str) or not api_key:
            raise RuntimeError(
                f"provider_registry: `providers.{name}.api_key` manquant ou vide "
                f"(vérifier l'interpolation ${{ANTHROPIC_API_KEY}} dans le YAML)"
            )
        return AnthropicProvider(
            model=cfg["model"],
            api_key=api_key,
            max_tokens=int(cfg.get("max_tokens", 1024)),
            temperature=float(cfg.get("temperature", 0.8)),
        )

    raise RuntimeError(
        f"provider_registry: protocol inconnu {protocol!r} pour `providers.{name}` "
        f"(protocols supportés : 'ollama', 'anthropic')"
    )
