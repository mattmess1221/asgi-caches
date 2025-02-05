from __future__ import annotations

import contextlib
import datetime as dt
import re
import typing
from functools import partial

import pytest
from aiocache import Cache
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from asgi_caches.exceptions import DuplicateCaching
from asgi_caches.middleware import CacheMiddleware
from asgi_caches.rules import Rule
from tests.utils import ComparableHTTPXResponse

if typing.TYPE_CHECKING:
    from starlette.requests import Request


async def standard_route(request: Request, *, status_code: int = 200) -> Response:
    return PlainTextResponse("Hello, world!", status_code=status_code)


def test_cache_response() -> None:
    cache = Cache(ttl=2 * 60)

    app = Starlette(
        routes=[Route("/", standard_route)],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert r.headers.pop("X-Cache") == "miss"

        assert "Expires" in r.headers
        expires_fmt = "%a, %d %b %Y %H:%M:%S GMT"
        expires = dt.datetime.strptime(r.headers["Expires"], expires_fmt).replace(
            tzinfo=dt.timezone.utc
        )
        delta: dt.timedelta = expires - dt.datetime.now(tz=dt.timezone.utc)
        assert delta.total_seconds() == pytest.approx(120, rel=1e-2)
        assert "Cache-Control" in r.headers
        assert r.headers["Cache-Control"] == "max-age=120"

        r1 = client.get("/")
        assert r1.headers.pop("X-Cache") == "hit"
        assert ComparableHTTPXResponse(r1) == r

        r2 = client.get("/")
        assert r2.headers.pop("X-Cache") == "hit"
        assert ComparableHTTPXResponse(r2) == r


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

    cache = Cache()
    app = Starlette(
        middleware=[Middleware(CacheMiddleware, cache=cache)],
        lifespan=lifespan,
    )

    with TestClient(app):
        assert lifespan_state == "started"

    assert lifespan_state == "stopped"


def test_non_cachable_request() -> None:
    cache = Cache()
    app = Starlette(
        routes=[Route("/", standard_route, methods=["POST"])],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )
    with TestClient(app) as client:
        r = client.post("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "Expires" not in r.headers
        assert "Cache-Control" not in r.headers
        assert "X-Cache" not in r.headers

        r1 = client.post("/")
        assert "X-Cache" not in r1.headers
        assert ComparableHTTPXResponse(r1) == r


@pytest.mark.parametrize(
    ("path", "match_path"),
    [
        ("/cache", "/cache"),
        ("/cache/subpath", re.compile(r"\/cache\/.+")),
    ],
)
def test_cache_match_paths(path: str, match_path: re.Pattern) -> None:
    cache = Cache()
    app = Starlette(
        routes=[
            Route("/", standard_route),
            Route(path, standard_route),
        ],
        middleware=[
            Middleware(
                CacheMiddleware,
                cache=cache,
                rules=[
                    Rule(match_path),
                ],
            )
        ],
    )

    with TestClient(app) as client:
        r = client.get(path)
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert r.headers["X-Cache"] == "miss"

        r1 = client.get(path)
        assert r1.status_code == 200
        assert r1.text == "Hello, world!"
        assert r1.headers["X-Cache"] == "hit"

        r2 = client.get("/")
        assert r2.status_code == 200
        assert r2.text == "Hello, world!"
        assert "X-Cache" not in r2.headers


def test_cache_deny_paths() -> None:
    cache = Cache()
    app = Starlette(
        routes=[
            Route("/", standard_route),
            Route("/no_cache", standard_route),
        ],
        middleware=[
            Middleware(
                CacheMiddleware,
                cache=cache,
                rules=[Rule("/no_cache", ttl=0), Rule()],
            )
        ],
    )
    with TestClient(app) as client:
        r = client.get("/no_cache")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "X-Cache" not in r.headers

        r1 = client.get("/no_cache")
        assert r1.status_code == 200
        assert r1.text == "Hello, world!"
        assert "X-Cache" not in r.headers


def test_use_cached_head_response_on_get() -> None:
    """
    Making a HEAD request should use the cached response for future GET requests.
    """
    cache = Cache()
    app = Starlette(
        routes=[Route("/", standard_route)],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )
    with TestClient(app) as client:
        r = client.head("/")
        assert not r.text
        assert r.status_code == 200
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers
        assert r.headers["X-Cache"] == "miss"

        r1 = client.get("/")
        assert r1.text == "Hello, world!"
        assert r1.status_code == 200
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers
        assert r1.headers["X-Cache"] == "hit"


def test_rule_exclusion() -> None:
    cache = Cache()
    # 404 status is not included, so it should not be cached.
    rules = [Rule(status=200, ttl=60)]
    app = Starlette(
        routes=[Route("/", partial(standard_route, status_code=404))],
        middleware=[Middleware(CacheMiddleware, cache=cache, rules=rules)],
    )

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 404
        assert r.text == "Hello, world!"
        assert "X-Cache" not in r.headers

        r1 = client.get("/")
        assert r1.status_code == 404
        assert r1.text == "Hello, world!"
        assert "X-Cache" not in r.headers


def test_rule_stacking() -> None:
    cache = Cache()
    rules = [
        Rule("/", ttl=0),  # don't cache the root path
        Rule(),
    ]
    app = Starlette(
        routes=[
            Route("/", partial(standard_route, status_code=404)),
            Route("/test", partial(standard_route, status_code=404)),
        ],
        middleware=[Middleware(CacheMiddleware, cache=cache, rules=rules)],
    )

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 404
        assert r.text == "Hello, world!"
        assert "X-Cache" not in r.headers

        r1 = client.get("/")
        assert r1.status_code == 404
        assert r1.text == "Hello, world!"
        assert "X-Cache" not in r.headers

        # /test should be cached
        r = client.get("/test")
        assert r.status_code == 404
        assert r.text == "Hello, world!"
        assert r.headers["X-Cache"] == "miss"

        r1 = client.get("/test")
        assert r1.status_code == 404
        assert r1.text == "Hello, world!"
        assert r1.headers["X-Cache"] == "hit"


@pytest.mark.parametrize(
    "status_code", [201, 202, 307, 308, 400, 401, 403, 500, 502, 503]
)
def test_not_200_ok(status_code: int) -> None:
    """Responses that don't have status code 200 should not be cached."""
    cache = Cache()
    app = Starlette(
        routes=[Route("/", partial(standard_route, status_code=status_code))],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == status_code
        assert r.text == "Hello, world!"
        assert "Expires" not in r.headers
        assert "Cache-Control" not in r.headers
        assert "X-Cache" not in r.headers

        r1 = client.get("/")
        assert "X-Cache" not in r1.headers
        assert ComparableHTTPXResponse(r1) == r


def test_streaming_response() -> None:
    """Streaming responses should not be cached."""
    cache = Cache()

    async def body() -> typing.AsyncIterator[str]:
        yield "Hello, "
        yield "world!"

    async def streaming_route(request: Request) -> Response:
        return StreamingResponse(body())

    app = Starlette(
        routes=[Route("/", streaming_route)],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "X-Cache" not in r.headers

        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "X-Cache" not in r.headers


def test_vary() -> None:
    """
    Sending different values for request headers registered as varying should
    result in different cache entries.
    """
    cache = Cache()

    app = Starlette(
        routes=[Route("/", standard_route)],
        middleware=[
            Middleware(CacheMiddleware, cache=cache),
            Middleware(GZipMiddleware, minimum_size=0),
        ],
    )

    with TestClient(app) as client:
        r = client.get("/", headers={"accept-encoding": "gzip"})
        assert r.headers["X-Cache"] == "miss"
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert r.headers.get("vary", "").lower() == "accept-encoding"
        assert r.headers.get("content-encoding") == "gzip"
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers

        # Different "Accept-Encoding" header => the cached result
        # for "Accept-Encoding: gzip" should not be used.
        r1 = client.get("/", headers={"accept-encoding": "identity"})
        assert r1.headers["X-Cache"] == "miss"
        assert r1.status_code == 200
        assert r1.text == "Hello, world!"
        assert r1.headers.get("vary", "").lower() == "accept-encoding"
        assert "Expires" in r1.headers
        assert "Cache-Control" in r1.headers

        # This "Accept-Encoding" header has already been seen => we should
        # get a cached response.
        r2 = client.get("/", headers={"accept-encoding": "gzip"})
        assert r2.headers["X-Cache"] == "hit"
        assert r2.status_code == 200
        assert r2.text == "Hello, world!"
        assert r.headers.get("vary", "").lower() == "accept-encoding"
        assert r2.headers.get("Content-Encoding") == "gzip"
        assert "Expires" in r2.headers
        assert "Cache-Control" in r2.headers


def test_cookies_in_response_and_cookieless_request() -> None:
    """
    Responses that set cookies shouldn't be cached
    if the request doesn't have cookies.
    """
    cache = Cache()

    async def cookie_route(request: Request) -> Response:
        response = PlainTextResponse("Hello, world!")
        response.set_cookie("session_id", "1234")
        return response

    app = Starlette(
        routes=[Route("/", cookie_route)],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        # first request is not cached
        assert "X-Cache" not in r.headers

        r = client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert r.headers["X-Cache"] == "miss"


def test_duplicate_caching() -> None:
    cache = Cache()
    special_cache = Cache()

    class DuplicateCache(HTTPEndpoint):
        pass

    app = Starlette(
        routes=[
            Route(
                "/duplicate_cache", CacheMiddleware(DuplicateCache, cache=special_cache)
            )
        ],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )

    with TestClient(app) as client, pytest.raises(DuplicateCaching):
        client.get("/duplicate_cache")
