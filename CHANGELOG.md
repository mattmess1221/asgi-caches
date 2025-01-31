# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Unreleased

### Changed

- BREAKING: Switch to [aiocache](https://pypi.org/project/aiocache) for caching backends. This enables you to choose between memory, redis, or memcached as backends, as well as customize how the cached data is serialized.

### Added

- Add `rules` option for CacheMiddleware to allow for more fine-grained control over which paths are cached.

### Internal

- Switch build backend to hatchling.
- Run tests using github actions, with a tox config for running locally.

## Older releases

Older changes can be found in the original project's [changelog](https://github.com/florimondmanca/asgi-caches/blob/master/CHANGELOG.md).
