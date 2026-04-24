"""Tests unitaires — shadow_storage : ABC, _extract_candidates, feed filter, init/subscribe.

Pas de Mongo/Chroma réels — on stube `MongoShadowStorage` au strict nécessaire pour
valider la logique pure (filtre, candidats, embedding text).
"""
from __future__ import annotations

import pytest

from simphonia.services import shadow_storage as svc_module


# ---------------------------------------------------------------------------
# Helpers — fake instance bypassant Mongo/Chroma
# ---------------------------------------------------------------------------

class _FakeShadow:
    """Instance minimaliste qui implémente seulement ce qui est testable
    sans Mongo/Chroma : la logique de filtrage et d'extraction des candidats."""

    def __init__(self, excluded_keys: set[str]) -> None:
        self._excluded_keys = excluded_keys
        self.fed: list[dict] = []
        self.skipped: int = 0

    # Recopie 1:1 du code de MongoShadowStorage._extract_candidates.
    def _extract_candidates(self, payload: dict) -> dict:
        found: dict = {}
        for source in (
            payload.get("private") or {},
            payload.get("public")  or {},
            payload,
        ):
            if not isinstance(source, dict):
                continue
            for k, v in source.items():
                if k in ("private", "public"):
                    continue
                if k in self._excluded_keys:
                    continue
                if not v:
                    continue
                if k not in found:
                    found[k] = v
        return found

    def _embedding_text(self, candidates: dict) -> str:
        parts = []
        for k in sorted(candidates):
            v = candidates[k]
            if isinstance(v, (dict, list)):
                import json
                v = json.dumps(v, ensure_ascii=False)
            parts.append(f"{k}: {v}")
        return "\n".join(parts)

    def feed(self, message: dict) -> None:
        from_char = message.get("from_char")
        if not from_char:
            self.skipped += 1
            return
        payload = message.get("payload") or {}
        candidates = self._extract_candidates(payload)
        if not candidates:
            self.skipped += 1
            return
        self.fed.append({
            "from": from_char,
            "candidates": candidates,
            "payload": payload,
        })


# ---------------------------------------------------------------------------
# _extract_candidates — schemaless, denylist
# ---------------------------------------------------------------------------

class TestExtractCandidates:

    def test_empty_payload_returns_empty(self):
        s = _FakeShadow(excluded_keys={"from", "to", "round", "ts", "_id", "id"})
        assert s._extract_candidates({}) == {}

    def test_only_excluded_returns_empty(self):
        s = _FakeShadow(excluded_keys={"from", "round"})
        assert s._extract_candidates({"from": "antoine", "round": 3}) == {}

    def test_flat_payload_keeps_non_excluded(self):
        s = _FakeShadow(excluded_keys={"from"})
        result = s._extract_candidates({"from": "antoine", "talk": "salut", "inner": "tendu"})
        assert result == {"talk": "salut", "inner": "tendu"}

    def test_nested_private_unwrapped(self):
        s = _FakeShadow(excluded_keys={"from", "round"})
        payload = {
            "from": "antoine",
            "round": 3,
            "private": {"inner": "panique", "expected": "elle va deviner"},
            "public":  {"talk": "ça va", "mood": "neutre"},
        }
        result = s._extract_candidates(payload)
        assert result == {
            "inner":    "panique",
            "expected": "elle va deviner",
            "talk":     "ça va",
            "mood":     "neutre",
        }

    def test_private_priority_over_public_on_collision(self):
        s = _FakeShadow(excluded_keys=set())
        payload = {
            "private": {"shared": "private_value"},
            "public":  {"shared": "public_value"},
        }
        # private est lu en premier → gagne sur la collision
        assert s._extract_candidates(payload) == {"shared": "private_value"}

    def test_empty_values_filtered(self):
        s = _FakeShadow(excluded_keys=set())
        payload = {
            "private": {"inner": "", "expected": None, "noticed": []},
            "public":  {"talk": "non vide"},
        }
        # Tous les vides ignorés (str vide, None, list vide → falsy)
        assert s._extract_candidates(payload) == {"talk": "non vide"}

    def test_wrapper_keys_themselves_not_kept(self):
        """Les conteneurs `public`/`private` ne doivent jamais apparaître comme clés feuilles."""
        s = _FakeShadow(excluded_keys=set())
        payload = {"private": {"inner": "x"}, "public": {"talk": "y"}}
        result = s._extract_candidates(payload)
        assert "private" not in result
        assert "public" not in result

    def test_chat_payload_flat_format(self):
        """Cas chat_service : pas de wrapper public/private, tout à plat."""
        s = _FakeShadow(excluded_keys={"from", "to", "round"})
        payload = {"talk": "hello", "inner": "anxious", "expected": "rejection"}
        assert s._extract_candidates(payload) == {
            "talk":     "hello",
            "inner":    "anxious",
            "expected": "rejection",
        }


# ---------------------------------------------------------------------------
# feed — filtre d'admission
# ---------------------------------------------------------------------------

