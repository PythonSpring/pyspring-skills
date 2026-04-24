# Scheduling

Scheduled tasks live in the `pyspring-scheduler` plugin, not in `py-spring-core` itself. It's a thin layer over APScheduler that wires scheduled methods into PySpring's DI container.

## Install

```bash
pip install git+ssh://git@github.com/PythonSpring/pyspring-scheduler.git
```

This is a Git install, not a PyPI package at the time of this writing. Users behind strict proxies or without SSH access to GitHub will need an alternative.

## Register the scheduler with the application

The scheduler is registered as an *entity provider* — `PySpringApplication` doesn't know about it until you pass it in:

```python
from py_spring_core import PySpringApplication
from pyspring_scheduler import provide_scheduler


def main() -> None:
    app = PySpringApplication(
        "./app-config.json",
        entity_providers=[provide_scheduler()],
    )
    app.run()


if __name__ == "__main__":
    main()
```

Forgetting `entity_providers=[provide_scheduler()]` is the #1 reason `@Scheduled` does nothing — no error at startup, the decorated method just never fires.

## Scheduling a method

Use `@Scheduled(trigger=...)` on a method of any `Component`. Because it's a component method, full DI is available — scheduled jobs can call other services.

```python
from py_spring_core import Component
from pyspring_scheduler import Scheduled
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger


class HealthCheckService(Component):
    @Scheduled(trigger=IntervalTrigger(seconds=30))
    def ping(self) -> None:
        print("Health check")


class NightlyReportService(Component):
    metrics_service: MetricsService  # Injected — works in scheduled jobs

    @Scheduled(trigger=CronTrigger(hour=2, minute=0))
    def nightly_report(self) -> None:
        data = self.metrics_service.collect()
        # ... write report ...
```

## Trigger types

Triggers come from APScheduler directly, not from the PySpring plugin:

| Trigger | Import | Use for |
| --- | --- | --- |
| `IntervalTrigger` | `apscheduler.triggers.interval` | Fixed periods — every N seconds/minutes/hours |
| `CronTrigger` | `apscheduler.triggers.cron` | Calendar schedules — "every weekday at 9:00" |
| `DateTrigger` | `apscheduler.triggers.date` | One-shot at a specific datetime |
| `AndTrigger` / `OrTrigger` | `apscheduler.triggers.combining` | Combine multiple triggers |

`CronTrigger` accepts the usual keyword args: `year`, `month`, `day`, `day_of_week`, `hour`, `minute`, `second`, and also a single `expression` string for standard cron syntax.

```python
# Every weekday at 9 AM
CronTrigger(day_of_week="mon-fri", hour=9, minute=0)

# Every 15 minutes during business hours
CronTrigger(hour="9-17", minute="*/15")

# Morning and evening
OrTrigger([
    CronTrigger(hour=9, minute=0),
    CronTrigger(hour=17, minute=0),
])
```

## Scheduler configuration

Add a `scheduler` section to `application-properties.json` to tune the underlying APScheduler executor:

```json
{
  "scheduler": {
    "number_of_workers": 10,
    "max_instances": 3,
    "timezone": "UTC",
    "coalesce": true
  }
}
```

- `number_of_workers` — thread pool size for running jobs concurrently.
- `max_instances` — how many copies of the same job can run simultaneously. Set to 1 if jobs must never overlap.
- `timezone` — required for `CronTrigger` to mean what you expect. Use IANA names (`"Asia/Taipei"`, `"America/New_York"`), not abbreviations.
- `coalesce` — if the scheduler was down and multiple runs were missed, collapse them into one "catch-up" run. Almost always what you want.

## Gotchas

- **No error when the plugin isn't registered.** `@Scheduled` decorates fine with or without `provide_scheduler()`; the method simply never fires. Check this first when a job isn't running.
- **`self` is the component.** The method signature is `def my_job(self) -> None`, same as any other component method. Don't add APScheduler-style `*args` unless you've read the APScheduler docs for your trigger.
- **Long-running jobs and `max_instances`.** If a job takes longer than its interval, APScheduler will skip the next run if `max_instances=1`. Either raise `max_instances` or split the work so runs stay bounded.
- **Timezone inconsistency.** If you set `timezone` in config but use `CronTrigger` without specifying `timezone=`, the trigger's own default can override. When in doubt, pass `timezone="..."` to every `CronTrigger` explicitly.
- **Task discovery timing.** Scheduled methods are registered during the DI container's post-construct phase. Methods decorated on prototype-scoped components behave differently — stick with singleton-scoped components for scheduled tasks.
