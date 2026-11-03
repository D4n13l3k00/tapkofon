import pytest
from pydantic import ValidationError

from tapkofon.config import load_settings


def test_first_run_creates_parent_and_config(tmp_path):
    directory = tmp_path / "nested" / "session"
    settings = load_settings(directory)
    assert settings.api_id == 0
    assert settings.api_hash == ""
    assert load_settings(directory) == settings


def test_existing_config_and_environment_override(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        'api_id = 123\napi_hash = "test"\nrecognize_lang = "en-US"\n', encoding="utf-8"
    )
    monkeypatch.setenv("TAPKOFON_API_ID", "456")
    monkeypatch.setenv("TAPKOFON_PASSWD", "пароль")
    settings = load_settings(tmp_path)
    assert settings.api_id == 456
    assert settings.passwd == "пароль"
    assert settings.recognize_lang == "en-US"
    assert "пароль" not in (tmp_path / "config.toml").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "content",
    ["unknown = true", "pic_quality = 101", "pic_max_size = 0", 'pic_format = "exe"'],
)
def test_invalid_config_is_rejected(tmp_path, content):
    (tmp_path / "config.toml").write_text(content, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(tmp_path)
