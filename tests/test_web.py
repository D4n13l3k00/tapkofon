import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from conftest import post_form
from fastapi.testclient import TestClient
from telethon import errors, types

from tapkofon.config import Settings
from tapkofon.main import create_app


def test_html_routes_and_shutdown(tmp_path, telegram):
    app = create_app(settings=Settings(), data_dir=tmp_path, client=telegram)
    with TestClient(app) as web:
        for url in (
            "/",
            "/about",
            "/auth",
            "/cache",
            "/cache/list",
            "/logout",
            "/docs",
        ):
            assert web.get(url).status_code == 200
        assert web.get("/health").json() == {"status": "ok"}
        assert web.get("/about").headers["cache-control"] == "no-store"
    telegram.disconnect.assert_awaited_once()


def test_missing_credentials_do_not_break_public_pages(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as web:
        assert web.get("/about").status_code == 200
        response = web.get("/")
        assert response.status_code == 503
        assert "api_id" in response.text


def test_templates_work_outside_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app(data_dir=tmp_path / "session")) as web:
        assert web.get("/about").status_code == 200


def test_password_access_and_cookie(tmp_path, telegram):
    app = create_app(
        settings=Settings(passwd="пароль"), data_dir=tmp_path, client=telegram
    )
    with TestClient(app) as web:
        assert web.get("/", follow_redirects=False).headers["location"] == "/pass"
        form = web.get("/pass")
        match = re.search(r'name="csrf_token" value="([^"]+)"', form.text)
        assert match is not None
        token = match.group(1)
        assert (
            web.post(
                "/pass", data={"password": "wrong", "csrf_token": token}
            ).status_code
            == 401
        )
        response = web.post(
            "/pass",
            data={"password": "пароль", "csrf_token": token},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "HttpOnly" in response.headers["set-cookie"]
        assert web.get("/").status_code == 200
        post_form(web, "/lock")
        assert web.get("/", follow_redirects=False).status_code == 303


def test_post_requires_csrf_and_rejects_cross_site(web, telegram):
    assert web.post("/chat/1/send_message", data={"text": "test"}).status_code == 403
    assert (
        post_form(
            web,
            "/chat/1/send_message",
            {"text": "test"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    telegram.send_message.assert_not_awaited()


def test_unauthorized_telegram(web, telegram):
    telegram.is_user_authorized.return_value = False
    assert web.get("/").status_code == 401
    assert web.get("/chat/123").status_code == 401


def test_auth_code_then_2fa(web, telegram):
    telegram.is_user_authorized.return_value = False
    assert post_form(web, "/auth", {"phone": "+123"}).status_code == 200
    telegram.send_code_request.assert_awaited_once_with("+123")
    telegram.sign_in.side_effect = errors.SessionPasswordNeededError(request=None)
    response = post_form(web, "/auth", {"phone": "+123", "code": "12345"})
    assert "2FA" in response.text
    telegram.sign_in.assert_awaited_with(
        phone="+123", code="12345", phone_code_hash="hash"
    )
    telegram.sign_in.side_effect = None
    response = post_form(web, "/auth", {"phone": "+123", "tfa": "secret"})
    assert "Tester" in response.text
    assert "secret" not in response.text
    telegram.sign_in.assert_awaited_with(password="secret")


@pytest.mark.parametrize(
    "exception, expected",
    [
        (errors.PhoneCodeInvalidError(request=None), "Неверный код"),
        (errors.PhoneCodeExpiredError(request=None), "истёк"),
        (errors.FloodWaitError(request=None, capture=42), "42"),
    ],
)
def test_auth_errors(web, telegram, exception, expected):
    telegram.is_user_authorized.return_value = False
    web.app.state.runtime.phone_codes["+123"] = "hash"
    telegram.sign_in.side_effect = exception
    assert expected in post_form(web, "/auth", {"phone": "+123", "code": "12345"}).text


def test_message_and_attachment_submission(web, telegram):
    assert (
        post_form(web, "/chat/-123/send_message", {"text": "<b>text</b>"}).status_code
        == 200
    )
    telegram.send_message.assert_awaited_once_with(-123, "<b>text</b>", reply_to=None)
    response = post_form(
        web,
        "/chat/-123/send_message",
        {"text": "caption", "reply_to": "42"},
        files={"file": ("test.txt", b"file contents", "text/plain")},
    )
    assert response.status_code == 200
    assert telegram.send_file.await_args.args[1].getvalue() == b"file contents"
    assert telegram.send_file.await_args.kwargs["reply_to"] == 42
    assert post_form(web, "/chat/1/send_message").status_code == 400


def test_delete_is_post_only_and_edit(web, telegram):
    message = SimpleNamespace(id=42, text="old", edit=AsyncMock(), delete=AsyncMock())
    telegram.get_messages.return_value = message
    assert web.get("/chat/1/delete/42").status_code == 200
    message.delete.assert_not_awaited()
    assert post_form(web, "/chat/1/delete/42").status_code == 200
    message.delete.assert_awaited_once()
    assert (
        post_form(
            web, "/chat/1/edit_message", {"msg_id": "42", "text": "new"}
        ).status_code
        == 200
    )
    message.edit.assert_awaited_once_with("new")


def test_marked_channel_id_in_links(web, telegram):
    telegram.get_entity.return_value = types.Channel(
        id=123, title="Channel", photo=types.ChatPhotoEmpty(), date=None
    )
    response = web.get("/chat/-1000000000123")
    assert response.status_code == 200
    assert "/chat/-1000000000123/compose" in response.text


def test_cache_clear_is_post_only(web):
    cache = web.app.state.runtime.cache_dir
    cache.mkdir()
    (cache / "test.txt").write_text("test")
    assert web.get("/cache/clear").status_code == 405
    assert (cache / "test.txt").exists()
    assert post_form(web, "/cache/clear").status_code == 200
    assert not list(cache.iterdir())


def test_logout_requires_post(web, telegram):
    web.get("/logout")
    telegram.log_out.assert_not_awaited()
    assert post_form(web, "/logout").status_code == 200
    telegram.log_out.assert_awaited_once()
