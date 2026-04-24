# Event System

PySpring's event system lets components communicate without importing each other. A publisher emits a typed event; any listener registered for that type reacts. The coupling flows through the *event type* rather than through a direct reference.

## The three pieces

### 1. Define the event

Events are Pydantic models that extend `ApplicationEvent`. Because they're Pydantic, you get validation and serialization for free.

```python
from py_spring_core.core.entities.event.application_event import ApplicationEvent


class UserCreatedEvent(ApplicationEvent):
    user_id: str
    username: str
```

Name events in the past tense. They represent something that *has happened*, not a command for something to happen.

### 2. Publish

Inject `ApplicationEventPublisher` like any other dependency:

```python
from py_spring_core import Component
from py_spring_core.core.entities.event.application_event_publisher import (
    ApplicationEventPublisher,
)


class UserService(Component):
    event_publisher: ApplicationEventPublisher  # Injected

    def create_user(self, username: str) -> None:
        # ... persist the user ...
        self.event_publisher.publish(
            UserCreatedEvent(user_id="123", username=username)
        )
```

### 3. Listen

Use `@EventListener(EventType)` on any method of any `Component`. Multiple listeners across multiple components can subscribe to the same event — they'll all be invoked.

```python
from py_spring_core import Component
from py_spring_core.core.entities.event.event_listener import EventListener


class WelcomeEmailService(Component):
    @EventListener(UserCreatedEvent)
    def on_user_created(self, event: UserCreatedEvent) -> None:
        print(f"Welcome email to {event.username}")


class AuditLog(Component):
    @EventListener(UserCreatedEvent)
    def on_user_created(self, event: UserCreatedEvent) -> None:
        print(f"Audit: user {event.user_id} created")
```

`WelcomeEmailService` and `AuditLog` don't know about each other, and neither knows `UserService` publishes the event. That's the decoupling — adding a third listener later needs zero changes to the publisher.

## How it behaves

- **Synchronous by default** — `publish()` calls every listener in the publisher's thread before returning. If a listener raises, handling depends on the framework version; don't rely on "other listeners still fire" unless you've verified it for your version.
- **Thread-safe** — you can publish from any thread (useful in scheduled jobs or background workers).
- **Type-dispatched** — listeners are selected by the exact event class, not by subclass relationships. A listener for `BaseEvent` does not fire for `SubEvent` unless it's explicitly registered.
- **Introduced in 0.0.11** — if the user is on an older version, this won't work.

## When to use events vs direct injection

Reach for events when:
- The publisher shouldn't know or care who listens (audit logging, metrics, cache invalidation, integrations).
- You're breaking a circular dependency. If `A` needs to "tell" `B` something and `B` needs to "tell" `A` something, inverting one direction through an event often untangles the cycle.
- Multiple independent components need to react to the same thing.

Stick with direct injection when:
- You need a return value. `publish()` is fire-and-forget; listeners don't return data to the publisher.
- The call is conceptually *commanding* a specific collaborator to do work. Events are for *notifications*, not RPC.
- There's exactly one handler and the coupling is natural (`UserService` calling `UserRepository` shouldn't be an event).

## Common mistake

Defining the event class inside the publisher's file and forcing listeners to import from there. That recreates the coupling events are supposed to avoid. Put event classes in their own module (e.g., `src/events/user_events.py`) that both publisher and listeners import.
