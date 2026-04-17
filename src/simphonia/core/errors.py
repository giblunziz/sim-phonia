class SimphoniaError(Exception):
    pass


class BusNotFound(SimphoniaError, KeyError):
    def __init__(self, bus_name: str) -> None:
        super().__init__(bus_name)
        self.bus_name = bus_name

    def __str__(self) -> str:
        return f"bus not found: {self.bus_name!r}"


class CommandNotFound(SimphoniaError, KeyError):
    def __init__(self, bus_name: str, code: str) -> None:
        super().__init__(code)
        self.bus_name = bus_name
        self.code = code

    def __str__(self) -> str:
        return f"command {self.code!r} not found on bus {self.bus_name!r}"


class DuplicateCommand(SimphoniaError, ValueError):
    def __init__(self, bus_name: str, code: str) -> None:
        super().__init__(code)
        self.bus_name = bus_name
        self.code = code

    def __str__(self) -> str:
        return f"command {self.code!r} already registered on bus {self.bus_name!r}"


class CommandContractError(SimphoniaError, ValueError):
    def __init__(self, bus_name: str, code: str, reason: str) -> None:
        super().__init__(reason)
        self.bus_name = bus_name
        self.code = code
        self.reason = reason

    def __str__(self) -> str:
        return f"invalid command contract for {self.bus_name}/{self.code}: {self.reason}"


class CharacterNotFound(SimphoniaError, KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"character not found: {self.name!r}"


class ProviderNotFound(SimphoniaError, KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"provider not found: {self.name!r}"


class DuplicateCascade(SimphoniaError, ValueError):
    def __init__(self, bus_name: str, code: str, position: str, fn_name: str) -> None:
        super().__init__(fn_name)
        self.bus_name = bus_name
        self.code = code
        self.position = position
        self.fn_name = fn_name

    def __str__(self) -> str:
        return (
            f"cascade {self.fn_name!r} ({self.position}) already registered "
            f"on {self.bus_name}/{self.code}"
        )


class SessionNotFound(SimphoniaError, KeyError):
    def __init__(self, session_id: str) -> None:
        super().__init__(session_id)
        self.session_id = session_id

    def __str__(self) -> str:
        return f"session not found: {self.session_id!r}"


class InvalidParticipant(SimphoniaError, ValueError):
    def __init__(self, name: str, session_id: str) -> None:
        super().__init__(name)
        self.name = name
        self.session_id = session_id

    def __str__(self) -> str:
        return f"invalid participant {self.name!r} for session {self.session_id!r}"


class LLMError(SimphoniaError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:
        return f"LLM error: {self.reason}"


class DispatchError(SimphoniaError):
    def __init__(self, bus_name: str, code: str, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.bus_name = bus_name
        self.code = code
        self.cause = cause

    def __str__(self) -> str:
        return f"dispatch of {self.bus_name}/{self.code} failed: {self.cause!r}"
