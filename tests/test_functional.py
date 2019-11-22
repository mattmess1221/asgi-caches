import math
import typing

import httpx
import pytest
from caches import Cache
from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route

from asgi_caches.decorators import cache_control, cached
from asgi_caches.exceptions import DuplicateCaching
from asgi_caches.middleware import CacheMiddleware

cache = Cache("locmem://default", ttl=2 * 60)
special_cache = Cache("locmem://special", ttl=60)

pi_calls = 0
e_calls = 0


async def home(request: Request) -> Response:
    return PlainTextResponse("Hello, world!")


@cached(cache)
@cache_control(max_age=30, must_revalidate=True)
class Pi(HTTPEndpoint):
    async def get(self, request: Request) -> Response:
        global pi_calls
        pi_calls += 1
        return JSONResponse({"value": math.pi})


@cached(special_cache)
class Exp(HTTPEndpoint):
    async def get(self, request: Request) -> Response:
        global e_calls
        math.e
        e_calls += 1
        return JSONResponse({"value": math.e})


async def sub_home(request: Request) -> Response:
    return PlainTextResponse("Hello, sub world!")


sub_app = Starlette(
    routes=[Route("/", sub_home)], middleware=[Middleware(CacheMiddleware, cache=cache)]
)


app = Starlette(
    routes=[
        Route("/", home),
        Route("/pi", Pi),
        Route("/exp", Exp),
        Mount("/sub", sub_app),
    ],
)


@pytest.fixture(name="client")
async def fixture_client() -> typing.AsyncIterator[httpx.AsyncClient]:
    client = httpx.AsyncClient(app=app, base_url="http://testserver")
    async with cache, special_cache, client:
        yield client


@pytest.mark.asyncio
async def test_caching(client: httpx.AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    assert r.text == "Hello, world!"
    assert "Expires" not in r.headers
    assert "Cache-Control" not in r.headers

    r = await client.get("/pi")
    assert r.status_code == 200
    assert r.json() == {"value": math.pi}
    assert pi_calls == 1
    assert "Expires" in r.headers
    assert "Cache-Control" in r.headers
    assert r.headers["Cache-Control"] == "max-age=30, must-revalidate"

    r = await client.get("/pi")
    assert pi_calls == 1

    r = await client.get("/sub/")
    assert r.status_code == 200
    assert r.text == "Hello, sub world!"
    assert "Expires" in r.headers
    assert "Cache-Control" in r.headers
    assert r.headers["Cache-Control"] == "max-age=120"

    r = await client.get("/exp")
    assert r.status_code == 200
    assert r.json() == {"value": math.e}
    assert e_calls == 1
    assert "Expires" in r.headers
    assert "Cache-Control" in r.headers
    assert r.headers["Cache-Control"] == "max-age=60"

    r = await client.get("/exp")
    assert e_calls == 1


@pytest.mark.asyncio
async def test_duplicate_caching() -> None:
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

    client = httpx.AsyncClient(app=app, base_url="http://testserver")

    async with cache, special_cache, client:
        with pytest.raises(DuplicateCaching):
            await client.get("/duplicate_cache")
