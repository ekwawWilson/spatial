from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sync"
    verbose_name = "Field sync, conflicts and ground-truthing"
