#!/usr/bin/env python3
"""
Scaffold a new PySpring project.

Creates the standard PySpring layout:
    <project>/
      main.py
      app-config.json
      application-properties.json
      requirements.txt
      .gitignore
      src/
        __init__.py
        controllers/
          __init__.py
          hello_controller.py
        services/
          __init__.py
          hello_service.py
        properties/
          __init__.py
          app_properties.py
        beans/__init__.py
        events/__init__.py
        middleware/__init__.py
      logs/.gitkeep
      README.md

Usage:
    python scaffold_project.py <project_dir> [--name <app_name>] [--port <port>]

The scaffold writes files that already work — `python main.py` from inside the
generated directory starts the server and serves /api/hello/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from textwrap import dedent


# ---------------------------------------------------------------------------
# File templates
# ---------------------------------------------------------------------------

MAIN_PY = dedent(
    '''\
    """Entry point for the {app_name} PySpring application."""
    from py_spring_core import PySpringApplication


    def main() -> None:
        app = PySpringApplication("./app-config.json")
        app.run()


    if __name__ == "__main__":
        main()
    '''
)


def build_app_config(port: int) -> dict:
    """Build app-config.json. Matches the structure PySpring generates itself."""
    return {
        "app_src_target_dir": "./src",
        "server_config": {
            "host": "0.0.0.0",
            "port": port,
            "enabled": True,
        },
        "properties_file_path": "./application-properties.json",
        "loguru_config": {
            "log_file_path": "./logs/app.log",
            "log_level": "DEBUG",
        },
        "type_checking_mode": "strict",
        "shutdown_config": {
            "timeout_seconds": 30.0,
            "enabled": True,
        },
    }


APP_PROPERTIES = {
    "app": {
        "greeting": "Hello from PySpring!",
    }
}


APP_PROPERTIES_PY = dedent(
    '''\
    """Application-level typed configuration."""
    from py_spring_core import Properties


    class AppProperties(Properties):
        __key__ = "app"
        greeting: str
    '''
)


HELLO_SERVICE_PY = dedent(
    '''\
    """Demo service showing DI of a Properties class."""
    from py_spring_core import Component

    from src.properties.app_properties import AppProperties


    class HelloService(Component):
        app_properties: AppProperties  # Auto-injected

        def post_construct(self) -> None:
            # Runs AFTER injection — safe to read app_properties here.
            print(f"HelloService ready: {self.app_properties.greeting}")

        def greet(self, name: str) -> str:
            return f"{self.app_properties.greeting} ({name})"
    '''
)


HELLO_CONTROLLER_PY = dedent(
    '''\
    """Demo REST controller showing class-based routes with DI."""
    from py_spring_core import RestController
    from py_spring_core.core.entities.controllers.rest_controller import GetMapping

    from src.services.hello_service import HelloService


    class HelloController(RestController):
        class Config:
            prefix = "/api/hello"

        hello_service: HelloService  # Auto-injected

        @GetMapping("/")
        def hello(self):
            return {"message": self.hello_service.greet("world")}

        @GetMapping("/{name}")
        def hello_name(self, name: str):
            return {"message": self.hello_service.greet(name)}
    '''
)


REQUIREMENTS = dedent(
    """\
    py-spring-core
    """
)


GITIGNORE = dedent(
    """\
    __pycache__/
    *.pyc
    *.pyo
    .venv/
    venv/
    env/
    .env
    logs/*.log
    .vscode/
    .idea/
    """
)


def build_readme(app_name: str, port: int) -> str:
    return dedent(
        f"""\
        # {app_name}

        A PySpring application.

        ## Run

        ```bash
        pip install -r requirements.txt
        python main.py
        ```

        The server starts on `http://0.0.0.0:{port}`.

        - API docs: <http://127.0.0.1:{port}/docs>
        - ReDoc: <http://127.0.0.1:{port}/redoc>
        - Example endpoint: <http://127.0.0.1:{port}/api/hello/>

        ## Layout

        ```
        main.py                       # Entry point
        app-config.json               # Framework config
        application-properties.json   # Your app's Properties
        src/
          controllers/                # RestController classes
          services/                   # Component classes (business logic)
          properties/                 # Properties classes (typed config)
          beans/                      # BeanCollection classes (third-party wiring)
          events/                     # ApplicationEvent classes
          middleware/                 # Middleware + MiddlewareConfiguration
        ```

        ## Adding entities

        Keep the layout: services go in `src/services/`, controllers in
        `src/controllers/`, and so on. PySpring scans everything under `src/`.
        """
    )


# ---------------------------------------------------------------------------
# Scaffolder
# ---------------------------------------------------------------------------


def scaffold(project_dir: Path, app_name: str, port: int) -> None:
    """Write the scaffold. Fails if the target directory already exists and is non-empty."""
    if project_dir.exists() and any(project_dir.iterdir()):
        raise SystemExit(
            f"error: {project_dir} exists and is not empty. "
            "Refusing to overwrite — pick an empty or non-existent directory."
        )

    project_dir.mkdir(parents=True, exist_ok=True)

    # Top-level files
    (project_dir / "main.py").write_text(MAIN_PY.format(app_name=app_name))
    (project_dir / "app-config.json").write_text(
        json.dumps(build_app_config(port), indent=4) + "\n"
    )
    (project_dir / "application-properties.json").write_text(
        json.dumps(APP_PROPERTIES, indent=4) + "\n"
    )
    (project_dir / "requirements.txt").write_text(REQUIREMENTS)
    (project_dir / ".gitignore").write_text(GITIGNORE)
    (project_dir / "README.md").write_text(build_readme(app_name, port))

    # src/ tree
    src = project_dir / "src"
    for sub in ("", "controllers", "services", "properties", "beans", "events", "middleware"):
        subdir = src / sub if sub else src
        subdir.mkdir(parents=True, exist_ok=True)
        (subdir / "__init__.py").write_text("")

    (src / "properties" / "app_properties.py").write_text(APP_PROPERTIES_PY)
    (src / "services" / "hello_service.py").write_text(HELLO_SERVICE_PY)
    (src / "controllers" / "hello_controller.py").write_text(HELLO_CONTROLLER_PY)

    # logs/ placeholder
    logs = project_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / ".gitkeep").write_text("")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new PySpring project.")
    parser.add_argument("project_dir", type=Path, help="Target directory (must be empty or nonexistent)")
    parser.add_argument("--name", default=None, help="Human-readable app name (default: directory name)")
    parser.add_argument("--port", type=int, default=8080, help="Default HTTP port (default 8080)")
    args = parser.parse_args(argv)

    app_name = args.name or args.project_dir.name
    scaffold(args.project_dir.resolve(), app_name, args.port)

    print(f"Scaffolded PySpring project at {args.project_dir.resolve()}")
    print()
    print("Next steps:")
    print(f"  cd {args.project_dir}")
    print("  pip install -r requirements.txt")
    print("  python main.py")
    print(f"  open http://127.0.0.1:{args.port}/docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
