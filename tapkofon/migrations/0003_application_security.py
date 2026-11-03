from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("data", "0002_plain_html")]

    initial = False

    operations = [
        ops.CreateModel(
            name="AccessSession",
            fields=[
                (
                    "id",
                    fields.CharField(
                        primary_key=True, unique=True, db_index=True, max_length=64
                    ),
                ),
                ("browser_id", fields.CharField(db_index=True, max_length=64)),
                ("revision", fields.IntField()),
                (
                    "expires_at",
                    fields.DatetimeField(auto_now=False, auto_now_add=False),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={"table": "accesssession", "app": "data", "pk_attr": "id"},
            bases=["Model"],
        ),
        ops.CreateModel(
            name="ApplicationSetting",
            fields=[
                (
                    "id",
                    fields.IntField(
                        generated=True, primary_key=True, unique=True, db_index=True
                    ),
                ),
                ("password_hash", fields.TextField(default="", unique=False)),
                ("auth_revision", fields.IntField(default=0)),
                ("pic_quality", fields.SmallIntField(default=80)),
                ("pic_format", fields.CharField(default="jpeg", max_length=8)),
                ("recognize_lang", fields.CharField(default="ru-RU", max_length=64)),
                ("recognize_enabled", fields.BooleanField(default=True)),
                ("msg_regex_tme", fields.BooleanField(default=True)),
            ],
            options={"table": "applicationsetting", "app": "data", "pk_attr": "id"},
            bases=["Model"],
        ),
    ]
