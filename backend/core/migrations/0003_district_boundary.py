# Hand-written (GeoDjango field; no GDAL on the dev machine).
# test_no_model_changes_without_migrations checks it matches models.py.

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0002_tenancy_and_audit")]

    operations = [
        migrations.AddField(
            model_name="district",
            name="boundary",
            field=django.contrib.gis.db.models.fields.MultiPolygonField(blank=True, null=True, srid=4326),
        ),
    ]
