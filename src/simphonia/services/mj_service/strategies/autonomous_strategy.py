"""AutonomousMJ — MJ piloté par un LLM via boucle tool-use.

Port du Beholder legacy dans l'architecture bus + MCP sim-phonia. Le LLM MJ
utilise les tools `mcp_role="mj"` (`activity/give_turn`, `activity/next_round`,
`activity/end`) via la boucle tool-use native des providers.

Pas de boucle continue interne : le MJ est **réveillé à chaque événement** —
`on_session_start` (briefing initial → choisit le starter), puis
`on_turn_complete` après chaque réponse joueur.

Contrainte structurelle : `activity/give_turn` est non-bloquant, donc un réveil
= typiquement un `give_turn` par tour LLM. Le MJ peut en revanche chaîner des
tools synchrones (`next_round` + `give_turn` du nouveau starter).

Safety guard : `max_iterations = max_rounds * 10` — coupe la boucle si le MJ
s'emballe ou si un bug fait diverger le state.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from simphonia.core import default_registry
from simphonia.core.mcp import list_mcp_commands, mcp_tool_definitions
from simphonia.services.activity_service.context_builder import format_exchange
from simphonia.services.activity_service.turning_modes import next_speaker
from simphonia.services.mj_service import MJService

if TYPE_CHECKING:
    from simphonia.services.activity_service.engine import SessionState

log = logging.getLogger("simphonia.mj.autonomous")


def _make_mj_tool_executor():
    """Executor générique pour les tools MJ : dispatch via bus.

    Trouve la commande par `name` parmi les `mcp_role="mj"`, dispatch avec les
    args fournis. Résultat sérialisé en JSON pour réinjection dans le contexte LLM.
    """
    mj_commands = list_mcp_commands(role="mj")

    def execute(name: str, args: dict) -> str:
        cmd = next((c for c in mj_commands if c.code == name), None)
        if cmd is None:
            log.warning("[mj_executor] tool inconnu : %s", name)
            return f"Outil MJ inconnu : {name}"
        try:
            result = default_registry().get(cmd.bus_name).dispatch(cmd.code, args)
        except Exception as exc:
            log.warning("[mj_executor] %s/%s a échoué : %s", cmd.bus_name, cmd.code, exc)
            return f"Erreur : {exc}"
        log.info("[mj_executor] %s/%s → %.120s", cmd.bus_name, cmd.code, str(result))
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False, default=str)
        return str(result) if result is not None else "ok"

    return execute


def _publish_sse(session_id: str, event: dict) -> None:
    try:
        from simphonia.http import sse
        sse.publish(session_id, event)
    except Exception as exc:
        log.debug("[autonomous] sse publish échoué : %s", exc)


class AutonomousMJ(MJService):

    def __init__(self) -> None:
        self._mj_history:    list[dict] = []
        self._iterations:    int = 0
        self._max_iterations: int = 0  # résolu à session_start

    # ------------------------------------------------------------------
    #  Hooks MJService
    # ------------------------------------------------------------------

    def on_session_start(self, session: "SessionState") -> None:
        max_rounds = int(session.instance.get("max_rounds", 0) or 0)
        self._max_iterations = max(max_rounds * 10, 30)
        self._iterations = 0
        self._mj_history = []

        briefing = self._build_briefing(session)
        self._mj_history.append({"role": "user", "content": briefing})

        log.info("[autonomous] session_start session=%s max_iter=%d",
                 session.session_id, self._max_iterations)
        self._wake_mj(session)

    def on_turn_complete(self, session: "SessionState", exchange: dict) -> None:
        # Formate l'exchange pour que le LLM MJ sache ce qui vient d'être dit
        speaker = exchange.get("from", "?")
        raw     = exchange.get("raw_response") or json.dumps(exchange.get("public", {}), ensure_ascii=False)
        formatted = format_exchange(speaker, raw)
        self._mj_history.append({"role": "user", "content": formatted})

        # Pré-résolution du prochain speaker si le mode ne passe pas par
        # `named` — évite de laisser le MJ décider à la place du turning_mode.
        turning_mode = session.instance.get("turning_mode", "named")
        if turning_mode != "named":
            target = next_speaker(turning_mode, session.instance, session, exchange)
            if target:
                self._mj_history.append({
                    "role":    "user",
                    "content": f"Le prochain speaker désigné par turning_mode={turning_mode} est : {target}. Compose son instruction.",
                })

        self._wake_mj(session)

    def on_next_turn(self, session: "SessionState") -> str | None:
        # En mode autonome, la progression passe par les réveils sur événement,
        # pas par un appel externe à on_next_turn.
        return None

    def on_session_end(self, session: "SessionState") -> None:
        log.info("[autonomous] session_end session=%s iterations=%d/%d history_len=%d",
                 session.session_id, self._iterations, self._max_iterations,
                 len(self._mj_history))
        self._mj_history = []

    # ------------------------------------------------------------------
    #  Helpers internes
    # ------------------------------------------------------------------

    @staticmethod
    def _build_briefing(session: "SessionState") -> str:
        """Construit le message de briefing initial pour le LLM MJ."""
        activity = session.activity
        scene    = session.scene
        instance = session.instance

        parts: list[str] = ["## Briefing"]
        amorce = instance.get("amorce")
        if amorce:
            parts.append(f"### Amorce narrative\n{amorce}")
        scene_content = scene.get("content") if isinstance(scene, dict) else None
        if scene_content:
            parts.append(f"### Scène\n{scene_content}")
        players = instance.get("players") or []
        parts.append("### Participants\n" + "\n".join(f"- {p}" for p in players))
        starter = instance.get("starter")
        if starter:
            parts.append(f"### Starter désigné\n{starter}")
        max_rounds = instance.get("max_rounds")
        if max_rounds:
            parts.append(f"### Tours max\n{max_rounds}")
        turning_mode = instance.get("turning_mode", "named")
        parts.append(f"### Mode de rotation\n{turning_mode}")
        parts.append(f"### Session ID (à réutiliser dans tes tool_calls)\n{session.session_id}")
        parts.append(
            "Tu es le MJ. Analyse la scène, choisis le starter et compose son instruction "
            "pour lancer l'activité via `give_turn`. Tu ne parles jamais aux joueurs directement "
            "— tout passe par tes tool_calls."
        )
        return "\n\n".join(parts)

    def _wake_mj(self, session: "SessionState") -> None:
        """Un tour de réveil du LLM MJ — lance provider.call avec les tools MJ."""
        if self._iterations >= self._max_iterations:
            log.warning("[autonomous] safety guard atteint (%d), MJ stoppé sur session=%s",
                        self._max_iterations, session.session_id)
            return
        self._iterations += 1

        from simphonia.services import provider_registry
        providers     = session.instance.get("providers") or {}
        provider_name = (
            providers.get("mj") if isinstance(providers, dict) else None
        ) or session.provider_name
        try:
            provider = provider_registry.get(provider_name)
        except Exception as exc:
            log.error("[autonomous] provider %r introuvable : %s", provider_name, exc)
            return

        rules         = session.activity.get("rules") or {}
        system_prompt = rules.get("mj") if isinstance(rules, dict) else ""
        if not system_prompt:
            log.warning("[autonomous] activity.rules.mj vide — LLM MJ sans instructions")
            system_prompt = "Tu es le MJ. Orchestre l'activité via les tools disponibles."

        tools    = mcp_tool_definitions(role="mj")
        executor = _wrap_executor_with_sse(_make_mj_tool_executor(), session.session_id)

        log.info("[autonomous] wake iter=%d/%d session=%s",
                 self._iterations, self._max_iterations, session.session_id)

        try:
            reply, _stats = provider.call(
                system_prompt,
                list(self._mj_history),
                tools=tools,
                tool_executor=executor,
            )
        except Exception as exc:
            log.error("[autonomous] provider.call a échoué : %s", exc, exc_info=True)
            return

        if reply:
            self._mj_history.append({"role": "assistant", "content": reply})
            log.info("[autonomous] MJ reply=%.200s", reply)
            _publish_sse(session.session_id, {
                "type":       "mj.thinking",
                "session_id": session.session_id,
                "text":       reply,
            })


def _wrap_executor_with_sse(executor, session_id: str):
    """Enrobe le tool_executor pour publier SSE `mj.decision` à chaque tool_call."""
    def execute(name: str, args: dict[str, Any]) -> str:
        _publish_sse(session_id, {
            "type":       "mj.decision",
            "session_id": session_id,
            "tool_name":  name,
            "args":       args,
        })
        return executor(name, args)
    return execute
