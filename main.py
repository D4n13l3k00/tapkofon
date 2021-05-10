import io
import os
import time
import traceback
from pathlib import Path
from typing import *

import emoji
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydub import AudioSegment
from telethon.sync import TelegramClient, errors, types

import config
import models
import utils

if __name__ == '__main__':
    print("For start: uvicorn main:app --reload")
    exit(0)

templates = Jinja2Templates(directory="templates")

app = FastAPI(
    title="Tapkofon API",
    version="1.0"
)
user = TelegramClient(
    "session",
    config.api_id,
    config.api_hash
)
user.parse_mode = "html"
##### / Работа с подключением / #####
@app.get(
    "/logout",
    description="Деавторизоваться",
    response_class=HTMLResponse
)
async def logout():
    await user.log_out()
    return templates.get_template("auth/logout.html").render()
@app.get(
    "/auth_old",
    description="Авторизация через терминал",
    response_class=HTMLResponse
)
async def auth_old():
    await user.start()
    me = await user.get_me()
    return templates.get_template("auth/authorized.jinja2").render(me=me)
@app.get(
    "/auth",
    description="Веб-Авторизация",
    response_class=HTMLResponse
)
async def auth(phone: Optional[str] = None, code: Optional[str] = None, tfa: Optional[str] = None ):
    if not phone:
        await user.connect()
        return templates.get_template("auth/auth.jinja2").render()
    else:
        if not code: 
            try:
                await user.sign_in(phone)
                return templates.get_template("auth/auth.jinja2").render(phone=phone, code=code, tfa=tfa)
            except errors.FloodWaitError as ex:
                tm = time.strftime("%Hh:%Mm:%Ss", time.gmtime(ex.seconds))
                return templates.get_template("auth/auth.jinja2").render(phone=phone, msg=f"Флудвейт! Подождите {tm}")
            except Exception as ex:
                print(traceback.format_exc())
                return templates.get_template("auth/auth.jinja2").render(phone=phone, code=code, msg=' '.join(ex.args))
        else:
            try:
                if tfa:
                    await user.sign_in(password=tfa)
                else:
                    await user.sign_in(code=code)
                await user.sign_in(phone)
                me = await user.get_me()
                return templates.get_template("auth/authorized.jinja2").render(me=me)
            except errors.SessionPasswordNeededError as ex:
                return templates.get_template("auth/auth.jinja2").render(phone=phone, msg="Введите 2FA пароль")
            except errors.PhoneCodeInvalidError as ex:
                return templates.get_template("auth/auth.jinja2").render(phone=phone, msg="Неверный код")
            except errors.PhoneCodeExpiredError as ex:
                await user.send_code_request(phone, force_sms=True)
                return templates.get_template("auth/auth.jinja2").render(phone=phone, msg="Время кода истекло")
            except errors.FloodWaitError as ex:
                tm = time.strftime("%Hh:%Mm:%Ss", time.gmtime(ex.seconds))
                return templates.get_template("auth/auth.jinja2").render(phone=phone, msg=f"Флудвейт! Подождите {tm}")
            except Exception as ex:
                print(traceback.format_exc())
                return templates.get_template("auth/auth.jinja2").render(phone=phone, code=code, msg=' '.join(ex.args))

##### / Список чатов / #####
@app.get(
    "/",
    description="Список чатов",
    response_class=HTMLResponse
)
async def get_dialogs():
    if not user.is_connected():
        await user.connect()
    if not await user.is_user_authorized():
        return templates.get_template("auth/not_authorized.html").render()
    dialogs = await user.get_dialogs()
    chats = [
        models.Chat(
            id=chat.id,
            title=chat.title,
            unread=chat.unread_count)
        for chat in dialogs
        ]
    return templates.get_template("chats.jinja2").render(chats=chats)

