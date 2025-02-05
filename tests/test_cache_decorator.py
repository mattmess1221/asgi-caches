from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiocache import Cache
from fastapi.routing import Mount
from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from asgi_caches.decorators import cached
from asgi_caches.middleware import CacheMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.types import Receive, Scope, Send


def test_decorator_raw_asgi() -> None:
    cache = Cache(ttl=2 * 60)

    @cached(cache)
    async def mount(scope: Scope, receive: Receive, send: Send) -> None:
        response = PlainTextResponse("Hello, world!")
        await response(scope, receive, send)

    app = Starlette(routes=[Mount("/", mount)])

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers
        assert r.headers["X-Cache"] == "miss"

        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers
        assert r.headers["X-Cache"] == "hit"


def test_decorator_starlette_endpoint() -> None:
    cache = Cache(ttl=2 * 60)

    @cached(cache)
    class CachedHome(HTTPEndpoint):
        async def get(self, request: Request) -> Response:
            return PlainTextResponse("Hello, world!")

    class UncachedUsers(HTTPEndpoint):
        async def get(self, request: Request) -> Response:
            return PlainTextResponse("Hello, users!")

    assert isinstance(CachedHome, CacheMiddleware)

    app = Starlette(routes=[Route("/", CachedHome), Route("/users", UncachedUsers)])

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers
        assert r.headers["X-Cache"] == "miss"

        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers
        assert r.headers["X-Cache"] == "hit"

        r = client.get("/users")
        assert r.status_code == 200
        assert r.text == "Hello, users!"
        assert "Expires" not in r.headers
        assert "Cache-Control" not in r.headers
        assert "X-Cache" not in r.headers

        r = client.get("/users")
        assert r.status_code == 200
        assert r.text == "Hello, users!"
        assert "Expires" not in r.headers
        assert "Cache-Control" not in r.headers
        assert "X-Cache" not in r.headers


def test_decorate_starlette_view() -> None:
    cache = Cache(ttl=2 * 60)

    with pytest.raises(ValueError, match="does not seem to be an ASGI3 callable"):

        @cached(cache)
        async def home(request: Request) -> Response: ...  # pragma: no cover
