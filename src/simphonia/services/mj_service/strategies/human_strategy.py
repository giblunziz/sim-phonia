"""HumanMJ — stratégie pour le mode MJ humain.

Rôle minimal : la vraie orchestration step-by-step est portée par la commande
bus `mj/next_turn` (voir `commands/mj.py`). Cette stratégie publie en complément
une **preview** SSE `mj.next_ready` après chaque exchange, pour que le dashboard
affiche « Prochain : Bob » à côté du bouton ▶ Next.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from simphonia.services.activity_service.turning_modes import next_speaker
from simphonia.services.mj_service import MJService

if TYPE_CHECKING:
    from simphonia.services.activity_service.engine import SessionState

log = logging.getLogger("simphonia.mj.human")


class HumanMJ(MJService):

    def on_session_start(self, session: "SessionState") -> None:
        log.info("[human] session_start session=%s — dashboard pilote", session.session_id)

    def on_turn_complete(self, session: "SessionState", exchange: dict) -> None:
        log.info("[human] turn_complete session=%s speaker=%s round=%d",
                 session.session_id, exchange.get("from"), exchange.get("round"))
        self._publish_next_ready(session)

    def on_next_turn(self, session: "SessionState") -> str | None:
        """En `human`, l'orchestration est faite par la commande bus `mj/next_turn`.
        Cette méthode reste implémentée pour cohérence (et tests)."""
        instance      = session.instance
        turning_mode  = instance.get("turning_mode", "named")
        last_exchange = session.exchange_history[-1] if session.exchange_history else None
        return next_speaker(turning_mode, instance, session, last_exchange)

    def on_session_end(self, session: "SessionState") -> None:
        log.info("[human] session_end session=%s — nothing to cleanup", session.session_id)

    # ------------------------------------------------------------------
    #  Helpers internes
    # ------------------------------------------------------------------

    @staticmethod
    def _publish_next_ready(session: "SessionState") -> None:
        """Publie SSE `mj.next_ready` avec le candidat résolu via `turning_mode`.

        Best-effort — une exception (ex: SSE indisponible) ne doit pas faire
        échouer le hook `on_turn_complete` ni bloquer le flux du run.
        """
        try:
            from simphonia.http import sse
            instance      = session.instance
            turning_mode  = instance.get("turning_mode", "named")
            last_exchange = session.exchange_history[-1] if session.exchange_history else None
            target        = next_speaker(turning_mode, instance, session, last_exchange)
            sse.publish(session.session_id, {
                "type":           "mj.next_ready",
                "session_id":     session.session_id,
                "target":         target,
                "turning_mode":   turning_mode,
                "round_complete": target is None and bool(session.exchange_history),
            })
            log.info("[human] next_ready preview target=%s turning_mode=%s",
                     target, turning_mode)
        except Exception as exc:
            log.warning("[human] next_ready preview a échoué : %s", exc)
