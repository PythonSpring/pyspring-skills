# Qualifiers & Component Lifecycle

Two advanced DI topics that come up together because they both deal with "what instance gets injected, and when."

## Part 1: Qualifiers — picking between implementations

### The problem

DI resolves by type. If you have *one* concrete implementation of an abstract base, fine — PySpring picks it. But if you have two:

```python
from py_spring_core import Component


class AbstractNotifier(Component):
    def notify(self, message: str) -> None:
        raise NotImplementedError


class EmailNotifier(AbstractNotifier):
    def notify(self, message: str) -> None:
        print(f"Email: {message}")


class SlackNotifier(AbstractNotifier):
    def notify(self, message: str) -> None:
        print(f"Slack: {message}")
```

…then `notifier: AbstractNotifier` is ambiguous. Which one?

### The fix: `Annotated` with a qualifier string

```python
from typing import Annotated


class AlertService(Component):
    email: Annotated[AbstractNotifier, "EmailNotifier"]
    slack: Annotated[AbstractNotifier, "SlackNotifier"]

    def post_construct(self) -> None:
        self.email.notify("Server is down!")
        self.slack.notify("Server is down!")
```

The second argument to `Annotated` is the **class name of the implementation** — not an arbitrary label you invented. It's the literal name of the subclass.

Rule of thumb: if you find yourself qualifying a lot of injections, the abstraction is probably leaking. Consider whether "email vs slack" deserves separate interface methods rather than a single `AbstractNotifier`.

### When qualifiers aren't needed

- Only one implementation of a given base → no qualifier needed.
- You're injecting the concrete class directly (`email: EmailNotifier`) → no qualifier needed.
- The dependency type isn't a Component subclass (e.g., a `BeanCollection`-produced bean like `Redis`) → beans are registered by their concrete return type, so no qualifier needed unless you've registered two beans of the same type (which you should generally avoid).

## Part 2: Component lifecycle — what happens when

### The stages

Every component, every run:

1. **Discovery** — PySpring walks `app_src_target_dir` and finds all `Component`, `Properties`, `RestController`, and `BeanCollection` subclasses.
2. **Instantiation** — Each class is instantiated (`__init__` runs). Dependencies are *not* yet set at this point.
3. **Dependency injection** — Type-annotated fields are populated from the container.
4. **Post-construction** — `post_construct()` runs on each component.
5. **Running** — the app serves traffic.
6. **Pre-destruction** — on shutdown, `pre_destroy()` runs in **reverse initialization order**.
7. **Destruction** — instances are released for GC.

### Initialization order is dependency order

If `UserService` depends on `UserRepository`, then `UserRepository` is fully initialized — including its own `post_construct()` completing — before `UserService` gets dependencies injected. This means you can safely use injected dependencies in `post_construct` knowing they've already run their own setup.

Corollary: **circular dependencies fail at startup**. If `A` depends on `B` and `B` depends on `A`, PySpring can't decide who initializes first. Fix:
- Extract a third component that both depend on.
- Replace one direction with an event (see `events.md`).
- Merge the two if they genuinely can't be separated.

### `post_construct` vs `__init__` — one more time

This comes up often enough to restate: **anything that reads from an injected field must live in `post_construct`, not `__init__`.**

```python
class Cache(Component):
    db: Database

    # DOES NOT WORK
    # def __init__(self):
    #     self.data = self.db.load()     # self.db is None here

    def post_construct(self) -> None:
        self.data = self.db.load()       # self.db is populated
```

You can still override `__init__` for things that don't touch injected fields — default state for non-injected attributes, for instance. But 99% of the time `post_construct` is what you want, and defining `__init__` at all invites mistakes.

### Scopes: Singleton vs Prototype

| Scope | Behavior | Lifecycle |
| --- | --- | --- |
| `Singleton` (default) | One instance per application. All injection sites share it. | `post_construct` and `pre_destroy` each called **once**. |
| `Prototype` | A fresh instance is built per injection site. | `post_construct` called **per instance**. `pre_destroy` is not reliably called for prototypes — don't rely on it for cleanup. |

To switch:

```python
from py_spring_core.core.entities.component import ComponentScope


class ShortLivedWorker(Component):
    class Config:
        scope = ComponentScope.Prototype
```

Use `Prototype` only when you have a real reason — e.g., a stateful helper whose instance-local state would collide across callers. Most components (services, repositories, controllers, shutdown handlers, middleware) must be singletons.

### Order diagram

For a typical service + repository + controller:

```
startup:  Database.post_construct  →  Repository.post_construct  →  Service.post_construct  →  Controller.post_construct
shutdown: Controller.pre_destroy   →  Service.pre_destroy        →  Repository.pre_destroy  →  Database.pre_destroy
```

Reverse order on shutdown is what makes layered cleanup safe — the Controller stops accepting requests before the Service it depends on tears down its connections.
