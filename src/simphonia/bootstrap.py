import logging

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from simphonia.commands.system import SYSTEM_BUS  # noqa: E402
from simphonia.core import default_registry  # noqa: E402
from simphonia.core.discovery import discover  # noqa: E402
from simphonia.http.app import create_app  # noqa: E402
from simphonia.services import activity_storage, character_service, character_storage, chat_service, configuration_service, memory_service, provider_registry, shadow_storage, tools_service  # noqa: E402

log = logging.getLogger(__name__)

COMMANDS_PACKAGE = "simphonia.commands"


def build_app() -> FastAPI:
    configuration_service.init()
    character_storage.init(configuration_service.section("services.character_storage"))
    activity_storage.init(configuration_service.section("services.activity_storage"))
    provider_registry.init(configuration_service.section("providers"))

    registry = default_registry()
    registry.get_or_create(SYSTEM_BUS)

    discover(COMMANDS_PACKAGE)

    system_bus = registry.get(SYSTEM_BUS)
    assert any(c.code == "help" for c in system_bus.list()), "system/help missing after discovery"

    memory_service.init(configuration_service.section("services.memory_service"))
    character_service.init(configuration_service.section("services.character_service"))
    chat_service.init(configuration_service.section("services.chat_service"))
    tools_service.init(configuration_service.section("services.tools_service"))

    # shadow_storage : initialisé après discovery (le bus `messages` doit
    # exister avant la subscription du listener `feed`).
    shadow_storage.init(configuration_service.section("services.shadow_storage"))

    log.info(
        "simphonia ready: %d bus(es), %d system command(s)",
        len(registry.all()),
        len(system_bus.list()),
    )
    return create_app()
