"""Tests unitaires — bus `messages` + commande no-op `published`."""
from __future__ import annotations

import pytest

from simphonia.commands.messages import MESSAGES_BUS
from simphonia.core.registry import default_registry


# ---------------------------------------------------------------------------
# Présence du bus + commande dans le registry global
# ---------------------------------------------------------------------------

class TestMessagesBusRegistration:

    def test_bus_messages_exists_in_registry(self):
        bus = default_registry().get(MESSAGES_BUS)
        assert bus.name == "messages"

    def test_command_published_registered(self):
        bus = default_registry().get(MESSAGES_BUS)
        cmd = bus.get("published")
        assert cmd.code == "published"
        assert cmd.bus_name == "messages"

    def test_command_published_is_not_mcp(self):
        """Le bus messages est un canal interne — aucun tool MCP exposé."""
        cmd = default_registry().get(MESSAGES_BUS).get("published")
        assert cmd.mcp is False
        assert cmd.mcp_description is None
        assert cmd.mcp_params is None
        assert cmd.mcp_hint is None


# ---------------------------------------------------------------------------
# Comportement no-op + fan-out via subscribe
# ---------------------------------------------------------------------------

class TestPublishedNoOp:

    def test_dispatch_returns_none(self):
        result = default_registry().get(MESSAGES_BUS).dispatch("published", {
            "bus_origin": "test",
            "from_char":  "antoine",
            "payload":    {"talk": "salut"},
        })
        assert result is None

    def test_dispatch_accepts_arbitrary_payload(self):
        """Schemaless — la commande no-op accepte n'importe quel kwargs."""
        bus = default_registry().get(MESSAGES_BUS)
        # rien ne doit lever
        bus.dispatch("published", {})
        bus.dispatch("published", {"foo": "bar", "nested": {"x": 1}})
        bus.dispatch("published", None)


class TestPublishedFanOut:

    def test_listener_receives_payload(self):
        """Un listener inscrit sur messages doit voir passer les payloads."""
        bus = default_registry().get(MESSAGES_BUS)
        seen = []
        listener = lambda p: seen.append(p)
        bus.subscribe(listener)
        try:
            payload = {
                "bus_origin": "activity",
                "from_char":  "manon",
                "payload":    {"private": {"inner": "tendue"}},
            }
            bus.dispatch("published", payload)
            assert seen == [payload]
        finally:
            # Nettoyage : on retire le listener pour ne pas polluer les autres tests.
            bus._listeners.remove(listener)

    def test_multiple_listeners_independent(self):
        """Plusieurs services peuvent écouter le même bus messages."""
        bus = default_registry().get(MESSAGES_BUS)
        a, b = [], []
        la = lambda p: a.append(p)
        lb = lambda p: b.append(p)
        bus.subscribe(la)
        bus.subscribe(lb)
        try:
            bus.dispatch("published", {"k": 1})
            assert a == [{"k": 1}]
            assert b == [{"k": 1}]
        finally:
            bus._listeners.remove(la)
            bus._listeners.remove(lb)
