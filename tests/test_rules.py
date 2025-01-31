import re
import typing

import pytest
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import Response

from asgi_caches.rules import (
    Rule,
    get_rule_matching_request,
    get_rule_matching_response,
    request_matches_rule,
    response_matches_rule,
)


def mock_request(path: str) -> Request:
    return Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": {},
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
            "root_path": "",
            "app": None,
            "url": URL(path),
        }
    )


@pytest.mark.parametrize("match", ["/test", re.compile(r"^/test")])
def test_request_matches_rule(match: typing.Union[str, re.Pattern]) -> None:
    rule = Rule(match=match)
    request = mock_request("/test")
    assert request_matches_rule(rule, request=request)


def test_request_matches_rule_with_wildcard() -> None:
    rule = Rule(match="*")
    request = mock_request("/any")
    assert request_matches_rule(rule, request=request)


def test_request_does_not_match_rule() -> None:
    rule = Rule(match="/test")
    request = mock_request("/other")
    assert not request_matches_rule(rule, request=request)


def test_response_matches_rule_with_status() -> None:
    rule = Rule(match="/test", status=200)
    request = mock_request("/test")
    response = Response(status_code=200)
    assert response_matches_rule(rule, request=request, response=response)


def test_response_does_not_match_rule_with_status() -> None:
    rule = Rule(match="/test", status=404)
    request = mock_request("/test")
    response = Response(status_code=200)
    assert not response_matches_rule(rule, request=request, response=response)


def test_get_rule_matching_request() -> None:
    rules = [Rule(match="/test1"), Rule(match="/test2")]
    request = mock_request("/test2")
    rule = get_rule_matching_request(rules, request=request)
    assert rule is not None
    assert rule.match == "/test2"


def test_get_rule_matching_response() -> None:
    rules = [Rule(match="/test1", status=200), Rule(match="/test2", status=404)]
    request = mock_request("/test2")
    response = Response(status_code=404)
    rule = get_rule_matching_response(rules, request=request, response=response)
    assert rule is not None
    assert rule.match == "/test2"
    assert rule.status == 404
