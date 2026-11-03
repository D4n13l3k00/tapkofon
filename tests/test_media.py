import asyncio
import io
import shutil
import subprocess
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from tapkofon.config import Settings
from tapkofon.media import cached_media, media_type, recognize_audio
from tapkofon.runtime import Runtime
from tapkofon.utils import humanize, replacing_text


def test_message_html_is_escaped_and_links_replaced():
    text = replacing_text(
        "<script>alert(1)</script>\nhttps://t.me/example/123 😀", Settings()
    )
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "<br>" in text
    assert "/chat/example" in text
    assert 'href="/chat/example"' in text
    assert ":grinning_face:" in text
    assert humanize(1024**4) == "1.0TiB"


def test_image_download_is_converted_once(tmp_path):
    image = io.BytesIO()
    Image.new("RGBA", (500, 400), (255, 0, 0, 128)).save(image, "PNG")
    message = SimpleNamespace(
        id=1,
        file=SimpleNamespace(mime_type="image/png", ext=".png", name="test.png"),
        download_media=AsyncMock(return_value=image.getvalue()),
    )
    runtime = Runtime(Settings(), tmp_path)

    async def exercise():
        path = await cached_media(runtime, message, -123)
        assert await cached_media(runtime, message, -123) == path
        return path

    path = asyncio.run(exercise())
    with Image.open(path) as result:
        assert result.format == "JPEG"
        assert result.size == (256, 205)
        assert result.mode == "RGB"
    assert media_type(path) == "image/jpeg"
    message.download_media.assert_awaited_once()
    assert not list(path.parent.glob("*.part"))


def test_download_filename_cannot_escape_cache(tmp_path):
    async def write_download(file):
        from pathlib import Path

        await asyncio.to_thread(Path(file).write_bytes, b"test")
        return file

    message = SimpleNamespace(
        id=1,
        file=SimpleNamespace(mime_type=None, ext=".txt", name="../../outside.txt"),
        download_media=AsyncMock(side_effect=write_download),
    )
    runtime = Runtime(Settings(), tmp_path)
    path = asyncio.run(cached_media(runtime, message, 123))
    assert path == tmp_path / "cache" / "123" / "1" / "outside.txt"
    assert path.read_bytes() == b"test"


@pytest.mark.parametrize(
    "name", ["Z:private.txt", "file.txt:stream", "../../file.txt", r"..\..\file.txt"]
)
def test_windows_drive_and_stream_names_are_safe(name):
    from pathlib import PureWindowsPath

    from tapkofon.media import safe_filename

    filename = safe_filename(
        SimpleNamespace(file=SimpleNamespace(name=name, ext=".txt"))
    )
    assert ":" not in filename
    assert not PureWindowsPath(filename).drive
    assert PureWindowsPath(filename).name == filename


def test_failed_download_does_not_poison_cache(tmp_path):
    runtime = Runtime(Settings(), tmp_path)
    message = SimpleNamespace(
        id=1,
        file=SimpleNamespace(mime_type="image/png", ext=".png", name=None),
        download_media=AsyncMock(return_value=b"invalid image"),
    )
    with pytest.raises(OSError):
        asyncio.run(cached_media(runtime, message, 123))
    assert not list((runtime.cache_dir / "123" / "1").iterdir())


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
def test_real_audio_conversion_and_recognition_language(tmp_path, monkeypatch):
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
            "anullsrc=r=16000:cl=mono",
            "-t",
            "0.2",
            "-f",
            "ogg",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout
    message = SimpleNamespace(
        id=1,
        file=SimpleNamespace(mime_type="audio/ogg", ext=".ogg", name=None),
        download_media=AsyncMock(return_value=source),
    )
    runtime = Runtime(Settings(recognize_lang="en-US"), tmp_path)
    path = asyncio.run(cached_media(runtime, message, 123))
    assert media_type(path) == "audio/mpeg"
    decoded = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-f",
            "wav",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout
    with wave.open(io.BytesIO(decoded)) as audio:
        frames = audio.readframes(16000)
        duration = len(frames) / (
            audio.getframerate() * audio.getnchannels() * audio.getsampwidth()
        )
        # Vorbis/MP3 encoder delay can trim the very short fixture.
        assert 0.15 <= duration <= 0.3
    recognize_google = Mock(return_value="recognized")
    monkeypatch.setattr("tapkofon.media.recognize_legacy", recognize_google)
    assert recognize_audio(path, "en-US") == "recognized"
    recognize_google.assert_called_once()
    assert recognize_google.call_args.kwargs == {"language": "en-US"}
    assert recognize_google.call_args.args[1].sample_rate == 16000
    assert recognize_google.call_args.args[1].frame_data
    assert not list(path.parent.glob("*.wav"))
