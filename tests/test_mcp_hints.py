"""Tests unitaires — `mcp_hint` attribut + `register_mcp_group` + `mcp_tool_hints`."""
from __future__ import annotations

import pytest

from simphonia.core import command
from simphonia.core.command import Command
from simphonia.core.errors import CommandContractError
from simphonia.core.mcp import (
    McpGroup,
    _reset_mcp_groups_for_tests,
    get_mcp_group,
    mcp_tool_hints,
    mcp_tool_reminders,
    register_mcp_group,
)
from simphonia.core.registry import BusRegistry


@pytest.fixture(autouse=True)
def _reset_groups():
    """Isole les tests du registre global de groupes MCP."""
    _reset_mcp_groups_for_tests()
    yield
    _reset_mcp_groups_for_tests()


# ---------------------------------------------------------------------------
#  Command.mcp_hint default + decorator validation
# ---------------------------------------------------------------------------

class TestMcpHintAttribute:

    def test_default_is_none(self):
        cmd = Command(code="foo", description="d", callback=lambda: None, bus_name="b")
        assert cmd.mcp_hint is None

    def test_decorator_rejects_hint_without_mcp(self):
        with pytest.raises(CommandContractError, match="mcp_hint provided but mcp=False"):
            @command(bus="test", code="cmd", description="d", mcp_hint="trigger when doubt")
            def fn():
                return None

    def test_decorator_accepts_hint_with_mcp(self, monkeypatch):
        reg = BusRegistry()
        monkeypatch.setattr("simphonia.core.decorators.default_registry", lambda: reg)

        @command(
            bus="test", code="cmd", description="d",
            mcp=True, mcp_description="desc",
            mcp_params={"type": "object", "properties": {}},
            mcp_role="player",
            mcp_hint="- `cmd` — quand tu veux X",
        )
        def fn():
            return None

        stored = reg.get("test").get("cmd")
        assert stored.mcp_hint == "- `cmd` — quand tu veux X"


# ---------------------------------------------------------------------------
#  register_mcp_group
# ---------------------------------------------------------------------------

