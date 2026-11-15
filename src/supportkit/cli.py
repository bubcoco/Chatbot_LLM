"""supportkit command-line interface."""

import sys
from pathlib import Path

import psycopg
import typer

from supportkit.settings import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@app.command()
def migrate() -> None:
    """Apply Alembic migrations, then create LangGraph checkpointer/store tables."""
    from alembic import command
    from alembic.config import Config
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.store.postgres import PostgresStore

    settings = get_settings()

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)
    command.upgrade(cfg, "head")
    typer.echo("alembic: upgraded to head")

    # LangGraph manages its own schema; setup() is idempotent.
    with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        checkpointer.setup()
    typer.echo("langgraph: checkpointer tables ready")

    with PostgresStore.from_conn_string(settings.database_url) as store:
        store.setup()
    typer.echo("langgraph: store tables ready")


@app.command("db-status")
def db_status() -> None:
    """Print installed extensions and tables — a quick check that migrations ran."""
    with psycopg.connect(get_settings().database_url) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
        typer.echo(f"postgres {version}")
        for name, ver in conn.execute(
            "SELECT extname, extversion FROM pg_extension ORDER BY extname"
        ):
            typer.echo(f"extension {name} {ver}")
        for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        ):
            typer.echo(f"table {table}")


def _repo_on_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


@app.command()
def seed() -> None:
    """Load the deterministic demo dataset (baan-bai-cha + shop-b). Replaces only those two shops' rows."""
    _repo_on_path()
    from seed.load import seed_database

    counts = seed_database(get_settings().database_url)
    for table, n in counts.items():
        typer.echo(f"{table}: {n}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the FastAPI app."""
    from supportkit.api.server import serve as _serve

    _serve(host, port)


@app.command("eval")
def eval_(
    dataset: Path = typer.Option(Path("evals/datasets/phase1.jsonl")),  # noqa: B008
    model: str | None = typer.Option(None, help="Overrides SUPPORTKIT_MODEL"),
    tag: str | None = typer.Option(None),
    case: str | None = typer.Option(None),
    report_dir: Path = typer.Option(Path("evals/reports")),  # noqa: B008
    require_all: bool = typer.Option(False, "--require-all"),
) -> None:
    """Run an eval dataset against the support graph."""
    _repo_on_path()
    from evals.runner import run_cli

    raise typer.Exit(
        run_cli(
            dataset=dataset,
            model=model,
            tag=tag,
            case=case,
            report_dir=report_dir,
            require_all=require_all,
        )
    )


if __name__ == "__main__":
    app()
