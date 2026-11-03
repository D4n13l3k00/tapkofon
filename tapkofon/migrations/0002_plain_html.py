from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("data", "0001_initial")]

    initial = False

    operations = [
        ops.AddField(
            model_name="BrowserState",
            name="simple_html",
            field=fields.BooleanField(default=False, db_default=False),
        ),
    ]
