"""Typer CLI with a stable machine-readable result envelope."""

import json
import sqlite3
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from typer._click.exceptions import ClickException

from motteta import __version__, browser
from motteta.cli.display import CHECK_LABELS, print_record, print_records
from motteta.core.errors import MottetaError
from motteta.core.ledger import Ledger
from motteta.core.models import (
    AddRecord,
    Candidate,
    Correction,
    HistoryBatch,
    IdentityBinding,
    Resolution,
)
from motteta.storage.database import data_directory

app = typer.Typer(no_args_is_help=True, invoke_without_command=True, pretty_exceptions_enable=False)
browser_app = typer.Typer(no_args_is_help=True)
review_app = typer.Typer(no_args_is_help=True)
app.add_typer(browser_app, name="browser")
app.add_typer(review_app, name="review")
Input = Annotated[str, typer.Option("--input", help="JSON path or - for stdin")]
Output = Annotated[Path, typer.Option("--output")]


class ExportFormat(StrEnum):
    json = "json"
    csv = "csv"


class RestoreFormat(StrEnum):
    sqlite = "sqlite"
    json = "json"


@dataclass
class State:
    directory: Path
    json_output: bool


@app.callback()
def configure(
    ctx: typer.Context,
    data_dir: Annotated[Path | None, typer.Option("--data-dir", help="Ledger directory")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    version: Annotated[bool, typer.Option("--version", is_eager=True)] = False,
):
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    ctx.obj = State(data_directory(data_dir), json_output)


def read_input(path: str, model):
    data = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return model.model_validate_json(data)


def emit(ctx: typer.Context, result: dict) -> None:
    typer.echo(
        json.dumps(
            {"schema_version": 1, **result},
            ensure_ascii=False,
            indent=None if ctx.obj.json_output else 2,
        )
    )
    if result["result"] == "needs_review":
        raise typer.Exit(3)
    if result["result"] == "error":
        raise typer.Exit(4)


@app.command()
def init(ctx: typer.Context):
    """Create a ledger without overwriting an existing one."""
    emit(ctx, Ledger(ctx.obj.directory).db.initialize())


@app.command()
def add(ctx: typer.Context, input: Input, dry_run: bool = False):
    """Add one acquisition or ownership assertion."""
    emit(ctx, Ledger(ctx.obj.directory).add(read_input(input, AddRecord), dry_run=dry_run))


@app.command("import")
def import_history(ctx: typer.Context, history: Path, dry_run: bool = False):
    """Import observations and their explicit coverage report atomically."""
    emit(
        ctx,
        Ledger(ctx.obj.directory).import_history(
            read_input(str(history), HistoryBatch), dry_run=dry_run
        ),
    )


@app.command("list")
def list_books(ctx: typer.Context):
    """List registered books in a readable table."""
    display_records(ctx, Ledger(ctx.obj.directory).search(""))


def display_records(ctx: typer.Context, result: dict) -> None:
    if ctx.obj.json_output:
        emit(ctx, result)
    else:
        print_records(result["records"])


@app.command()
def search(ctx: typer.Context, term: str):
    """Search titles, authors, ISBNs, and product identifiers."""
    display_records(ctx, Ledger(ctx.obj.directory).search(term))


@app.command()
def show(ctx: typer.Context, record_id: str):
    """Show a book's purchase and ownership details."""
    result = Ledger(ctx.obj.directory).get(record_id)
    if ctx.obj.json_output:
        emit(ctx, result)
    else:
        print_record(result["record"])


@app.command()
def check(ctx: typer.Context, input: Input):
    """Check a purchase candidate against the local ledger."""
    result = Ledger(ctx.obj.directory).check(read_input(input, Candidate))
    result["label"] = CHECK_LABELS[result["label"]]
    emit(ctx, result)


@app.command()
def status(ctx: typer.Context):
    """Show coverage and freshness separately for each account and source."""
    emit(ctx, Ledger(ctx.obj.directory).status())


@app.command()
def bind_identity(ctx: typer.Context, record_id: str, input: Input, dry_run: bool = False):
    """Explicitly bind a verified derived identity to an existing purchase."""
    emit(
        ctx,
        Ledger(ctx.obj.directory).bind_identity(
            record_id, read_input(input, IdentityBinding), dry_run=dry_run
        ),
    )


@app.command()
def update(ctx: typer.Context, record_id: str, input: Input):
    """Apply an explicit correction which future imports must preserve."""
    emit(ctx, Ledger(ctx.obj.directory).update(record_id, read_input(input, Correction)))


@review_app.command("list")
def list_reviews(ctx: typer.Context):
    emit(ctx, Ledger(ctx.obj.directory).reviews())


@review_app.command("resolve")
def resolve_review(ctx: typer.Context, review_id: str, input: Input):
    emit(ctx, Ledger(ctx.obj.directory).resolve(review_id, read_input(input, Resolution)))


@app.command("export")
def export_data(ctx: typer.Context, format: ExportFormat = ExportFormat.json):
    """Export a lossless JSON snapshot or a CSV reading aid to stdout."""
    typer.echo(Ledger(ctx.obj.directory).export(format.value), nl=False)


@app.command()
def backup(ctx: typer.Context, output: Output):
    emit(ctx, Ledger(ctx.obj.directory).backup(output))


@app.command()
def restore(
    ctx: typer.Context, input: Input, output: Output, format: RestoreFormat = RestoreFormat.sqlite
):
    emit(ctx, Ledger.restore(Path(input), output, format.value))


@browser_app.command("install")
def browser_install(
    ctx: typer.Context,
    browser_name: Annotated[str, typer.Option("--browser")],
    extension_id: Annotated[str, typer.Option("--extension-id")],
):
    """Register the host. This does not launch or control the browser."""
    emit(ctx, browser.install(ctx.obj.directory, browser_name, extension_id))


@browser_app.command("uninstall")
def browser_uninstall(ctx: typer.Context, browser_name: Annotated[str, typer.Option("--browser")]):
    emit(ctx, browser.uninstall(ctx.obj.directory, browser_name))


@app.command()
def doctor(ctx: typer.Context):
    """Inspect local files without connecting to Chrome or any website."""
    emit(ctx, browser.doctor(ctx.obj.directory))


def main() -> None:
    args = sys.argv[1:]
    # --json is a global output option, intentionally accepted after subcommands too.
    end = args.index("--") if "--" in args else len(args)
    json_mode = "--json" in args[:end]
    if json_mode:
        args = ["--json", *[a for a in args[:end] if a != "--json"], *args[end:]]
    try:
        result = app(args=args, standalone_mode=False)
        if isinstance(result, int):
            raise SystemExit(result)
    except (
        ClickException,
        ValidationError,
        MottetaError,
        json.JSONDecodeError,
        UnicodeError,
        OSError,
        sqlite3.Error,
    ) as exc:
        if isinstance(exc, MottetaError):
            code, exit_code = exc.code, exc.exit_code
        elif isinstance(exc, (ClickException, ValidationError, ValueError, UnicodeError)):
            code, exit_code = "invalid_input", 2
        else:
            code, exit_code = "execution_failed", 4
        message = exc.format_message() if isinstance(exc, ClickException) else str(exc)
        details = (
            exc.errors(include_url=False, include_context=False)
            if isinstance(exc, ValidationError)
            else None
        )
        envelope = {
            "schema_version": 1,
            "result": "error",
            "error": {"code": code, "message": message},
        }
        if details:
            envelope["error"]["fields"] = [
                {"location": d["loc"], "message": d["msg"], "type": d["type"]} for d in details
            ]
        if json_mode:
            typer.echo(json.dumps(envelope, ensure_ascii=False))
        else:
            typer.echo(f"{code}: {message}", err=True)
        raise SystemExit(exit_code) from exc
