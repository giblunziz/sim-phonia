from typing import Any

from simphonia.core.command import Command
from simphonia.core.errors import CommandNotFound, DispatchError, DuplicateCommand


class Bus:
    def __init__(self, name: str) -> None:
        self.name = name
        self._commands: dict[str, Command] = {}

    def register(self, cmd: Command) -> None:
        if cmd.code in self._commands:
            raise DuplicateCommand(self.name, cmd.code)
        self._commands[cmd.code] = cmd

    def get(self, code: str) -> Command:
        try:
            return self._commands[code]
        except KeyError:
            raise CommandNotFound(self.name, code) from None

    def list(self) -> list[Command]:
        return list(self._commands.values())

    def dispatch(self, code: str, payload: dict[str, Any] | None = None) -> Any:
        cmd = self.get(code)
        try:
            return cmd.callback(**(payload or {}))
        except (CommandNotFound, DispatchError):
            raise
        except Exception as exc:
            raise DispatchError(self.name, code, exc) from exc
