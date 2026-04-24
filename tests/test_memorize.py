"""Tests unitaires — `memory.memorize` (commande, helper markdown, tool_executor).

Le coeur de `chroma_strategy.memorize` (query Chroma + push Mongo) est testé
via ses branches de validation sans mocker tout le stack. Les branches qui
dépendent de Chroma/Mongo sont testées via le tool_executor en monkeypatchant
`memory_service.get()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from simphonia.commands.memory import (
    MEMORIZE_CATEGORIES,
    format_memorize_markdown,
    memorize_command,
)


# ---------------------------------------------------------------------------
#  format_memorize_markdown
# ---------------------------------------------------------------------------

class TestFormatMarkdown:

    def test_added_only(self):
        result = {
            "added": 2, "skipped": 0,
            "details": [
                {"about": "antoine", "category": "perceived_traits", "value": "Il est jaloux.", "status": "added"},
                {"about": "self",    "category": "watchouts",        "value": "Rester lucide.",  "status": "added"},
            ],
        }
        md = format_memorize_markdown(result)
        assert "2 nouvelle(s)" in md
        assert "antoine" in md and "Il est jaloux." in md
        assert "self"    in md and "Rester lucide."  in md
        assert "ignorée" not in md  # pas de section skipped

    def test_skipped_only(self):
        result = {
            "added": 0, "skipped": 1,
            "details": [
                {"about": "elise", "category": "assumptions", "value": "Elle cache qqch.",
                 "status": "skipped", "reason": "semantic_duplicate", "distance": 0.12},
            ],
        }
        md = format_memorize_markdown(result)
        assert "ignorée(s)" in md
        assert "elise" in md and "Elle cache qqch." in md
        assert "nouvelle" not in md

    def test_mixed(self):
        result = {
            "added": 1, "skipped": 1,
            "details": [
                {"about": "a", "category": "approach",      "value": "v1", "status": "added"},
                {"about": "b", "category": "assumptions", "value": "v2",
                 "status": "skipped", "reason": "semantic_duplicate", "distance": 0.1},
            ],
        }
        md = format_memorize_markdown(result)
        assert "1 nouvelle(s)" in md
        assert "1 note(s) ignorée(s)" in md

    def test_empty(self):
        md = format_memorize_markdown({"added": 0, "skipped": 0, "details": []})
        assert "Aucune note" in md

    def test_other_issues_shown(self):
        result = {
            "added": 0, "skipped": 1,
            "details": [
                {"about": "x", "category": "approach", "status": "skipped", "reason": "invalid_category"},
            ],
        }
        md = format_memorize_markdown(result)
        assert "problème" in md or "invalid_category" in md


# ---------------------------------------------------------------------------
#  memorize_command — dispatch vers memory_service
# ---------------------------------------------------------------------------

class TestMemorizeCommand:

    def test_dispatches_with_all_params(self, monkeypatch):
        calls = []

        class FakeSvc:
            def memorize(self, from_char, notes, activity="", scene=""):
                calls.append({"from_char": from_char, "notes": notes,
                              "activity": activity, "scene": scene})
                return {"added": 1, "skipped": 0, "details": [{"about": "x", "category": "approach", "value": "v", "status": "added"}]}

        class FakeMod:
            @staticmethod
            def get(): return FakeSvc()

        monkeypatch.setattr("simphonia.commands.memory.memory_service", FakeMod)

        notes = [{"about": "antoine", "category": "approach", "value": "v"}]
        result = memorize_command(from_char="alice", notes=notes, activity="chat", scene="s1")

        assert len(calls) == 1
        assert calls[0]["from_char"] == "alice"
        assert calls[0]["notes"] == notes
        assert calls[0]["activity"] == "chat"
        assert calls[0]["scene"] == "s1"
        assert result["added"] == 1


# ---------------------------------------------------------------------------
#  Tool executor activity_engine — persistance memorize_log
# ---------------------------------------------------------------------------

@dataclass
class FakeSessionState:
    instance: dict = field(default_factory=lambda: {"activity": "presentation", "scene": "yacht"})
    memorize_log: dict[str, list[str]] = field(default_factory=dict)


class TestActivityEngineExecutor:

    def test_memorize_appends_markdown_to_session_log(self, monkeypatch):
        """Le tool_executor de l'engine doit stocker le markdown dans session.memorize_log[from_char]."""
        from simphonia.services.activity_service.engine import _make_tool_executor

        # Mock memory_service.get().memorize(...)
        class FakeSvc:
            def memorize(self, from_char, notes, activity="", scene=""):
                return {
                    "added": 1, "skipped": 0,
                    "details": [{"about": "bob", "category": "watchouts", "value": "Ne pas lui faire confiance.", "status": "added"}],
                }

        class FakeMemMod:
            @staticmethod
            def get(): return FakeSvc()

        monkeypatch.setattr("simphonia.services.memory_service", FakeMemMod, raising=False)
        import simphonia.services
        monkeypatch.setattr(simphonia.services, "memory_service", FakeMemMod, raising=False)

        session = FakeSessionState()
        executor = _make_tool_executor("alice", session)

        result = executor("memorize", {"notes": [
            {"about": "bob", "category": "watchouts", "value": "Ne pas lui faire confiance."},
        ]})

        # Vérifications
        assert "bob" in result
        assert "Ne pas lui faire confiance" in result
        # memorize_log a bien reçu le markdown
        assert "alice" in session.memorize_log
        assert len(session.memorize_log["alice"]) == 1
        assert "bob" in session.memorize_log["alice"][0]

    def test_memorize_multiple_calls_accumulate(self, monkeypatch):
        from simphonia.services.activity_service.engine import _make_tool_executor

        class FakeSvc:
            def memorize(self, from_char, notes, activity="", scene=""):
                return {
                    "added": len(notes), "skipped": 0,
                    "details": [{"about": n["about"], "category": n["category"], "value": n["value"], "status": "added"} for n in notes],
                }

        class FakeMemMod:
            @staticmethod
            def get(): return FakeSvc()

        import simphonia.services
        monkeypatch.setattr(simphonia.services, "memory_service", FakeMemMod, raising=False)

        session = FakeSessionState()
        executor = _make_tool_executor("alice", session)

        executor("memorize", {"notes": [{"about": "bob", "category": "approach", "value": "v1"}]})
        executor("memorize", {"notes": [{"about": "claire", "category": "assumptions", "value": "v2"}]})

        assert len(session.memorize_log["alice"]) == 2