##### / Чат / #####
@app.get(
    "/chat/{id}",
    description="Чат",
    response_class=HTMLResponse
)
async def chat(id: str, page: Optional[int]=0):
    if not user.is_connected():
        await user.connect()
    if not await user.is_user_authorized():
        return templates.get_template("auth/not_authorized.html").render()
    try:
        try: id = int(id)
        except: pass
        chat = await user.get_entity(id)
        await user.conversation(chat).mark_read()
        messages = await user.get_messages(id, limit=10, add_offset=10*page)
        msgs = []
        for m in messages:
            m: types.Message
            r = await m.get_reply_message()
            reply = None
            if r:
                if hasattr(r.sender, 'title'):
                    name = r.sender.title
                else:
                    name = r.sender.first_name
                if r.file:
                    rfile = models.MessageMedia(
                    type=r.file.mime_type,
                    size=utils.humanize(r.file.size),
                    filename=r.file.name
                    )
                else:
                    rfile = None
                reply = models.ReplyMessage(
                    name=name,
                    id=r.id,
                    file=rfile,
                    text=emoji.demojize(r.text)
                )
            if m.file:
                file = models.MessageMedia(
                    type=m.file.mime_type,
                    size=utils.humanize(m.file.size),
                    filename=m.file.name
                )
            else:
                file = None
            msgs.append(models.Message(
                id=m.id,
                sender=m.sender,
                text=emoji.demojize(m.text.replace('\n', '<br>')) if m.text else None,
                file=file,
                reply=reply,
                mentioned=m.mentioned,
                date=m.date.strftime("%Y-%m-%d %H:%M:%S"),
                out=m.out
            ))
        return templates.get_template("chat.jinja2").render(messages=msgs, chat=chat, page=page)
    except Exception as ex:
        print(traceback.format_exc())
        return templates.get_template("error.jinja2").render(error='<br>'.join(ex.args))

##### / Реплай / #####
@app.get(
    "/chat/{id}/reply/{msg_id}",
    description="Реплай на сообщение",
    response_class=HTMLResponse
)
async def chat(id: str, msg_id: int):
    if not user.is_connected():
        await user.connect()
    if not await user.is_user_authorized():
        return templates.get_template("auth/not_authorized.html").render()
    try:
        return templates.get_template("reply.jinja2").render(chat=id, id=msg_id)
    except Exception as ex:
        print(traceback.format_exc())
        return HTMLResponse(templates.get_template("error.jinja2").render(error='<br>'.join(ex.args)))

##### / Отправка сообщения / #####
@app.post(
    "/chat/{id}/send_message",
    description="API Отправка сообщения",
    response_class=HTMLResponse
)
async def chat(id: str, text: Optional[str] = Form(None), reply_to: Optional[int] = Form(None), file: Optional[UploadFile] = File(None)):
    if not user.is_connected():
        await user.connect()
    if not await user.is_user_authorized():
        return templates.get_template("auth/not_authorized.html").render()
    try:
        try: id = int(id)
        except: pass
        chat = await user.get_entity(id)
        if file.file.read():
            file.file.seek(0)
            f = io.BytesIO(file.file.read())
            f.name = file.filename
            await user.send_file(chat, f, caption=text, reply_to=reply_to)
        else:
            await user.send_message(chat, text, reply_to=reply_to)
        return templates.get_template("success.jinja2").render(id=id, text="Сообщение отправлено")
    except Exception as ex:
        print(traceback.format_exc())
        return templates.get_template("error.jinja2").render(error='<br>'.join(ex.args))

##### / Работа с сообщениями / #####
@app.get(
    "/chat/{id}/edit/{msg_id}",
    description="Изменить сообщение",
    response_class=HTMLResponse
)
async def chat(id: str, msg_id: int):
    if not user.is_connected():
        await user.connect()
    if not await user.is_user_authorized():
        return templates.get_template("auth/not_authorized.html").render()
    try:
        try: id = int(id)
        except: pass
        msg = await user.get_messages(id, ids=msg_id)
        if msg:
            msg: types.Message
            return templates.get_template("edit.jinja2").render(chat=id, id=msg.id, text=msg.text)
        else:
            return HTMLResponse(templates.get_template("error.jinja2")).render(error="Такого сообщения не существует")
    except Exception as ex:
        print(traceback.format_exc())
        return HTMLResponse(templates.get_template("error.jinja2").render(error='<br>'.join(ex.args)))

