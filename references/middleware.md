# Middleware

Middleware intercepts HTTP requests before they reach controllers. Use it for cross-cutting concerns — authentication, logging, CORS, rate limiting, request IDs — anything that applies to many routes and shouldn't live in each controller.

## Writing a middleware

Extend `Middleware` and implement the async `process_request` method. Return `None` to let the request continue to the next middleware (or the route handler); return a `Response` to short-circuit with that response immediately.

```python
from fastapi import Request, Response
from py_spring_core.core.entities.middlewares.middleware import Middleware


class LoggingMiddleware(Middleware):
    async def process_request(self, request: Request) -> Response | None:
        print(f"{request.method} {request.url}")
        return None  # Continue


class ApiKeyMiddleware(Middleware):
    async def process_request(self, request: Request) -> Response | None:
        if not request.headers.get("X-API-Key"):
            return Response(content="Missing API key", status_code=401)
        return None
```

`Middleware` is a DI-managed class — it can declare `Component`/`Properties`/bean fields and they'll be injected before any request is processed.

## Skipping routes conditionally

Override `should_skip(request)` to bypass the middleware for certain requests. Returns `False` by default.

```python
class AuthMiddleware(Middleware):
    def should_skip(self, request: Request) -> bool:
        # Let health checks and docs through without auth
        path = request.url.path
        return path in ("/health", "/docs", "/redoc", "/openapi.json")

    async def process_request(self, request: Request) -> Response | None:
        if not request.headers.get("Authorization"):
            return Response(content="Unauthorized", status_code=401)
        return None
```

## Registering middleware

Middleware is *not* picked up automatically. You register it by subclassing `MiddlewareConfiguration` and implementing `configure_middlewares`:

```python
from py_spring_core.core.entities.middlewares.middleware_registry import (
    MiddlewareConfiguration,
    MiddlewareRegistry,
)


class AppMiddlewareConfiguration(MiddlewareConfiguration):
    def configure_middlewares(self, registry: MiddlewareRegistry) -> None:
        registry.add_middleware(LoggingMiddleware)
        registry.add_middleware(AuthMiddleware)
```

PySpring discovers the `MiddlewareConfiguration` subclass automatically — no manual wiring in `main.py`. Just put it anywhere inside the scanned source tree.

## Ordering

The registry builds a stack. Registration order matters because of how stacks unwrap:

| Method | Effect |
| --- | --- |
| `add_middleware(cls)` | Append at the end |
| `add_at_index(i, cls)` | Insert at a specific position |
| `add_before(target, cls)` | Insert immediately before `target` |
| `add_after(target, cls)` | Insert immediately after `target` |

**The counter-intuitive bit**: the *last* middleware added is the *outermost* — it runs first on the request path and last on the response path. So if you register `[A, B, C]`, the order on the way in is `C → B → A → route`, and on the way out is `route → A → B → C`.

Practical consequence: if you want logging to capture *everything* (including auth rejections), register `LoggingMiddleware` *after* `AuthMiddleware`. Putting logging first means auth rejections never reach it.

```python
def configure_middlewares(self, registry: MiddlewareRegistry) -> None:
    registry.add_middleware(AuthMiddleware)        # inner
    registry.add_middleware(LoggingMiddleware)     # outer — wraps Auth, sees all rejections
```

Or build it explicitly with `add_before` / `add_after` when the intent needs to read clearly.

## Common pitfalls

- **Forgetting to register** — writing a `Middleware` subclass and never referencing it in `MiddlewareConfiguration`. The class does nothing on its own.
- **Confusing order** — last-added runs first. When in doubt, add a `print` to each middleware's `process_request` and watch the order.
- **Blocking I/O in `process_request`** — it's async. Use async clients (`httpx`, `asyncpg`, `aioredis`) for downstream calls, or offload to a thread pool with `run_in_executor`.
- **Returning the wrong sentinel** — you must return `None` to continue. Returning nothing (implicit `None`) works, but returning anything truthy that isn't a `Response` will break the pipeline.
