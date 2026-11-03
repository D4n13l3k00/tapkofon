import asyncio
import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from conftest import post_form
from PIL import Image
from rich.console import Console
from telethon import errors

from tapkofon.config import Settings
from tapkofon.qr_auth import terminal_qr_login
from tapkofon.runtime import Runtime


def pending_qr(telegram):
    async def wait():
        await asyncio.Event().wait()

    qr = SimpleNamespace(
        url="tg://login?token=synthetic-test-token",
        expires=datetime.now(UTC) + timedelta(seconds=30),
        wait=AsyncMock(side_effect=wait),
    )
    telegram.is_user_authorized.return_value = False
    telegram.qr_login = AsyncMock(return_value=qr)
    return qr


def test_web_qr_listener_starts_before_image_and_token_stays_private(web, telegram):
    qr = pending_qr(telegram)
    response = post_form(web, "/auth/qr")
    assert response.status_code == 200
    qr.wait.assert_awaited_once()
    assert "tg://login" not in response.text
    assert "synthetic-test-token" not in response.text
    response = web.get("/auth/qr/image")
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.width >= 128
    challenge = web.app.state.runtime.qr
    assert challenge.task is not None and not challenge.task.done()
    web.cookies.clear()
    assert web.get("/auth/qr/image").status_code == 404
    assert post_form(web, "/auth/qr").status_code == 409


def test_web_qr_check_authorized_and_2fa(web, telegram):
    qr = pending_qr(telegram)
    qr.wait.side_effect = errors.SessionPasswordNeededError(request=None)
    post_form(web, "/auth/qr")
    response = post_form(web, "/auth/qr/check")
    assert "Облачный пароль" in response.text
    telegram.sign_in.side_effect = errors.PasswordHashInvalidError(request=None)
    assert (
        post_form(web, "/auth/qr/password", {"tfa": "test-cloud-password"}).status_code
        == 401
    )
    telegram.sign_in.side_effect = None
    response = post_form(web, "/auth/qr/password", {"tfa": "test-cloud-password"})
    assert "Tester" in response.text
    assert "test-cloud-password" not in response.text
    telegram.sign_in.assert_awaited_with(password="test-cloud-password")
    assert web.get("/auth/qr/image").status_code == 410


def test_expired_qr_can_be_recreated(web, telegram):
    qr = pending_qr(telegram)
    qr.wait.side_effect = TimeoutError
    post_form(web, "/auth/qr")
    assert "истёк" in post_form(web, "/auth/qr/check").text
    assert web.get("/auth/qr/image").status_code == 410
    old = web.app.state.runtime.qr.public_id
    qr.wait.side_effect = AsyncMock(
        return_value=SimpleNamespace(id=1, first_name="QR user")
    )
    post_form(web, "/auth/qr")
    assert web.app.state.runtime.qr.public_id != old
    assert "QR user" in post_form(web, "/auth/qr/check").text


def test_starting_phone_login_cancels_pending_qr(web, telegram):
    pending_qr(telegram)
    post_form(web, "/auth/qr")
    task = web.app.state.runtime.qr.task
    post_form(web, "/auth", {"phone": "+123"})
    assert task.cancelled()
    assert web.app.state.runtime.qr is None


def test_terminal_qr_handles_2fa_without_printing_url(tmp_path, telegram, monkeypatch):
    qr = pending_qr(telegram)
    qr.wait.side_effect = errors.SessionPasswordNeededError(request=None)
    monkeypatch.setattr(
        "tapkofon.qr_auth.Prompt.ask", lambda *args, **kwargs: "test-cloud-password"
    )
    output = io.StringIO()
    console = Console(file=output, width=90)
    asyncio.run(terminal_qr_login(Runtime(Settings(), tmp_path, telegram), console))
    telegram.sign_in.assert_awaited_once_with(password="test-cloud-password")
    assert "Telegram QR" in output.getvalue()
    assert "tg://login" not in output.getvalue()
    assert "test-cloud-password" not in output.getvalue()
