import asyncio
import sqlite3

from tapkofon.database import Store, database_config
from tapkofon.preferences import Preferences


def test_second_migration_preserves_existing_browser_settings(tmp_path):
    from tortoise.context import TortoiseContext
    from tortoise.migrations.api import migrate

    async def create_old_database():
        async with TortoiseContext():
            await migrate(
                config=database_config(tmp_path),
                target="data.0001_initial",
                direction="forward",
            )

    asyncio.run(create_old_database())
    with sqlite3.connect(tmp_path / "tapkofon.sqlite3") as connection:
        connection.execute(
            "INSERT INTO browserstate (id, show_images, page_size, image_size, text_limit) VALUES (?, ?, ?, ?, ?)",
            ("browser", True, 5, 128, 300),
        )

    async def upgrade():
        store = Store(tmp_path)
        await store.open()
        try:
            prefs = await store.preferences("browser")
            assert prefs.show_images is True
            assert prefs.page_size == 5 and prefs.image_size == 128
            assert prefs.simple_html is False
        finally:
            await store.close()

    asyncio.run(upgrade())


def test_migrations_and_data_survive_restart(tmp_path):
    async def exercise():
        first = Store(tmp_path)
        await first.open()
        try:
            await first.save_preferences(
                "browser", Preferences(page_size=5, favorites=[123])
            )
            await first.save_draft("browser", "123", None, "private draft")
            media = tmp_path / "cache" / "voice.mp3"
            media.parent.mkdir()
            media.write_bytes(b"media")
            await first.record_media(media, "audio/mpeg")
            await first.save_recognition(media, "ru-RU", "recognized")
        finally:
            await first.close()
        second = Store(tmp_path)
        await second.open()
        try:
            assert (await second.preferences("browser")).favorites == [123]
            assert (await second.preferences("browser")).page_size == 5
            assert await second.draft("browser", "123", None) == "private draft"
            assert await second.recognition(media, "ru-RU") == "recognized"
            assert await second.cache_count() == 1
            await second.clear_cache()
            assert await second.cache_count() == 0
            assert await second.recognition(media, "ru-RU") is None
            assert await second.draft("browser", "123", None) == "private draft"
            assert (await second.preferences("browser")).favorites == [123]
        finally:
            await second.close()

    asyncio.run(exercise())
    assert (tmp_path / "tapkofon.sqlite3").exists()
    assert not list(tmp_path.glob("*.json"))


def test_orm_contexts_and_concurrent_writes_are_isolated(tmp_path):
    async def exercise():
        directories = [tmp_path / "first", tmp_path / "second"]
        for directory in directories:
            directory.mkdir()
        first, second = (Store(directory) for directory in directories)
        await first.open()
        await second.open()
        try:
            await asyncio.gather(
                first.save_draft("browser", "123", None, "first"),
                second.save_draft("browser", "123", None, "second"),
            )
            assert await first.draft("browser", "123", None) == "first"
            assert await second.draft("browser", "123", None) == "second"
            await asyncio.gather(
                *(
                    first.save_draft("browser", str(index), None, str(index))
                    for index in range(10)
                )
            )
            assert await first.draft("browser", "9", None) == "9"
        finally:
            await first.close()
            await second.close()

    asyncio.run(exercise())
