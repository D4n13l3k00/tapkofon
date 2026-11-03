from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from conftest import post_form
from telethon import errors, types


def message(text="hello", file=None):
    return SimpleNamespace(
        id=42,
        text=text,
        file=file,
        mentioned=False,
        out=True,
        date=datetime.now(UTC),
        get_sender=AsyncMock(return_value=types.User(id=123, first_name="Tester")),
        get_reply_message=AsyncMock(return_value=None),
    )


def test_text_mode_does_not_load_pictures(web, telegram):
    telegram.get_messages.return_value = [
        message(file=SimpleNamespace(mime_type="image/png", name=None, size=12345))
    ]
    response = web.get("/chat/123")
    assert response.status_code == 200
    assert "<img" not in response.text
    assert "Фото ·" in response.text
    assert "/chat/123/media/42" in response.text
    assert "<textarea" not in response.text
    assert "/chat/123/compose" in response.text


def test_preferences_are_saved_in_sqlite_and_browser_isolated(web, telegram):
    web.get("/settings")
    original_cookies = dict(web.cookies)
    response = post_form(
        web,
        "/settings",
        {
            "show_images": "true",
            "page_size": "5",
            "image_size": "128",
            "text_limit": "300",
        },
    )
    assert response.status_code == 200
    assert "Настройки сохранены" in response.text
    assert 'value="128" selected' in response.text
    assert "tapkofon_prefs" not in web.cookies
    telegram.get_messages.return_value = [
        message(file=SimpleNamespace(mime_type="image/png", name=None, size=1))
    ]
    assert "<img" in web.get("/chat/123").text
    web.cookies.clear()
    assert "<img" not in web.get("/chat/123").text
    web.cookies.clear()
    web.cookies.update(original_cookies)
    assert "<img" in web.get("/chat/123").text


def test_invalid_settings_do_not_replace_saved_values(web):
    web.get("/settings")
    assert (
        post_form(
            web, "/settings", {"page_size": "99", "image_size": "999"}
        ).status_code
        == 422
    )
    assert 'value="176" selected' in web.get("/settings").text


def test_chat_pagination_and_filters(web, telegram):
    telegram.get_dialogs.return_value = [
        SimpleNamespace(id=i, title=f"Chat-{i:02}", unread_count=i % 2)
        for i in range(25)
    ]
    response = web.get("/")
    assert "Chat-09" in response.text and "Chat-10" not in response.text
    assert "Следующая" in response.text
    response = web.get("/?page=1")
    assert "Chat-10" in response.text and "Chat-09" not in response.text
    response = web.get("/?mode=unread")
    assert "Chat-01" in response.text and "Chat-00" not in response.text
    assert "Chat-19" in response.text and "Chat-21" not in response.text
    assert web.get("/?page=-1").status_code == 422


def test_favorites_toggle_and_filter(web, telegram):
    telegram.get_dialogs.return_value = [
        SimpleNamespace(id=123, title="Favorite chat", unread_count=0),
        SimpleNamespace(id=456, title="Other chat", unread_count=0),
    ]
    web.get("/")
    assert post_form(web, "/chat/123/favorite").status_code == 200
    response = web.get("/?mode=favorites")
    assert "Favorite chat" in response.text and "Other chat" not in response.text
    post_form(web, "/chat/123/favorite")
    assert "Избранных чатов нет" in web.get("/?mode=favorites").text


def test_long_message_preview_and_full_page(web, telegram):
    value = message("a" * 601 + "<script>unsafe</script>")
    telegram.get_messages.return_value = [value]
    response = web.get("/chat/123")
    assert "Полностью" in response.text
    assert "unsafe" not in response.text
    telegram.get_messages.return_value = value
    response = web.get("/chat/123/message/42")
    assert "unsafe" in response.text
    assert "<script>" not in response.text


def test_last_page_has_no_empty_older_link(web, telegram):
    telegram.get_messages.return_value = [message()]
    assert "Старые сообщения" not in web.get("/chat/123").text
    telegram.get_messages.return_value = [message()] * 11
    assert "Старые сообщения" in web.get("/chat/123").text


