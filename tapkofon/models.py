# Copyright 2022 d4n13l3k00.
# SPDX-License-Identifier: AGPL-3.0-or-later
from dataclasses import dataclass
from typing import Any


@dataclass
class Chat:
    id: int
    title: str
    unread: int


@dataclass
class MessageMedia:
    type: str
    typ: str
    size: str
    filename: str | None = None


@dataclass
class ReplyMessage:
    name: str
    id: int
    file: MessageMedia | None = None
    text: str | None = None
    truncated: bool = False


@dataclass
class Message:
    id: int
    sender: Any
    text: str | None
    file: MessageMedia | None
    reply: ReplyMessage | None
    mentioned: bool
    date: str
    out: bool
    truncated: bool = False
