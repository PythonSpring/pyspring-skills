---
name: pyspring
description: Build and maintain PySpring (py-spring-core) Python web applications. Use whenever the user mentions PySpring, py_spring_core, or requests that fit the framework — Spring Boot-style dependency injection in Python, class-based REST controllers built on FastAPI, Pydantic-backed configuration via Properties/`__key__`, BeanCollection factories, ApplicationEvent pub/sub, middleware pipelines, @Scheduled tasks, or GracefulShutdownHandler. Trigger even if the user just says "start a new Python web app with DI like Spring Boot" or shares code with `Component`, `Properties`, `RestController`, `BeanCollection`, `post_construct`, `pre_destroy`, `PySpringApplication`, `@GetMapping`, `@EventListener`, or `app-config.json` / `application-properties.json`. Covers scaffolding new projects, adding entities, wiring DI correctly (including qualifiers for multiple implementations), and diagnosing the common PySpring pitfalls that don't exist in plain FastAPI.
---

# PySpring

PySpring (PyPI: `py-spring-core`) is a Spring Boot-inspired Python framework built on FastAPI and Pydantic. It gives you automatic dependency injection from type hints, validated configuration from JSON/YAML, class-based REST controllers, event pub/sub, middleware, scheduling, and graceful shutdown — with minimal boilerplate.

