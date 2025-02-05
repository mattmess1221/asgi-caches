import importlib
import typing

import pytest
from starlette.testclient import TestClient
from starlette.types import ASGIApp

from .utils import cleanup_new_imports

EXAMPLES = [
    pytest.param("tests.examples.invalidation.fastapi", id="fastapi"),
    pytest.param("tests.examples.invalidation.starlette", id="starlette"),
]


@pytest.fixture(name="app", params=EXAMPLES)
def app_factory(request: pytest.FixtureRequest) -> typing.Iterator[ASGIApp]:
    with cleanup_new_imports():
        module: typing.Any = importlib.import_module(request.param)
        yield module.app


@pytest.fixture(name="client")
def client_factory(app: ASGIApp) -> typing.Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def test_response_auto_invalidation(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.text == "Hello, GET!"
    assert r.headers.get("X-Cache") == "miss"

    r = client.post("/")
    assert r.status_code == 200
    assert r.text == "Hello, POST!"
    assert "X-Cache" not in r.headers

    r = client.get("/")
    assert r.status_code == 200
    assert r.text == "Hello, GET!"
    assert r.headers.get("X-Cache") == "miss"


def test_response_manual_invalidation(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.text == "Hello, GET!"
    assert r.headers["X-Cache"] == "miss"

    r = client.get("/")
    assert r.headers["X-Cache"] == "hit"

    r = client.post("/invalidate")
    assert r.status_code == 204, r.text

    r = client.get("/")
    assert r.text == "Hello, GET!"
    assert r.headers["X-Cache"] == "miss"


def test_response_invalidation_noop(client: TestClient) -> None:
    r = client.post("/invalidate")
    assert r.status_code == 204, r.text

    r = client.get("/")
    assert r.status_code == 200
    assert r.text == "Hello, GET!"
    assert r.headers["X-Cache"] == "miss"
