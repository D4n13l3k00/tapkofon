from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name="BrowserState",
            fields=[
                (
                    "id",
                    fields.CharField(
                        primary_key=True, unique=True, db_index=True, max_length=64
                    ),
                ),
                ("show_images", fields.BooleanField(default=False)),
                ("page_size", fields.SmallIntField(default=10)),
                ("image_size", fields.SmallIntField(default=176)),
                ("text_limit", fields.SmallIntField(default=600)),
            ],
            options={"table": "browserstate", "app": "data", "pk_attr": "id"},
            bases=["Model"],
        ),
        ops.CreateModel(
            name="CacheFile",
            fields=[
                (
                    "id",
                    fields.CharField(
                        primary_key=True, unique=True, db_index=True, max_length=64
                    ),
                ),
                ("path", fields.TextField(unique=False)),
                ("size", fields.BigIntField()),
                ("mime_type", fields.CharField(max_length=128)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={"table": "cachefile", "app": "data", "pk_attr": "id"},
            bases=["Model"],
        ),
        ops.CreateModel(
            name="Draft",
            fields=[
                (
                    "id",
                    fields.IntField(
                        generated=True, primary_key=True, unique=True, db_index=True
                    ),
                ),
                (
                    "browser",
                    fields.ForeignKeyField(
                        "data.BrowserState",
                        source_field="browser_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="drafts",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("chat", fields.CharField(max_length=255)),
                ("reply_to", fields.BigIntField(default=0)),
                ("text", fields.TextField(unique=False)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={
                "table": "draft",
                "app": "data",
                "unique_together": (("browser", "chat", "reply_to"),),
                "pk_attr": "id",
            },
            bases=["Model"],
        ),
        ops.CreateModel(
            name="Favorite",
            fields=[
                (
                    "id",
                    fields.IntField(
                        generated=True, primary_key=True, unique=True, db_index=True
                    ),
                ),
                (
                    "browser",
                    fields.ForeignKeyField(
                        "data.BrowserState",
                        source_field="browser_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="favorites",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("chat_id", fields.BigIntField()),
            ],
            options={
                "table": "favorite",
                "app": "data",
                "unique_together": (("browser", "chat_id"),),
                "pk_attr": "id",
            },
            bases=["Model"],
        ),
        ops.CreateModel(
            name="Recognition",
            fields=[
                (
                    "id",
                    fields.CharField(
                        primary_key=True, unique=True, db_index=True, max_length=64
                    ),
                ),
                ("source_path", fields.TextField(unique=False)),
                ("language", fields.CharField(max_length=64)),
                ("text", fields.TextField(unique=False)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={"table": "recognition", "app": "data", "pk_attr": "id"},
            bases=["Model"],
        ),
    ]
