import io
from typing import Literal
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, RedirectResponse
from telethon.utils import get_peer_id

from .. import models
from ..media import cached_media, cached_recognition, media_type
from ..preferences import get_preferences, save_preferences
from ..runtime import NotAuthorized, authorized, entity_id, get_runtime
from ..utils import humanize, replacing_text
from ..views import render

router = APIRouter(dependencies=[Depends(authorized)])
# Save text before attempting a network connection or Telegram authorization.
compose_router = APIRouter()
QUICK_REPLIES = ("Да", "Нет", "Хорошо", "Спасибо", "Напишу позже")


def message_media(message) -> models.MessageMedia | None:
    if not message.file:
        return None
    mime = message.file.mime_type or "application/octet-stream"
    return models.MessageMedia(
        type=mime,
        typ=mime.split("/")[0],
        size=humanize(message.file.size or 0),
        filename=message.file.name,
    )


async def find_message(request: Request, chat: str, message_id: int):
    message = await get_runtime(request).client.get_messages(
        entity_id(chat), ids=message_id
    )
    if not message:
        raise HTTPException(404, "Такого сообщения не существует")
    return message


def display_text(text: str | None, request: Request, limit: int | None):
    if not text:
        return None, False
    truncated = limit is not None and len(text) > limit
    return replacing_text(
        text[:limit] if truncated else text,
        get_runtime(request).settings,
        request.state.common.msg_regex_tme,
    ), truncated


async def present_message(request: Request, message, limit: int | None):
    reply = None
    original = await message.get_reply_message()
    if original:
        sender = await original.get_sender()
        text, truncated = display_text(original.text, request, limit)
        reply = models.ReplyMessage(
            name=getattr(sender, "title", None)
            or getattr(sender, "first_name", None)
            or "Неизвестно",
            id=original.id,
            file=message_media(original),
            text=text,
            truncated=truncated,
        )
    text, truncated = display_text(message.text, request, limit)
    return models.Message(
        id=message.id,
        sender=await message.get_sender(),
        text=text,
        file=message_media(message),
        reply=reply,
        mentioned=bool(message.mentioned),
        date=message.date.strftime("%d.%m %H:%M"),
        out=bool(message.out),
        truncated=truncated,
    )


@router.get("/")
async def dialogs(
    request: Request,
    page: int = Query(0, ge=0),
    mode: Literal["all", "unread", "favorites"] = "all",
):
    runtime = get_runtime(request)
    prefs = get_preferences(request)
    dialogs = await runtime.client.get_dialogs()
    if mode == "unread":
        dialogs = [chat for chat in dialogs if chat.unread_count]
    elif mode == "favorites":
        dialogs = [chat for chat in dialogs if chat.id in prefs.favorites]
    start = page * prefs.page_size
    chats = [
        models.Chat(chat.id, chat.title or "Без названия", chat.unread_count)
        for chat in dialogs[start : start + prefs.page_size]
    ]
    return render(
        request,
        "chats.html",
        chats=chats,
        page=page,
        mode=mode,
        has_next=start + prefs.page_size < len(dialogs),
        is_passwd=request.state.policy.enabled,
    )


@router.get("/chat/{id}")
async def chat(
    request: Request,
    id: str,
    before: int | None = Query(None, gt=0, le=2147483647),
    after: int | None = Query(None, gt=0, le=2147483647),
    sent: bool = False,
):
    if before is not None and after is not None:
        raise HTTPException(422, "Выберите только одно направление истории")
    runtime = get_runtime(request)
    prefs = get_preferences(request)
    entity = await runtime.client.get_entity(entity_id(id))
    messages = await runtime.client.get_messages(
        entity,
        limit=prefs.page_size + 1,
        offset_id=before or after or 0,
        reverse=after is not None,
    )
    has_more = len(messages) > prefs.page_size
    visible = messages[: prefs.page_size]
    if after is not None:
        visible.reverse()
    result = [
        await present_message(request, message, prefs.text_limit) for message in visible
    ]
    older = visible[-1].id if visible and (after is not None or has_more) else None
    newer = (
        visible[0].id
        if visible and (before is not None or (after is not None and has_more))
        else None
    )
    response = render(
        request,
        "chat.html",
        messages=result,
        chat=entity,
        chat_id=id,
        older=older,
        newer=newer,
        browsing_history=before is not None or after is not None,
        sent=sent,
        favorite=get_peer_id(entity) in prefs.favorites,
    )
    # Rendering must succeed first; never acknowledge unseen arrivals or old pages.
    if visible and before is None and after is None:
        await runtime.client.send_read_acknowledge(entity, max_id=visible[0].id)
    return response


