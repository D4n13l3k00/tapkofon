import asyncio
import copy
import sqlite3
import tomllib
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from conftest import post_form
from fastapi.testclient import TestClient

from tapkofon.config import Settings
from tapkofon.db_models import AccessSession
from tapkofon.main import create_app
from tapkofon.security import verify_password

PASSWORD = "test access password 2026"
NEW_PASSWORD = "another test password 2026"


def save_browser(web):
    jar = CookieJar()
    for cookie in web.cookies.jar:
        jar.set_cookie(copy.copy(cookie))
    return jar


def enable_password(web):
    web.get("/admin")
    response = post_form(
        web, "/admin/password", {"new_password": PASSWORD, "repeat_password": PASSWORD}
    )
    assert response.status_code == 200


def test_web_password_is_hashed_and_api_keys_stay_server_side(tmp_path, telegram):
    settings = Settings(api_id=7654321, api_hash="server-only-test-value")
    with TestClient(
        create_app(settings=settings, data_dir=tmp_path, client=telegram),
        base_url="http://localhost",
        client=("127.0.0.1", 50000),
    ) as web:
        enable_password(web)
        response = web.get("/admin")
        assert "server-only-test-value" not in response.text
        assert "7654321" not in response.text
        with sqlite3.connect(tmp_path / "tapkofon.sqlite3") as db:
            encoded = db.execute(
                "SELECT password_hash FROM applicationsetting"
            ).fetchone()[0]
            fields = {
                row[1] for row in db.execute("PRAGMA table_info(applicationsetting)")
            }
        assert encoded.startswith("$argon2id$")
        assert PASSWORD not in encoded
        assert verify_password(encoded, PASSWORD)
        assert not {"api_id", "api_hash", "passwd"} & fields


def test_initial_admin_setup_requires_local_peer_and_host(tmp_path, telegram):
    app = create_app(settings=Settings(), data_dir=tmp_path, client=telegram)
    with TestClient(
        app, base_url="http://localhost", client=("203.0.113.1", 50000)
    ) as remote:
        assert remote.get("/admin").status_code == 403
        assert (
            post_form(
                remote,
                "/admin/password",
                {"new_password": PASSWORD, "repeat_password": PASSWORD},
            ).status_code
            == 403
        )
    with TestClient(
        app, base_url="http://public.example", client=("127.0.0.1", 50000)
    ) as rebinding:
        assert rebinding.get("/admin").status_code == 403


def test_password_change_revokes_other_browser_and_old_forms(web):
    enable_password(web)
    first_browser = save_browser(web)
    old_browser_id = web.cookies["tapkofon_browser"]
    old_csrf = web.app.state.runtime.form_token(old_browser_id)
    web.cookies.clear()
    assert post_form(web, "/pass", {"password": PASSWORD}).status_code == 200
    second_browser = save_browser(web)
    web.cookies = first_browser
    response = post_form(
        web,
        "/admin/password",
        {
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "repeat_password": NEW_PASSWORD,
        },
    )
    assert response.status_code == 200
    assert web.get("/").status_code == 200
    assert web.post("/admin/settings", data={"csrf_token": old_csrf}).status_code == 403
    web.cookies = second_browser
    assert web.get("/", follow_redirects=False).status_code == 303
    assert post_form(web, "/pass", {"password": PASSWORD}).status_code == 401
    assert post_form(web, "/pass", {"password": NEW_PASSWORD}).status_code == 200


def test_wrong_current_password_cannot_change_password(web):
    enable_password(web)
    assert (
        post_form(
            web,
            "/admin/password",
            {
                "current_password": "wrong",
                "new_password": NEW_PASSWORD,
                "repeat_password": NEW_PASSWORD,
            },
        ).status_code
        == 401
    )
    web.cookies.clear()
    assert post_form(web, "/pass", {"password": PASSWORD}).status_code == 200


def test_password_disabling_requires_explicit_confirmation(web):
    enable_password(web)
    assert (
        post_form(
            web, "/admin/password", {"current_password": PASSWORD, "action": "disable"}
        ).status_code
        == 400
    )
    assert (
        post_form(
            web,
            "/admin/password",
            {
                "current_password": PASSWORD,
                "action": "disable",
                "confirm_open_access": "true",
            },
        ).status_code
        == 200
    )
    web.cookies.clear()
    assert web.get("/").status_code == 200


