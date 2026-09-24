# Hand-written (GeoDjango app; no GDAL on the dev machine).
# test_no_model_changes_without_migrations checks it matches models.py.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0002_native_geometry_rls_audit")]

    operations = [
        migrations.AddField(
            model_name="planproject",
            name="boundary_feature",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="projects.feature",
            ),
        ),
        migrations.AddField(
            model_name="planproject",
            name="boundary_status",
            field=models.CharField(
                choices=[("draft", "Draft"), ("agreed", "Agreed with stakeholders"), ("approved", "Approved")],
                default="draft",
                max_length=10,
            ),
        ),
    ]
