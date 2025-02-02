import datetime as dt
import gzip
import re
import typing

import httpx
import pytest
from aiocache import Cache
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.endpoints import HTTPEndpoint
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from asgi_caches.exceptions import DuplicateCaching
from asgi_caches.middleware import CacheMiddleware
from asgi_caches.rules import Rule
from tests.utils import CacheSpy, ComparableHTTPXResponse, mock_receive, mock_send


@pytest.mark.asyncio
async def test_cache_response() -> None:
    cache = Cache(ttl=2 * 60)
    spy = CacheSpy(PlainTextResponse("Hello, world!"))
    app = CacheMiddleware(spy, cache=cache)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        assert spy.misses == 0

        r = await client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert spy.misses == 1

        assert "Expires" in r.headers
        expires_fmt = "%a, %d %b %Y %H:%M:%S GMT"
        expires = dt.datetime.strptime(r.headers["Expires"], expires_fmt).replace(
            tzinfo=dt.timezone.utc
        )
        delta: dt.timedelta = expires - dt.datetime.now(tz=dt.timezone.utc)
        assert delta.total_seconds() == pytest.approx(120, rel=1e-2)
        assert "Cache-Control" in r.headers
        assert r.headers["Cache-Control"] == "max-age=120"

        r1 = await client.get("/")
        assert spy.misses == 1
        assert ComparableHTTPXResponse(r1) == r

        r2 = await client.get("/")
        assert spy.misses == 1
        assert ComparableHTTPXResponse(r2) == r


@pytest.mark.asyncio
async def test_not_http() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        assert scope["type"] == "lifespan"

    cache = Cache()
    app = CacheMiddleware(app, cache=cache)
    await app({"type": "lifespan"}, mock_receive, mock_send)


@pytest.mark.asyncio
async def test_non_cachable_request() -> None:
    cache = Cache()
    spy = CacheSpy(PlainTextResponse("Hello, world!"))
    app = CacheMiddleware(spy, cache=cache)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        assert spy.misses == 0

        r = await client.post("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert "Expires" not in r.headers
        assert "Cache-Control" not in r.headers
        assert spy.misses == 1

        r1 = await client.post("/")
        assert ComparableHTTPXResponse(r1) == r
        assert spy.misses == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "match_path"),
    [
        ("/cache", "/cache"),
        ("/cache/subpath", re.compile(r"\/cache\/.+")),
    ],
)
async def test_cache_match_paths(path: str, match_path: re.Pattern) -> None:
    cache = Cache()
    spy = CacheSpy(PlainTextResponse("Hello, world!"))
    app = CacheMiddleware(spy, cache=cache, rules=[Rule(match_path)])
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        assert spy.misses == 0

        r = await client.get(path)
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert spy.misses == 1

        r1 = await client.get(path)
        assert r1.status_code == 200
        assert r1.text == "Hello, world!"
        assert spy.misses == 1

        r2 = await client.get("/")
        assert r2.status_code == 200
        assert r2.text == "Hello, world!"
        assert spy.misses == 2


@pytest.mark.asyncio
async def test_cache_deny_paths() -> None:
    cache = Cache()
    spy = CacheSpy(PlainTextResponse("Hello, world!"))
    app = CacheMiddleware(spy, cache=cache, rules=[Rule("/no_cache", ttl=0), Rule()])
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        assert spy.misses == 0

        r = await client.get("/no_cache")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert spy.misses == 1

        r1 = await client.get("/no_cache")
        assert r1.status_code == 200
        assert r1.text == "Hello, world!"
        assert spy.misses == 2


@pytest.mark.asyncio
async def test_use_cached_head_response_on_get() -> None:
    """
    Making a HEAD request should use the cached response for future GET requests.
    """
    cache = Cache()
    spy = CacheSpy(PlainTextResponse("Hello, world!"))
    app = CacheMiddleware(spy, cache=cache)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        assert spy.misses == 0

        r = await client.head("/")
        assert not r.text
        assert r.status_code == 200
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers
        assert spy.misses == 1

        r1 = await client.get("/")
        assert r1.text == "Hello, world!"
        assert r1.status_code == 200
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers
        assert spy.misses == 1


@pytest.mark.asyncio
async def test_rule_exclusion() -> None:
    cache = Cache()
    spy = CacheSpy(PlainTextResponse("Hello, world!", status_code=404))
    # 404 status is not included, so it should not be cached.
    rules = [Rule(status=200, ttl=60)]
    app = CacheMiddleware(spy, cache=cache, rules=rules)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        assert spy.misses == 0

        r = await client.get("/")
        assert r.status_code == 404
        assert r.text == "Hello, world!"
        assert spy.misses == 1

        r1 = await client.get("/")
        assert r1.status_code == 404
        assert r1.text == "Hello, world!"
        assert spy.misses == 2


