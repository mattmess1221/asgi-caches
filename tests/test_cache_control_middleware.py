from __future__ import annotations

import contextlib
import typing

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Mount
from starlette.testclient import TestClient

from asgi_caches.middleware import CacheControlMiddleware


@pytest.mark.parametrize(
    ("initial", "kwargs", "result"),
    [
        pytest.param(None, {}, None, id="no-op"),
        pytest.param("stale-if-error=30", {}, "stale-if-error=30", id="copy-initial"),
        pytest.param(None, {"stale_if_error": 60}, "stale-if-error=60", id="add-value"),
        pytest.param(
            "stale-if-error=30",
            {"stale_if_error": 60},
            "stale-if-error=60",
            id="override-value",
        ),
        pytest.param(
            "max-stale=60",
            {"max_stale": False},
            None,
            id="remove-value",
        ),
        pytest.param(None, {"must_revalidate": True}, "must-revalidate", id="add-true"),
        pytest.param(None, {"must_revalidate": False}, None, id="add-false"),
        pytest.param(
            "must-revalidate",
            {"must_revalidate": False},
            None,
            id="remove-false",
        ),
        pytest.param(
            "must-revalidate, max-stale=60, only-if-cached",
            {"stale_if_error": 60, "no_transform": True, "max_stale": False},
            "must-revalidate, only-if-cached, stale-if-error=60, no-transform",
            id="mixed",
        ),
        pytest.param(
            "max-age=60", {"max_age": 30}, "max-age=30", id="override-max-age-1"
        ),
        pytest.param(
            "max-age=30", {"max_age": 60}, "max-age=30", id="override-max-age-2"
        ),
        pytest.param(None, {"public": True}, NotImplementedError),
        pytest.param(None, {"private": True}, NotImplementedError),
    ],
)
def test_cache_control_middleware(
    initial: str | None,
    kwargs: dict,
    result: str | type[BaseException] | None,
) -> None:
    app = Starlette(
        routes=[
            Mount(
                "/",
                PlainTextResponse(
                    "Hello, world!",
                    headers={"Cache-Control": initial} if initial else {},
                ),
            )
        ],
        middleware=[Middleware(CacheControlMiddleware, **kwargs)],
    )
    client = TestClient(app)

    with client:
        if result is NotImplementedError:
            with pytest.raises(NotImplementedError):
                client.get("/")
        else:
            r = client.get("/")
            assert r.status_code == 200
            assert r.text == "Hello, world!"
            if not result:
                assert "Cache-Control" not in r.headers
            else:
                assert r.headers["Cache-Control"] == result


def test_not_http() -> None:
    lifespan_state = None

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> typing.AsyncIterator[None]:
        nonlocal lifespan_state
        lifespan_state = "started"
        try:
            yield
        finally:
            lifespan_state = "stopped"

    app = Starlette(middleware=[Middleware(CacheControlMiddleware)], lifespan=lifespan)

    with TestClient(app):
        assert lifespan_state == "started"
    assert lifespan_state == "stopped"
