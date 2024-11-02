import os
import warnings
from typing import Optional
from pathlib import Path
import typer
import uvicorn
from typing_extensions import Annotated

from .version import VERSION
from .._docker import (
    check_docker_running,
    check_browser_image,
    check_python_image,
    build_browser_image,
    build_python_image,
)

app = typer.Typer()

# Ignore deprecation warnings from websockets
warnings.filterwarnings("ignore", message="websockets.legacy is deprecated*")
warnings.filterwarnings(
    "ignore", message="websockets.server.WebSocketServerProtocol is deprecated*"
)


def get_env_file_path():
    app_dir = os.path.join(os.path.expanduser("~"), ".magentic_ui")
    if not os.path.exists(app_dir):
        os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, "temp_env_vars.env")


@app.command()
def ui(
    host: str = "127.0.0.1",
    port: int = 8081,
    workers: int = 1,
    reload: Annotated[bool, typer.Option("--reload")] = False,
    docs: bool = True,
    appdir: str = str(Path.home() / ".magentic_ui"),
    database_uri: Optional[str] = None,
    upgrade_database: bool = False,
    config: Optional[str] = None,
    rebuild_docker: Optional[bool] = False,
):
    """
    Run Magentic-UI.

    Args:
        host (str, optional): Host to run the UI on. Defaults to 127.0.0.1 (localhost).
        port (int, optional): Port to run the UI on. Defaults to 8081.
        workers (int, optional): Number of workers to run the UI with. Defaults to 1.
        reload (bool, optional): Whether to reload the UI on code changes. Defaults to False.
        docs (bool, optional): Whether to generate API docs. Defaults to False.
        appdir (str, optional): Path to the app directory where files are stored. Defaults to None.
        database-uri (str, optional): Database URI to connect to. Defaults to None.
        config (str, optional): Path to the config file. Defaults to `config.yaml`.
        rebuild_docker: bool, optional: Rebuild the docker images. Defaults to False.
    """

    # Set things up for Docker
    if not check_docker_running():
        typer.echo("Docker is not running. Please start Docker and try again.")
        raise typer.Exit(1)

    if not check_browser_image() or rebuild_docker:
        typer.echo(
            "Docker image for vnc browser not found. Building the image (this may take a few minutes)..."
        )
        build_browser_image()

    if not check_python_image() or rebuild_docker:
        typer.echo(
            "Docker image for python not found. Building the image (this may take a few minutes)..."
        )
        build_python_image()

    # Write configuration
    env_vars = {
        "_HOST": host,
        "_PORT": port,
        "_API_DOCS": str(docs),
    }

    if appdir:
        env_vars["_APPDIR"] = appdir
    if database_uri:
        env_vars["DATABASE_URI"] = database_uri
    if upgrade_database:
        env_vars["_UPGRADE_DATABASE"] = "1"

    env_vars["INSIDE_DOCKER"] = "0"
    env_vars["EXTERNAL_WORKSPACE_ROOT"] = appdir
    env_vars["INTERNAL_WORKSPACE_ROOT"] = appdir

    # If the config file is not provided, check for the default config file
    if not config:
        if os.path.isfile("config.yaml"):
            config = "config.yaml"
        else:
            typer.echo("Config file not provided. Using default settings.")
    if config:
        env_vars["_CONFIG"] = config

    # Create temporary env file to share configuration with uvicorn workers
    env_file_path = get_env_file_path()
    with open(env_file_path, "w") as temp_env:
        for key, value in env_vars.items():
            temp_env.write(f"{key}={value}\n")

    uvicorn.run(
        "magentic_ui.backend.web.app:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        reload_excludes=["**/alembic/*", "**/alembic.ini", "**/versions/*"]
        if reload
        else None,
        env_file=env_file_path,
    )


@app.command()
def version():
    """
    Print the version of the Magentic-UI backend CLI.
    """

    typer.echo(f"Magentic-UI version: {VERSION}")


def run():
    app()


if __name__ == "__main__":
    app()
