# Copyright 2022 d4n13l3k00.
# SPDX-License-Identifier: AGPL-3.0-or-later
import os
import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_id: int = Field(default=0, ge=0)
    api_hash: str = ""
    # Legacy values are accepted only for one-time database bootstrap.
    passwd: str = Field(default="", exclude=True)
    access_cookie: str = Field(default="", exclude=True)
    cookie_secure: bool = False
    session_ttl_hours: int = Field(default=24, ge=1, le=720)
    pic_quality: int = Field(default=80, ge=1, le=100, exclude=True)
    pic_max_size: int = Field(default=256, ge=1)
    pic_format: str = Field(default="jpeg", pattern="^(jpeg|png|webp)$", exclude=True)
    pic_avatar_max_size: int = Field(default=256, ge=1)
    msg_regex_tme: bool = Field(default=True, exclude=True)
    msg_replace_regex: str = r"(https?://)?t\.me/(?P<chat>[A-Za-z0-9_-]{3,32})/?\d*"
    msg_regex_to: str = r"/chat/\g<chat>"
    recognize_lang: str = Field(
        default="ru-RU", min_length=2, max_length=64, exclude=True
    )
    recognize_enabled: bool = Field(default=True, exclude=True)
    _config_path: Path | None = PrivateAttr(default=None)
    _needs_cleanup: bool = PrivateAttr(default=False)


def load_settings(data_dir: Path) -> Settings:
    """Read existing TOML, with environment overrides for credentials."""
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    config_path = data_dir / "config.toml"
    if config_path.exists():
        with config_path.open("rb") as stream:
            values = tomllib.load(stream)
    else:
        values = Settings().model_dump()
        with config_path.open("wb") as stream:
            tomli_w.dump(values, stream)
        if os.name != "nt":
            config_path.chmod(0o600)
    for name in ("api_id", "api_hash", "passwd"):
        if (value := os.environ.get(f"TAPKOFON_{name.upper()}")) is not None:
            values[name] = value
    settings = Settings.model_validate(values)
    settings._config_path = config_path
    settings._needs_cleanup = bool(
        set(values)
        & {
            "passwd",
            "access_cookie",
            "pic_quality",
            "pic_format",
            "msg_regex_tme",
            "recognize_lang",
            "recognize_enabled",
        }
    )
    return settings


def clean_legacy_config(settings: Settings) -> None:
    """Remove migrated values only after the database transaction succeeded."""
    if settings._config_path is not None and settings._needs_cleanup:
        temporary = settings._config_path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            tomli_w.dump(settings.model_dump(), stream)
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(settings._config_path)
        settings._needs_cleanup = False
    settings.passwd = ""
    settings.access_cookie = ""
