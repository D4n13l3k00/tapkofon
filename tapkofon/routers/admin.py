import asyncio
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from ..app_settings import CommonSettings
from ..runtime import get_runtime
from ..security import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    hash_password,
    verify_password,
)
from ..views import render
from .auth import unlock


def require_admin(request: Request) -> None:
    if not request.state.can_admin:
        raise HTTPException(
            403,
            "При отключённом пароле общие настройки доступны только локально на сервере",
        )


router = APIRouter(dependencies=[Depends(require_admin)])


def admin_page(request: Request, msg: str = "", status_code: int = 200):
    return render(
        request,
        "admin.html",
        enabled=request.state.policy.enabled,
        msg=msg,
        password_min=PASSWORD_MIN_LENGTH,
        status_code=status_code,
    )


@router.get("/admin")
async def admin_form(request: Request):
    return admin_page(request)


@router.post("/admin/settings")
async def common_settings(
    request: Request,
    pic_quality: int = Form(80),
    pic_format: str = Form("jpeg"),
    recognize_lang: str = Form("ru-RU"),
    recognize_enabled: bool = Form(False),
    msg_regex_tme: bool = Form(False),
):
    try:
        common = CommonSettings.model_validate(
            dict(
                pic_quality=pic_quality,
                pic_format=pic_format,
                recognize_lang=recognize_lang,
                recognize_enabled=recognize_enabled,
                msg_regex_tme=msg_regex_tme,
            )
        )
    except ValidationError:
        return admin_page(request, "Проверьте качество, формат и код языка", 422)
    runtime = get_runtime(request)
    if not await runtime.store.save_common_settings(
        common, request.state.policy.revision
    ):
        return admin_page(
            request, "Настройки доступа изменились. Обновите страницу", 409
        )
    runtime.apply_common(common)
    return RedirectResponse("/admin?saved=settings", status_code=303)


@router.post("/admin/password")
async def password_change(
    request: Request,
    current_password: str = Form("", max_length=PASSWORD_MAX_LENGTH),
    new_password: str = Form("", max_length=PASSWORD_MAX_LENGTH),
    repeat_password: str = Form("", max_length=PASSWORD_MAX_LENGTH),
    action: Literal["change", "disable"] = Form("change"),
    confirm_open_access: bool = Form(False),
):
    runtime = get_runtime(request)
    peer = request.client.host if request.client else "unknown"
    policy = request.state.policy
    async with runtime.security_lock:
        if policy.enabled:
            if runtime.attempts.blocked(peer):
                return admin_page(
                    request, "Слишком много попыток. Подождите 5 минут", 429
                )
            if not await asyncio.to_thread(
                verify_password, policy.password_hash, current_password
            ):
                runtime.attempts.fail(peer)
                return admin_page(request, "Неверный текущий пароль", 401)
            runtime.attempts.reset(peer)
        if action == "disable":
            if not confirm_open_access:
                return admin_page(
                    request, "Подтвердите открытый доступ перед отключением пароля", 400
                )
            encoded = ""
        else:
            if len(new_password) < PASSWORD_MIN_LENGTH:
                return admin_page(
                    request,
                    f"Пароль должен содержать не менее {PASSWORD_MIN_LENGTH} символов",
                    400,
                )
            if not secrets.compare_digest(
                new_password.encode(), repeat_password.encode()
            ):
                return admin_page(request, "Новые пароли не совпадают", 400)
            encoded = await asyncio.to_thread(hash_password, new_password)
        updated = await runtime.store.change_password(encoded, policy.revision)
        if updated is None:
            return admin_page(
                request, "Настройки доступа изменились. Обновите страницу", 409
            )
        runtime.policy = updated
        await runtime.clear_qr()
        if action == "disable":
            response = RedirectResponse("/settings", status_code=303)
            response.delete_cookie("access_token")
            return response
        response = await unlock(request, updated.revision)
        if response.status_code == 303:
            response.headers["location"] = "/admin?saved=password"
        return response
