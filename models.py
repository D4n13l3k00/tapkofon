# Copyright 2022 d4n13l3k00.
# SPDX-License-Identifier: 	AGPL-3.0-or-later

from typing import *

from fastapi import File, UploadFile
from pydantic import BaseModel


##### / Модели данных / #####
class Chat(BaseModel):
    id: int
    title: str
    unread: int


class MessageMedia(BaseModel):
    type: Optional[str] = None
    typ: Optional[str] = None
    filename: Optional[str] = None
    size: Optional[str] = None


class ReplyMessage(BaseModel):
    name: str
    text: Optional[str] = None
    id: int
    file: Optional[MessageMedia] = None


class Message(BaseModel):
    id: int
    sender: Any
    text: Optional[str] = None
    file: Optional[MessageMedia] = None
    reply: Optional[ReplyMessage] = None
    mentioned: bool
    date: str
    out: bool
