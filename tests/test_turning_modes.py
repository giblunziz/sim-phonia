"""Tests unitaires — `activity_service/turning_modes`."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import pytest

from simphonia.services.activity_service.turning_modes import (
    TurningMode,
    next_speaker,
)


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@dataclass
class FakeSession:
    """Mock minimal — reproduit les attributs de SessionState consommés."""
    round: int = 1
    exchange_history: list[dict] = field(default_factory=list)


@pytest.fixture
def players() -> list[str]:
    return ["alice", "bob", "charlie"]


@pytest.fixture
def instance(players) -> dict:
    return {"players": players}


@pytest.fixture
def fake_character_service(monkeypatch):
    """Monkeypatche `character_service.get()` pour isoler les tests de `_named`.

    Retourne un fuzzy-match basique : `lower().strip()` avec correspondance
    canonique sur un dict connu (aucune dépendance au vrai service).
    """
    class FakeSvc:
        def __init__(self, mapping: dict[str, str] | None = None):
            self._mapping = mapping or {}

        def get_identifier(self, raw: str) -> str | None:
            if not raw:
                return None
            return self._mapping.get(raw.lower().strip())

    svc = FakeSvc({"alice": "alice", "bob": "bob", "charlie": "charlie"})

    # Patch direct de la fonction `get` du sous-module. Pytest force l'import
    # via le path string, pas besoin de pré-importer le module.
    monkeypatch.setattr("simphonia.services.character_service.get", lambda: svc)
    return svc


# ---------------------------------------------------------------------------
#  starter
# ---------------------------------------------------------------------------

class TestStarter:

    def test_starter_defined(self, instance):
        instance["starter"] = "charlie"
        assert next_speaker("starter", instance, FakeSession()) == "charlie"

    def test_starter_undefined_fallback_first(self, instance):
        assert next_speaker("starter", instance, FakeSession()) == "alice"

    def test_starter_undefined_fallback_next_when_alice_spoke(self, instance):
        session = FakeSession(round=1, exchange_history=[{"round": 1, "from": "alice"}])
        assert next_speaker("starter", instance, session) == "bob"

    def test_starter_empty_players_returns_none(self):
        assert next_speaker("starter", {"players": []}, FakeSession()) is None


# ---------------------------------------------------------------------------
#  named
# ---------------------------------------------------------------------------

class TestNamed:

    def test_named_target_resolves(self, instance, fake_character_service):
        last = {"from": "alice", "round": 1, "public": {"to": "bob"}}
        assert next_speaker("named", instance, FakeSession(round=2), last) == "bob"

    def test_named_target_all_returns_none(self, instance, fake_character_service):
        last = {"public": {"to": "all"}}
        assert next_speaker("named", instance, FakeSession(), last) is None

    def test_named_no_last_exchange(self, instance, fake_character_service):
        assert next_speaker("named", instance, FakeSession(), None) is None

    def test_named_no_to_field(self, instance, fake_character_service):
        last = {"public": {"talk": "..."}}
        assert next_speaker("named", instance, FakeSession(), last) is None

    def test_named_target_outside_instance(self, instance, fake_character_service):
        last = {"public": {"to": "daniel"}}
        assert next_speaker("named", instance, FakeSession(), last) is None

    def test_named_fallback_on_to_at_root(self, instance, fake_character_service):
        last = {"from": "alice", "round": 1, "to": "bob"}
        assert next_speaker("named", instance, FakeSession(round=2), last) == "bob"

    def test_named_fuzzy_match_case_insensitive(self, instance, fake_character_service):
        last = {"public": {"to": "  Bob  "}}
        assert next_speaker("named", instance, FakeSession(), last) == "bob"


# ---------------------------------------------------------------------------
#  round_robin
# ---------------------------------------------------------------------------

class TestRoundRobin:

    def test_empty_round_returns_first(self, instance):
        assert next_speaker("round_robin", instance, FakeSession(round=1)) == "alice"

    def test_after_two_speakers(self, instance):
        session = FakeSession(round=1, exchange_history=[
            {"round": 1, "from": "alice"},
            {"round": 1, "from": "bob"},
        ])
        assert next_speaker("round_robin", instance, session) == "charlie"

    def test_complete_round_returns_none(self, instance, players):
        session = FakeSession(
            round=1,
            exchange_history=[{"round": 1, "from": p} for p in players],
        )
        assert next_speaker("round_robin", instance, session) is None

    def test_only_counts_current_round(self, instance):
        # alice a parlé au round 1, au round 2 on recommence à zéro
        session = FakeSession(round=2, exchange_history=[{"round": 1, "from": "alice"}])
        assert next_speaker("round_robin", instance, session) == "alice"

    def test_empty_players(self):
        assert next_speaker("round_robin", {"players": []}, FakeSession()) is None


# ---------------------------------------------------------------------------
#  next_remaining
# ---------------------------------------------------------------------------

class TestNextRemaining:

    def test_empty_round_returns_first(self, instance):
        assert next_speaker("next_remaining", instance, FakeSession()) == "alice"

    def test_skip_spoken(self, instance):
        session = FakeSession(round=1, exchange_history=[
            {"round": 1, "from": "alice"},
            {"round": 1, "from": "charlie"},
        ])
        assert next_speaker("next_remaining", instance, session) == "bob"

    def test_complete_round_returns_none(self, instance, players):
        session = FakeSession(
            round=1,
            exchange_history=[{"round": 1, "from": p} for p in players],
        )
        assert next_speaker("next_remaining", instance, session) is None


# ---------------------------------------------------------------------------
#  random_remaining
# ---------------------------------------------------------------------------

class TestRandomRemaining:

    def test_picks_in_remaining(self, instance):
        """alice a parlé → le tirage doit être bob ou charlie, jamais alice."""
        session = FakeSession(round=1, exchange_history=[{"round": 1, "from": "alice"}])
        random.seed(42)
        for _ in range(20):
            result = next_speaker("random_remaining", instance, session)
            assert result in ("bob", "charlie")

    def test_deterministic_with_seed(self, instance):
        session = FakeSession(round=1, exchange_history=[])
        random.seed(123)
        first = next_speaker("random_remaining", instance, session)
        random.seed(123)
        second = next_speaker("random_remaining", instance, session)
        assert first == second

    def test_complete_round_returns_none(self, instance, players):
        session = FakeSession(
            round=1,
            exchange_history=[{"round": 1, "from": p} for p in players],
        )
        assert next_speaker("random_remaining", instance, session) is None


# ---------------------------------------------------------------------------
#  random
# ---------------------------------------------------------------------------

class TestRandom:

    def test_picks_any_player(self, instance, players):
        for _ in range(20):
            result = next_speaker("random", instance, FakeSession())
            assert result in players

    def test_empty_players_returns_none(self):
        assert next_speaker("random", {"players": []}, FakeSession()) is None

    def test_does_not_respect_spoken(self, instance):
        """random ignore l'historique — peut re-tirer un joueur déjà parlé."""
        session = FakeSession(round=1, exchange_history=[
            {"round": 1, "from": "alice"},
            {"round": 1, "from": "bob"},
            {"round": 1, "from": "charlie"},
        ])
        # Peut retourner n'importe qui, y compris un qui a déjà parlé
        random.seed(0)
        result = next_speaker("random", instance, session)
        assert result in ("alice", "bob", "charlie")


# ---------------------------------------------------------------------------
#  dispatch & erreurs
# ---------------------------------------------------------------------------

class TestDispatch:

    @pytest.mark.parametrize("mode", list(TurningMode))
    def test_all_modes_accept_strenum(self, mode, instance, fake_character_service):
        """Chaque membre de l'enum est bien routé sans ValueError."""
        session = FakeSession()
        last = {"public": {"to": "bob"}}
        # On se fiche du résultat exact, on vérifie juste qu'il n'y a pas d'exception
        next_speaker(mode, instance, session, last)

    @pytest.mark.parametrize("mode_str", [m.value for m in TurningMode])
    def test_all_modes_accept_string(self, mode_str, instance, fake_character_service):
        session = FakeSession()
        last = {"public": {"to": "bob"}}
        next_speaker(mode_str, instance, session, last)

    def test_unknown_mode_raises(self, instance):
        with pytest.raises(ValueError, match="Unknown turning_mode"):
            next_speaker("foo", instance, FakeSession())
