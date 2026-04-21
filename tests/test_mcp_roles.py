"""Tests unitaires — `mcp_role` attribut + filtrage helper `list_mcp_commands(role)`.

Vérifie :
  - `Command.mcp_role` default `"player"` (rétro-compat)
  - `@command(mcp=True, mcp_role="mj")` fonctionne
  - `mcp_role != "player"` sans `mcp=True` → CommandContractError
  - `mcp_role` invalide → CommandContractError
  - `list_mcp_commands(role=...)` filtre correctement
  - `list_mcp_commands()` sans role → pas de filtre (rétro-compat)
"""
from __future__ import annotations

import pytest

from simphonia.core import command
from simphonia.core.command import MCP_ROLES, Command
from simphonia.core.errors import CommandContractError
from simphonia.core.mcp import (
    list_mcp_commands,
    mcp_tool_definitions,
    to_tool_definitions,
)
from simphonia.core.registry import BusRegistry


# ---------------------------------------------------------------------------
#  Command dataclass
# ---------------------------------------------------------------------------

class TestCommandDataclass:

    def test_default_role_is_player(self):
        cmd = Command(
            code="foo", description="bar", callback=lambda: None, bus_name="test",
        )
        assert cmd.mcp_role == "player"

    def test_explicit_role_mj(self):
        cmd = Command(
            code="foo", description="bar", callback=lambda: None, bus_name="test",
            mcp=True,
            mcp_description="x", mcp_params={"type": "object", "properties": {}},
            mcp_role="mj",
        )
        assert cmd.mcp_role == "mj"

    def test_mcp_roles_frozen_set(self):
        assert MCP_ROLES == frozenset({"player", "mj", "npc"})


# ---------------------------------------------------------------------------
#  Décorateur — validation
# ---------------------------------------------------------------------------

class TestDecoratorValidation:

    def test_decorator_accepts_mcp_role_mj(self, monkeypatch):
        reg = BusRegistry()
        monkeypatch.setattr("simphonia.core.decorators.default_registry", lambda: reg)

        @command(
            bus="test", code="cmd1", description="d",
            mcp=True, mcp_description="desc",
            mcp_params={"type": "object", "properties": {}},
            mcp_role="mj",
        )
        def fn():
            return None

        assert reg.get("test").get("cmd1").mcp_role == "mj"

    def test_mcp_role_mj_without_mcp_raises(self):
        with pytest.raises(CommandContractError, match="mcp_role='mj' provided but mcp=False"):
            @command(bus="test", code="cmd", description="d", mcp_role="mj")
            def fn():
                return None

    def test_invalid_mcp_role_raises(self):
        with pytest.raises(CommandContractError, match="mcp_role='admin' invalid"):
            @command(
                bus="test", code="cmd", description="d",
                mcp=True, mcp_description="desc",
                mcp_params={"type": "object", "properties": {}},
                mcp_role="admin",
            )
            def fn():
                return None

    def test_mcp_false_mcp_role_player_ok(self, monkeypatch):
        """mcp=False + mcp_role='player' (default) = pas d'erreur (rétro-compat)."""
        reg = BusRegistry()
        monkeypatch.setattr("simphonia.core.decorators.default_registry", lambda: reg)

        @command(bus="test", code="cmd-retro", description="d")
        def fn():
            return None

        assert reg.get("test").get("cmd-retro").mcp_role == "player"


# ---------------------------------------------------------------------------
#  Helper list_mcp_commands(role=...)
# ---------------------------------------------------------------------------

class TestListMcpCommands:

    @pytest.fixture
    def registry_with_mixed_tools(self):
        """Registry avec 3 commandes : 1 non-MCP, 1 MCP player, 1 MCP mj."""
        reg = BusRegistry()

        # non-MCP (ne doit jamais remonter)
        reg.get_or_create("test").register(Command(
            code="non_mcp", description="plain", callback=lambda: None,
            bus_name="test",
        ))
        # MCP player
        reg.get_or_create("test").register(Command(
            code="player_tool", description="p", callback=lambda: None,
            bus_name="test", mcp=True,
            mcp_description="desc", mcp_params={"type": "object", "properties": {}},
            mcp_role="player",
        ))
        # MCP mj
        reg.get_or_create("test").register(Command(
            code="mj_tool", description="m", callback=lambda: None,
            bus_name="test", mcp=True,
            mcp_description="desc", mcp_params={"type": "object", "properties": {}},
            mcp_role="mj",
        ))
        return reg

    def test_role_none_returns_all_mcp(self, registry_with_mixed_tools):
        """Rétro-compat : pas de role = toutes les MCP."""
        result = list_mcp_commands(registry_with_mixed_tools)
        codes = {cmd.code for cmd in result}
        assert codes == {"player_tool", "mj_tool"}

    def test_role_player_filters(self, registry_with_mixed_tools):
        result = list_mcp_commands(registry_with_mixed_tools, role="player")
        assert [cmd.code for cmd in result] == ["player_tool"]

    def test_role_mj_filters(self, registry_with_mixed_tools):
        result = list_mcp_commands(registry_with_mixed_tools, role="mj")
        assert [cmd.code for cmd in result] == ["mj_tool"]

    def test_role_unknown_returns_empty(self, registry_with_mixed_tools):
        """Filtre strict par ==. Un role inconnu → liste vide (pas d'erreur)."""
        assert list_mcp_commands(registry_with_mixed_tools, role="admin") == []


class TestMcpToolDefinitionsRole:

    def test_propagates_role_filter(self, monkeypatch):
        reg = BusRegistry()
        reg.get_or_create("test").register(Command(
            code="player_tool", description="p", callback=lambda: None,
            bus_name="test", mcp=True,
            mcp_description="d", mcp_params={"type": "object", "properties": {}},
            mcp_role="player",
        ))
        reg.get_or_create("test").register(Command(
            code="mj_tool", description="m", callback=lambda: None,
            bus_name="test", mcp=True,
            mcp_description="d", mcp_params={"type": "object", "properties": {}},
            mcp_role="mj",
        ))

        defs_mj = mcp_tool_definitions(reg, role="mj")
        assert [d["name"] for d in defs_mj] == ["mj_tool"]

        defs_player = mcp_tool_definitions(reg, role="player")
        assert [d["name"] for d in defs_player] == ["player_tool"]
