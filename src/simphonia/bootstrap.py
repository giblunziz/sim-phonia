import logging

from fastapi import FastAPI

from simphonia.commands.system import SYSTEM_BUS
from simphonia.core import default_registry
from simphonia.core.discovery import discover
from simphonia.http.app import create_app

log = logging.getLogger(__name__)

COMMANDS_PACKAGE = "simphonia.commands"


def build_app() -> FastAPI:
    registry = default_registry()
    registry.get_or_create(SYSTEM_BUS)

    discover(COMMANDS_PACKAGE)

    system_bus = registry.get(SYSTEM_BUS)
    assert any(c.code == "help" for c in system_bus.list()), "system/help missing after discovery"
    log.info("simphonia ready: %d bus(es), %d system command(s)", len(registry.all()), len(system_bus.list()))

    return create_app()


app = build_app()