def test_compose_draft_and_quick_reply_do_not_send(web, telegram):
    web.get("/chat/123/compose")
    assert (
        post_form(
            web, "/chat/123/send_message", {"text": "first line", "action": "draft"}
        ).status_code
        == 200
    )
    assert "first line" in web.get("/chat/123/compose").text
    response = post_form(
        web,
        "/chat/123/send_message",
        {"text": "first line", "action": "insert", "quick_reply": "Спасибо"},
    )
    assert "first line\nСпасибо" in response.text
    telegram.send_message.assert_not_awaited()


def test_send_failure_preserves_text_before_connection(web, telegram):
    web.get("/chat/123/compose")
    telegram.is_connected.return_value = False
    telegram.connect.side_effect = OSError("offline")
    response = post_form(web, "/chat/123/send_message", {"text": "my draft"})
    assert response.status_code == 502
    assert "my draft" in response.text
    telegram.connect.side_effect = None
    telegram.is_connected.return_value = True
    assert "my draft" in web.get("/chat/123/compose").text


def test_success_clears_only_the_sent_draft(web):
    web.get("/chat/123/compose")
    post_form(
        web,
        "/chat/123/send_message",
        {"text": "reply draft", "reply_to": "42", "action": "draft"},
    )
    response = post_form(
        web, "/chat/123/send_message", {"text": "normal draft"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/chat/123?sent=1"
    assert "normal draft" not in web.get("/chat/123/compose").text
    assert "reply draft" in web.get("/chat/123/reply/42").text


def test_auth_shows_only_the_current_step(web, telegram):
    telegram.is_user_authorized.return_value = False
    response = web.get("/auth")
    assert 'type="tel"' in response.text
    assert 'name="code"' not in response.text and 'name="tfa"' not in response.text
    response = post_form(web, "/auth", {"phone": "+123"})
    assert 'name="code"' in response.text and 'name="tfa"' not in response.text
    assert 'type="tel"' not in response.text
    telegram.sign_in.side_effect = errors.SessionPasswordNeededError(request=None)
    response = post_form(web, "/auth", {"phone": "+123", "code": "12345"})
    assert 'name="tfa"' in response.text and 'name="code"' not in response.text
    assert 'name="tfa"' in web.get("/auth").text
    assert 'type="tel"' in web.get("/auth?restart=1").text


def test_auth_empty_code_does_not_request_another_code(web, telegram):
    telegram.is_user_authorized.return_value = False
    post_form(web, "/auth", {"phone": "+123"})
    response = post_form(web, "/auth", {"phone": "+123", "step": "code"})
    assert 'name="code"' in response.text
    telegram.send_code_request.assert_awaited_once()


def test_common_document_and_no_scripts(web):
    for route in (
        "/",
        "/settings",
        "/about",
        "/cache",
        "/auth",
        "/chat/123",
        "/chat/123/compose",
    ):
        response = web.get(route)
        assert response.text.startswith("<!DOCTYPE html>")
        assert '<meta charset="utf-8">' in response.text
        assert 'name="viewport"' in response.text
        assert "<style>" in response.text
        assert "<script" not in response.text


def test_profile_avatar_is_optional(web, telegram):
    telegram.get_entity.return_value.photo = types.UserProfilePhoto(photo_id=1, dc_id=1)
    telegram.side_effect = AsyncMock(
        return_value=SimpleNamespace(full_user=SimpleNamespace(about=""))
    )
    response = web.get("/user/123")
    assert "Открыть аватар" in response.text
    assert "<img" not in response.text


def test_plain_html_mode_keeps_forms_and_navigation(web):
    web.get("/settings")
    post_form(web, "/settings", {"simple_html": "true"})
    response = web.get("/chat/123/compose")
    assert "<style>" not in response.text
    assert "<textarea" in response.text
    assert 'name="csrf_token"' in response.text
    assert "Назад в чат" in response.text
    assert (
        post_form(
            web, "/chat/123/send_message", {"text": "plain draft", "action": "draft"}
        ).status_code
        == 200
    )


def test_attachment_step_saves_text_before_showing_file_picker(web, telegram):
    response = web.get("/chat/123/compose")
    assert 'type="file"' not in response.text
    assert 'enctype="multipart/form-data"' not in response.text
    response = post_form(
        web, "/chat/123/send_message", {"action": "attach", "text": "caption"}
    )
    assert 'type="file"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert "caption" in response.text
    assert "caption" in web.get("/chat/123/compose").text
    telegram.send_message.assert_not_awaited()
