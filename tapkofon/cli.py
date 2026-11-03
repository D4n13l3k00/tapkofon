"""Typer commands and Rich terminal output."""

import asyncio
import io
import logging
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .logging_config import configure_logging, log_config

console = Console()
app = typer.Typer(
    name="tapkofon",
    help="Telegram для кнопочных телефонов: сервер, вход и управление базой.",
    invoke_without_command=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)
db_app = typer.Typer(help="Миграции и история SQLite.", add_completion=False)
password_app = typer.Typer(
    help="Управление паролем веб-клиента на сервере.", add_completion=False
)
app.add_typer(db_app, name="db")
app.add_typer(password_app, name="password")


class LogLevel(StrEnum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


@dataclass
class CliState:
    data_dir: Path
    log_level: str


def state(ctx: typer.Context) -> CliState:
    if not isinstance(ctx.obj, CliState):
        raise RuntimeError("CLI context is not initialized")
    return ctx.obj


def project_version() -> str:
    try:
        return version("tapkofon")
    except PackageNotFoundError:
        return "dev"


@app.callback()
def root(
    ctx: typer.Context,
    data_dir: Annotated[
        Path | None,
        typer.Option(
            "--data-dir",
            envvar="TAPKOFON_DATA_DIR",
            file_okay=False,
            resolve_path=True,
            help="Папка конфигурации, сессии и SQLite.",
        ),
    ] = None,
    log_level: Annotated[
        LogLevel, typer.Option(help="Уровень логов приложения.")
    ] = LogLevel.info,
    no_color: Annotated[
        bool, typer.Option("--no-color", help="Без цветов и ANSI-кодов.")
    ] = False,
    show_version: Annotated[
        bool, typer.Option("--version", is_eager=True, help="Версия приложения.")
    ] = False,
):
    console.no_color = no_color or "NO_COLOR" in os.environ
    if show_version:
        console.print(f"Tapkofon {project_version()}")
        raise typer.Exit()
    directory = (data_dir or Path("session")).resolve()
    os.environ["TAPKOFON_DATA_DIR"] = str(directory)
    if no_color:
        os.environ["NO_COLOR"] = "1"
    os.environ.setdefault("PYTHONUTF8", "1")
    configure_logging(log_level.value)
    ctx.obj = CliState(directory, log_level.value)
    if ctx.invoked_subcommand is None:
        start_server(state(ctx), "127.0.0.1", 8888, False)


def start_server(options: CliState, host: str, port: int, reload: bool) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_row("Адрес", f"http://{host}:{port}")
    table.add_row("Данные", str(options.data_dir))
    table.add_row("Логи", f"{options.log_level} · UTC")
    console.print(
        Panel(table, title=f"Tapkofon {project_version()}", border_style="cyan")
    )
    uvicorn.run(
        "tapkofon.main:app",
        host=host,
        port=port,
        reload=reload,
        log_config=log_config(options.log_level),
        log_level=options.log_level,
    )


@app.command()
def serve(
    ctx: typer.Context,
    host: Annotated[str, typer.Option(help="Интерфейс сервера.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="Порт сервера.")] = 8888,
    reload: Annotated[
        bool, typer.Option(help="Перезапуск при изменении кода.")
    ] = False,
):
    """Запустить веб-клиент."""
    start_server(state(ctx), host, port, reload)


@app.command()
def login(
    ctx: typer.Context,
    qr: Annotated[
        bool, typer.Option("--qr", help="Вход по QR вместо номера и кода.")
    ] = False,
):
    """Войти в Telegram на сервере (при остановленном веб-сервере)."""
    asyncio.run(terminal_login(state(ctx).data_dir, qr))


async def terminal_login(directory: Path, qr: bool = False) -> None:
    from .config import load_settings
    from .runtime import Runtime

    runtime = Runtime(await asyncio.to_thread(load_settings, directory), directory)
    try:
        if qr:
            from .qr_auth import terminal_qr_login

            await terminal_qr_login(runtime, console)
        else:

            async def ask_phone():
                return await asyncio.to_thread(
                    Prompt.ask, "Номер Telegram с кодом страны", console=console
                )

            async def ask_code():
                return await asyncio.to_thread(
                    Prompt.ask, "Код Telegram", password=True, console=console
                )

            async def ask_password():
                return await asyncio.to_thread(
                    Prompt.ask,
                    "Облачный пароль Telegram",
                    password=True,
                    console=console,
                )

            await runtime.client.start(
                phone=ask_phone, code_callback=ask_code, password=ask_password
            )
        console.print("[green]Вход в Telegram выполнен.[/green]")
    finally:
        await runtime.close()


@db_app.command("migrate")
def migrate_command(ctx: typer.Context):
    """Применить миграции и перенести старые настройки в SQLite."""
    with console.status("Применяем миграции…"):
        asyncio.run(migrate_database(state(ctx).data_dir))
    console.print("[green]Миграции применены.[/green]")


async def migrate_database(directory: Path) -> None:
    from .config import clean_legacy_config, load_settings
    from .database import Store

    settings = await asyncio.to_thread(load_settings, directory)
    store = Store(directory)
    try:
        await store.open()
        await store.bootstrap_settings(settings)
        await asyncio.to_thread(clean_legacy_config, settings)
    finally:
        await store.close()


@db_app.command("history")
def migration_history(ctx: typer.Context):
    """Показать применённые миграции, не изменяя базу."""
    path = state(ctx).data_dir / "tapkofon.sqlite3"
    if not path.is_file():
        console.print(
            "База ещё не создана. Выполните [cyan]tapkofon db migrate[/cyan]."
        )
        return
    connection = sqlite3.connect(
        "file:" + quote(path.as_posix(), safe="/:") + "?mode=ro", uri=True
    )
    try:
        rows = connection.execute(
            "SELECT app, name, applied_at FROM tortoise_migrations ORDER BY applied_at, name"
        ).fetchall()
    finally:
        connection.close()
    table = Table(title="История миграций", header_style="cyan")
    for column in ("Приложение", "Миграция", "Применена (UTC)"):
        table.add_column(column)
    for label, name, applied in rows:
        stamp = (
            datetime.fromisoformat(applied).astimezone(UTC).strftime("%d.%m.%Y %H:%M")
        )
        table.add_row(label, name, stamp)
    console.print(table)


@password_app.command("set")
def password_set(ctx: typer.Context):
    """Установить/сбросить пароль и отозвать прежние веб-сессии."""
    from .security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

    password = Prompt.ask("Новый пароль веб-клиента", password=True, console=console)
    repeat = Prompt.ask("Повторите пароль", password=True, console=console)
    if (
        not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH
        or password != repeat
    ):
        console.print(
            f"[red]Пароли должны совпадать и содержать {PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} символов.[/red]"
        )
        raise typer.Exit(1)
    with console.status("Сохраняем пароль…"):
        asyncio.run(set_password(state(ctx).data_dir, password))
    console.print("[green]Пароль сохранён. Прежние веб-сессии отозваны.[/green]")


async def set_password(directory: Path, password: str) -> None:
    from .config import clean_legacy_config, load_settings
    from .database import Store
    from .security import hash_password

    settings = await asyncio.to_thread(load_settings, directory)
    store = Store(directory)
    try:
        await store.open()
        await store.bootstrap_settings(settings)
        await store.change_password(await asyncio.to_thread(hash_password, password))
        await asyncio.to_thread(clean_legacy_config, settings)
    finally:
        await store.close()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    try:
        app()
    except KeyboardInterrupt:
        console.print("Остановлено.")
        raise SystemExit(130) from None
    except Exception as error:
        logging.getLogger(__name__).error(
            "CLI operation failed: %s", type(error).__name__
        )
        console.print(
            f"[red]Операция не выполнена ({type(error).__name__}). Проверьте конфиг и права доступа.[/red]"
        )
        raise SystemExit(1) from None