@router.post("/chat/{id}/favorite")
async def favorite(request: Request, id: str):
    prefs = get_preferences(request)
    entity = await get_runtime(request).client.get_entity(entity_id(id))
    chat_id = get_peer_id(entity)
    if chat_id in prefs.favorites:
        prefs.favorites.remove(chat_id)
    else:
        if len(prefs.favorites) >= 32:
            raise HTTPException(400, "Можно сохранить до 32 избранных чатов")
        prefs.favorites.append(chat_id)
    return await save_preferences(
        request, RedirectResponse(f"/chat/{quote(id, safe='')}", status_code=303), prefs
    )


@router.get("/chat/{id}/message/{msg_id}")
async def full_message(request: Request, id: str, msg_id: int):
    message = await present_message(
        request, await find_message(request, id, msg_id), None
    )
    return render(request, "message.html", message=message, chat_id=id)


async def draft_text(request: Request, id: str, reply_to: int | None) -> str:
    runtime = get_runtime(request)
    async with runtime.draft_lock:
        return await runtime.store.draft(request.state.browser_id, id, reply_to)


async def save_draft(request: Request, id: str, reply_to: int | None, text: str):
    runtime = get_runtime(request)
    async with runtime.draft_lock:
        await runtime.store.save_draft(request.state.browser_id, id, reply_to, text)


def compose_page(
    request: Request,
    id: str,
    text: str,
    reply_to: int | None = None,
    msg: str = "",
    status_code: int = 200,
    attachment: bool = False,
):
    return render(
        request,
        "compose.html",
        chat_id=id,
        text=text,
        reply_to=reply_to,
        quick_replies=QUICK_REPLIES,
        msg=msg,
        status_code=status_code,
        attachment=attachment,
    )


@router.get("/chat/{id}/compose")
async def compose(request: Request, id: str):
    return compose_page(request, id, await draft_text(request, id, None))


@router.get("/chat/{id}/reply/{msg_id}")
async def reply(request: Request, id: str, msg_id: int):
    return compose_page(request, id, await draft_text(request, id, msg_id), msg_id)


@compose_router.post("/chat/{id}/send_message")
async def send_message(
    request: Request,
    id: str,
    text: str = Form(""),
    reply_to: int | None = Form(None),
    file: UploadFile | None = File(None),
    action: Literal["send", "draft", "insert", "attach"] = Form("send"),
    quick_reply: str = Form(""),
    attachment_mode: bool = Form(False),
):
    attachment = attachment_mode or action == "attach" or file is not None
    if action == "insert":
        if quick_reply not in QUICK_REPLIES:
            return compose_page(
                request, id, text, reply_to, "Выберите быстрый ответ", 400, attachment
            )
        text = f"{text}\n{quick_reply}" if text else quick_reply
    await save_draft(request, id, reply_to, text)
    if action in ("draft", "insert", "attach"):
        message = {
            "draft": "Черновик сохранён",
            "insert": "Ответ добавлен. Нажмите «Отправить», когда всё готово",
            "attach": "Текст сохранён. Выберите файл",
        }[action]
        return compose_page(
            request,
            id,
            text,
            reply_to,
            message,
            attachment=attachment,
        )
    try:
        client = await authorized(request)
        data = await file.read() if file is not None else b""
        if file is not None and data:
            buffer = io.BytesIO(data)
            buffer.name = file.filename or "file"
            await client.send_file(
                entity_id(id), buffer, caption=text, reply_to=reply_to
            )
        elif text.strip():
            await client.send_message(entity_id(id), text, reply_to=reply_to)
        else:
            return compose_page(
                request,
                id,
                text,
                reply_to,
                "Введите сообщение или выберите файл",
                400,
                attachment,
            )
    except NotAuthorized:
        return compose_page(
            request,
            id,
            text,
            reply_to,
            "Войдите в Telegram. Текст сохранён в черновике",
            401,
            attachment,
        )
    except Exception:
        return compose_page(
            request,
            id,
            text,
            reply_to,
            "Не удалось подтвердить отправку. Проверьте чат перед повтором. Текст сохранён; файл выберите заново",
            502,
            attachment,
        )
    await save_draft(request, id, reply_to, "")
    return RedirectResponse(f"/chat/{quote(id, safe='')}?sent=1", status_code=303)


