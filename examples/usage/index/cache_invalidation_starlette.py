from aiocache import Cache
from starlette_caches.helpers import CacheHelper
from starlette_caches.middleware import CacheMiddleware
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


async def invalidate_cache(request: Request) -> Response:
    cache_helper = CacheHelper(request)
    await cache_helper.invalidate_cache_for("my_endpoint")
    return Response(status_code=204)


async def my_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"message": "Hello, World!"})


app = Starlette(
    routes=[
        Route("/invalidate", invalidate_cache, methods=["POST"]),
        Route("/", my_endpoint, name="my_endpoint", methods=["GET"]),
    ],
    middleware=[
        Middleware(CacheMiddleware, cache=Cache()),
    ],
)
