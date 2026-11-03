import io
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from conftest import post_form
from PIL import Image
from telethon import types


def test_chat_renders_reply_and_escapes_content(web, telegram):
    sender = types.User(id=123, first_name="<script>sender</script>")
    reply = SimpleNamespace(
        id=41, text="<b>reply</b>", file=None, get_sender=AsyncMock(return_value=None)
    )
    message = SimpleNamespace(
        id=42,
        text="<script>message</script>",
        file=None,
        mentioned=True,
        date=datetime.now(UTC),
        out=True,
        get_sender=AsyncMock(return_value=sender),
        get_reply_message=AsyncMock(return_value=reply),
    )
    telegram.get_messages.return_value = [message]
    response = web.get("/chat/123")
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;message" in response.text
    assert "&lt;b&gt;reply" in response.text
    assert "Неизвестно" in response.text


def test_missing_message_is_html_404(web, telegram):
    telegram.get_messages.return_value = None
    response = web.get("/chat/123/edit/42")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]


def test_image_download_response_and_range(web, telegram):
    image = io.BytesIO()
    Image.new("RGB", (300, 300), "red").save(image, "PNG")
    telegram.get_messages.return_value = SimpleNamespace(
        id=42,
        file=SimpleNamespace(mime_type="image/png", ext=".png", name=None),
        download_media=AsyncMock(return_value=image.getvalue()),
    )
    response = web.get("/chat/123/download/42")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(response.content)) as result:
        assert result.size == (176, 176)
    response = web.get("/chat/123/download/42", headers={"Range": "bytes=0-9"})
    assert response.status_code == 206
    assert len(response.content) == 10


def test_avatar_format_and_size(web, telegram):
    image = io.BytesIO()
    Image.new("RGBA", (400, 400)).save(image, "PNG")
    telegram.download_profile_photo = AsyncMock(return_value=image.getvalue())
    response = web.get("/user/123/avatar")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(response.content)) as result:
        assert result.size == (176, 176)
    telegram.download_profile_photo.return_value = None
    assert web.get("/user/123/avatar").status_code == 404


def test_profile_uses_current_full_user_schema(web, telegram):
    telegram.side_effect = AsyncMock(
        return_value=SimpleNamespace(full_user=SimpleNamespace(about="Test bio"))
    )
    response = web.get("/user/123")
    assert response.status_code == 200
    assert "Test bio" in response.text
    assert "Неизвестно" in response.text


def test_old_csrf_form_is_rejected_after_restart(tmp_path, telegram):
    from fastapi.testclient import TestClient

    from tapkofon.config import Settings
    from tapkofon.main import create_app

    first_app = create_app(settings=Settings(), data_dir=tmp_path, client=telegram)
    with TestClient(first_app) as first:
        first.get("/pass", follow_redirects=False)
        token = first_app.state.runtime.form_token(first.cookies["tapkofon_browser"])
    with TestClient(
        create_app(settings=Settings(), data_dir=tmp_path, client=telegram)
    ) as second:
        assert second.post("/pass", data={"csrf_token": token}).status_code == 403
        assert post_form(second, "/pass").status_code == 200
