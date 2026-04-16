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


class DispatchError(SimphoniaError):
    def __init__(self, bus_name: str, code: str, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.bus_name = bus_name
        self.code = code
        self.cause = cause

    def __str__(self) -> str:
        return f"dispatch of {self.bus_name}/{self.code} failed: {self.cause!r}"
