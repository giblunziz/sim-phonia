"""Tests unitaires — bifurcation HITL dans `_do_give_turn` et `submit_human_turn`.

Cf. documents/human_in_the_loop.md.
"""
from __future__ import annotations

import pytest

from simphonia.core.errors import (
    EmptyTurn,
    InvalidHumanSubmit,
    SessionNotFound,
)
from simphonia.services.activity_service import engine
from simphonia.services.activity_service.engine import RunState, SessionState


class FakeCharacterService:
    """Stub minimal — `get_type` et `get_identifier` précâblés."""

    def __init__(self, types: dict[str, str] | None = None,
                 identifier_map: dict[str, str] | None = None) -> None:
        self.types          = types or {}
        self.identifier_map = identifier_map or {}

    def get_type(self, slug: str) -> str:
        return self.types.get(slug, "player")

    def get_identifier(self, name: str) -> str | None:
        return self.identifier_map.get(name)


@pytest.fixture
def session(monkeypatch):
    """Session de test — enregistrée dans `_sessions`, nettoyée au teardown.

    Stubs : `_persist`, `_publish_sse`, `_publish_messages`,
    `_notify_mj_turn_complete`, et l'instance partagée de `character_service`.
    """
    captured_sse:      list[dict]                   = []
    captured_messages: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(engine, "_persist",       lambda s: None)
    monkeypatch.setattr(engine, "_publish_sse",
                        lambda sid, ev: captured_sse.append(ev))
    monkeypatch.setattr(engine, "_publish_messages",
                        lambda bo, fc, p: captured_messages.append((bo, fc, p)))
    monkeypatch.setattr(engine, "_notify_mj_turn_complete", lambda s, e: None)

    fake_svc = FakeCharacterService(
        types={"valere": "human", "antoine": "player"},
        identifier_map={
            "valere":  "valere",
            "Valère":  "valere",
            "antoine": "antoine",
        },
    )
    from simphonia.services import character_service
    monkeypatch.setattr(character_service, "_instance", fake_svc)

    sess = SessionState(
        session_id="sess-1",
        instance_id="inst-1",
        run_id="run-1",
        instance={"players": ["valere", "antoine"], "exchanges": [], "mj": []},
        activity={},
        scene={},
        characters={"valere": {"type": "human"}, "antoine": {}},
        knowledge={},
        system_schemas=[],
        provider_name="gemma4",
        round=1,
        state=RunState.RUNNING,
        human_player="valere",
    )
    engine._sessions["sess-1"] = sess

    yield sess, captured_sse, captured_messages

    engine._sessions.pop("sess-1", None)


# ---------------------------------------------------------------------------
#  Bifurcation _do_give_turn vers HITL
# ---------------------------------------------------------------------------

class TestGiveTurnBifurcationHITL:

    def test_publie_input_required_et_flag_pending(self, session):
        sess, sse, _ = session
        engine._do_give_turn("sess-1", "valere", None)

        # Pas d'exchange ajouté (pas de LLM appelé)
        assert sess.exchange_history == []
        # SSE émis
        events = [e for e in sse if e.get("type") == "activity.input_required"]
        assert len(events) == 1
        ev = events[0]
        assert ev["session_id"] == "sess-1"
        assert ev["target"]     == "valere"
        assert ev["round"]      == 1
        # Pending flagué
        assert sess.pending_human_input is not None
        assert sess.pending_human_input["target"] == "valere"
        assert sess.pending_human_input["round"]  == 1

    def test_persiste_instruction_mj_avant_bifurcation(self, session):
        sess, sse, _ = session
        engine._do_give_turn("sess-1", "valere", "Sois sec et bref")
        # Instruction persistée dans instance.mj[]
        assert len(sess.instance["mj"]) == 1
        assert sess.instance["mj"][0]["instruction"] == "Sois sec et bref"
        assert sess.instance["mj"][0]["target"]      == "valere"
        # Bifurcation toujours effective
        assert any(e.get("type") == "activity.input_required" for e in sse)

    def test_resolution_via_get_identifier(self, session):
        """target='Valère' doit être résolu vers 'valere' avant comparaison."""
        sess, sse, _ = session
        engine._do_give_turn("sess-1", "Valère", None)
        events = [e for e in sse if e.get("type") == "activity.input_required"]
        assert len(events) == 1
        assert events[0]["target"] == "valere"

    def test_payload_minimal_pas_de_whisper_ni_event(self, session):
        """Q11 — payload SSE minimal, pas d'enrichissement whisper/event."""
        sess, sse, _ = session
        # Ajoute un whisper résolvable
        sess.instance["instructions"] = [
            {"round": 1, "who": "valere", "content": "ne dis rien"},
        ]
        sess.instance["events"] = [{"round": 1, "label": "scene"}]
        engine._do_give_turn("sess-1", "valere", None)
        ev = next(e for e in sse if e.get("type") == "activity.input_required")
        # Payload limité aux 4 champs spec'ds
        assert set(ev.keys()) == {"type", "session_id", "target", "round"}