class TestFeedAdmissionFilter:

    def test_no_from_char_skipped(self):
        s = _FakeShadow(excluded_keys=set())
        s.feed({"bus_origin": "activity", "payload": {"inner": "x"}})
        assert s.fed == []
        assert s.skipped == 1

    def test_empty_from_char_skipped(self):
        s = _FakeShadow(excluded_keys=set())
        s.feed({"from_char": "", "payload": {"inner": "x"}})
        assert s.skipped == 1

    def test_no_payload_skipped(self):
        s = _FakeShadow(excluded_keys=set())
        s.feed({"from_char": "antoine"})
        assert s.skipped == 1

    def test_all_excluded_skipped(self):
        s = _FakeShadow(excluded_keys={"from", "round"})
        s.feed({
            "from_char": "antoine",
            "payload":   {"from": "antoine", "round": 3},
        })
        assert s.fed == []
        assert s.skipped == 1

    def test_admitted_when_at_least_one_candidate(self):
        s = _FakeShadow(excluded_keys={"from", "round"})
        s.feed({
            "bus_origin": "activity",
            "from_char":  "antoine",
            "payload":    {"from": "antoine", "round": 3, "inner": "panique"},
        })
        assert len(s.fed) == 1
        assert s.fed[0]["from"] == "antoine"
        assert s.fed[0]["candidates"] == {"inner": "panique"}


# ---------------------------------------------------------------------------
# _embedding_text — déterministe, alphabétique
# ---------------------------------------------------------------------------

class TestEmbeddingText:

    def test_alphabetic_order(self):
        s = _FakeShadow(excluded_keys=set())
        text = s._embedding_text({
            "talk":     "hello",
            "inner":    "world",
            "expected": "test",
        })
        # Ordre attendu : expected, inner, talk (alphabétique)
        assert text == "expected: test\ninner: world\ntalk: hello"

    def test_dict_value_serialized_as_json(self):
        s = _FakeShadow(excluded_keys=set())
        text = s._embedding_text({"complex": {"a": 1, "b": [2, 3]}})
        assert "complex:" in text
        assert '"a": 1' in text or "'a': 1" not in text  # JSON, pas repr Python


# ---------------------------------------------------------------------------
# init() — subscription auto sur les bus YAML
# ---------------------------------------------------------------------------

class TestInitSubscribe:

    def test_init_subscribes_to_listed_buses(self, monkeypatch):
        """init() doit s'abonner à chaque bus listé dans subscriptions."""
        from simphonia.commands.messages import MESSAGES_BUS  # force registration
        from simphonia.core import default_registry

        # Build une fake instance qui n'instancie pas Mongo/Chroma.
        fake = _FakeShadow(excluded_keys={"from"})

        def fake_build(cfg):
            return fake

        monkeypatch.setattr(svc_module, "build_shadow_storage_service", fake_build)
        # Reset l'instance globale avant test
        monkeypatch.setattr(svc_module, "_instance", None)

        # Capture les listeners du bus messages avant
        bus = default_registry().get(MESSAGES_BUS)
        listeners_before = bus.listeners()

        try:
            svc_module.init({
                "strategy":      "mongodb_strategy",  # ignoré (build mocké)
                "subscriptions": [MESSAGES_BUS],
            })
            listeners_after = bus.listeners()
            assert len(listeners_after) == len(listeners_before) + 1
            assert fake.feed in listeners_after
        finally:
            # Cleanup
            if fake.feed in bus.listeners():
                bus._listeners.remove(fake.feed)

    def test_init_warns_on_unknown_bus(self, monkeypatch, caplog):
        """init() ne doit pas crasher si un bus déclaré n'existe pas."""
        import logging

        fake = _FakeShadow(excluded_keys=set())
        monkeypatch.setattr(svc_module, "build_shadow_storage_service",
                            lambda cfg: fake)
        monkeypatch.setattr(svc_module, "_instance", None)

        with caplog.at_level(logging.WARNING, logger="simphonia.shadow_storage"):
            svc_module.init({"subscriptions": ["bus_inexistant"]})

        assert any("introuvable" in rec.message for rec in caplog.records)

    def test_init_with_no_subscriptions_works(self, monkeypatch):
        """Pas de subscriptions → init OK, instance disponible quand même."""
        fake = _FakeShadow(excluded_keys=set())
        monkeypatch.setattr(svc_module, "build_shadow_storage_service",
                            lambda cfg: fake)
        monkeypatch.setattr(svc_module, "_instance", None)

        svc_module.init({})  # config minimale

        assert svc_module.get() is fake


# ---------------------------------------------------------------------------
# get() — guard d'init
# ---------------------------------------------------------------------------

class TestGet:

    def test_get_before_init_raises(self, monkeypatch):
        monkeypatch.setattr(svc_module, "_instance", None)
        with pytest.raises(RuntimeError, match="non initialisé"):
            svc_module.get()
