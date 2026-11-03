from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from telethon import types

from tapkofon.config import Settings
from tapkofon.main import create_app


@pytest.fixture
def telegram():
    client = Mock()
    client.is_connected.return_value = False
    client.connect = AsyncMock(
        side_effect=lambda: setattr(client.is_connected, "return_value", True)
    )
    client.disconnect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.get_me = AsyncMock(return_value=SimpleNamespace(first_name="Tester", id=1))
    client.get_dialogs = AsyncMock(return_value=[])
    client.get_entity = AsyncMock(return_value=types.User(id=123, first_name="Test"))
    client.get_messages = AsyncMock(return_value=[])
    client.send_read_acknowledge = AsyncMock()
    client.send_message = AsyncMock()
    client.send_file = AsyncMock()
    client.send_code_request = AsyncMock(
        return_value=SimpleNamespace(phone_code_hash="hash")
    )
    client.sign_in = AsyncMock()
    client.log_out = AsyncMock()
    return client


@pytest.fixture
def web(tmp_path, telegram):
    app = create_app(settings=Settings(), data_dir=tmp_path, client=telegram)
    with TestClient(
        app, base_url="http://localhost", client=("127.0.0.1", 50000)
    ) as client:
        yield client


def post_form(web, url, data=None, **kwargs):
    if "tapkofon_browser" not in web.cookies:
        web.get("/pass", follow_redirects=False)
    token = web.app.state.runtime.form_token(web.cookies["tapkofon_browser"])
    return web.post(
        url,
        data={"csrf_token": token, **(data or {})},
        **kwargs,
    )
