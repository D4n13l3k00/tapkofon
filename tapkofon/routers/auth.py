import asyncio

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from telethon import errors

from ..runtime import get_runtime
from ..security import verify_password
from ..views import render

router = APIRouter()


async def unlock(request: Request, revision: int):
    runtime = get_runtime(request)
    token = await runtime.store.create_access_session(
        request.state.browser_id, revision, runtime.settings.session_ttl_hours
    )
    if token is None:
        return render(
            request,
            "pass/pass.html",
            msg="Настройки доступа изменились. Обновите страницу",
            status_code=409,
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=runtime.settings.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/pass")
async def password_form(request: Request):
    if not request.state.policy.enabled or request.state.authenticated:
        return RedirectResponse("/", status_code=303)
    return render(request, "pass/pass.html")


@router.post("/pass")
async def password_submit(request: Request, password: str = Form("", max_length=256)):
    runtime = get_runtime(request)
    if not request.state.policy.enabled:
        return RedirectResponse("/", status_code=303)
    peer = request.client.host if request.client else "unknown"
    async with runtime.security_lock:
        if runtime.attempts.blocked(peer):
            return render(
                request,
                "pass/pass.html",
                msg="Слишком много попыток. Подождите 5 минут",
                status_code=429,
            )
        if not await asyncio.to_thread(
            verify_password, request.state.policy.password_hash, password
        ):
            runtime.attempts.fail(peer)
            return render(
                request, "pass/pass.html", msg="Неверный пароль", status_code=401
            )
        runtime.attempts.reset(peer)
        return await unlock(request, request.state.policy.revision)


@router.get("/lock")
async def lock_form(request: Request):
    return render(request, "pass/lock.html")


@router.post("/lock")
async def lock(request: Request):
    runtime = get_runtime(request)
    if runtime.qr is not None and runtime.qr.browser == request.state.browser_id:
        await runtime.clear_qr()
    await runtime.store.revoke_access_session(request.cookies.get("access_token", ""))
    response = RedirectResponse("/pass", status_code=303)
    response.delete_cookie("access_token")
    return response


def auth_page(request: Request, step: str = "phone", phone: str = "", msg: str = ""):
    return render(request, "auth/auth.html", step=step, phone=phone, msg=msg)


@router.get("/auth")
async def auth_form(request: Request, restart: bool = False):
    runtime = get_runtime(request)
    phone = next(iter(runtime.phone_codes), "")
    step = (
        "password"
        if runtime.password_phone == phone and phone
        else "code"
        if phone
        else "phone"
    )
    return auth_page(request, "phone" if restart else step, phone)


@router.post("/auth")
async def auth_submit(
    request: Request,
    phone: str = Form(""),
    code: str = Form(""),
    tfa: str = Form(""),
    step: str = Form("phone"),
):
    runtime = get_runtime(request)
    client = await runtime.connect()
    async with runtime.auth_lock:
        try:
            if await client.is_user_authorized():
                return render(request, "auth/authorized.html", me=await client.get_me())
            if not phone:
                return auth_page(request, msg="Введите номер телефона")
            if tfa or step == "password":
                if runtime.password_phone != phone or phone not in runtime.phone_codes:
                    return auth_page(
                        request, phone=phone, msg="Вход устарел. Запросите новый код"
                    )
                if not tfa:
                    return auth_page(
                        request, "password", phone, "Введите облачный пароль"
                    )
                step = "password"
                await client.sign_in(password=tfa)
            elif code or step == "code":
                step = "code"
                code_hash = runtime.phone_codes.get(phone)
                if not code_hash:
                    return auth_page(request, phone=phone, msg="Сначала запросите код")
                if not code:
                    return auth_page(request, "code", phone, "Введите полученный код")
                await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
            else:
                await runtime.clear_qr()
                result = await client.send_code_request(phone)
                runtime.phone_codes.clear()
                runtime.phone_codes[phone] = result.phone_code_hash
                runtime.password_phone = None
                return auth_page(
                    request, "code", phone, "Код запрошен. Проверьте Telegram или SMS"
                )
            runtime.phone_codes.clear()
            runtime.password_phone = None
            return render(request, "auth/authorized.html", me=await client.get_me())
        except errors.SessionPasswordNeededError:
            runtime.password_phone = phone
            return auth_page(request, "password", phone, "Введите 2FA пароль")
        except errors.PhoneCodeInvalidError:
            message = "Неверный код. Попробуйте ещё раз"
        except errors.PhoneCodeExpiredError:
            runtime.phone_codes.pop(phone, None)
            runtime.password_phone = None
            return auth_page(
                request, phone=phone, msg="Срок кода истёк. Запросите новый код"
            )
        except errors.PasswordHashInvalidError:
            step = "password"
            message = "Неверный облачный пароль"
        except errors.FloodWaitError as error:
            message = f"Подождите {error.seconds} секунд"
        except errors.RPCError:
            message = "Не удалось войти. Проверьте номер и настройки Telegram API"
    return auth_page(request, step, phone, message)


@router.get("/logout")
async def logout_form(request: Request):
    return render(request, "auth/logout_confirm.html")


@router.post("/logout")
async def logout(request: Request):
    runtime = get_runtime(request)
    await runtime.clear_qr()
    client = await runtime.connect()
    if await client.is_user_authorized():
        await client.log_out()
        await runtime.close()
        runtime._client = None
    runtime.phone_codes.clear()
    runtime.password_phone = None
    return render(request, "auth/logout.html")
