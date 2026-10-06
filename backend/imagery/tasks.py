# Celery finds tasks in each app's tasks module.
from .services import process_imagery

__all__ = ["process_imagery"]
