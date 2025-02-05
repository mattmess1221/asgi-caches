from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from asgi_caches.decorators import cache_control

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.types import Receive, Scope, Send


def test_cache_control_decorator() -> None:
    @cache_control(stale_if_error=60, must_revalidate=True)
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = PlainTextResponse("Hello, world!")
        await response(scope, receive, send)

    app = Starlette(routes=[Route("/", app)])

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert r.headers["Cache-Control"] == "stale-if-error=60, must-revalidate"


def test_decorate_starlette_view() -> None:
    with pytest.raises(ValueError, match="does not seem to be an ASGI3 callable"):

        @cache_control(stale_if_error=60)
        async def home(request: Request) -> Response: ...  # pragma: no cover
