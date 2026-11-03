import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request, Response
from telethon import errors

from ..qr_auth import WebQR, qr_png
from ..runtime import get_runtime
from ..views import render

router = APIRouter()


def owned_qr(request: Request) -> WebQR:
    challenge = get_runtime(request).qr
    if challenge is None or challenge.browser != request.state.browser_id:
        raise HTTPException(404, "QR-код не найден. Создайте новый")
    return challenge


def qr_page(request: Request, msg: str = "", status_code: int = 200):
    challenge = get_runtime(request).qr
    if challenge is not None and challenge.browser != request.state.browser_id:
        challenge = None
    if challenge is not None and challenge.status == "authorized":
        return render(request, "auth/authorized.html", me=challenge.user)
    return render(
        request, "auth/qr.html", challenge=challenge, msg=msg, status_code=status_code
    )


@router.get("/auth/qr")
async def qr_form(request: Request):
    return qr_page(request)


@router.post("/auth/qr")
async def qr_start(request: Request):
    runtime = get_runtime(request)
    async with runtime.auth_lock:
        client = await runtime.connect()
        if await client.is_user_authorized():
            return render(request, "auth/authorized.html", me=await client.get_me())
        previous = runtime.qr
        if (
            previous is not None
            and previous.browser != request.state.browser_id
            and previous.status in ("waiting", "password")
        ):
            return qr_page(
                request,
                "В другом браузере уже начат вход. Дождитесь его завершения",
                409,
            )
        await runtime.clear_qr()
        runtime.phone_codes.clear()
        runtime.password_phone = None
        challenge = WebQR(await client.qr_login(), request.state.browser_id)
        runtime.qr = challenge
        challenge.task = asyncio.create_task(challenge.monitor())
        await asyncio.sleep(0)
    return qr_page(request)


@router.get("/auth/qr/image")
async def qr_image(request: Request, v: str = ""):
    challenge = owned_qr(request)
    if (
        challenge.status != "waiting"
        or datetime.now(UTC) >= challenge.qr.expires
        or (v and v != challenge.public_id)
    ):
        raise HTTPException(410, "QR-код истёк или уже использован")
    data = await asyncio.to_thread(qr_png, challenge.qr.url)
    return Response(data, media_type="image/png")


@router.post("/auth/qr/check")
async def qr_check(request: Request):
    owned_qr(request)
    return qr_page(request)


@router.post("/auth/qr/password")
async def qr_password(request: Request, tfa: str = Form("", max_length=256)):
    runtime = get_runtime(request)
    async with runtime.auth_lock:
        challenge = owned_qr(request)
        if challenge.status != "password":
            raise HTTPException(400, "Сначала отсканируйте QR-код")
        if not tfa:
            return qr_page(request, "Введите облачный пароль", 400)
        try:
            client = await runtime.connect()
            await client.sign_in(password=tfa)
            challenge.user = await client.get_me()
            challenge.status = "authorized"
        except errors.PasswordHashInvalidError:
            return qr_page(request, "Неверный облачный пароль", 401)
        except errors.FloodWaitError as error:
            return qr_page(request, f"Подождите {error.seconds} секунд", 429)
    return qr_page(request)
