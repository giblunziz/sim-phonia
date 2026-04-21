"""Tests unitaires — `AutonomousMJ` (port Beholder).

Provider mocké pour ne pas appeler de vrai LLM. On vérifie :
  - on_session_start initialise mj_history avec un briefing + déclenche le 1er wake
  - on_turn_complete injecte l'exchange formatté + pré-résolution turning_mode
  - safety guard `max_iterations` coupe la boucle
  - on_session_end vide l'historique
  - tool_executor générique dispatch via le bus et sérialise correctement
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from simphonia.services.mj_service.strategies.autonomous_strategy import (
    AutonomousMJ,
    _make_mj_tool_executor,
)


@dataclass
class FakeSession:
    session_id:       str = "sess-auto"
    round:            int = 1
    exchange_history: list[dict] = field(default_factory=list)
    instance: dict = field(default_factory=lambda: {
        "players":      ["alice", "bob"],
        "turning_mode": "round_robin",
        "starter":      "alice",
        "max_rounds":   3,
        "amorce":       "Une nuit calme.",
        "providers":    {"mj": "mock_provider", "players": "mock_provider"},
    })
    activity: dict = field(default_factory=lambda: {
        "rules": {"mj": "Tu es le MJ. Orchestre."},
    })
    scene: dict = field(default_factory=lambda: {"content": "Sur le pont."})
    provider_name: str = "mock_provider"


class MockProvider:
    """Provider qui retourne un reply prédéfini, ignore les tools."""

    def __init__(self, reply: str = "OK je vais lancer.") -> None:
        self.reply  = reply
        self.calls: list[tuple] = []

    def call(self, system_prompt, messages, tools=None, tool_executor=None, **kwargs):
        self.calls.append((system_prompt[:50], len(messages), len(tools or [])))
        # Pas de stats utilisée dans ces tests
        return self.reply, type("S", (), {})()


@pytest.fixture
def fake_provider_registry(monkeypatch):
    provider = MockProvider()

    class FakeRegistry:
        @staticmethod
        def get(name):
            return provider

    monkeypatch.setattr("simphonia.services.provider_registry", FakeRegistry, raising=False)
    # Patche aussi l'import lazy à l'intérieur de _wake_mj
    import simphonia.services
    monkeypatch.setattr(simphonia.services, "provider_registry", FakeRegistry, raising=False)
    return provider


# ---------------------------------------------------------------------------
#  on_session_start
# ---------------------------------------------------------------------------

class TestSessionStart:

    def test_builds_briefing_and_triggers_wake(self, fake_provider_registry):
        svc = AutonomousMJ()
        svc.on_session_start(FakeSession())

        # Briefing présent dans mj_history
        assert len(svc._mj_history) >= 2  # user briefing + assistant reply
        briefing = svc._mj_history[0]
        assert briefing["role"] == "user"
        assert "Briefing" in briefing["content"]
        assert "alice" in briefing["content"]
        assert "Sur le pont" in briefing["content"]
        assert "sess-auto" in briefing["content"]

        # Provider appelé
        assert len(fake_provider_registry.calls) == 1

        # Reply stocké
        assert any(m["role"] == "assistant" for m in svc._mj_history)

    def test_max_iterations_set_from_max_rounds(self, fake_provider_registry):
        svc = AutonomousMJ()
        session = FakeSession()
        session.instance["max_rounds"] = 5
        svc.on_session_start(session)
        assert svc._max_iterations == 50  # 5 * 10

    def test_iterations_floor_30(self, fake_provider_registry):
        """max_rounds=1 → max_iter=10 → forcé à 30 (sécurité minimale)."""
        svc = AutonomousMJ()
        session = FakeSession()
        session.instance["max_rounds"] = 1
        svc.on_session_start(session)
        assert svc._max_iterations == 30


# ---------------------------------------------------------------------------
#  on_turn_complete
# ---------------------------------------------------------------------------

class TestTurnComplete:

    def test_injects_exchange_in_history(self, fake_provider_registry):
        svc = AutonomousMJ()
        svc._mj_history    = []
        svc._iterations    = 0
        svc._max_iterations = 100

        exchange = {
            "from":  "alice",
            "round": 1,
            "raw_response": '{"from":"alice","talk":"Bonjour","to":"bob"}',
        }

        svc.on_turn_complete(FakeSession(), exchange)

        # L'exchange formatté + pré-résolution round_robin (turning_mode != named)
        # + une réponse provider
        contents = [m["content"] for m in svc._mj_history]
        assert any("alice" in c for c in contents)
        # Pré-résolution round_robin → next speaker = bob (alice a parlé au round 1)
        assert any("turning_mode=round_robin" in c for c in contents)
        assert any("bob" in c for c in contents)

    def test_safety_guard_stops_loop(self, fake_provider_registry):
        svc = AutonomousMJ()
        svc._max_iterations = 2
        svc._iterations = 2  # déjà à la limite
        svc._mj_history = []

        svc.on_turn_complete(FakeSession(), {"from": "alice", "round": 1})

        # Provider PAS appelé (safety guard)
        assert fake_provider_registry.calls == []


# ---------------------------------------------------------------------------
#  on_session_end
# ---------------------------------------------------------------------------

class TestSessionEnd:

    def test_clears_history(self, fake_provider_registry):
        svc = AutonomousMJ()
        svc._mj_history = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
        svc.on_session_end(FakeSession())
        assert svc._mj_history == []


# ---------------------------------------------------------------------------
#  on_next_turn
# ---------------------------------------------------------------------------

class TestNextTurn:

    def test_returns_none(self):
        """En autonome, on_next_turn n'est pas le canal d'orchestration."""
        svc = AutonomousMJ()
        assert svc.on_next_turn(FakeSession()) is None


# ---------------------------------------------------------------------------
#  Tool executor générique
# ---------------------------------------------------------------------------

class TestMjToolExecutor:

    def test_dispatches_via_bus_and_serializes(self, monkeypatch):
        """Le tool_executor trouve la commande MJ par name et la dispatch."""
        from simphonia.core.command import Command
        from simphonia.core.registry import BusRegistry

        # Mock command MJ qui retourne un dict
        called = {}

        def fake_callback(session_id, target):
            called["args"] = (session_id, target)
            return {"action": "give_turn", "target": target}

        reg = BusRegistry()
        reg.get_or_create("activity").register(Command(
            code="give_turn", description="d", callback=fake_callback,
            bus_name="activity", mcp=True, mcp_role="mj",
            mcp_description="d",
            mcp_params={"type": "object", "properties": {}},
        ))

        # Patch list_mcp_commands ET default_registry pour ce test
        from simphonia.services.mj_service.strategies import autonomous_strategy as mod
        monkeypatch.setattr(mod, "list_mcp_commands", lambda role=None: list(reg.get("activity")._commands.values()))
        monkeypatch.setattr(mod, "default_registry", lambda: reg)

        executor = _make_mj_tool_executor()
        result = executor("give_turn", {"session_id": "s1", "target": "alice"})

        assert called["args"] == ("s1", "alice")
        # Sérialisation JSON
        assert '"action": "give_turn"' in result
        assert '"target": "alice"' in result

    def test_unknown_tool_returns_error(self, monkeypatch):
        from simphonia.services.mj_service.strategies import autonomous_strategy as mod
        monkeypatch.setattr(mod, "list_mcp_commands", lambda role=None: [])
        executor = _make_mj_tool_executor()
        result = executor("unknown", {})
        assert "inconnu" in result
