import pytest
from aiocache import Cache
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from asgi_caches.middleware import CacheMiddleware
from tests.utils import override_log_level


def test_logs_debug(capsys: pytest.CaptureFixture) -> None:
    cache = Cache(ttl=2 * 60)
    app = Starlette(
        routes=[Route("/", PlainTextResponse("Hello, world!"))],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )

    with TestClient(app) as client, override_log_level("debug"):
        client.get("/")
        client.get("/")

    stderr = capsys.readouterr().err
    miss_line, store_line, hit_line, *_ = stderr.split("\n")
    assert "cache_lookup MISS" in miss_line
    assert "store_in_cache max_age=120" in store_line
    assert "cache_lookup HIT" in hit_line
    assert "get_from_cache request.url='http://testserver/" not in stderr


def test_logs_trace(capsys: pytest.CaptureFixture) -> None:
    cache = Cache(ttl=2 * 60)
    app = Starlette(
        routes=[Route("/", PlainTextResponse("Hello, world!"))],
        middleware=[Middleware(CacheMiddleware, cache=cache)],
    )

    with TestClient(app) as client, override_log_level("trace"):
        client.get("/")

    stderr = capsys.readouterr().err
    assert "cache_lookup MISS" in stderr
    assert "get_from_cache request.url='http://testserver/" in stderr
