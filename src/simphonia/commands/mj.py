"""Commandes bus `mj` — orchestration MJ (step-by-step humain + futur autorun)."""
from __future__ import annotations

import logging

from simphonia.core import command
from simphonia.services.activity_service import engine
from simphonia.services.activity_service.turning_modes import next_speaker

log = logging.getLogger("simphonia.mj")

MJ_BUS = "mj"


@command(
    bus=MJ_BUS,
    code="next_turn",
    description=(
        "Orchestre un pas de jeu selon le turning_mode de l'instance. "
        "Utilisé par le bouton Next du dashboard MJ humain et par AutonomousMJ "
        "comme raccourci de décision. Non-bloquant côté give_turn (résultat via SSE)."
    ),
)
def next_turn(session_id: str) -> dict:
    """Dispatche la prochaine action selon `turning_mode` :

    - target résolu → `activity/give_turn(session_id, target)`
    - round complet, round < max_rounds → `activity/next_round` puis re-résolution
    - round complet, round >= max_rounds → `activity/end`
    - target irrésolu au tout premier tour (cas `named` sans amorce) → no-op explicite

    Retourne un dict `{action, ...}` documentant l'action prise (utile au front).
    """
    session         = engine._get_session(session_id)
    instance        = session.instance
    turning_mode    = instance.get("turning_mode", "named")
    last_exchange   = session.exchange_history[-1] if session.exchange_history else None

    target = next_speaker(turning_mode, instance, session, last_exchange)

    if target is not None:
        engine.give_turn(session_id, target)
        log.info("[next_turn] session=%s round=%d → give_turn(%s)",
                 session_id, session.round, target)
        return {
            "action":  "give_turn",
            "target":  target,
            "round":   session.round,
        }

    # target is None — distinguer "round pas commencé" vs "round complet"
    if not session.exchange_history:
        log.warning("[next_turn] session=%s turning_mode=%r ne peut résoudre le 1er target",
                    session_id, turning_mode)
        return {
            "action": "no_target",
            "reason": f"turning_mode={turning_mode!r} requires manual give_turn for initial step",
        }

    # Round complet — transition. `engine.next_round` délègue lui-même à `end`
    # si max_rounds est atteint, donc on s'appuie dessus pour la fin de partie.
    result = engine.next_round(session_id)
    if result.get("state") == "ended":
        log.info("[next_turn] session=%s ended (max_rounds atteint)", session_id)
        return {"action": "ended"}

    # Nouveau round — résoudre le starter du nouveau round (last_exchange=None
    # car le round vient de basculer, on ne se réfère pas au round précédent).
    new_round = result.get("round", session.round)
    new_target = next_speaker(turning_mode, instance, session, last_exchange=None)
    if new_target is not None:
        engine.give_turn(session_id, new_target)
        log.info("[next_turn] session=%s round_changed → %d → give_turn(%s)",
                 session_id, new_round, new_target)
        return {
            "action": "round_changed+give_turn",
            "round":  new_round,
            "target": new_target,
        }

    log.info("[next_turn] session=%s round_changed → %d (no auto-target — turning_mode=%r)",
             session_id, new_round, turning_mode)
    return {"action": "round_changed", "round": new_round}
