"""Phase 13: retention and housekeeping commands."""

import os
import time
from datetime import timedelta
from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog, Role

pytestmark = pytest.mark.django_db


def run(*args):
    out = StringIO()
    call_command(*args, stdout=out)
    return out.getvalue()


def test_old_audit_entries_are_pruned_and_recent_ones_kept(district_a):
    now = timezone.now()
    for days in (10, 400, 3000):
        AuditLog.objects.create(
            occurred_at=now - timedelta(days=days),
            table_name="t",
            row_id=str(days),
            action="UPDATE",
            district_id=district_a.id,
        )
    assert "1 entries" in run("prune_audit", "--older-than-days", "2555", "--dry-run")
    assert AuditLog.objects.filter(table_name="t").count() == 3  # a dry run removes nothing
    assert "Removed 1 entries" in run("prune_audit", "--older-than-days", "2555")
    assert sorted(AuditLog.objects.filter(table_name="t").values_list("row_id", flat=True)) == [
        "10",
        "400",
    ]
    with pytest.raises(CommandError, match="at least 365"):
        run("prune_audit", "--older-than-days", "30")


def test_unreferenced_files_are_removed_and_used_ones_kept(api, members_a, district_a, settings):
    planner = api(members_a[Role.PLANNER], district_a)
    project = planner.post(reverse("project-list"), {"name": "Housekeeping"}, format="json").json()
    items = planner.get(reverse("project-checklist", args=[project["id"]])).json()["items"]
    upload = SimpleUploadedFile("resolution.pdf", b"%PDF kept", "application/pdf")
    planner.post(
        reverse("checklist-item-attachments", args=[items[0]["id"]]),
        {"file": upload},
        format="multipart",
    )
    root = settings.MEDIA_ROOT
    (used,) = [p for p in (root / "readiness").rglob("*") if p.is_file()]
    stray = root / "readiness" / str(district_a.id) / "999-left-behind.pdf"
    stray.write_bytes(b"orphan")
    fresh = root / "sync" / "photos" / "1" / "uploading.part"
    fresh.parent.mkdir(parents=True)
    fresh.write_bytes(b"in progress")
    old = time.time() - 3 * 24 * 3600
    os.utime(stray, (old, old))
    os.utime(used, (old, old))

    assert "would remove" in run("clean_media", "--dry-run") and stray.exists()
    assert "1 file(s)" in run("clean_media")
    assert not stray.exists() and used.exists()
    assert fresh.exists()  # too new to judge: it may still be uploading
