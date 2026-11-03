import asyncio
import io
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from tapkofon.config import Settings
from tapkofon.database import Store
from tapkofon.media import cached_media, cached_recognition
from tapkofon.runtime import Runtime


def test_thumbnail_profiles_and_original_have_separate_cache(tmp_path):
    source = io.BytesIO()
    Image.new("RGBA", (500, 400), (255, 0, 0, 128)).save(source, "PNG")
    data = source.getvalue()

    async def download(file):
        if file is bytes:
            return data
        await asyncio.to_thread(Path(file).write_bytes, data)
        return file

    message = SimpleNamespace(
        id=42,
        file=SimpleNamespace(mime_type="image/png", name=None, ext=".png"),
        download_media=AsyncMock(side_effect=download),
    )
    runtime = Runtime(Settings(), tmp_path)

    async def exercise():
        small = await cached_media(runtime, message, 123, image_size=128)
        large = await cached_media(runtime, message, 123, image_size=240)
        original = await cached_media(runtime, message, 123, variant="full")
        assert await cached_media(runtime, message, 123, image_size=128) == small
        return small, large, original

    small, large, original = asyncio.run(exercise())
    assert small != large != original
    assert original.read_bytes() == data
    with Image.open(small) as image:
        assert image.size == (128, 102) and image.format == "JPEG"
    with Image.open(large) as image:
        assert image.size == (240, 192) and image.format == "JPEG"
    assert message.download_media.await_count == 3


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg tools not installed",
)
def test_voice_profile_is_mono_32k(tmp_path):
    source = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            "1",
            "-f",
            "ogg",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    message = SimpleNamespace(
        id=42,
        file=SimpleNamespace(mime_type="audio/ogg", name=None, ext=".ogg"),
        download_media=AsyncMock(return_value=source),
    )
    path = asyncio.run(
        cached_media(Runtime(Settings(), tmp_path), message, 123, variant="voice")
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["codec_name"] == "mp3"
    assert stream["channels"] == 1
    assert stream["sample_rate"] == "22050"
    assert stream["bit_rate"] == "32000"


def test_recognition_is_cached_by_language_in_database(tmp_path, monkeypatch):
    recognize = Mock(return_value="recognized")
    monkeypatch.setattr("tapkofon.media.recognize_audio", recognize)

    async def exercise():
        store = Store(tmp_path)
        await store.open()
        runtime = Runtime(Settings(), tmp_path)
        runtime.store = store
        path = tmp_path / "cache" / "voice.mp3"
        path.parent.mkdir()
        path.write_bytes(b"voice")
        try:
            assert await cached_recognition(runtime, path) == "recognized"
            assert await cached_recognition(runtime, path) == "recognized"
            runtime.settings.recognize_lang = "en-US"
            assert await cached_recognition(runtime, path) == "recognized"
            assert recognize.call_count == 2
        finally:
            await store.close()

    asyncio.run(exercise())
    assert not list(tmp_path.rglob("*.txt"))