class TestRegisterMcpGroup:

    def test_register_and_retrieve(self):
        register_mcp_group(bus="memory", role="player", intro="Intro ici", outro="Outro ici")
        group = get_mcp_group("memory", "player")
        assert isinstance(group, McpGroup)
        assert group.intro == "Intro ici"
        assert group.outro == "Outro ici"

    def test_unknown_group_returns_none(self):
        assert get_mcp_group("nope", "player") is None

    def test_re_register_overwrites_with_warning(self, caplog):
        register_mcp_group(bus="memory", role="player", intro="A", outro="a")
        register_mcp_group(bus="memory", role="player", intro="B", outro="b")
        group = get_mcp_group("memory", "player")
        assert group.intro == "B"
        assert group.outro == "b"
        assert any("déjà enregistré" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
#  mcp_tool_hints — composition intro + hints + outro, multi-groupes
# ---------------------------------------------------------------------------

def _make_cmd(bus, code, role, hint=None) -> Command:
    return Command(
        code=code, description="d", callback=lambda: None, bus_name=bus,
        mcp=True, mcp_description="x", mcp_params={"type": "object", "properties": {}},
        mcp_role=role, mcp_hint=hint,
    )


class TestMcpToolHints:

    def test_single_group_full(self):
        """intro + 2 hints + outro joints par \\n\\n."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall",   "player", "hint1"))
        reg.get_or_create("memory").register(_make_cmd("memory", "memorize", "player", "hint2"))
        register_mcp_group(bus="memory", role="player", intro="INTRO", outro="OUTRO")

        out = mcp_tool_hints(role="player", registry=reg)
        # Structure attendue
        lines = out.split("\n\n")
        assert lines[0]  == "INTRO"
        assert lines[1]  == "hint1"
        assert lines[2]  == "hint2"
        assert lines[-1] == "OUTRO"

    def test_no_group_just_hints(self):
        """Sans register_mcp_group : concaténation pure des hints."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall",   "player", "hint1"))
        reg.get_or_create("memory").register(_make_cmd("memory", "memorize", "player", "hint2"))
        out = mcp_tool_hints(role="player", registry=reg)
        assert out == "hint1\n\nhint2"

    def test_group_but_no_hints_still_emitted(self):
        """Groupe enregistré sans commandes hintées : intro + outro quand même (tant que la commande existe)."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player", None))
        register_mcp_group(bus="memory", role="player", intro="INTRO", outro="OUTRO")
        out = mcp_tool_hints(role="player", registry=reg)
        # intro + outro sans hints entre les deux
        assert out == "INTRO\n\nOUTRO"

    def test_no_commands_returns_empty(self):
        """Aucune commande → chaîne vide."""
        reg = BusRegistry()
        assert mcp_tool_hints(role="player", registry=reg) == ""

    def test_filter_by_role(self):
        """role=player n'inclut pas les commandes mj."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player", "player hint"))
        reg.get_or_create("activity").register(_make_cmd("activity", "give_turn", "mj", "mj hint"))
        out_p = mcp_tool_hints(role="player", registry=reg)
        out_m = mcp_tool_hints(role="mj",     registry=reg)
        assert "player hint" in out_p and "mj hint" not in out_p
        assert "mj hint"     in out_m and "player hint" not in out_m

    def test_multi_bus_groups_separated(self):
        """Plusieurs groupes (memory + shadow) séparés par \\n\\n---\\n\\n."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player", "mem hint"))
        reg.get_or_create("shadow").register(_make_cmd("shadow", "peek",   "player", "shadow hint"))
        register_mcp_group(bus="memory", role="player", intro="MEM INTRO", outro="MEM OUTRO")
        register_mcp_group(bus="shadow", role="player", intro="SHD INTRO", outro="SHD OUTRO")

        out = mcp_tool_hints(role="player", registry=reg)
        assert "\n\n---\n\n" in out
        # Structure de chaque section
        sections = out.split("\n\n---\n\n")
        assert len(sections) == 2


# ---------------------------------------------------------------------------
#  McpGroup.reminder + mcp_tool_reminders — placeholder ${commands}
# ---------------------------------------------------------------------------

class TestMcpGroupReminderField:

    def test_default_reminder_is_none(self):
        register_mcp_group(bus="memory", role="player", intro="i", outro="o")
        group = get_mcp_group("memory", "player")
        assert group.reminder is None

    def test_register_with_reminder(self):
        register_mcp_group(
            bus="memory", role="player",
            intro="i", outro="o",
            reminder="N'oublie pas tes outils ${commands}",
        )
        group = get_mcp_group("memory", "player")
        assert group.reminder == "N'oublie pas tes outils ${commands}"


class TestMcpToolReminders:

    def test_no_groups_returns_empty(self):
        reg = BusRegistry()
        assert mcp_tool_reminders(role="player", registry=reg) == ""

    def test_group_without_reminder_skipped(self):
        """Si le groupe n'a pas de reminder, rien n'est retourné même si commandes présentes."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player", "h"))
        register_mcp_group(bus="memory", role="player", intro="I", outro="O")  # pas de reminder
        assert mcp_tool_reminders(role="player", registry=reg) == ""

    def test_placeholder_commands_resolved_single(self):
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player"))
        register_mcp_group(
            bus="memory", role="player",
            reminder="Pense à ${commands} pour tes souvenirs",
        )
        out = mcp_tool_reminders(role="player", registry=reg)
        assert out == "Pense à `recall` pour tes souvenirs"

    def test_placeholder_commands_resolved_multiple(self):
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall",   "player"))
        reg.get_or_create("memory").register(_make_cmd("memory", "memorize", "player"))
        register_mcp_group(
            bus="memory", role="player",
            reminder="Tu disposes de ${commands} pour gérer ta mémoire",
        )
        out = mcp_tool_reminders(role="player", registry=reg)
        assert out == "Tu disposes de `recall`, `memorize` pour gérer ta mémoire"

    def test_reminder_without_placeholder_passes_through(self):
        """Reminder statique sans ${commands} : conservé tel quel."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player"))
        register_mcp_group(
            bus="memory", role="player",
            reminder="Texte fixe sans variable",
        )
        out = mcp_tool_reminders(role="player", registry=reg)
        assert out == "Texte fixe sans variable"

    def test_unknown_placeholder_left_untouched(self):
        """safe_substitute : un placeholder inconnu ne fait pas planter, juste ignoré."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player"))
        register_mcp_group(
            bus="memory", role="player",
            reminder="Tools=${commands}, weird=${nope}",
        )
        out = mcp_tool_reminders(role="player", registry=reg)
        assert out == "Tools=`recall`, weird=${nope}"

    def test_filter_by_role(self):
        """Seul le reminder du role demandé est composé."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player"))
        reg.get_or_create("activity").register(_make_cmd("activity", "give_turn", "mj"))
        register_mcp_group(bus="memory",   role="player", reminder="P=${commands}")
        register_mcp_group(bus="activity", role="mj",     reminder="M=${commands}")

        out_p = mcp_tool_reminders(role="player", registry=reg)
        out_m = mcp_tool_reminders(role="mj",     registry=reg)
        assert out_p == "P=`recall`"
        assert out_m == "M=`give_turn`"

    def test_multi_group_separated(self):
        """Plusieurs groupes du même role : reminders concaténés avec \\n\\n---\\n\\n."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "recall", "player"))
        reg.get_or_create("shadow").register(_make_cmd("shadow", "peek",   "player"))
        register_mcp_group(bus="memory", role="player", reminder="MEM=${commands}")
        register_mcp_group(bus="shadow", role="player", reminder="SHD=${commands}")

        out = mcp_tool_reminders(role="player", registry=reg)
        sections = out.split("\n\n---\n\n")
        assert set(sections) == {"MEM=`recall`", "SHD=`peek`"}

    def test_command_order_preserved(self):
        """L'ordre d'enregistrement des commandes est respecté dans la résolution."""
        reg = BusRegistry()
        reg.get_or_create("memory").register(_make_cmd("memory", "zeta",  "player"))
        reg.get_or_create("memory").register(_make_cmd("memory", "alpha", "player"))
        register_mcp_group(bus="memory", role="player", reminder="${commands}")
        out = mcp_tool_reminders(role="player", registry=reg)
        # zeta avant alpha (ordre d'enregistrement, pas alphabétique)
        assert out == "`zeta`, `alpha`"
