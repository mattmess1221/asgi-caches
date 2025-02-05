from __future__ import annotations

import importlib
import math
import typing

import pytest
from starlette.testclient import TestClient

from .utils import cleanup_new_imports

if typing.TYPE_CHECKING:
    from starlette.types import ASGIApp

# TIP: use 'pytest -k <id>' to run tests for a given example application only.
EXAMPLES = [
    pytest.param("tests.examples.functional.starlette", id="starlette"),
]


@pytest.fixture(name="app", params=EXAMPLES)
def fixture_app(request: pytest.FixtureRequest) -> typing.Iterator[ASGIApp]:
    with cleanup_new_imports():
        module: typing.Any = importlib.import_module(request.param)
        yield module.app


@pytest.fixture(name="client")
def fixture_client(app: ASGIApp) -> typing.Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def test_caching(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.text == "Hello, world!"
    assert "Expires" not in r.headers
    assert "Cache-Control" not in r.headers
    assert "X-Cache" not in r.headers

    r = client.get("/")
    assert "X-Cache" not in r.headers

    r = client.get("/pi")
    assert r.status_code == 200
    assert r.json() == {"value": math.pi}
    assert r.headers["X-Cache"] == "miss"
    assert "Expires" in r.headers
    assert "Cache-Control" in r.headers
    assert r.headers["Cache-Control"] == "max-age=30, must-revalidate"

    r = client.get("/pi")
    assert r.headers["X-Cache"] == "hit"

    r = client.get("/sub/")
    assert r.status_code == 200
    assert r.text == "Hello, sub world!"
    assert r.headers["X-Cache"] == "miss"
    assert "Expires" in r.headers
    assert "Cache-Control" in r.headers
    assert r.headers["Cache-Control"] == "max-age=120"

    r = client.get("/sub/")
    assert r.headers["X-Cache"] == "hit"

    r = client.get("/exp")
    assert r.status_code == 200
    assert r.json() == {"value": math.e}
    assert r.headers["X-Cache"] == "miss"
    assert "Expires" in r.headers
    assert "Cache-Control" in r.headers
    assert r.headers["Cache-Control"] == "max-age=60"

    r = client.get("/exp")
    assert r.headers["X-Cache"] == "hit"
