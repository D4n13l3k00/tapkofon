"""Persistent application data; Telegram's own session stays with Telethon."""

from tortoise import fields
from tortoise.models import Model


class BrowserState(Model):
    id = fields.CharField(max_length=64, primary_key=True)
    show_images = fields.BooleanField(default=False)
    simple_html = fields.BooleanField(default=False, db_default=False)
    page_size = fields.SmallIntField(default=10)
    image_size = fields.SmallIntField(default=176)
    text_limit = fields.SmallIntField(default=600)


class Favorite(Model):
    id = fields.IntField(primary_key=True)
    browser = fields.ForeignKeyField("data.BrowserState", related_name="favorites")
    chat_id = fields.BigIntField()

    class Meta(Model.Meta):
        unique_together = (("browser", "chat_id"),)


class Draft(Model):
    id = fields.IntField(primary_key=True)
    browser = fields.ForeignKeyField("data.BrowserState", related_name="drafts")
    chat = fields.CharField(max_length=255)
    reply_to = fields.BigIntField(default=0)
    text = fields.TextField()
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta(Model.Meta):
        unique_together = (("browser", "chat", "reply_to"),)


class CacheFile(Model):
    id = fields.CharField(max_length=64, primary_key=True)
    path = fields.TextField()
    size = fields.BigIntField()
    mime_type = fields.CharField(max_length=128)
    created_at = fields.DatetimeField(auto_now_add=True)


class Recognition(Model):
    id = fields.CharField(max_length=64, primary_key=True)
    source_path = fields.TextField()
    language = fields.CharField(max_length=64)
    text = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)


class ApplicationSetting(Model):
    id = fields.IntField(primary_key=True)
    password_hash = fields.TextField(default="")
    auth_revision = fields.IntField(default=0)
    pic_quality = fields.SmallIntField(default=80)
    pic_format = fields.CharField(max_length=8, default="jpeg")
    recognize_lang = fields.CharField(max_length=64, default="ru-RU")
    recognize_enabled = fields.BooleanField(default=True)
    msg_regex_tme = fields.BooleanField(default=True)


class AccessSession(Model):
    id = fields.CharField(max_length=64, primary_key=True)
    browser_id = fields.CharField(max_length=64, db_index=True)
    revision = fields.IntField()
    expires_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)
