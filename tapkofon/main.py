# Copyright 2022 d4n13l3k00.
# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from speech_recognition import RequestError, UnknownValueError
from starlette.exceptions import HTTPException
from telethon import errors

from .config import Settings, clean_legacy_config, load_settings
from .database import Store
from .routers import admin, auth, chats, pages, qr, users
from .runtime import ConfigurationError, NotAuthorized, Runtime, protect_form
from .security import is_local_request
from .views import render

logger = logging.getLogger(__name__)


def create_app(
    *, settings: Settings | None = None, data_dir: Path | None = None, client=None
) -> FastAPI:
    directory = (
        data_dir or Path(os.environ.get("TAPKOFON_DATA_DIR", "session"))
    ).resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        app.state.runtime = Runtime(
            settings or load_settings(directory), directory, client
        )
        store = Store(directory)
        app.state.runtime.store = store
        try:
            await store.open()
            await store.bootstrap_settings(app.state.runtime.settings)
            await asyncio.to_thread(clean_legacy_config, app.state.runtime.settings)
            app.state.runtime.policy, common = await store.application_settings()
            app.state.runtime.apply_common(common)
            yield
        finally:
            await app.state.runtime.close()
            await store.close()

    app = FastAPI(
        title="Tapkofon API",
        version="2.0.0",
        lifespan=lifespan,
        dependencies=[Depends(protect_form)],
    )
    app.state.templates = Jinja2Templates(
        directory=str(Path(__file__).parent / "templates")
    )

    @app.middleware("http")
    async def access_control(request: Request, call_next):
        runtime = request.app.state.runtime
        browser = request.cookies.get("tapkofon_browser", "")
        new_browser = re.fullmatch(r"[A-Za-z0-9_-]{32,64}", browser) is None
        request.state.browser_id = secrets.token_urlsafe(32) if new_browser else browser
        request.state.preferences = await runtime.store.preferences(
            request.state.browser_id
        )
        policy, common = await runtime.store.application_settings()
        runtime.policy = policy
        runtime.apply_common(common)
        request.state.policy = policy
        request.state.common = common
        request.state.csrf_token = runtime.form_token(
            request.state.browser_id, policy.revision
        )
        request.state.authenticated = (
            await runtime.store.valid_access_session(
                request.cookies.get("access_token", ""),
                request.state.browser_id,
                policy.revision,
            )
            if policy.enabled
            else False
        )
        request.state.can_admin = (
            request.state.authenticated if policy.enabled else is_local_request(request)
        )
        if (
            request.url.path not in ("/pass", "/health")
            and policy.enabled
            and not request.state.authenticated
        ):
            return RedirectResponse("/pass", status_code=303)
        if request.method == "POST":
            origin = request.headers.get("origin") or request.headers.get("referer")
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin
                and (
                    urlsplit(origin).netloc != request.url.netloc
                    or urlsplit(origin).scheme != request.url.scheme
                )
            ):
                return HTMLResponse("Запрос с другого сайта запрещён", status_code=403)
        response = await call_next(request)
        if new_browser:
            response.set_cookie(
                "tapkofon_browser",
                request.state.browser_id,
                max_age=31536000,
                httponly=True,
                secure=runtime.settings.cookie_secure,
                samesite="lax",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(NotAuthorized)
    async def not_authorized(request, error):
        return render(request, "auth/not_authorized.html", status_code=401)

    @app.exception_handler(ConfigurationError)
    async def configuration_error(request, error):
        return render(request, "error.html", error=str(error), status_code=503)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return render(
            request,
            "error.html",
            error=str(error.detail),
            status_code=error.status_code,
        )

    @app.exception_handler(errors.RPCError)
    async def telegram_error(request, error):
        return render(
            request,
            "error.html",
            error="Ошибка Telegram. Повторите запрос позже",
            status_code=502,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return render(
            request,
            "error.html",
            error="Проверьте поля формы и параметры адреса",
            status_code=422,
        )

    @app.exception_handler(UnknownValueError)
    async def unknown_speech(request, error):
        return render(
            request, "error.html", error="Не удалось разобрать речь", status_code=422
        )

    @app.exception_handler(RequestError)
    async def recognition_unavailable(request, error):
        return render(
            request,
            "error.html",
            error="Сервис распознавания недоступен",
            status_code=502,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        # Avoid recording account credentials or messages in error logs.
        logger.error("Request failed: %s", type(error).__name__)
        return render(
            request, "error.html", error="Не удалось выполнить запрос", status_code=500
        )

    for router in (
        auth.router,
        chats.router,
        users.router,
        pages.router,
        admin.router,
        qr.router,
    ):
        app.include_router(router)
    app.include_router(chats.compose_router)
    return app


app = create_app()
