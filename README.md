# PySpring Skills for Claude Code

A [Claude Code custom skill](https://docs.anthropic.com/en/docs/claude-code/skills) that teaches Claude how to build, extend, and debug [PySpring](https://github.com/PythonSpring) (`py-spring-core`) applications.

PySpring is a Spring Boot-inspired Python framework built on FastAPI and Pydantic. It provides automatic dependency injection from type hints, validated JSON/YAML configuration, class-based REST controllers, event pub/sub, middleware, scheduling, and graceful shutdown.

This skill encodes the framework's conventions, common pitfalls, and code generation templates so Claude can assist PySpring developers without hallucinating plain-FastAPI patterns.

## What's Included

```
SKILL.md                             # Main skill definition and rules
scripts/
  scaffold_project.py                # Generate a full PySpring project skeleton
  add_entity.py                      # Add a single entity to an existing project
references/
  config-files.md                    # app-config.json and application-properties.json
  events.md                          # ApplicationEvent pub/sub system
  middleware.md                      # Middleware and MiddlewareConfiguration
  qualifiers-and-lifecycle.md        # Annotated qualifiers, scopes, init/destroy order
  scheduling.md                      # @Scheduled tasks via pyspring-scheduler
  shutdown.md                        # GracefulShutdownHandler and ShutdownType
```

### `SKILL.md`

The core skill file. It covers:

- The PySpring mental model and how it maps to Spring Boot / FastAPI concepts
- Standard project layout
- How to create each entity type (Component, Properties, RestController, BeanCollection)
- The 8 most common mistakes that are specific to PySpring (e.g. using `__init__` instead of `post_construct`, missing return type annotations on `create_*` methods)
- A verification checklist for generated code

### Reference Files

Detailed guides for advanced features, loaded on demand when the user's question matches the topic:

| File | Topic |
| --- | --- |
| `references/config-files.md` | `app-config.json` schema, `application-properties.json`, YAML support, environment strategies |
| `references/events.md` | `ApplicationEvent`, `ApplicationEventPublisher`, `@EventListener` |
| `references/middleware.md` | `Middleware`, `MiddlewareConfiguration`, ordering (`add_before`/`add_after`) |
| `references/qualifiers-and-lifecycle.md` | `Annotated[Base, "ClassName"]` qualifiers, Singleton vs Prototype scope, init/destroy order |
| `references/scheduling.md` | `@Scheduled`, `pyspring-scheduler` plugin, APScheduler triggers |
| `references/shutdown.md` | `GracefulShutdownHandler`, `ShutdownType`, drain-then-close patterns |

### Scripts

**`scripts/scaffold_project.py`** -- Generates a complete PySpring project that runs out of the box:

```bash
python scripts/scaffold_project.py my_app --name "My App" --port 8080
```

Creates `main.py`, config files, a `src/` tree with sample service and controller, `requirements.txt`, and `.gitignore`.

**`scripts/add_entity.py`** -- Adds a single entity file with correct imports and boilerplate:

```bash
python scripts/add_entity.py <kind> <ClassName> [--project-root .] [--prefix /api/...]
```

Supported kinds: `component`, `controller`, `properties`, `bean-collection`, `event`, `middleware`, `scheduled`, `shutdown`.

Examples:

```bash
python scripts/add_entity.py controller UserController --prefix /api/users
python scripts/add_entity.py component OrderService
python scripts/add_entity.py properties DatabaseProperties
python scripts/add_entity.py bean-collection InfrastructureBeans
```

## Installation

Copy or symlink this directory into your Claude Code skills location so it is picked up as a custom skill. The skill triggers automatically when Claude detects PySpring-related code, imports, or configuration files.

## When the Skill Activates

The skill engages when the conversation involves:

- `py_spring_core` imports or PySpring class hierarchies (`Component`, `Properties`, `RestController`, `BeanCollection`)
- `app-config.json` or `application-properties.json` files
- Spring Boot-style DI patterns in Python
- Requests to scaffold a new Python web app with dependency injection

## Key PySpring Concepts

| Concept | Description |
| --- | --- |
| `Component` | Managed class -- instantiated, wired, and lifecycle-managed by the framework |
| `Properties` | Typed config mapped from a JSON/YAML section via `__key__` |
| `RestController` | Class-based route group with `Config.prefix` |
| `BeanCollection` | Factory class whose `create_*` methods register third-party objects in DI |
| `ApplicationEvent` | Pydantic model for pub/sub between components |
| `Middleware` | Async request interceptor registered through `MiddlewareConfiguration` |
| `@Scheduled` | Cron/interval task decorator (requires `pyspring-scheduler` plugin) |
| `GracefulShutdownHandler` | Cross-component shutdown coordination |

## License

This skill is provided as-is for use with Claude Code.
