import re
import typing
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import Response

T = typing.TypeVar("T")

MaybeIter = typing.Union[T, typing.Iterable[T]]
MaybePattern = typing.Union[str, re.Pattern]
MatchType = typing.Union[MaybePattern, MaybeIter[MaybePattern]]
StatusType = MaybeIter[int]


@dataclass
class Rule:
    match: MatchType = "*"
    status: typing.Optional[StatusType] = None
    ttl: typing.Optional[float] = None


def request_matches_rule(
    rule: Rule,
    *,
    request: Request,
) -> bool:
    match = rule.match
    if isinstance(match, (str, re.Pattern)):
        match = [match]
    for item in match:
        if isinstance(item, re.Pattern):
            if item.match(request.url.path):
                return True
        elif item == "*" or item == request.url.path:
            return True
    return False


def response_matches_rule(rule: Rule, *, request: Request, response: Response) -> bool:
    if not request_matches_rule(rule, request=request):
        return False

    if rule.status is not None:
        statuses = [rule.status] if isinstance(rule.status, int) else rule.status
        if response.status_code not in statuses:
            return False
    return True


def get_rule_matching_request(
    rules: typing.Sequence[Rule], *, request: Request
) -> typing.Optional[Rule]:
    return next(
        (rule for rule in rules if request_matches_rule(rule, request=request)), None
    )


def get_rule_matching_response(
    rules: typing.Sequence[Rule],
    *,
    request: Request,
    response: Response,
) -> typing.Optional[Rule]:
    return next(
        (
            rule
            for rule in rules
            if response_matches_rule(rule, request=request, response=response)
        ),
        None,
    )
