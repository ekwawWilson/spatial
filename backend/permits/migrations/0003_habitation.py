# Hand-written, like 0001 (see the note there).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("permits", "0002_rls_audit")]

    operations = [
        migrations.AddField(
            model_name="application",
            name="habitation_on",
            field=models.DateField(blank=True, null=True),
        ),
    ]
