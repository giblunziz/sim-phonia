class SimcliError(Exception):
    pass


class ServerUnreachable(SimcliError):
    def __init__(self, base_url: str, cause: BaseException) -> None:
        super().__init__(f"server unreachable at {base_url}: {cause!r}")
        self.base_url = base_url
        self.cause = cause


class NotFound(SimcliError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class ServerError(SimcliError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"server returned {status}: {body}")
        self.status = status
        self.body = body


class InvalidPayload(SimcliError):
    pass
