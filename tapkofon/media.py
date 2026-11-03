"""Shared download/conversion cache for files and speech recognition."""

import asyncio
import io
import mimetypes
import re
import subprocess
from pathlib import Path
from typing import Protocol, cast

import speech_recognition as sr
from PIL import Image
from speech_recognition.recognizers.google import recognize_legacy

from .app_settings import CommonSettings
from .runtime import Runtime


def convert_image(
    data: bytes,
    destination: Path,
    runtime: Runtime,
    image_size: int | None = None,
    quality: int | None = None,
) -> None:
    settings = runtime.settings
    size = image_size or settings.pic_max_size
    with Image.open(io.BytesIO(data)) as original:
        image = original.convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        background.thumbnail((size, size), Image.Resampling.LANCZOS)
        background.save(
            destination,
            "jpeg",
            quality=settings.pic_quality if quality is None else quality,
        )


def convert_audio(data: bytes, destination: Path, voice: bool = False) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            *(["-ac", "1", "-ar", "22050", "-b:a", "32k"] if voice else []),
            "-f",
            "mp3",
            "-y",
            str(destination),
        ],
        input=data,
        capture_output=True,
        check=True,
        timeout=120,
    )


def safe_filename(message) -> str:
    filename = (
        (message.file.name or f"file{message.file.ext or ''}")
        .replace("\\", "/")
        .split("/")[-1]
    )
    # Disallow drive-relative paths and NTFS alternate data streams too.
    filename = re.sub(r'[\x00-\x1f<>:"|?*]', "_", filename).rstrip(" .")
    return "file" if filename in ("", ".", "..") else filename


async def cached_media(
    runtime: Runtime,
    message,
    chat_id: int,
    *,
    image_size: int | None = None,
    variant: str = "default",
    common: CommonSettings | None = None,
) -> Path:
    quality = common.pic_quality if common is not None else runtime.settings.pic_quality
    folder = runtime.cache_dir / str(chat_id) / str(message.id)
    mime = message.file.mime_type or "application/octet-stream"
    image = mime.startswith("image/") and variant != "full"
    voice = mime.startswith("audio/") and variant == "voice"
    audio = (
        mime.startswith("audio/") and message.file.ext != ".mp3" and variant != "full"
    )
    if variant == "full":
        filename = "original-" + safe_filename(message)
    elif voice:
        filename = "voice-mono-32k.mp3"
    elif audio:
        filename = "audio.mp3"
    elif image:
        filename = (
            f"preview-{image_size or runtime.settings.pic_max_size}-q{quality}.jpeg"
        )
    else:
        filename = safe_filename(message)
    destination = folder / filename
    async with runtime.media_lock:
        if destination.is_file():
            if runtime.has_store:
                await runtime.store.record_media(destination, media_type(destination))
            return destination
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / f".{filename}.part"
        try:
            if voice or audio:
                data = await message.download_media(bytes)
                await asyncio.to_thread(convert_audio, data, temporary, voice)
            elif image:
                data = await message.download_media(bytes)
                await asyncio.to_thread(
                    convert_image, data, temporary, runtime, image_size, quality
                )
            else:
                result = await message.download_media(file=str(temporary))
                if result is None:
                    raise ValueError("Telegram не вернул файл")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        if runtime.has_store:
            await runtime.store.record_media(destination, media_type(destination))
    return destination


async def cached_recognition(
    runtime: Runtime, path: Path, language: str | None = None
) -> str:
    language = language or runtime.settings.recognize_lang
    async with runtime.recognition_lock:
        if runtime.has_store:
            text = await runtime.store.recognition(path, language)
            if text is not None:
                return text
        text = await asyncio.to_thread(recognize_audio, path, language)
        if runtime.has_store:
            await runtime.store.save_recognition(path, language, text)
        return text


def media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class TimedRecognizer(Protocol):
    operation_timeout: float | None

    def record(self, source: sr.AudioSource) -> sr.AudioData: ...


def recognize_audio(path: Path, language: str) -> str:
    # A separate WAV is not mixed with the downloadable media cache.
    result = subprocess.run(
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
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    wav = io.BytesIO(result.stdout)
    recognizer = cast(TimedRecognizer, sr.Recognizer())
    recognizer.operation_timeout = 30.0
    with sr.AudioFile(wav) as source:
        audio = recognizer.record(source)
    text = recognize_legacy(recognizer, audio, language=language)
    if not isinstance(text, str):
        raise ValueError("Unexpected speech recognition result")
    return text


def avatar_image(
    data: bytes,
    runtime: Runtime,
    image_size: int | None = None,
    common: CommonSettings | None = None,
) -> bytes:
    output = io.BytesIO()
    preferences = common or CommonSettings(
        pic_quality=runtime.settings.pic_quality, pic_format=runtime.settings.pic_format
    )
    with Image.open(io.BytesIO(data)) as original:
        image = original.convert("RGB")
        size = image_size or runtime.settings.pic_avatar_max_size
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        image.save(output, preferences.pic_format, quality=preferences.pic_quality)
    return output.getvalue()
