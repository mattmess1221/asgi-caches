from __future__ import annotations

import contextlib
import logging
import os
import typing

import httpx
from starlette.responses import Response

import asgi_caches.utils.logging

if typing.TYPE_CHECKING:
    from starlette.types import Message


async def mock_receive() -> Message:
    raise NotImplementedError  # pragma: no cover


async def mock_send(message: Message) -> None:
    raise NotImplementedError  # pragma: no cover


class ComparableStarletteResponse:
    # As of 0.12, Starlette does not provide a '.__eq__()' implementation
    # for responses yet.

    def __init__(self, response: Response) -> None:
        self.response = response

    def __eq__(self, other: typing.Any) -> bool:
        assert isinstance(other, Response)
        return (
            self.response.body == other.body
            and self.response.raw_headers == other.raw_headers
            and self.response.status_code == other.status_code
        )


class ComparableHTTPXResponse:
    # As of 0.7, HTTPX does not provide a '.__eq__()' implementation
    # for responses yet.

    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    def __eq__(self, other: typing.Any) -> bool:
        assert isinstance(other, httpx.Response)
        return (
            self.response.content == other.content
            and self.response.headers == other.headers
            and self.response.status_code == other.status_code
        )


@contextlib.contextmanager
def override_log_level(log_level: str) -> typing.Iterator[None]:
    os.environ["ASGI_CACHES_LOG_LEVEL"] = log_level

    # Force a reload on the logging handlers
    asgi_caches.utils.logging._logger_factory._initialized = False
    asgi_caches.utils.logging.get_logger("asgi_caches")

    try:
        yield
    finally:
        # Reset the logger so we don't have verbose output in all unit tests
        logging.getLogger("asgi_caches").handlers = []
