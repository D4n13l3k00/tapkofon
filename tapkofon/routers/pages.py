import asyncio
import html

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from ..preferences import Preferences, get_preferences, save_preferences
from ..runtime import get_runtime
from ..utils import cache_tree, clear_dir, get_size, humanize
from ..views import render

router = APIRouter()


@router.get("/settings")
async def settings_form(request: Request):
    return render(request, "settings.html")


@router.post("/settings")
async def settings_save(
    request: Request,
    show_images: bool = Form(False),
    simple_html: bool = Form(False),
    page_size: int = Form(10),
    image_size: int = Form(176),
    text_limit: int = Form(600),
):
    try:
        preferences = Preferences.model_validate(
            dict(
                show_images=show_images,
                simple_html=simple_html,
                page_size=page_size,
                image_size=image_size,
                text_limit=text_limit,
                favorites=get_preferences(request).favorites,
            )
        )
    except ValidationError:
        return render(
            request, "settings.html", msg="Выберите значения из списка", status_code=422
        )
    response = RedirectResponse("/settings?saved=1", status_code=303)
    return await save_preferences(request, response, preferences)


@router.get("/about")
async def about(request: Request):
    return render(request, "about.html")


@router.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@router.get("/cache")
async def cache(request: Request):
    size = await asyncio.to_thread(get_size, get_runtime(request).cache_dir)
    return render(
        request,
        "cache.html",
        size=humanize(size),
        count=await get_runtime(request).store.cache_count(),
    )


@router.post("/cache/clear")
async def cache_clear(request: Request):
    runtime = get_runtime(request)
    async with runtime.media_lock:
        async with runtime.recognition_lock:
            await asyncio.to_thread(clear_dir, runtime.cache_dir)
            await runtime.store.clear_cache()
    return RedirectResponse("/cache", status_code=303)


@router.get("/cache/list")
async def cache_list(request: Request):
    tree = await asyncio.to_thread(cache_tree, get_runtime(request).cache_dir)
    if not tree:
        return render(request, "error.html", error="Кеш пустой")
    return render(request, "cache_list.html", tree=html.escape(tree))