@pytest.mark.asyncio
async def test_rule_stacking() -> None:
    cache = Cache()
    spy = CacheSpy(PlainTextResponse("Hello, world!", status_code=404))
    rules = [
        Rule("/", ttl=0),  # don't cache the root path
        Rule(),
    ]
    app = CacheMiddleware(spy, cache=cache, rules=rules)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        assert spy.misses == 0

        r = await client.get("/")
        assert r.status_code == 404
        assert r.text == "Hello, world!"
        assert spy.misses == 1

        r1 = await client.get("/")
        assert r1.status_code == 404
        assert r1.text == "Hello, world!"
        assert spy.misses == 2

        # /test should be cached
        r = await client.get("/test")
        assert r.status_code == 404
        assert r.text == "Hello, world!"
        assert spy.misses == 3

        r1 = await client.get("/test")
        assert r1.status_code == 404
        assert r1.text == "Hello, world!"
        assert spy.misses == 3


@pytest.mark.parametrize(
    "status_code", (201, 202, 307, 308, 400, 401, 403, 500, 502, 503)
)
@pytest.mark.asyncio
async def test_not_200_ok(status_code: int) -> None:
    """Responses that don't have status code 200 should not be cached."""
    cache = Cache()
    spy = CacheSpy(PlainTextResponse("Hello, world!", status_code=status_code))
    app = CacheMiddleware(spy, cache=cache)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        r = await client.get("/")
        assert r.status_code == status_code
        assert r.text == "Hello, world!"
        assert "Expires" not in r.headers
        assert "Cache-Control" not in r.headers
        assert spy.misses == 1

        r1 = await client.get("/")
        assert ComparableHTTPXResponse(r1) == r
        assert spy.misses == 2


@pytest.mark.asyncio
async def test_streaming_response() -> None:
    """Streaming responses should not be cached."""
    cache = Cache()

    async def body() -> typing.AsyncIterator[str]:
        yield "Hello, "
        yield "world!"

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = StreamingResponse(body())
        await response(scope, receive, send)

    spy = CacheSpy(app)
    app = CacheMiddleware(spy, cache=cache)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        assert spy.misses == 0

        r = await client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert spy.misses == 1

        r = await client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert spy.misses == 2


@pytest.mark.asyncio
async def test_vary() -> None:
    """
    Sending different values for request headers registered as varying should
    result in different cache entries.
    """
    cache = Cache()

    async def gzippable_app(scope: Scope, receive: Receive, send: Send) -> None:
        headers = Headers(scope=scope)

        if "gzip" in headers.getlist("accept-encoding"):
            body = gzip.compress(b"Hello, world!")
            response = PlainTextResponse(
                content=body,
                headers={"Content-Encoding": "gzip", "Content-Length": str(len(body))},
            )
        else:
            response = PlainTextResponse("Hello, world!")

        response.headers["Vary"] = "Accept-Encoding"
        await response(scope, receive, send)

    spy = CacheSpy(gzippable_app)
    app = CacheMiddleware(spy, cache=cache)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        r = await client.get("/", headers={"accept-encoding": "gzip"})
        assert spy.misses == 1
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert r.headers["content-encoding"] == "gzip"
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers

        # Different "Accept-Encoding" header => the cached result
        # for "Accept-Encoding: gzip" should not be used.
        r1 = await client.get("/", headers={"accept-encoding": "identity"})
        assert spy.misses == 2
        assert r1.status_code == 200
        assert r1.text == "Hello, world!"
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers

        # This "Accept-Encoding" header has already been seen => we should
        # get a cached response.
        r2 = await client.get("/", headers={"accept-encoding": "gzip"})
        assert spy.misses == 2
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert r2.headers["Content-Encoding"] == "gzip"
        assert "Expires" in r.headers
        assert "Cache-Control" in r.headers


@pytest.mark.asyncio
async def test_cookies_in_response_and_cookieless_request() -> None:
    """
    Responses that set cookies shouldn't be cached
    if the request doesn't have cookies.
    """
    cache = Cache()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = PlainTextResponse("Hello, world!")
        response.set_cookie("session_id", "1234")
        await response(scope, receive, send)

    spy = CacheSpy(app)
    app = CacheMiddleware(spy, cache=cache)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, client:
        r = await client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert spy.misses == 1

        r = await client.get("/")
        assert r.status_code == 200
        assert r.text == "Hello, world!"
        assert spy.misses == 2


@pytest.mark.asyncio
async def test_duplicate_caching() -> None:
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

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )

    async with cache, special_cache, client:
        with pytest.raises(DuplicateCaching):
            await client.get("/duplicate_cache")
