import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon import errors, types


def history_message(number):
    return SimpleNamespace(
        id=number,
        text=f"history-{number}",
        file=None,
        mentioned=False,
        out=False,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        get_sender=AsyncMock(return_value=types.User(id=123, first_name="Tester")),
        get_reply_message=AsyncMock(return_value=None),
    )


def install_history(telegram, numbers):
    async def get_messages(entity, *, limit, offset_id=0, reverse=False, add_offset=0):
        selected = sorted(
            (
                n
                for n in numbers
                if not offset_id or (n > offset_id if reverse else n < offset_id)
            ),
            reverse=not reverse,
        )
        return [history_message(n) for n in selected[add_offset : add_offset + limit]]

    telegram.get_messages.side_effect = get_messages


def ids(response):
    assert response.status_code == 200
    return [int(n) for n in re.findall(r"history-(\d+)", response.text)]


def link(response, label):
    match = re.search(r'<a href="([^"]+)">' + label + r"</a>", response.text)
    assert match, response.text
    return match.group(1)


def test_latest_acknowledges_only_displayed_boundary(web, telegram):
    install_history(telegram, list(range(1, 21)))
    assert ids(web.get("/chat/123")) == list(range(20, 10, -1))
    assert telegram.send_read_acknowledge.await_args.kwargs == {"max_id": 20}


@pytest.mark.parametrize("failure", ["fetch", "present"])
def test_failed_history_does_not_mark_read(web, telegram, failure):
    if failure == "fetch":
        telegram.get_messages.side_effect = errors.RPCError(None, "offline")
    else:
        item = history_message(20)
        item.get_sender.side_effect = errors.RPCError(None, "offline")
        telegram.get_messages.return_value = [item]
    assert web.get("/chat/123").status_code == 502
    telegram.send_read_acknowledge.assert_not_awaited()


def test_empty_history_does_not_mark_read(web, telegram):
    assert ids(web.get("/chat/123")) == []
    telegram.send_read_acknowledge.assert_not_awaited()


@pytest.mark.parametrize("change", ["insert", "delete"])
def test_history_navigation_survives_changes(web, telegram, change):
    numbers = list(range(1, 31))
    install_history(telegram, numbers)
    first = web.get("/chat/123")
    assert ids(first) == list(range(30, 20, -1))
    if change == "insert":
        numbers.append(31)
    else:
        numbers.remove(30)
    telegram.send_read_acknowledge.reset_mock()
    older = web.get(link(first, "Старые сообщения"))
    assert ids(older) == list(range(20, 10, -1))
    newer = web.get(link(older, "Новые сообщения"))
    assert ids(newer) == (
        list(range(30, 20, -1)) if change == "insert" else list(range(29, 20, -1))
    )
    telegram.send_read_acknowledge.assert_not_awaited()
    last = web.get(link(older, "Старые сообщения"))
    assert ids(last) == list(range(10, 0, -1))
    assert "Старые сообщения</a>" not in last.text


@pytest.mark.parametrize("query", ["before=0", "after=-1", "before=10&after=20"])
def test_invalid_history_cursors(web, telegram, query):
    assert web.get("/chat/123?" + query).status_code == 422
    telegram.send_read_acknowledge.assert_not_awaited()