# ---------------------------------------------------------------------------
#  submit_human_turn — happy path
# ---------------------------------------------------------------------------

class TestSubmitHumanTurnHappyPath:

    @pytest.fixture
    def with_pending(self, session):
        sess, sse, msg = session
        sess.pending_human_input = {"round": 1, "target": "valere", "ts": "now"}
        return sess, sse, msg

    def test_construit_exchange_avec_wrapping(self, with_pending):
        sess, sse, msg = with_pending
        result = engine.submit_human_turn(
            "sess-1", "valere", "all",
            "Salut tout le monde.", "sourit",
        )
        # Exchange ajouté à l'history et à l'instance
        assert len(sess.exchange_history) == 1
        assert len(sess.instance["exchanges"]) == 1
        ex = sess.exchange_history[0]
        # Forme attendue
        assert ex["from"]         == "valere"
        assert ex["round"]        == 1
        assert ex["raw_response"] is None        # signature humaine
        assert ex["private"]      == {}
        # Wrapping str → list[str]
        assert ex["public"]["talk"]    == ["Salut tout le monde."]
        assert ex["public"]["actions"] == ["sourit"]
        assert ex["public"]["to"]      == "all"
        assert ex["public"]["body"]    == ""
        assert ex["public"]["mood"]    == ""
        # Pending reset
        assert sess.pending_human_input is None
        # SSE turn_complete émis
        assert any(e.get("type") == "activity.turn_complete" for e in sse)
        # Bus messages publié
        assert len(msg) == 1
        assert msg[0][0] == "activity"
        assert msg[0][1] == "valere"
        # Retour
        assert result["status"]  == "ok"
        assert result["speaker"] == "valere"
        assert result["round"]   == 1

    def test_resolution_target_via_identifier(self, with_pending):
        sess, _, _ = with_pending
        result = engine.submit_human_turn(
            "sess-1", "Valère", "all", "Salut", "",
        )
        assert result["speaker"] == "valere"
        assert sess.exchange_history[0]["from"] == "valere"

    def test_actions_seul_sans_talk(self, with_pending):
        sess, _, _ = with_pending
        engine.submit_human_turn("sess-1", "valere", "all", "", "fait signe")
        ex = sess.exchange_history[0]
        assert ex["public"]["talk"]    == []
        assert ex["public"]["actions"] == ["fait signe"]

    def test_talk_seul_sans_actions(self, with_pending):
        sess, _, _ = with_pending
        engine.submit_human_turn("sess-1", "valere", "all", "Bonjour", "")
        ex = sess.exchange_history[0]
        assert ex["public"]["talk"]    == ["Bonjour"]
        assert ex["public"]["actions"] == []

    def test_to_specific_participant(self, with_pending):
        sess, _, _ = with_pending
        engine.submit_human_turn("sess-1", "valere", "antoine", "Salut Antoine", "")
        assert sess.exchange_history[0]["public"]["to"] == "antoine"

    def test_to_vide_fallback_all(self, with_pending):
        sess, _, _ = with_pending
        engine.submit_human_turn("sess-1", "valere", "", "Hello", "")
        assert sess.exchange_history[0]["public"]["to"] == "all"


# ---------------------------------------------------------------------------
#  submit_human_turn — cas d'erreur
# ---------------------------------------------------------------------------