@router.get("/chat/{id}/edit/{msg_id}")
async def edit(request: Request, id: str, msg_id: int):
    message = await find_message(request, id, msg_id)
    return render(request, "edit.html", chat=id, id=message.id, text=message.text or "")


@router.post("/chat/{id}/edit_message")
async def edit_message(
    request: Request, id: str, msg_id: int = Form(...), text: str = Form(...)
):
    message = await find_message(request, id, msg_id)
    await message.edit(text)
    return render(request, "success.html", id=id, text="Сообщение изменено")


@router.get("/chat/{id}/delete/{msg_id}")
async def delete_form(request: Request, id: str, msg_id: int):
    await find_message(request, id, msg_id)
    return render(request, "delete.html", chat=id, id=msg_id)


@router.post("/chat/{id}/delete/{msg_id}")
async def delete_message(request: Request, id: str, msg_id: int):
    message = await find_message(request, id, msg_id)
    await message.delete()
    return render(request, "success.html", id=id, text="Сообщение удалено")


async def downloadable(
    request: Request, id: str, msg_id: int, variant: str = "default"
):
    message = await find_message(request, id, msg_id)
    if not message.file:
        raise HTTPException(404, "У сообщения нет файла")
    if variant == "voice" and not (message.file.mime_type or "").startswith("audio/"):
        raise HTTPException(400, "Распознавание доступно только для аудио")
    entity = await get_runtime(request).client.get_entity(entity_id(id))
    return await cached_media(
        get_runtime(request),
        message,
        get_peer_id(entity),
        image_size=get_preferences(request).image_size,
        variant=variant,
        common=request.state.common,
    )


@router.get("/chat/{id}/download/{msg_id}")
async def download(
    request: Request,
    id: str,
    msg_id: int,
    variant: Literal["default", "full", "voice"] = "default",
):
    path = await downloadable(request, id, msg_id, variant)
    mime = media_type(path)
    filename = path.name.removeprefix("original-") if variant == "full" else path.name
    safe_inline = mime in {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "video/mp4",
        "video/webm",
    }
    if safe_inline:
        return FileResponse(
            path, media_type=mime, filename=filename, content_disposition_type="inline"
        )
    return FileResponse(
        path,
        media_type=mime,
        filename=filename,
        content_disposition_type="attachment",
        headers={"Content-Security-Policy": "sandbox; default-src 'none'"},
    )


@router.get("/chat/{id}/media/{msg_id}")
async def media_page(request: Request, id: str, msg_id: int):
    message = await find_message(request, id, msg_id)
    if not message.file:
        raise HTTPException(404, "У сообщения нет файла")
    return render(
        request, "media.html", media=message_media(message), chat_id=id, id=msg_id
    )


@router.get("/chat/{id}/recognize/{msg_id}")
async def recognize(request: Request, id: str, msg_id: int):
    runtime = get_runtime(request)
    if not request.state.common.recognize_enabled:
        raise HTTPException(403, "Распознавание отключено владельцем")
    path = await downloadable(request, id, msg_id, "voice")
    text = await cached_recognition(runtime, path, request.state.common.recognize_lang)
    return render(request, "voice_recognized.html", id=id, text=text)
