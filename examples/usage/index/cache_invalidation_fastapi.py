from typing import Annotated, Any

from aiocache import Cache
from starlette_caches.helpers import CacheHelper
from starlette_caches.middleware import CacheMiddleware
from fastapi import Depends, FastAPI

app = FastAPI()
app.add_middleware(CacheMiddleware, cache=Cache())


@app.post("/invalidate", status_code=204)
async def invalidate_cache(
    cache_helper: Annotated[CacheHelper, Depends()],
) -> None:
    await cache_helper.invalidate_cache_for("my_endpoint")


@app.get("/endpoint")
async def my_endpoint() -> Any:
    return {"message": "Hello, World!"}
