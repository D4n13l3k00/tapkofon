import logging
import sqlite3
from unittest.mock import AsyncMock, Mock

from typer.testing import CliRunner

from tapkofon import cli
from tapkofon.logging_config import SafeLogFilter
from tapkofon.security import verify_password

runner = CliRunner()


def test_cli_help_and_validation_do_not_create_files(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPKOFON_DATA_DIR", str(tmp_path / "data"))
    assert runner.invoke(cli.app, ["--help"]).exit_code == 0
    assert runner.invoke(cli.app, ["--version"]).exit_code == 0
    assert runner.invoke(cli.app, ["serve", "--port", "70000"]).exit_code == 2
    assert not list(tmp_path.iterdir())


def test_cli_serve_dispatch_and_default(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPKOFON_DATA_DIR", str(tmp_path))
    serve = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", serve)
    assert (
        runner.invoke(
            cli.app, ["serve", "--host", "0.0.0.0", "--port", "9000"]
        ).exit_code
        == 0
    )
    assert serve.call_args.kwargs["port"] == 9000
    assert serve.call_args.kwargs["log_config"]["handlers"]["rich"]
    assert runner.invoke(cli.app, []).exit_code == 0
    assert serve.call_args.kwargs["host"] == "127.0.0.1"


def test_cli_migration_and_read_only_history(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPKOFON_DATA_DIR", str(tmp_path))
    result = runner.invoke(cli.app, ["db", "history"])
    assert result.exit_code == 0
    assert not (tmp_path / "tapkofon.sqlite3").exists()
    assert runner.invoke(cli.app, ["db", "migrate"]).exit_code == 0
    with sqlite3.connect(tmp_path / "tapkofon.sqlite3") as db:
        before = db.execute("SELECT count(*) FROM tortoise_migrations").fetchone()[0]
    result = runner.invoke(cli.app, ["db", "history"])
    assert result.exit_code == 0
    assert "0003_application_security" in result.output
    with sqlite3.connect(tmp_path / "tapkofon.sqlite3") as db:
        assert (
            db.execute("SELECT count(*) FROM tortoise_migrations").fetchone()[0]
            == before
        )


def test_cli_password_is_not_an_argument_or_output(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPKOFON_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        cli.Prompt, "ask", lambda *args, **kwargs: "terminal test password"
    )
    result = runner.invoke(cli.app, ["password", "set"])
    assert result.exit_code == 0
    assert "terminal test password" not in result.output
    with sqlite3.connect(tmp_path / "tapkofon.sqlite3") as db:
        encoded = db.execute("SELECT password_hash FROM applicationsetting").fetchone()[
            0
        ]
    assert verify_password(encoded, "terminal test password")


def test_cli_qr_dispatch(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPKOFON_DATA_DIR", str(tmp_path))
    login = AsyncMock()
    monkeypatch.setattr(cli, "terminal_login", login)
    assert runner.invoke(cli.app, ["login", "--qr"]).exit_code == 0
    login.assert_awaited_once_with(tmp_path, True)


def test_log_filter_removes_query_and_exception_values():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", "/pass?password=test-private-value", "1.1", 200),
        None,
    )
    SafeLogFilter().filter(record)
    assert "test-private-value" not in record.getMessage()
    assert "/pass" in record.getMessage()
    error = ValueError("test-private-value")
    record.exc_info = (ValueError, error, None)
    SafeLogFilter().filter(record)
    assert record.exc_info is not None
    assert "test-private-value" not in str(record.exc_info[1])
