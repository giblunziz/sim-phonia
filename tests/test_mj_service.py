"""Tests unitaires — `mj_service` ABC + factory + HumanMJ."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from simphonia.services.mj_service import MJService, build_mj_service
from simphonia.services.mj_service.strategies.human_strategy import HumanMJ


@dataclass
class FakeSession:
    """Mock minimal SessionState — seul le typage compte pour le test."""
    session_id: str = "sess-test"
    round: int = 1
    exchange_history: list[dict] = field(default_factory=list)
    instance: dict = field(default_factory=lambda: {
        "players":      ["alice", "bob", "charlie"],
        "turning_mode": "round_robin",
        "max_rounds":   3,
    })


# ---------------------------------------------------------------------------
#  Factory
# ---------------------------------------------------------------------------

class TestBuildMjService:

    def test_build_human_returns_humanmj(self):
        svc = build_mj_service("human")
        assert isinstance(svc, HumanMJ)
        assert isinstance(svc, MJService)

    def test_build_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mj_mode"):
            build_mj_service("foo")

    def test_build_planned_modes_raise_for_now(self):
        """Les modes planifiés (human_in_loop, autonomous) ne sont pas encore livrés.

        Ils doivent lever ValueError proprement — si un jour ils sont livrés
        (étapes #5 et #8), ce test devra basculer vers un `isinstance` check.
        """
        with pytest.raises(ValueError):
            build_mj_service("human_in_loop")
        with pytest.raises(ValueError):
            build_mj_service("autonomous")

    def test_error_message_lists_valid_modes(self):
        with pytest.raises(ValueError) as exc_info:
            build_mj_service("nope")
        msg = str(exc_info.value)
        assert "'human'" in msg  # valid v1
        assert "human_in_loop" in msg  # planned
        assert "autonomous" in msg     # planned


# ---------------------------------------------------------------------------
#  HumanMJ — no-op
# ---------------------------------------------------------------------------

class TestHumanMJ:

    def test_on_turn_complete_is_noop(self):
        svc = HumanMJ()
        # Doit ne rien lever, ne rien muter, ne rien retourner (None)
        result = svc.on_turn_complete(FakeSession(), {"from": "alice", "round": 1})
        assert result is None

    def test_on_next_turn_returns_resolved_speaker(self):
        """on_next_turn délègue à `next_speaker(turning_mode, ...)`.

        FakeSession.instance.turning_mode = round_robin, history vide → 'alice'.
        """
        svc = HumanMJ()
        assert svc.on_next_turn(FakeSession()) == "alice"

    def test_on_session_end_is_noop(self):
        svc = HumanMJ()
        result = svc.on_session_end(FakeSession())
        assert result is None

    def test_implements_mjservice_contract(self):
        """Vérifie que HumanMJ implémente bien toutes les abstractmethod."""
        # Si une méthode abstraite manque, l'instanciation lève TypeError
        HumanMJ()


# ---------------------------------------------------------------------------
#  Contrat MJService
# ---------------------------------------------------------------------------

class TestMjServiceContract:

    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            MJService()  # ABC — non instanciable

    def test_subclass_must_implement_all_methods(self):
        class Incomplete(MJService):
            def on_turn_complete(self, session, exchange): pass
            # manque on_next_turn et on_session_end
        with pytest.raises(TypeError):
            Incomplete()