@app.post(
    "/chat/{id}/edit_message",
    description="API Изменить соообщение",
    response_class=HTMLResponse
)
async def chat(id: str, msg_id: int = Form(...), text: str = Form(...)):
    if not user.is_connected():
        await user.connect()
    if not await user.is_user_authorized():
        return templates.get_template("auth/not_authorized.html").render()
    try:
        try: id = int(id)
        except: pass
        msg = await user.get_messages(id, ids=msg_id)
        if msg:
            msg: types.Message
            await msg.edit(text)
            return templates.get_template("success.jinja2").render(id=id, text="Сообщение изменено")
        else:
            return HTMLResponse(templates.get_template("error.jinja2")).render(error="Такого сообщения не существует")
    except Exception as ex:
        print(traceback.format_exc())
        return templates.get_template("error.jinja2").render(error='<br>'.join(ex.args))

@app.get(
    "/chat/{id}/delete/{msg_id}",
    description="Удаление сообщения",
    response_class=HTMLResponse
)
async def chat(id: str, msg_id: int):
    if not user.is_connected():
        await user.connect()
    if not await user.is_user_authorized():
        return templates.get_template("auth/not_authorized.html").render()
    try:
        try: id = int(id)
        except: pass
        msg = await user.get_messages(id, ids=msg_id)
        if msg:
            msg: types.Message
            await msg.delete()
            return templates.get_template("success.jinja2").render(id=id, text="Сообщение удалено")
        else:
            return HTMLResponse(templates.get_template("error.jinja2")).render(error="Такого сообщения не существует")
    except Exception as ex:
        print(traceback.format_exc())
        return HTMLResponse(templates.get_template("error.jinja2").render(error='<br>'.join(ex.args)))

##### / Загрузка и стримминг файла из кеша / #####
@app.get(
    "/chat/{id}/download/{msg_id}",
    description="Загрузка файла",
    response_class=HTMLResponse
)
async def chat(id: str, msg_id: int):
    if not user.is_connected():
        await user.connect()
    if not await user.is_user_authorized():
        return templates.get_template("auth/not_authorized.html").render()
    try:
        try: id = int(id)
        except: pass
        msg = await user.get_messages(id, ids=msg_id)
        if msg:
            msg: types.Message
            if msg.file:
                if os.path.isdir(f"cache/{id}/{msg_id}") and os.listdir(f"cache/{id}/{msg_id}/") != []:
                    file = f"cache/{id}/{msg_id}/"+os.listdir(f"cache/{id}/{msg_id}/")[0]
                    stream = open(file, mode="rb")
                    return StreamingResponse(stream, media_type=msg.file.mime_type)
                else:
                    path = f"cache/{id}/{msg_id}/{msg.file.name}"
                    await msg.download_media(path)
                    if msg.file.mime_type.split("/")[0] == "audio" and msg.file.ext != ".mp3":
                        file = f"cache/{id}/{msg_id}/audio.mp3"
                        AudioSegment.from_file(path).export(file)
                        os.remove(path)
                    else:
                        file = await msg.download_media(path)
                    stream = open(file, mode="rb")
                    return StreamingResponse(stream, media_type=msg.file.mime_type)
            else:
                return HTMLResponse(templates.get_template("error.jinja2")).render(error="Такого сообщения не существует")
    except Exception as ex:
        print(traceback.format_exc())
        return HTMLResponse(templates.get_template("error.jinja2").render(error=ex.args))

##### / Кеш / #####
@app.get(
    "/cache",
    description="Кеш",
    response_class=HTMLResponse
)
async def cache():
    size = utils.humanize(utils.get_size('cache'))
    return templates.get_template("cache.jinja2").render(size=size)
@app.get(
    "/cache/clear",
    description="Очистить кеш",
    response_class=HTMLResponse
)
async def cache():
    utils.clear_dir('cache')
    return RedirectResponse("/cache")
@app.get(
    "/cache/list",
    description="Дерево кеша",
    response_class=HTMLResponse
)
async def cache():
    if not os.path.isdir('cache') or os.listdir('cache') == []:
        return "Cache is empty"
    var = ""
    paths = utils.DisplayablePath.make_tree(Path('cache'))
    for path in paths:
        var += path.displayable() + "\n"
    return var.replace('\n', '<br>').replace(' ', ' ')
