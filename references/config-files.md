# Configuration Files

PySpring uses two JSON (or YAML) files. Both are auto-generated on first run of `python main.py` if missing — users shouldn't write them from scratch.

## `app-config.json` — framework configuration

This is PySpring's own config (server, logging, shutdown). You rarely edit it after the first generation except to change the port or enable type checking.

```json
{
    "app_src_target_dir": "./src",
    "server_config": {
        "host": "0.0.0.0",
        "port": 8080,
        "enabled": true
    },
    "properties_file_path": "./application-properties.json",
    "loguru_config": {
        "log_file_path": "./logs/app.log",
        "log_level": "DEBUG"
    },
    "type_checking_mode": "strict",
    "shutdown_config": {
        "timeout_seconds": 30.0,
        "enabled": true
    }
}
```

| Field | Purpose |
| --- | --- |
| `app_src_target_dir` | Directory PySpring scans for entities. Default `./src`. Anything outside is *not* discovered. |
| `server_config.host` / `port` | Where Uvicorn binds. Default `0.0.0.0:8080` — note 8080, not 8000. |
| `server_config.enabled` | Set `false` for headless apps (schedulers, workers) that shouldn't expose HTTP. |
| `properties_file_path` | Where to load `Properties` from. Usually `./application-properties.json`. Can point to YAML. |
| `loguru_config` | Controls the default logger. `log_level` accepts `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`. |
| `type_checking_mode` | `"strict"` enforces tighter type validation at DI time. Keep strict unless you know you need otherwise. |
| `shutdown_config.timeout_seconds` | How long graceful shutdown can take before `on_timeout()` fires. Match to orchestrator (K8s default is 30s). |

## `application-properties.json` — your app's config

This is where each `Properties` class reads from, indexed by its `__key__`:

```json
{
    "database": {
        "host": "localhost",
        "port": 5432,
        "name": "mydb"
    },
    "redis": {
        "host": "localhost",
        "port": 6379
    },
    "example": {
        "value": "hello"
    }
}
```

Every top-level key corresponds to a `Properties` class somewhere in `src/` whose `__key__` matches:

```python
class DatabaseProperties(Properties):
    __key__ = "database"
    host: str
    port: int
    name: str
```

Validation happens at startup — a missing field or wrong type produces a clear Pydantic error before the server ever binds, which is the whole reason to use Properties instead of `os.environ`.

## YAML instead of JSON

PySpring detects format from the file extension. Change `properties_file_path` to `"./application-properties.yaml"` and write:

```yaml
database:
  host: localhost
  port: 5432
  name: mydb

redis:
  host: localhost
  port: 6379
```

Both work for `app-config` and `application-properties`. Pick one and stay consistent.

## Environments (dev / staging / prod)

PySpring doesn't ship a Spring-style `application-{profile}.yaml` loader out of the box. Common approaches users take:

1. **Per-environment file + symlink** — keep `application-properties.dev.json` / `.prod.json` in the repo, symlink the active one to `application-properties.json` at deploy time.
2. **Environment variable interpolation** — put values in env vars and reference them inside `Properties` field defaults or a `BeanCollection` factory that reads `os.environ`.
3. **Templated config** — generate `application-properties.json` at container start from a template + env vars.

Option 2 is the simplest for secrets (never commit them); option 1 is cleanest for structural differences between environments.

## First-run generation

On the very first `python main.py`, you'll see:

```
[APP CONFIG GENERATED] App config file not exists, ./app-config.json generated
[APP PROPERTIES GENERATED] App properties file not exists, ./application-properties.json generated
```

PySpring's `ConfigFileTemplateGenerator` writes defaults derived from the `Properties` classes it discovers. For fresh Properties added later, re-generation does not happen automatically — you edit `application-properties.json` by hand (or delete it and re-run to regenerate, accepting the loss of any customizations).

## Tips

- Check `app-config.json` into version control. It's boilerplate, not secret.
- For `application-properties.json`, check in a template (no secrets) and generate the real file at deploy.
- When you can't figure out why a `Properties` field is empty, verify the `__key__` matches the JSON section name exactly — it's case-sensitive.
- The `logs/` directory is created on first run if it doesn't exist.
