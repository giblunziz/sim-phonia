"""Tests unitaires — commande bus `mj/next_turn` (orchestrateur step-by-step)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from simphonia.commands.mj import next_turn


@dataclass
class FakeSession:
    session_id:       str = "sess-test"
    round:            int = 1
    exchange_history: list[dict] = field(default_factory=list)
    instance:         dict = field(default_factory=lambda: {
        "players":      ["alice", "bob", "charlie"],
        "turning_mode": "round_robin",
        "max_rounds":   3,
    })


@pytest.fixture
def patched_engine(monkeypatch):
    """Mock l'engine : capture les appels give_turn / next_round, fournit _get_session.

    Utilisation : `patched_engine.session = FakeSession(...)` avant l'appel,
    puis inspection de `patched_engine.calls` après.
    """
    state = type("EngineMock", (), {})()
    state.session = FakeSession()
    state.calls: list[tuple[str, dict]] = []
    state.next_round_returns = {"round": 2, "state": "running", "event": None}

    def _get_session(session_id):
        return state.session

    def _give_turn(session_id, target, instruction=None):
        state.calls.append(("give_turn", {"session_id": session_id, "target": target}))
        return {"status": "pending", "session_id": session_id, "target": target}

    def _next_round(session_id):
        state.calls.append(("next_round", {"session_id": session_id}))
        # Met à jour la session pour refléter la transition (comme le vrai engine)
        if state.next_round_returns.get("state") != "ended":
            state.session.round = state.next_round_returns["round"]
        return state.next_round_returns

    monkeypatch.setattr("simphonia.commands.mj.engine._get_session", _get_session)
    monkeypatch.setattr("simphonia.commands.mj.engine.give_turn", _give_turn)
    monkeypatch.setattr("simphonia.commands.mj.engine.next_round", _next_round)
    return state


# ---------------------------------------------------------------------------
#  Cas 1 : target résolu → give_turn
# ---------------------------------------------------------------------------

class TestTargetResolved:

    def test_first_step_round_robin(self, patched_engine):
        """Round_robin, history vide → premier player."""
        patched_engine.session.instance["turning_mode"] = "round_robin"
        patched_engine.session.exchange_history = []

        result = next_turn("sess-test")

        assert result["action"] == "give_turn"
        assert result["target"] == "alice"
        assert result["round"]  == 1
        assert ("give_turn", {"session_id": "sess-test", "target": "alice"}) in patched_engine.calls

    def test_continues_round_robin(self, patched_engine):
        """alice a parlé → bob."""
        patched_engine.session.exchange_history = [{"round": 1, "from": "alice"}]

        result = next_turn("sess-test")

        assert result["action"] == "give_turn"
        assert result["target"] == "bob"


# ---------------------------------------------------------------------------
#  Cas 2 : round complet, transition next_round + nouveau give_turn
# ---------------------------------------------------------------------------

class TestRoundChangedWithGiveTurn:

    def test_round_complete_triggers_next_round_then_give_turn(self, patched_engine):
        """3 joueurs ont parlé au round 1 → next_round + give_turn(alice) au round 2."""
        patched_engine.session.exchange_history = [
            {"round": 1, "from": "alice"},
            {"round": 1, "from": "bob"},
            {"round": 1, "from": "charlie"},
        ]
        patched_engine.next_round_returns = {"round": 2, "state": "running"}

        result = next_turn("sess-test")

        assert result["action"] == "round_changed+give_turn"
        assert result["round"]  == 2
        assert result["target"] == "alice"
        # Vérifie l'ordre : next_round d'abord, puis give_turn
        assert patched_engine.calls[0][0] == "next_round"
        assert patched_engine.calls[1][0] == "give_turn"
        assert patched_engine.calls[1][1]["target"] == "alice"


# ---------------------------------------------------------------------------
#  Cas 3 : round complet + max_rounds atteint → ended
# ---------------------------------------------------------------------------

class TestEnded:

    def test_max_rounds_reached_returns_ended(self, patched_engine):
        """next_round retourne state=ended → orchestrateur retourne {action: ended}."""
        patched_engine.session.round = 3
        patched_engine.session.exchange_history = [
            {"round": 3, "from": "alice"},
            {"round": 3, "from": "bob"},
            {"round": 3, "from": "charlie"},
        ]
        patched_engine.next_round_returns = {"state": "ended", "session_id": "sess-test"}

        result = next_turn("sess-test")

        assert result == {"action": "ended"}
        # Aucun give_turn additionnel après le ended
        give_turns = [c for c in patched_engine.calls if c[0] == "give_turn"]
        assert len(give_turns) == 0


# ---------------------------------------------------------------------------
#  Cas 4 : round complet + new round mais turning_mode ne peut pas auto-résoudre
# ---------------------------------------------------------------------------

class TestRoundChangedNoAutoTarget:

    def test_named_after_round_change_no_auto_target(self, patched_engine, monkeypatch):
        """En `named`, pas de last_exchange après next_round → pas de give_turn auto."""
        # Mock character_service pour _named (au cas où)
        monkeypatch.setattr("simphonia.services.character_service.get",
                            lambda: type("S", (), {"get_identifier": lambda self, x: None})())
        patched_engine.session.instance["turning_mode"] = "named"
        patched_engine.session.exchange_history = [
            {"round": 1, "from": "alice", "public": {"to": "all"}},  # to=all → target None
        ]
        patched_engine.next_round_returns = {"round": 2, "state": "running"}

        result = next_turn("sess-test")

        assert result["action"] == "round_changed"
        assert result["round"]  == 2
        # next_round appelé mais pas de give_turn (named ne peut pas désigner après transition)
        assert any(c[0] == "next_round" for c in patched_engine.calls)
        assert not any(c[0] == "give_turn" for c in patched_engine.calls)


# ---------------------------------------------------------------------------
#  Cas 5 : history vide + turning_mode incapable → no_target
# ---------------------------------------------------------------------------

class TestNoTarget:

    def test_named_at_start_returns_no_target(self, patched_engine, monkeypatch):
        """Au tout premier tour en `named`, pas de last_exchange → no_target."""
        monkeypatch.setattr("simphonia.services.character_service.get",
                            lambda: type("S", (), {"get_identifier": lambda self, x: None})())
        patched_engine.session.instance["turning_mode"] = "named"
        patched_engine.session.exchange_history = []

        result = next_turn("sess-test")

        assert result["action"] == "no_target"
        assert "named" in result["reason"]
        # Aucune action engine déclenchée
        assert patched_engine.calls == []
