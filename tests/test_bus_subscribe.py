"""Tests unitaires — `Bus.subscribe` + dispatch fan-out (observer pattern)."""
from __future__ import annotations

import logging

import pytest

from simphonia.core.bus import Bus
from simphonia.core.command import Command
from simphonia.core.errors import CommandNotFound, DispatchError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bus() -> Bus:
    """Bus vierge avec une commande no-op `noop` enregistrée."""
    b = Bus("test")
    b.register(Command(
        code="noop",
        description="No-op pour les tests.",
        callback=lambda **kwargs: None,
        bus_name="test",
    ))
    return b


@pytest.fixture
def echo_bus() -> Bus:
    """Bus vierge avec une commande `echo` qui retourne ses kwargs."""
    b = Bus("test")
    b.register(Command(
        code="echo",
        description="Retourne ses kwargs en dict.",
        callback=lambda **kwargs: kwargs,
        bus_name="test",
    ))
    return b


# ---------------------------------------------------------------------------
# Subscription basique
# ---------------------------------------------------------------------------

class TestSubscribeBasics:

    def test_no_listeners_by_default(self, bus: Bus):
        assert bus.listeners() == []

    def test_subscribe_appends_listener(self, bus: Bus):
        def listener(payload: dict) -> None:
            pass
        bus.subscribe(listener)
        assert bus.listeners() == [listener]

    def test_subscribe_allows_multiple_listeners(self, bus: Bus):
        l1 = lambda p: None
        l2 = lambda p: None
        bus.subscribe(l1)
        bus.subscribe(l2)
        assert bus.listeners() == [l1, l2]

    def test_subscribe_same_listener_twice_keeps_both(self, bus: Bus):
        """Pas de dédup — c'est la responsabilité de l'appelant."""
        def listener(payload: dict) -> None:
            pass
        bus.subscribe(listener)
        bus.subscribe(listener)
        assert len(bus.listeners()) == 2

    def test_listeners_returns_snapshot(self, bus: Bus):
        """Modifier la liste retournée ne doit pas affecter le bus."""
        bus.subscribe(lambda p: None)
        snap = bus.listeners()
        snap.clear()
        assert len(bus.listeners()) == 1


# ---------------------------------------------------------------------------
# Dispatch fan-out
# ---------------------------------------------------------------------------

class TestDispatchFanOut:

    def test_listener_called_after_dispatch(self, bus: Bus):
        seen = []
        bus.subscribe(lambda p: seen.append(p))
        bus.dispatch("noop", {"x": 1})
        assert seen == [{"x": 1}]

    def test_listener_called_with_empty_payload_when_none(self, bus: Bus):
        seen = []
        bus.subscribe(lambda p: seen.append(p))
        bus.dispatch("noop")
        assert seen == [{}]

    def test_multiple_listeners_all_called_in_order(self, bus: Bus):
        order = []
        bus.subscribe(lambda p: order.append("a"))
        bus.subscribe(lambda p: order.append("b"))
        bus.subscribe(lambda p: order.append("c"))
        bus.dispatch("noop", {})
        assert order == ["a", "b", "c"]

    def test_listener_receives_payload_only_not_result(self, echo_bus: Bus):
        """Le listener voit le payload, pas le retour de la commande (YAGNI)."""
        seen = []
        echo_bus.subscribe(lambda p: seen.append(p))
        result = echo_bus.dispatch("echo", {"answer": 42})
        assert seen == [{"answer": 42}]
        assert result == {"answer": 42}  # le retour reste pour l'appelant

    def test_dispatch_returns_command_result_not_listener_result(self, echo_bus: Bus):
        """Les listeners ne peuvent pas modifier la valeur retournée par dispatch()."""
        echo_bus.subscribe(lambda p: "ignored")  # listener qui retourne qqc
        result = echo_bus.dispatch("echo", {"k": "v"})
        assert result == {"k": "v"}

    def test_no_subscribers_no_op(self, bus: Bus):
        """Sans listener, dispatch fonctionne normalement."""
        # ne doit rien lever
        assert bus.dispatch("noop", {}) is None


# ---------------------------------------------------------------------------
# Isolation des erreurs
# ---------------------------------------------------------------------------

class TestListenerErrorIsolation:

    def test_listener_exception_does_not_break_dispatch(self, echo_bus: Bus):
        def crashing(payload):
            raise ValueError("boom")
        echo_bus.subscribe(crashing)
        # Dispatch ne doit pas propager l'exception du listener.
        result = echo_bus.dispatch("echo", {"k": "v"})
        assert result == {"k": "v"}

    def test_listener_exception_does_not_block_other_listeners(self, bus: Bus):
        seen = []
        def crashing(p):
            raise RuntimeError("kaboom")
        def good(p):
            seen.append("called")
        bus.subscribe(crashing)
        bus.subscribe(good)
        bus.dispatch("noop", {})
        assert seen == ["called"]

    def test_listener_exception_logged_as_warning(self, bus: Bus, caplog: pytest.LogCaptureFixture):
        def crashing(p):
            raise ValueError("boom")
        bus.subscribe(crashing)
        with caplog.at_level(logging.WARNING, logger="simphonia.core.bus"):
            bus.dispatch("noop", {})
        assert any("listener" in rec.message and "boom" in rec.message
                   for rec in caplog.records)

    def test_command_callback_exception_is_still_raised(self, bus: Bus):
        """Une exception du callback de commande continue de remonter en DispatchError —
        seul le listener bénéficie de l'isolation."""
        b = Bus("test")
        def boom(**kwargs):
            raise RuntimeError("cmd failure")
        b.register(Command(code="bad", description="d", callback=boom, bus_name="test"))
        b.subscribe(lambda p: None)
        with pytest.raises(DispatchError):
            b.dispatch("bad", {})


# ---------------------------------------------------------------------------
# Ordre fan-out vs callback
# ---------------------------------------------------------------------------

class TestFanOutAfterCommand:

    def test_listeners_called_after_command_callback(self, bus: Bus):
        """Le callback doit s'exécuter avant les listeners."""
        order = []

        b = Bus("test")
        b.register(Command(
            code="noop",
            description="d",
            callback=lambda **kwargs: order.append("callback"),
            bus_name="test",
        ))
        b.subscribe(lambda p: order.append("listener"))
        b.dispatch("noop", {})
        assert order == ["callback", "listener"]

    def test_listeners_not_called_if_command_fails(self, bus: Bus):
        """Si le callback de commande lève, les listeners ne sont pas notifiés."""
        seen = []
        b = Bus("test")
        b.register(Command(
            code="bad",
            description="d",
            callback=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("fail")),
            bus_name="test",
        ))
        b.subscribe(lambda p: seen.append(p))
        with pytest.raises(DispatchError):
            b.dispatch("bad", {})
        assert seen == []

    def test_listeners_not_called_if_command_not_found(self, bus: Bus):
        """Si la commande n'existe pas, on lève CommandNotFound, pas de fan-out."""
        seen = []
        bus.subscribe(lambda p: seen.append(p))
        with pytest.raises(CommandNotFound):
            bus.dispatch("inexistante", {})
        assert seen == []
