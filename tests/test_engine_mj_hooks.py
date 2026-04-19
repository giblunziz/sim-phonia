"""Tests unitaires — hooks MJ dans `activity_service.engine`.

Vérifie que `_notify_mj_turn_complete` et `_notify_mj_session_end` :
  - No-op quand `session.mj_service is None`
  - Appellent la bonne méthode sinon
  - Best-effort : une exception dans le hook est attrapée (ne bloque pas le flux)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from simphonia.services.activity_service.engine import (
    _notify_mj_session_end,
    _notify_mj_turn_complete,
)
from simphonia.services.mj_service import MJService


@dataclass
class FakeSession:
    session_id:       str = "sess-test"
    round:            int = 1
    exchange_history: list[dict] = field(default_factory=list)
    mj_service:       MJService | None = None


class RecordingMJ(MJService):
    """Stratégie de test qui enregistre tous les appels reçus."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def on_turn_complete(self, session, exchange):
        self.calls.append(("on_turn_complete", exchange))

    def on_next_turn(self, session):
        self.calls.append(("on_next_turn", None))
        return None

    def on_session_end(self, session):
        self.calls.append(("on_session_end", None))


class FailingMJ(MJService):
    """Stratégie qui plante à chaque appel — sert à vérifier le best-effort."""

    def on_turn_complete(self, session, exchange):
        raise RuntimeError("boom turn_complete")

    def on_next_turn(self, session):
        raise RuntimeError("boom next_turn")

    def on_session_end(self, session):
        raise RuntimeError("boom session_end")


# ---------------------------------------------------------------------------
#  _notify_mj_turn_complete
# ---------------------------------------------------------------------------

class TestNotifyTurnComplete:

    def test_noop_when_service_is_none(self):
        session = FakeSession(mj_service=None)
        # Ne doit rien lever
        _notify_mj_turn_complete(session, {"from": "alice", "round": 1})

    def test_calls_on_turn_complete(self):
        mj  = RecordingMJ()
        session  = FakeSession(mj_service=mj)
        exchange = {"from": "alice", "round": 1, "public": {"talk": "salut"}}

        _notify_mj_turn_complete(session, exchange)

        assert len(mj.calls) == 1
        assert mj.calls[0][0] == "on_turn_complete"
        assert mj.calls[0][1] == exchange

    def test_swallows_exceptions(self, caplog):
        """Best-effort : une exception est attrapée + loggée, pas propagée."""
        session = FakeSession(mj_service=FailingMJ())
        # Ne doit pas lever
        _notify_mj_turn_complete(session, {"from": "alice"})
        # Un warning est émis
        assert any("on_turn_complete a échoué" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
#  _notify_mj_session_end
# ---------------------------------------------------------------------------

class TestNotifySessionEnd:

    def test_noop_when_service_is_none(self):
        session = FakeSession(mj_service=None)
        _notify_mj_session_end(session)

    def test_calls_on_session_end(self):
        mj      = RecordingMJ()
        session = FakeSession(mj_service=mj)

        _notify_mj_session_end(session)

        assert len(mj.calls) == 1
        assert mj.calls[0][0] == "on_session_end"

    def test_swallows_exceptions(self, caplog):
        session = FakeSession(mj_service=FailingMJ())
        _notify_mj_session_end(session)
        assert any("on_session_end a échoué" in r.message for r in caplog.records)
