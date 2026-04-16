from simphonia.core import command, default_registry

SYSTEM_BUS = "system"


@command(bus=SYSTEM_BUS, code="help", description="List all commands registered on the system bus")
def help_command() -> list[dict[str, str]]:
    bus = default_registry().get(SYSTEM_BUS)
    return [{"code": c.code, "description": c.description} for c in bus.list()]


@command(bus=SYSTEM_BUS, code="ping", description="Liveness probe — returns 'pong'")
def ping_command() -> str:
    return "pong"
