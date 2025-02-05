from starlette.requests import Request
from starlette.responses import Response


class ASGICachesException(Exception):
    pass


class RequestNotCachable(ASGICachesException):
    """Raised when a request cannot be cached."""

    def __init__(self, request: Request) -> None:
        super().__init__()
        self.request = request


class ResponseNotCachable(ASGICachesException):
    """Raised when a response cannot be cached."""

    def __init__(self, response: Response) -> None:
        super().__init__()
        self.response = response


class DuplicateCaching(ASGICachesException):
    """Raised when multiple cache middleware were detected."""


class MissingCaching(ASGICachesException):
    """Raised when no cache middleware was detected."""
