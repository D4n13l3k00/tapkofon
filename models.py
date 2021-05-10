from pydantic import BaseModel
from fastapi import File, UploadFile
from typing import *

##### / Модели данных / #####
class Chat(BaseModel):
    id: int
    title: str
    unread: int
class MessageMedia(BaseModel):
    type: Optional[str] = None
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