class TestSubmitHumanTurnErrors:

    def test_session_introuvable(self):
        with pytest.raises(SessionNotFound):
            engine.submit_human_turn("inconnue", "valere", "all", "Hi", "")

    def test_session_ended(self, session):
        sess, _, _ = session
        sess.state = RunState.ENDED
        sess.pending_human_input = {"round": 1, "target": "valere", "ts": "now"}
        with pytest.raises(InvalidHumanSubmit):
            engine.submit_human_turn("sess-1", "valere", "all", "Hi", "")

    def test_target_pas_le_human_player(self, session):
        sess, _, _ = session
        sess.pending_human_input = {"round": 1, "target": "valere", "ts": "now"}
        with pytest.raises(InvalidHumanSubmit):
            engine.submit_human_turn("sess-1", "antoine", "all", "Hi", "")

    def test_pas_de_pending_input(self, session):
        # session.pending_human_input is None par défaut
        with pytest.raises(InvalidHumanSubmit):
            engine.submit_human_turn("sess-1", "valere", "all", "Hi", "")

    def test_empty_turn(self, session):
        sess, _, _ = session
        sess.pending_human_input = {"round": 1, "target": "valere", "ts": "now"}
        with pytest.raises(EmptyTurn):
            engine.submit_human_turn("sess-1", "valere", "all", "", "")

    def test_empty_turn_whitespace_only(self, session):
        sess, _, _ = session
        sess.pending_human_input = {"round": 1, "target": "valere", "ts": "now"}
        with pytest.raises(EmptyTurn):
            engine.submit_human_turn("sess-1", "valere", "all", "   ", "  \n  ")


# ---------------------------------------------------------------------------
#  Intégration context_builder — l'exchange humain doit être visible des autres
# ---------------------------------------------------------------------------

class TestHumanExchangeVisibleInContext:
    """L'exchange humain doit être propagé dans le contexte LLM des autres
    joueurs (sinon ils ne voient rien quand l'humain parle).

    Bug initial : `build_messages` lisait `raw_response` qui est `None` pour
    les exchanges humains → contenu vide.
    Correction : fallback sur `_synthesize_raw_from_public` quand pas de raw.
    """

    def test_synthesize_raw_from_public_filtre_vides(self):
        from simphonia.services.activity_service.context_builder import (
            _synthesize_raw_from_public,
        )
        import json

        raw = _synthesize_raw_from_public("valere", {
            "to":      "all",
            "talk":    ["Salut tout le monde."],
            "actions": ["sourit"],
            "body":    "",
            "mood":    "",
        })
        data = json.loads(raw)
        assert data == {
            "from":    "valere",
            "to":      "all",
            "talk":    ["Salut tout le monde."],
            "actions": ["sourit"],
        }
        # body et mood vides absents
        assert "body" not in data
        assert "mood" not in data

    def test_exchange_humain_visible_dans_build_messages(self, session):
        """Après un submit_human_turn, build_messages produit un contenu non
        vide pour Antoine (qui doit voir Valère parler)."""
        from simphonia.services.activity_service.context_builder import build_messages

        sess, _, _ = session
        sess.pending_human_input = {"round": 1, "target": "valere", "ts": "now"}

        engine.submit_human_turn(
            "sess-1", "valere", "all",
            "Bonjour à tous.", "lève sa tasse",
        )

        # Build messages du POV d'Antoine
        msgs = build_messages(
            player="antoine",
            instance=sess.instance,
            exchange_history=sess.exchange_history,
        )
        # Le tour humain doit être présent comme "user" (Antoine n'est pas Valère)
        # avec un contenu non vide qui contient le talk de Valère.
        assert msgs, "build_messages a retourné une liste vide"
        target_msg = next(
            (m for m in msgs if m["role"] == "user" and "valere" in (m.get("content") or "").lower()),
            None,
        )
        assert target_msg is not None, f"aucun message user pour valere dans : {msgs!r}"
        assert "Bonjour à tous." in target_msg["content"]
        assert "lève sa tasse" in target_msg["content"]

    def test_exchange_humain_visible_du_pov_humain_en_assistant(self, session):
        """Du POV de Valère lui-même, son tour est en role=assistant."""
        from simphonia.services.activity_service.context_builder import build_messages

        sess, _, _ = session
        sess.pending_human_input = {"round": 1, "target": "valere", "ts": "now"}

        engine.submit_human_turn("sess-1", "valere", "all", "Bonjour.", "")

        msgs = build_messages(
            player="valere",
            instance=sess.instance,
            exchange_history=sess.exchange_history,
        )
        assistant_msg = next(
            (m for m in msgs if m["role"] == "assistant"),
            None,
        )
        assert assistant_msg is not None
        assert "Bonjour." in assistant_msg["content"]
