"""Validated settings for one browser; cookies contain only a random identifier."""

from typing import Literal

from fastapi import Request
from pydantic import BaseModel, Field


class Preferences(BaseModel):
    show_images: bool = False
    simple_html: bool = False
    page_size: Literal[5, 10, 20] = 10
    image_size: Literal[128, 176, 240] = 176
    text_limit: Literal[300, 600, 1200] = 600
    favorites: list[int] = Field(default_factory=list, max_length=32)


def get_preferences(request: Request) -> Preferences:
    return getattr(request.state, "preferences", Preferences())


async def save_preferences(request: Request, response, preferences: Preferences):
    await request.app.state.runtime.store.save_preferences(
        request.state.browser_id, preferences
    )
    response.delete_cookie("tapkofon_prefs")
    return response
