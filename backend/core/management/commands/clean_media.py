"""Removes uploaded files that no record refers to any more.

    manage.py clean_media [--dry-run]

Looks at checklist documents, field photos and imagery. Files being uploaded
right now (younger than a day) are left alone. Run as the database owner
(`make clean-media`), so every district's records are seen: run as the app
role it would see none and remove nothing (it stops instead).
"""

import time
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.models import District
from imagery.models import Imagery
from readiness.models import Attachment
from sync.models import Photo

GRACE_SECONDS = 24 * 3600


def referenced() -> set[Path]:
    root = Path(settings.MEDIA_ROOT)
    keep: set[Path] = set()
    for path in Attachment.objects.exclude(path="").values_list("path", flat=True):
        keep.add(root / path)
    for photo in Photo.objects.all():
        base = root / "sync" / "photos" / str(photo.district_id) / str(photo.uuid)
        keep.update({base.with_suffix(".jpg"), base.with_suffix(".part")})
    for imagery in Imagery.objects.all():
        folder = root / "imagery" / str(imagery.district_id) / str(imagery.uuid)
        keep.update({folder / "image.tif", folder / "source.tif"})
    return keep


class Command(BaseCommand):
    help = "Remove uploaded files that no record refers to."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Only list what would go")

    def handle(self, *args: Any, **options: Any) -> None:
        root = Path(settings.MEDIA_ROOT)
        if District.objects.exists() is False and any(root.rglob("*")):
            raise CommandError(
                "No districts are visible, but there are files: this must run as the"
                " database owner (`make clean-media`), or it would treat every file as unused."
            )
        keep = referenced()
        now = time.time()
        removed, size = 0, 0
        for folder in ("readiness", "sync", "imagery"):
            for path in (root / folder).rglob("*"):
                if not path.is_file() or path in keep:
                    continue
                if now - path.stat().st_mtime < GRACE_SECONDS:
                    continue
                removed += 1
                size += path.stat().st_size
                if options["dry_run"]:
                    self.stdout.write(f"would remove {path.relative_to(root)}")
                else:
                    path.unlink()
        # Import and export job folders are cleared by their own jobs; not touched here.
        verb = "would be removed" if options["dry_run"] else "removed"
        self.stdout.write(f"{removed} file(s), {size / 1024 / 1024:.1f} MB, {verb}.")
