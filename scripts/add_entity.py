#!/usr/bin/env python3
"""
Add a single PySpring entity (component, controller, properties, bean-collection,
event, middleware, scheduled task, or shutdown handler) to an existing project.

Usage:
    python add_entity.py <kind> <ClassName> [--project-root .] [--prefix /api/...]

Examples:
    python add_entity.py component UserService
    python add_entity.py controller UserController --prefix /api/users
    python add_entity.py properties DatabaseProperties
    python add_entity.py bean-collection InfrastructureBeans
    python add_entity.py event UserCreatedEvent
    python add_entity.py middleware AuthMiddleware
    python add_entity.py scheduled HealthCheckService
    python add_entity.py shutdown AppShutdownHandler

The file is written in snake_case under the conventional subdirectory of
<project-root>/src/. The script refuses to overwrite existing files.

This is a *starter* — review the output and customize. Scripts can't guess your
business logic, they can only place correct boilerplate.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from textwrap import dedent


VALID_KINDS = (
    "component",
    "controller",
    "properties",
    "bean-collection",
    "event",
    "middleware",
    "scheduled",
    "shutdown",
)


def to_snake(name: str) -> str:
    """CamelCase → snake_case. Handles runs of caps: `APIKeyMiddleware` → `api_key_middleware`."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def default_prefix(class_name: str) -> str:
    """`UserController` → `/api/users`. Best-effort — user can override with --prefix."""
    base = class_name
    for suffix in ("Controller", "RestController", "Rest"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    # UserController → /api/users (pluralize naively with "s")
    return f"/api/{to_snake(base)}s"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def render_component(class_name: str) -> str:
    return dedent(
        f'''\
        """{class_name} — business-logic component.

        Replace the placeholder fields and methods with your actual dependencies
        and operations. Keep setup that reads injected fields inside
        `post_construct`, never inside `__init__`.
        """
        from py_spring_core import Component


        class {class_name}(Component):
            # Declare injected dependencies as class-level type annotations:
            #     other_service: OtherService
            #     some_properties: SomeProperties

            def post_construct(self) -> None:
                """Runs after dependencies are injected. Use instead of __init__."""
                pass

            def pre_destroy(self) -> None:
                """Runs during shutdown, in reverse initialization order."""
                pass
        '''
    )


def render_controller(class_name: str, prefix: str) -> str:
    return dedent(
        f'''\
        """{class_name} — REST routes for `{prefix}`.

        Controllers should stay thin: inject services and delegate. Keep path
        params, request bodies, and response shapes clearly typed — PySpring
        rides on FastAPI, so Pydantic bodies and path parameter type conversion
        all work the same way.
        """
        from py_spring_core import RestController
        from py_spring_core.core.entities.controllers.rest_controller import (
            GetMapping,
            PostMapping,
            PutMapping,
            DeleteMapping,
            PatchMapping,
        )


        class {class_name}(RestController):
            class Config:
                prefix = "{prefix}"

            # Inject services here, e.g.:
            #     user_service: UserService

            @GetMapping("/")
            def index(self):
                return {{"items": []}}

            @GetMapping("/{{item_id}}")
            def get(self, item_id: int):
                return {{"id": item_id}}
        '''
    )


def render_properties(class_name: str) -> str:
    # Default __key__ = class name without "Properties", snake_cased.
    key_base = class_name
    if key_base.endswith("Properties"):
        key_base = key_base[: -len("Properties")]
    key = to_snake(key_base) or "app"
    return dedent(
        f'''\
        """{class_name} — typed configuration mapped from `application-properties.json`.

        The `__key__` must match a top-level section in the properties file.
        Pydantic validates fields at startup, so a missing/wrong-type value
        fails loudly rather than at request time.
        """
        from py_spring_core import Properties


        class {class_name}(Properties):
            __key__ = "{key}"

            # Declare your config fields:
            #     host: str
            #     port: int = 5432
            #     name: str = "default_name"
        '''
    )


def render_bean_collection(class_name: str) -> str:
    return dedent(
        f'''\
        """{class_name} — factories for third-party objects that cannot extend Component.

        Every `create_*` method must have a return type annotation — that's the
        type PySpring uses to register the bean in the DI container.
        """
        from py_spring_core import BeanCollection


        class {class_name}(BeanCollection):
            # Properties are injected BEFORE create_* methods run, so you can safely
            # read them when building the bean.
            # Example:
            #     redis_properties: RedisProperties
            #
            #     def create_redis_client(self) -> Redis:
            #         return Redis(
            #             host=self.redis_properties.host,
            #             port=self.redis_properties.port,
            #         )
            pass
        '''
    )


def render_event(class_name: str) -> str:
    return dedent(
        f'''\
        """{class_name} — application event (Pydantic model).

        Events are published by `ApplicationEventPublisher.publish(...)` and
        handled by any component method decorated with `@EventListener({class_name})`.
        Name events in the past tense — they represent something that *has
        happened*, not a command for something to happen.
        """
        from py_spring_core.core.entities.event.application_event import ApplicationEvent


        class {class_name}(ApplicationEvent):
            # Declare the event payload fields — Pydantic validation applies.
            pass
        '''
    )


def render_middleware(class_name: str) -> str:
    return dedent(
        f'''\
        """{class_name} — async middleware intercepting every request.

        Return `None` from `process_request` to continue to the next middleware
        or the route handler. Return a `Response` to short-circuit.

        Remember: middleware is NOT auto-registered. It must be added to a
        `MiddlewareConfiguration` subclass via `registry.add_middleware(...)`.
        """
        from fastapi import Request, Response

        from py_spring_core.core.entities.middlewares.middleware import Middleware


        class {class_name}(Middleware):
            def should_skip(self, request: Request) -> bool:
                """Return True to bypass this middleware for the given request."""
                return False

            async def process_request(self, request: Request) -> Response | None:
                # Do your pre-processing here.
                # Return Response(...) to short-circuit, or None to continue.
                return None
        '''
    )


def render_scheduled(class_name: str) -> str:
    return dedent(
        f'''\
        """{class_name} — scheduled tasks.

        Requires the `pyspring-scheduler` plugin. Your `main.py` must pass
        `entity_providers=[provide_scheduler()]` when constructing
        `PySpringApplication`, otherwise the decorators silently do nothing.
        """
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        from py_spring_core import Component
        from pyspring_scheduler import Scheduled


        class {class_name}(Component):
            # Inject services you want to call from scheduled jobs.

            @Scheduled(trigger=IntervalTrigger(seconds=60))
            def tick(self) -> None:
                """Example: every 60 seconds."""
                pass

            @Scheduled(trigger=CronTrigger(hour=2, minute=0))
            def nightly(self) -> None:
                """Example: once a day at 02:00 (timezone from scheduler config)."""
                pass
        '''
    )


def render_shutdown(class_name: str) -> str:
    return dedent(
        f'''\
        """{class_name} — application-level graceful shutdown.

        Use `pre_destroy()` on individual components for their local cleanup.
        Use this handler for cross-component ordering — "drain the queue before
        closing the DB it writes to."
        """
        from py_spring_core import Component
        from py_spring_core.core.entities.graceful_shutdown_handler import (
            GracefulShutdownHandler,
            ShutdownType,
        )


        class {class_name}(GracefulShutdownHandler, Component):
            # Inject any components whose shutdown needs coordinating, e.g.:
            #     database_service: DatabaseService
            #     queue_service: QueueService

            def on_shutdown(self, shutdown_type: ShutdownType) -> None:
                """Normal path — coordinate cleanup."""
                print(f"Shutdown triggered by: {{shutdown_type}}")

            def on_timeout(self) -> None:
                """`shutdown_config.timeout_seconds` was exceeded."""
                print("Shutdown timed out — forcing exit")

            def on_error(self, error: Exception) -> None:
                """A shutdown step raised."""
                print(f"Error during shutdown: {{error}}")
        '''
    )


# ---------------------------------------------------------------------------
# Placement rules
# ---------------------------------------------------------------------------


KIND_TO_SUBDIR = {
    "component": "src/services",
    "controller": "src/controllers",
    "properties": "src/properties",
    "bean-collection": "src/beans",
    "event": "src/events",
    "middleware": "src/middleware",
    "scheduled": "src/services",
    "shutdown": "src",
}


def render(kind: str, class_name: str, prefix: str | None) -> str:
    if kind == "component":
        return render_component(class_name)
    if kind == "controller":
        return render_controller(class_name, prefix or default_prefix(class_name))
    if kind == "properties":
        return render_properties(class_name)
    if kind == "bean-collection":
        return render_bean_collection(class_name)
    if kind == "event":
        return render_event(class_name)
    if kind == "middleware":
        return render_middleware(class_name)
    if kind == "scheduled":
        return render_scheduled(class_name)
    if kind == "shutdown":
        return render_shutdown(class_name)
    raise ValueError(f"unknown kind: {kind}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add a PySpring entity to an existing project."
    )
    parser.add_argument("kind", choices=VALID_KINDS, help="Entity type")
    parser.add_argument("class_name", help="CamelCase class name (e.g. UserService)")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Project root containing src/ (default: current directory)",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Route prefix for controllers (default: derived from class name)",
    )
    args = parser.parse_args(argv)

    if not args.class_name[0].isupper():
        print("error: class name should be CamelCase", file=sys.stderr)
        return 2

    subdir = args.project_root / KIND_TO_SUBDIR[args.kind]
    if not (args.project_root / "src").is_dir():
        print(
            f"error: {args.project_root / 'src'} does not exist. "
            "Run scaffold_project.py first, or point --project-root at a valid PySpring project.",
            file=sys.stderr,
        )
        return 1

    subdir.mkdir(parents=True, exist_ok=True)
    init_file = subdir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")

    filename = to_snake(args.class_name) + ".py"
    target = subdir / filename
    if target.exists():
        print(f"error: {target} already exists. Refusing to overwrite.", file=sys.stderr)
        return 1

    target.write_text(render(args.kind, args.class_name, args.prefix))
    print(f"Created {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
