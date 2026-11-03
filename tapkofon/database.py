"""SQLite storage with native Tortoise migrations and an isolated ORM context."""

import asyncio
import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tortoise.context import TortoiseContext
from tortoise.migrations.api import migrate
from tortoise.transactions import in_transaction

from .app_settings import AccessPolicy, CommonSettings
from .config import Settings
from .db_models import (
    AccessSession,
    ApplicationSetting,
    BrowserState,
    CacheFile,
    Draft,
    Favorite,
    Recognition,
)
from .preferences import Preferences
from .security import hash_password, token_digest


def database_config(data_dir: Path) -> dict:
    return {
        "connections": {
            "default": {
                "engine": "tortoise.backends.sqlite",
                "credentials": {
                    "file_path": str(data_dir / "tapkofon.sqlite3"),
                    "busy_timeout": 5000,
                },
            }
        },
        "apps": {
            "data": {
                "models": ["tapkofon.db_models"],
                "default_connection": "default",
                "migrations": "tapkofon.migrations",
            }
        },
        "use_tz": True,
        "timezone": "UTC",
    }


TORTOISE_ORM = database_config(
    Path(os.environ.get("TAPKOFON_DATA_DIR", "session")).resolve()
)


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.context = TortoiseContext()
        self.lock = asyncio.Lock()

    async def open(self) -> None:
        config = database_config(self.data_dir)
        # Migrate an existing database, never generate/drop runtime schemas.
        with self.context:
            await migrate(config=config, direction="forward")
            await self.context.close_connections()
            await self.context.init(config=config)

    @asynccontextmanager
    async def scope(self):
        # TortoiseContext's activation token is shared by an instance: serialize
        # its short DB operations to keep simultaneous requests isolated.
        async with self.lock:
            with self.context:
                yield

    async def close(self) -> None:
        async with self.scope():
            await self.context.close_connections()

    async def preferences(self, browser: str) -> Preferences:
        async with self.scope():
            state = await BrowserState.get_or_none(id=browser)
            if state is None:
                return Preferences()
            rows = await Favorite.filter(browser_id=browser).values("chat_id")
            favorites = [int(row["chat_id"]) for row in rows]
            return Preferences(
                show_images=state.show_images,
                simple_html=state.simple_html,
                page_size=state.page_size,
                image_size=state.image_size,
                text_limit=state.text_limit,
                favorites=favorites,
            )

    async def save_preferences(self, browser: str, prefs: Preferences) -> None:
        async with self.scope():
            async with in_transaction():
                await BrowserState.update_or_create(
                    id=browser, defaults=prefs.model_dump(exclude={"favorites"})
                )
                await Favorite.filter(browser_id=browser).delete()
                if prefs.favorites:
                    await Favorite.bulk_create(
                        [
                            Favorite(browser_id=browser, chat_id=chat)
                            for chat in dict.fromkeys(prefs.favorites)
                        ]
                    )

    async def draft(self, browser: str, chat: str, reply_to: int | None) -> str:
        async with self.scope():
            draft = await Draft.get_or_none(
                browser_id=browser, chat=chat, reply_to=reply_to or 0
            )
            return draft.text if draft else ""

    async def save_draft(
        self, browser: str, chat: str, reply_to: int | None, text: str
    ) -> None:
        async with self.scope():
            await BrowserState.get_or_create(id=browser)
            query = Draft.filter(browser_id=browser, chat=chat, reply_to=reply_to or 0)
            if text:
                await Draft.update_or_create(
                    browser_id=browser,
                    chat=chat,
                    reply_to=reply_to or 0,
                    defaults={"text": text},
                )
                keep = (
                    await Draft.filter(browser_id=browser)
                    .order_by("-updated_at")
                    .limit(32)
                    .values_list("id", flat=True)
                )
                await Draft.filter(browser_id=browser).exclude(id__in=keep).delete()
            else:
                await query.delete()

    async def record_media(self, path: Path, mime: str) -> None:
        relative = path.relative_to(self.data_dir).as_posix()
        identity = hashlib.sha256(relative.encode()).hexdigest()
        size = (await asyncio.to_thread(path.stat)).st_size
        async with self.scope():
            await CacheFile.update_or_create(
                id=identity,
                defaults={
                    "path": relative,
                    "size": size,
                    "mime_type": mime,
                },
            )

    @staticmethod
    def recognition_key(source: str, language: str) -> str:
        return hashlib.sha256(f"{source}\0{language}".encode()).hexdigest()

    async def recognition(self, path: Path, language: str) -> str | None:
        source = path.relative_to(self.data_dir).as_posix()
        async with self.scope():
            result = await Recognition.get_or_none(
                id=self.recognition_key(source, language)
            )
            return result.text if result else None

    async def save_recognition(self, path: Path, language: str, text: str) -> None:
        source = path.relative_to(self.data_dir).as_posix()
        async with self.scope():
            await Recognition.update_or_create(
                id=self.recognition_key(source, language),
                defaults={"source_path": source, "language": language, "text": text},
            )

    async def clear_cache(self) -> None:
        async with self.scope():
            async with in_transaction():
                await Recognition.all().delete()
                await CacheFile.all().delete()

    async def cache_count(self) -> int:
        async with self.scope():
            return await CacheFile.all().count()

    async def bootstrap_settings(self, settings: Settings) -> None:
        async with self.scope():
            if await ApplicationSetting.exists(id=1):
                return
            common = CommonSettings(
                **{
                    name: getattr(settings, name)
                    for name in CommonSettings.model_fields
                }
            )
            encoded = (
                await asyncio.to_thread(hash_password, settings.passwd)
                if settings.passwd
                else ""
            )
            await ApplicationSetting.create(
                id=1, password_hash=encoded, **common.model_dump()
            )

    async def application_settings(self) -> tuple[AccessPolicy, CommonSettings]:
        async with self.scope():
            row = await ApplicationSetting.get(id=1)
            return (
                AccessPolicy(
                    password_hash=row.password_hash, revision=row.auth_revision
                ),
                CommonSettings(
                    **{name: getattr(row, name) for name in CommonSettings.model_fields}
                ),
            )

    async def save_common_settings(self, common: CommonSettings, revision: int) -> bool:
        async with self.scope():
            changed = await ApplicationSetting.filter(
                id=1, auth_revision=revision
            ).update(**common.model_dump())
            return bool(changed)

    async def change_password(
        self, encoded: str, revision: int | None = None
    ) -> AccessPolicy | None:
        async with self.scope():
            async with in_transaction():
                row = await ApplicationSetting.get(id=1)
                if revision is not None and row.auth_revision != revision:
                    return None
                row.password_hash = encoded
                row.auth_revision += 1
                await row.save(update_fields=["password_hash", "auth_revision"])
                await AccessSession.all().delete()
                return AccessPolicy(password_hash=encoded, revision=row.auth_revision)

    async def create_access_session(
        self, browser: str, revision: int, hours: int
    ) -> str | None:
        async with self.scope():
            async with in_transaction():
                policy = await ApplicationSetting.get(id=1)
                if not policy.password_hash or policy.auth_revision != revision:
                    return None
                now = datetime.now(UTC)
                await AccessSession.filter(expires_at__lte=now).delete()
                # Replace this browser's previous session on every successful login.
                await AccessSession.filter(browser_id=browser).delete()
                token = secrets.token_urlsafe(32)
                await AccessSession.create(
                    id=token_digest(token),
                    browser_id=browser,
                    revision=revision,
                    expires_at=now + timedelta(hours=hours),
                )
                return token

    async def valid_access_session(
        self, token: str, browser: str, revision: int
    ) -> bool:
        if not token or len(token) > 128:
            return False
        async with self.scope():
            return await AccessSession.filter(
                id=token_digest(token),
                browser_id=browser,
                revision=revision,
                expires_at__gt=datetime.now(UTC),
            ).exists()

    async def revoke_access_session(self, token: str) -> None:
        if token and len(token) <= 128:
            async with self.scope():
                await AccessSession.filter(id=token_digest(token)).delete()