# ---------------------------------------------------------------------------
#  Context builder — injection memorize_log
# ---------------------------------------------------------------------------

class TestContextBuilderInjection:

    def test_build_messages_injects_memorize_log(self):
        from simphonia.services.activity_service.context_builder import build_messages

        msgs = build_messages(
            player="alice",
            instance={"players": ["alice", "bob"]},
            exchange_history=[],
            memorize_log=["✅ Tu as mémorisé 1 note (alice→bob)", "✅ Tu as mémorisé 2 notes (alice→self)"],
        )

        # 1 seul message injecté (memorize_log concaténé)
        memorize_msgs = [m for m in msgs if "Tes mémorisations récentes" in m.get("content", "")]
        assert len(memorize_msgs) == 1
        assert "alice→bob" in memorize_msgs[0]["content"]
        assert "alice→self" in memorize_msgs[0]["content"]

    def test_build_messages_no_injection_if_log_empty(self):
        from simphonia.services.activity_service.context_builder import build_messages

        msgs = build_messages(
            player="alice",
            instance={"players": ["alice"]},
            exchange_history=[],
            memorize_log=None,
        )
        memorize_msgs = [m for m in msgs if "Tes mémorisations récentes" in m.get("content", "")]
        assert memorize_msgs == []

    def test_build_messages_injection_position(self):
        """Le memorize_log doit venir après whisper et avant l'historique."""
        from simphonia.services.activity_service.context_builder import build_messages

        msgs = build_messages(
            player="alice",
            instance={"players": ["alice", "bob"]},
            exchange_history=[{"from": "bob", "round": 1, "raw_response": '{"talk":"salut"}'}],
            whisper="message MJ",
            memorize_log=["note mémorisée"],
        )

        # Ordre attendu : whisper → memorize_log → exchange bob
        contents = [m["content"] for m in msgs]
        idx_whisper   = next(i for i, c in enumerate(contents) if c == "message MJ")
        idx_memorize  = next(i for i, c in enumerate(contents) if "note mémorisée" in c)
        idx_exchange  = next(i for i, c in enumerate(contents) if "salut" in c)

        assert idx_whisper < idx_memorize < idx_exchange