def test_lock_revokes_cookie_on_server(web):
    enable_password(web)
    old_browser = save_browser(web)
    assert web.get("/lock").status_code == 200
    assert web.get("/").status_code == 200
    post_form(web, "/lock")
    web.cookies = old_browser
    assert web.get("/", follow_redirects=False).status_code == 303


def test_session_expires_even_with_cookie(web):
    enable_password(web)

    async def expire():
        async with web.app.state.runtime.store.scope():
            await AccessSession.all().update(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )

    web.portal.call(expire)
    assert web.get("/", follow_redirects=False).status_code == 303


def test_session_cookie_is_bound_to_browser(web):
    enable_password(web)
    token = web.cookies["access_token"]
    web.cookies.clear()
    web.get("/pass")
    web.cookies.set("access_token", token)
    assert web.get("/", follow_redirects=False).status_code == 303


def test_csrf_token_from_another_browser_is_rejected(web):
    web.get("/admin")
    token = web.app.state.runtime.form_token(web.cookies["tapkofon_browser"])
    web.cookies.clear()
    web.get("/admin")
    assert (
        web.post(
            "/admin/settings", data={"csrf_token": token, "pic_quality": "50"}
        ).status_code
        == 403
    )


def test_same_host_wrong_origin_scheme_is_rejected(web):
    web.get("/admin")
    assert (
        post_form(
            web,
            "/admin/settings",
            {"pic_quality": "50"},
            headers={"Origin": "https://localhost"},
        ).status_code
        == 403
    )


def test_password_attempts_are_limited(web):
    enable_password(web)
    post_form(web, "/lock")
    for _ in range(5):
        assert post_form(web, "/pass", {"password": "wrong"}).status_code == 401
    assert post_form(web, "/pass", {"password": PASSWORD}).status_code == 429


def test_common_settings_are_live_and_validated(web):
    web.get("/admin")
    assert (
        post_form(
            web,
            "/admin/settings",
            {
                "pic_quality": "42",
                "pic_format": "png",
                "recognize_lang": "en-US",
                "msg_regex_tme": "true",
            },
        ).status_code
        == 200
    )
    assert 'value="42"' in web.get("/admin").text
    assert web.app.state.runtime.settings.pic_quality == 42
    assert web.app.state.runtime.settings.recognize_lang == "en-US"
    assert web.app.state.runtime.settings.recognize_enabled is False
    assert web.get("/chat/123/recognize/42").status_code == 403
    assert post_form(web, "/admin/settings", {"pic_quality": "101"}).status_code == 422
    assert web.app.state.runtime.settings.pic_quality == 42


def test_legacy_config_is_imported_once_and_cleaned(tmp_path, telegram, monkeypatch):
    for name in ("TAPKOFON_API_ID", "TAPKOFON_API_HASH", "TAPKOFON_PASSWD"):
        monkeypatch.delenv(name, raising=False)
    config = tmp_path / "config.toml"
    config.write_text(
        'api_id = 123\napi_hash = "server-only-test-value"\npasswd = "legacy test password"\npic_quality = 55\nrecognize_lang = "en-US"\n',
        encoding="utf-8",
    )
    with TestClient(create_app(data_dir=tmp_path, client=telegram)) as web:
        assert (
            post_form(web, "/pass", {"password": "legacy test password"}).status_code
            == 200
        )
    values = tomllib.loads(config.read_text(encoding="utf-8"))
    assert values["api_id"] == 123 and values["api_hash"] == "server-only-test-value"
    assert (
        not {"passwd", "pic_quality", "recognize_lang", "access_cookie"} & values.keys()
    )
    app = create_app(data_dir=tmp_path, client=telegram)
    with TestClient(app) as web:
        assert (
            post_form(web, "/pass", {"password": "legacy test password"}).status_code
            == 200
        )
        assert app.state.runtime.settings.pic_quality == 55


@pytest.mark.parametrize(
    "mime, extension, variant",
    [("text/html", ".html", "default"), ("image/svg+xml", ".svg", "full")],
)
def test_active_attachment_cannot_render_in_app_origin(
    web, telegram, mime, extension, variant
):
    async def download(file):
        await asyncio.to_thread(
            Path(file).write_bytes, b"<html><script>alert(1)</script></html>"
        )
        return file

    telegram.get_messages.return_value = SimpleNamespace(
        id=42,
        file=SimpleNamespace(name=f"message{extension}", ext=extension, mime_type=mime),
        download_media=AsyncMock(side_effect=download),
    )
    response = web.get(f"/chat/123/download/42?variant={variant}")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
