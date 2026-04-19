"""Stratégies de sélection du prochain speaker pour une activité.

Helpers purs — zéro LLM, zéro I/O bus. Consommés par `mj_service` et par le
dashboard (mode `human_in_loop`) pour pré-résoudre le target avant de
solliciter le MJ.

Limite connue : stateless. Un joueur skippé par le circuit breaker n'est pas
comptabilisé comme ayant parlé (pas d'entrée dans `exchange_history`). À
l'engine ou au MJ service de traiter ce cas — soit en bypassant le tour,
soit en avançant au `next_round`.
"""
from __future__ import annotations

import logging
import random
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simphonia.services.activity_service.engine import SessionState

log = logging.getLogger("simphonia.activity.turning")


class TurningMode(StrEnum):
    STARTER          = "starter"
    NAMED            = "named"
    ROUND_ROBIN      = "round_robin"
    NEXT_REMAINING   = "next_remaining"
    RANDOM_REMAINING = "random_remaining"
    RANDOM           = "random"


# ---------------------------------------------------------------------------
#  Helpers internes
# ---------------------------------------------------------------------------

def _speakers_of_round(session: "SessionState", round_num: int) -> list[str]:
    """Slugs ayant déjà parlé lors du round donné (ordre chronologique)."""
    return [
        ex.get("from")
        for ex in session.exchange_history
        if ex.get("round") == round_num and ex.get("from")
    ]


# ---------------------------------------------------------------------------
#  Stratégies — signature (instance, session, last_exchange) -> str | None
# ---------------------------------------------------------------------------

def _starter(instance: dict, session: "SessionState", last_exchange: dict | None) -> str | None:
    target = instance.get("starter")
    if target:
        return target
    # Starter non défini — fallback sur `next_remaining` (= premier joueur
    # restant du round courant, typiquement `players[0]` au round 1).
    return _next_remaining(instance, session, last_exchange)


def _named(instance: dict, session: "SessionState", last_exchange: dict | None) -> str | None:
    if not last_exchange:
        return None
    public     = last_exchange.get("public") or {}
    target_raw = (public.get("to") or last_exchange.get("to") or "").strip()
    if not target_raw or target_raw == "all":
        return None

    from simphonia.services import character_service
    slug    = character_service.get().get_identifier(target_raw) or target_raw.lower()
    players = instance.get("players") or []
    if slug in players:
        return slug
    log.warning("[named] cible %r ne résout vers aucun joueur (%s)", target_raw, players)
    return None


def _round_robin(instance: dict, session: "SessionState", last_exchange: dict | None) -> str | None:
    players = instance.get("players") or []
    if not players:
        return None
    spoken_count = len(_speakers_of_round(session, session.round))
    if spoken_count >= len(players):
        return None
    return players[spoken_count]


def _next_remaining(instance: dict, session: "SessionState", last_exchange: dict | None) -> str | None:
    players = instance.get("players") or []
    spoken  = set(_speakers_of_round(session, session.round))
    for p in players:
        if p not in spoken:
            return p
    return None


def _random_remaining(instance: dict, session: "SessionState", last_exchange: dict | None) -> str | None:
    players   = instance.get("players") or []
    spoken    = set(_speakers_of_round(session, session.round))
    remaining = [p for p in players if p not in spoken]
    return random.choice(remaining) if remaining else None


def _random(instance: dict, session: "SessionState", last_exchange: dict | None) -> str | None:
    players = instance.get("players") or []
    return random.choice(players) if players else None


# ---------------------------------------------------------------------------
#  Dispatch
# ---------------------------------------------------------------------------

_DISPATCH = {
    TurningMode.STARTER:          _starter,
    TurningMode.NAMED:            _named,
    TurningMode.ROUND_ROBIN:      _round_robin,
    TurningMode.NEXT_REMAINING:   _next_remaining,
    TurningMode.RANDOM_REMAINING: _random_remaining,
    TurningMode.RANDOM:           _random,
}


def next_speaker(
    mode: str | TurningMode,
    instance: dict,
    session: "SessionState",
    last_exchange: dict | None = None,
) -> str | None:
    """Résout le prochain speaker selon le `turning_mode`.

    Retourne `None` quand :
    - `players` est vide
    - le round est complet (`round_robin` / `next_remaining` / `random_remaining`)
    - `named` : pas de `to` exploitable dans `last_exchange`

    Note : `starter` ne retourne jamais `None` tant que `players` est non vide
    — si `instance.starter` est absent, fallback automatique sur `next_remaining`.

    Lève `ValueError` si `mode` est inconnu.
    """
    try:
        mode_enum = TurningMode(mode)
    except ValueError:
        raise ValueError(
            f"Unknown turning_mode: {mode!r}. Valid: {[m.value for m in TurningMode]}"
        ) from None
    return _DISPATCH[mode_enum](instance, session, last_exchange)
