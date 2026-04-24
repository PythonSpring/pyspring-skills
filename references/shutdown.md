# Graceful Shutdown

Graceful shutdown = clean up properly when the application receives SIGINT (Ctrl+C) or SIGTERM (container orchestrator killing the pod). Without it, in-flight requests get truncated, database connections leak, queued writes vanish.

PySpring gives you two layers:

1. **`pre_destroy()` on every `Component`** — runs during shutdown, in reverse initialization order. Use for *component-local* cleanup (close a cursor, drain a queue, flush a buffer).
2. **`GracefulShutdownHandler`** — a single application-level hook for cross-cutting shutdown logic that coordinates between components.

Use both together: `pre_destroy` for each component's own resources, `GracefulShutdownHandler` for "send a final heartbeat, then wait for in-flight jobs, then log the reason."

## The handler

Implement `GracefulShutdownHandler` on a `Component`. It must provide three methods:

```python
from py_spring_core import Component
from py_spring_core.core.entities.graceful_shutdown_handler import (
    GracefulShutdownHandler,
    ShutdownType,
)


class AppShutdownHandler(GracefulShutdownHandler, Component):
    database_service: DatabaseService    # DI works here — it's a Component
    queue_service: QueueService

    def on_shutdown(self, shutdown_type: ShutdownType) -> None:
        # Normal path — clean exit.
        print(f"Shutdown triggered by: {shutdown_type}")
        self.queue_service.drain()
        self.database_service.close()

    def on_timeout(self) -> None:
        # Shutdown took longer than shutdown_config.timeout_seconds — force-close.
        print("Shutdown timed out — forcing exit")
        self.database_service.force_close()

    def on_error(self, error: Exception) -> None:
        # Something in on_shutdown raised.
        print(f"Error during shutdown: {error}")
```

Multiple inheritance (`GracefulShutdownHandler, Component`) is deliberate — PySpring needs `Component` to register and inject the class, and `GracefulShutdownHandler` to recognize it as the shutdown hook.

## `ShutdownType` — know why you're shutting down

| Value | Trigger |
| --- | --- |
| `MANUAL` | Programmatic (something called the shutdown API directly) |
| `SIGTERM` | SIGTERM received — typical for Docker, Kubernetes, systemd |
| `TIMEOUT` | Shutdown already in progress and overran |
| `ERROR` | A fatal error is causing shutdown |
| `UNKNOWN` | Unspecified source |

Branch on this when cleanup differs by source — e.g., send a "clean stop" heartbeat to a service mesh on `SIGTERM` but not on `ERROR`.

## Shutdown timeout

Configure it in `app-config.json`:

```json
{
  "shutdown_config": {
    "timeout_seconds": 30.0,
    "enabled": true
  }
}
```

If your handler + every component's `pre_destroy` together exceed this, `on_timeout()` fires. Kubernetes' default `terminationGracePeriodSeconds` is 30s, so matching 30 here works for most deployments — bump both in lockstep if you need more.

## Pattern: drain then close

A typical server shutdown wants to:

1. Stop accepting new requests (Uvicorn handles this).
2. Let in-flight requests finish.
3. Drain background queues.
4. Close connections in the right order (workers before pools).

```python
class AppShutdownHandler(GracefulShutdownHandler, Component):
    task_queue: TaskQueue
    db: Database

    def on_shutdown(self, shutdown_type: ShutdownType) -> None:
        self.task_queue.stop_accepting()
        self.task_queue.wait_until_empty(max_wait=20.0)
        self.db.close()
```

The `max_wait` inside `wait_until_empty` should be less than `shutdown_config.timeout_seconds` — leave headroom so `on_timeout` fires *before* the orchestrator kills you, not after.

## `pre_destroy` vs `GracefulShutdownHandler`

Use `pre_destroy` for purely local cleanup that has no cross-component dependencies:

```python
class FileLogger(Component):
    def post_construct(self) -> None:
        self.file = open("app.log", "a")

    def pre_destroy(self) -> None:
        self.file.close()
```

Use `GracefulShutdownHandler` when the order across components matters — "flush the queue *before* closing the DB it writes to." `pre_destroy` order is *reverse initialization order*, which is usually what you want but not always; if the ordering is subtle, centralize it in the handler.