This skill is how you help PySpring developers avoid the non-obvious mistakes that trip people up (the ones that don't show up in FastAPI or Flask) and produce code that matches the framework's actual conventions.

## When to reach for this skill

Any time the user is building, extending, debugging, or migrating code that uses `py_spring_core`. Concretely:

- Scaffolding a new PySpring project or adding entities to an existing one
- Wiring dependency injection, especially when multiple implementations exist or when injection "doesn't work"
- Writing REST controllers, middleware, scheduled tasks, event listeners, or shutdown handlers
- Integrating third-party clients (database drivers, Redis, HTTP clients) into DI via `BeanCollection`
- Diagnosing startup errors (circular deps, missing `__key__`, missing return type annotations on bean factories, `__init__` usage)

If you're not sure whether the user wants PySpring specifically or plain FastAPI, check for PySpring imports or the `app-config.json` / `application-properties.json` files before assuming.

## The mental model — read this first

PySpring reuses Spring Boot vocabulary intentionally. If you know Spring Boot the mapping is almost 1:1; if you only know FastAPI, these are the translations:

| PySpring concept | What it is | FastAPI analogue |
| --- | --- | --- |
| `Component` | A managed class — instantiated, wired, and lifecycle-managed by the framework | (none — FastAPI has no DI container) |
| `Properties` | Typed, validated config mapped from a JSON/YAML section via `__key__` | `BaseSettings` (pydantic-settings) |
| `RestController` | Class-based route group with a `Config.prefix` | `APIRouter` + class instance |
| `BeanCollection` | Factory class whose `create_*` methods register external objects in the DI container | Depends (but resolved at startup, not per-request) |
| `ApplicationEvent` | Pydantic model published through `ApplicationEventPublisher` | (none) |
| `Middleware` | Async class-based middleware registered through `MiddlewareConfiguration` | Starlette middleware |
| `PySpringApplication` | The entry point — scans source, resolves DI graph, starts Uvicorn | `FastAPI()` + `uvicorn.run` |

DI is resolved **by type hint, at class level**, at startup — not per-request. There are no decorators on the fields, no service locator calls, no magic strings. The type annotation *is* the wiring.

## Project layout

A standard PySpring project looks like this:

```
myapp/
├── main.py                          # PySpringApplication entry point
├── app-config.json                  # Framework config (server, logging, shutdown)
├── application-properties.json      # Your app's Properties (auto-loaded via __key__)
├── src/                             # Scanned for entities — set by app_src_target_dir
│   ├── controllers/
│   ├── services/
│   ├── repositories/
│   ├── beans/                       # BeanCollection classes
│   ├── events/                      # ApplicationEvent subclasses
│   └── middleware/
├── logs/
├── requirements.txt                 # or pyproject.toml
└── README.md
```

First run of `python main.py` auto-generates `app-config.json` and `application-properties.json` if missing — users don't write them from scratch. The default server port is **8080**, not 8000 (a common confusion point).

For a fresh project, use `scripts/scaffold_project.py` (see "Scripts" below). For adding a single entity to an existing project, use `scripts/add_entity.py`.

## The core workflow — creating an entity

When the user asks "add a service / controller / properties / bean", follow this pattern.

### 1. Components (services, repositories, any managed class)

```python
from py_spring_core import Component


class UserRepository(Component):
    def find_all(self) -> list[dict]:
        return []


class UserService(Component):
    user_repository: UserRepository  # Injected by type hint — no decorator, no Depends()

    def post_construct(self) -> None:
        # Runs AFTER all dependencies are injected. This is your constructor.
        print("UserService ready")

    def pre_destroy(self) -> None:
        # Runs during shutdown, in reverse init order.
        pass

    def list_users(self) -> list[dict]:
        return self.user_repository.find_all()
```

Default scope is `Singleton`. For a fresh instance per injection point, set `class Config: scope = ComponentScope.Prototype` — but 95% of components should stay singletons.

### 2. Properties (typed configuration)

```python
from py_spring_core import Properties
from pydantic import Field


class DatabaseProperties(Properties):
    __key__ = "database"          # Maps to the "database" section of application-properties.json
    host: str
    port: int = 5432              # Defaults work
    name: str = Field(default="mydb")
```

Then in `application-properties.json`:

```json
{ "database": { "host": "localhost", "port": 5432, "name": "mydb" } }
```

Inject by type like anything else: `database_properties: DatabaseProperties`. Pydantic validates at startup — a missing field or wrong type fails loud and clear rather than crashing mid-request.

### 3. REST Controllers

```python
from py_spring_core import RestController
from py_spring_core.core.entities.controllers.rest_controller import (
    GetMapping, PostMapping, PutMapping, DeleteMapping, PatchMapping,
)
from pydantic import BaseModel


class CreateUserRequest(BaseModel):
    name: str
    email: str


class UserController(RestController):
    class Config:
        prefix = "/api/users"

    user_service: UserService  # DI works in controllers too

    @GetMapping("/")
    def list_users(self):
        return {"users": self.user_service.list_users()}

    @GetMapping("/{user_id}")
    def get_user(self, user_id: int):
        return {"id": user_id}

    @PostMapping("/", status_code=201)
    def create_user(self, body: CreateUserRequest):
        return body
```

The mapping decorators are FastAPI route decorators under the hood — path params, Pydantic bodies, `status_code`, `response_model`, etc. all work. Keep controllers thin; delegate to services.

### 4. BeanCollection — integrating third-party code

When the class you want to inject is *not* yours (you can't make it extend `Component`), register it via a factory method whose name starts with `create` and has a return type annotation:

```python
from py_spring_core import BeanCollection, Properties
from redis import Redis


class RedisProperties(Properties):
    __key__ = "redis"
    host: str
    port: int = 6379


class InfrastructureBeans(BeanCollection):
    redis_properties: RedisProperties  # Properties are injected before create_* is called

    def create_redis_client(self) -> Redis:        # ← return type annotation is REQUIRED
        return Redis(host=self.redis_properties.host, port=self.redis_properties.port)
```

Now any component can inject `redis: Redis`. The return type is what PySpring uses as the registration key, so it must be present and accurate.

## The top mistakes — guard against these

These are PySpring-specific and bite everyone at least once. Check for them before finalizing any code you write.

**1. Using `__init__` to set up state that depends on an injected field.** Injection happens *after* `__init__` runs. The field will be unset (or the class attribute default, typically `None`). Always move DI-dependent setup to `post_construct`.

```python
# WRONG — db is not injected yet when __init__ runs
class Cache(Component):
    db: Database
    def __init__(self):
        self.data = self.db.load()  # AttributeError or None

# RIGHT
class Cache(Component):
    db: Database
    def post_construct(self) -> None:
        self.data = self.db.load()
```

**2. Forgetting the return type annotation on a `create_*` method.** Without it, PySpring has no type to register the bean under, and injection silently fails.

```python
# WRONG — bean won't be registered
def create_redis_client(self):
    return Redis(...)

# RIGHT
def create_redis_client(self) -> Redis:
    return Redis(...)
```

**3. Method name doesn't start with `create`.** `make_redis_client`, `build_redis_client`, `get_redis_client` are all ignored. The convention is strict.

**4. Multiple implementations of the same base type with no qualifier.** If two classes extend `AbstractNotifier`, injecting `notifier: AbstractNotifier` is ambiguous. Use `Annotated[AbstractNotifier, "EmailNotifier"]` where the string is the *class name* of the implementation. See `references/qualifiers-and-lifecycle.md` for the pattern.

**5. Circular dependencies.** If `A` needs `B` and `B` needs `A`, PySpring rejects the graph at startup. Fix by extracting a third component, moving the field access to an event, or rethinking the boundary.

**6. Missing `__key__` on a `Properties` class.** Without it, PySpring doesn't know which config section to load. The class will either stay empty or raise a validation error depending on field defaults.

**7. Reaching for plain FastAPI patterns.** `Depends(...)`, `APIRouter`, module-level `app = FastAPI()` — none of these are how PySpring works. The user declared PySpring for a reason; don't convert their code into vanilla FastAPI.

**8. Wrong default port.** PySpring serves at `http://0.0.0.0:8080` by default. Docs at `/docs` (Swagger) and `/redoc`.

## Advanced topics — load references as needed

The features below have enough surface area that they get their own reference files. Read the one that matches the user's request rather than trying to remember details:

| Topic | File | When to load |
| --- | --- | --- |
| Event system (publish/subscribe, `ApplicationEvent`, `@EventListener`) | `references/events.md` | User mentions events, pub/sub, decoupling, `ApplicationEventPublisher`, or anything about components reacting to each other without direct imports |
| Middleware (auth, logging, CORS, rate limit; `MiddlewareConfiguration` ordering) | `references/middleware.md` | User asks about middleware, request interception, `process_request`, `should_skip`, or registration ordering |
| Scheduling (`@Scheduled`, cron/interval triggers, `pyspring-scheduler` plugin) | `references/scheduling.md` | User mentions cron, interval jobs, `@Scheduled`, APScheduler, periodic tasks |
| Graceful shutdown (`GracefulShutdownHandler`, `ShutdownType`, SIGTERM handling) | `references/shutdown.md` | User mentions SIGTERM, graceful shutdown, Docker/K8s lifecycle, connection cleanup on exit |
| Qualifiers & component lifecycle (multiple impls of same base; init/destroy order) | `references/qualifiers-and-lifecycle.md` | User has multiple implementations of an abstract base, or asks about init order, `Singleton` vs `Prototype`, circular dependencies |
| Config files reference (`app-config.json` schema, `application-properties.json`) | `references/config-files.md` | User asks about configuration format, YAML support, default generation, `app_src_target_dir`, log/server/shutdown config |

Load only what you need. The main SKILL.md above is enough for most day-to-day asks.

## Scripts

Two generators in `scripts/` speed up common structural work. They don't replace judgment — read the code they produce and adjust.

### `scripts/scaffold_project.py`

Bootstraps a full PySpring project skeleton at the given path: `main.py`, the two config JSON files with sensible defaults, a `src/` tree with placeholder folders, a sample service and controller, and `requirements.txt`.

```bash
python scripts/scaffold_project.py <project_dir> [--name <app_name>] [--port <port>]
```

Use when the user says "start a new PySpring project" or shows up with an empty directory.

### `scripts/add_entity.py`

Adds a single entity file to an existing project with the correct imports and class structure, placed in the conventional subdirectory of `src/`.

```bash
python scripts/add_entity.py <kind> <Name> [--project-root .] [--prefix /api/...]
```

Where `<kind>` is one of: `component`, `controller`, `properties`, `bean-collection`, `event`, `middleware`, `scheduled`, `shutdown`.

For instance, `python scripts/add_entity.py controller UserController --prefix /api/users` produces `src/controllers/user_controller.py` with the correct skeleton, including a sensible `snake_case` filename derived from the class name.

These scripts write code that follows the conventions documented above — if you need a variant the script doesn't support, write the file by hand rather than hacking the script output.

## Verifying your work

Before declaring code "done":

1. Every field used inside a method exists as a class-level type annotation — otherwise DI won't populate it.
2. Setup code runs in `post_construct`, not `__init__`.
3. Every `create_*` method in a `BeanCollection` has a return type annotation.
4. Every `Properties` subclass has `__key__`.
5. Controllers set `class Config: prefix = "..."` — without it, routes register at root and collisions become likely.
6. If the feature needs `pyspring-scheduler`, the user's `main.py` passes `entity_providers=[provide_scheduler()]` to `PySpringApplication`.
7. When multiple implementations of a base exist, injection sites use `Annotated[Base, "ClassName"]`.

If the user reports a startup error, match it against the "top mistakes" list before digging deeper — most PySpring startup errors map to one of those eight.
