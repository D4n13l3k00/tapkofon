"""Application-owned Telegram session; no client or filesystem work at import."""

import asyncio
import secrets
from pathlib import Path
from typing import cast

from fastapi import HTTPException, Request
from telethon import TelegramClient

from .app_settings import AccessPolicy, CommonSettings
from .config import Settings
from .database import Store
from .qr_auth import WebQR
from .security import AttemptLimiter, form_token
from .telegram_gateway import TelegramGateway


class ConfigurationError(Exception):
    pass


class NotAuthorized(Exception):
    pass


class Runtime:
    def __init__(
        self, settings: Settings, data_dir: Path, client: TelegramGateway | None = None
    ):
        self.settings = settings
        self.data_dir = data_dir
        self.cache_dir = data_dir / "cache"
        self.csrf_secret = secrets.token_bytes(32)
        self.policy = AccessPolicy()
        self.shared = CommonSettings()
        self.security_lock = asyncio.Lock()
        self.attempts = AttemptLimiter()
        self._client = client
        self.connection_lock = asyncio.Lock()
        self.auth_lock = asyncio.Lock()
        self.media_lock = asyncio.Lock()
        self.recognition_lock = asyncio.Lock()
        self.phone_codes: dict[str, str] = {}
        self.password_phone: str | None = None
        self._store: Store | None = None
        self.draft_lock = asyncio.Lock()
        self.qr: WebQR | None = None

    @property
    def store(self) -> Store:
        if self._store is None:
            raise RuntimeError("Database is not initialized")
        return self._store

    @store.setter
    def store(self, value: Store) -> None:
        self._store = value

    @property
    def has_store(self) -> bool:
        return self._store is not None

    def form_token(self, browser: str, revision: int | None = None) -> str:
        return form_token(
            self.csrf_secret,
            browser,
            self.policy.revision if revision is None else revision,
        )

    def apply_common(self, common: CommonSettings) -> None:
        self.shared = common
        for name, value in common.model_dump().items():
            setattr(self.settings, name, value)

    @property
    def client(self) -> TelegramGateway:
        if self._client is None:
            if not self.settings.api_id or not self.settings.api_hash:
                raise ConfigurationError(
                    "Укажите свои api_id и api_hash в session/config.toml "
                    "или TAPKOFON_API_ID и TAPKOFON_API_HASH."
                )
            self._client = cast(
                TelegramGateway,
                TelegramClient(
                    str(self.data_dir / "session"),
                    self.settings.api_id,
                    self.settings.api_hash,
                ),
            )
            # User input is plain text, not Telegram HTML markup.
            self._client.parse_mode = None
        return self._client

    async def connect(self) -> TelegramGateway:
        client = self.client
        async with self.connection_lock:
            if not client.is_connected():
                await client.connect()
        return client

    async def close(self) -> None:
        await self.clear_qr()
        if self._client is not None:
            await self._client.disconnect()

    async def clear_qr(self) -> None:
        challenge = self.qr
        self.qr = None
        if challenge is not None:
            await challenge.cancel()


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


async def authorized(request: Request) -> TelegramGateway:
    client = await get_runtime(request).connect()
    if not await client.is_user_authorized():
        raise NotAuthorized
    return client


async def protect_form(request: Request) -> None:
    if request.method != "POST":
        return
    form = await request.form()
    token = form.get("csrf_token", "")
    expected = request.state.csrf_token
    if not isinstance(token, str) or not secrets.compare_digest(
        token.encode(), expected.encode()
    ):
        raise HTTPException(403, "Обновите страницу и повторите отправку формы")


def entity_id(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value
