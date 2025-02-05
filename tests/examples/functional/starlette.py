from __future__ import annotations

import math
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route

from asgi_caches.decorators import cache_control
from asgi_caches.middleware import CacheMiddleware

from .resources import cache, special_cache

if TYPE_CHECKING:
    from starlette.requests import Request


async def home(request: Request) -> Response:
    return PlainTextResponse("Hello, world!")


@cache_control(max_age=30, must_revalidate=True)
class Pi(HTTPEndpoint):
    async def get(self, request: Request) -> Response:
        return JSONResponse({"value": math.pi})


class Exp(HTTPEndpoint):
    async def get(self, request: Request) -> Response:
        return JSONResponse({"value": math.e})


async def sub_home(request: Request) -> Response:
    return PlainTextResponse("Hello, sub world!")


sub_app = Starlette(routes=[Route("/", sub_home)])


app = Starlette(
    routes=[
        Route("/", home),
        Route("/pi", CacheMiddleware(Pi, cache=cache)),
        Route("/exp", CacheMiddleware(Exp, cache=special_cache)),
        Mount("/sub", CacheMiddleware(sub_app, cache=cache)),
    ],
)
