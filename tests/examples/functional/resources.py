from aiocache import Cache

cache = Cache(ttl=2 * 60)
special_cache = Cache(ttl=60)
