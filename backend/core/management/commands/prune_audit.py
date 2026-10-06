"""Removes audit-log entries older than a retention period.

    manage.py prune_audit --older-than-days 2555 [--dry-run]

Must run as the database owner (`make prune-audit DAYS=2555`): the app role
can't change the audit log. Refuses to keep less than a year. A feature's
history comes from the audit log, so history older than the cut-off goes too.
"""

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DatabaseError
from django.utils import timezone

from core.models import AuditLog

MINIMUM_DAYS = 365


class Command(BaseCommand):
    help = "Remove audit-log entries older than a retention period (at least a year)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--older-than-days", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true", help="Only say how many would go")

    def handle(self, *args: Any, **options: Any) -> None:
        days = options["older_than_days"]
        if days < MINIMUM_DAYS:
            raise CommandError(
                f"The audit log is kept for at least {MINIMUM_DAYS} days; {days} is too short."
            )
        cutoff = timezone.now() - timedelta(days=days)
        old = AuditLog.objects.filter(occurred_at__lt=cutoff)
        count = old.count()
        if options["dry_run"]:
            self.stdout.write(
                f"{count} entries are older than {cutoff:%Y-%m-%d} and would be removed."
            )
            return
        try:
            old.delete()
        except DatabaseError as exc:
            raise CommandError(
                "The audit log can only be changed by the database owner."
                f" Run this with `make prune-audit DAYS={days}`. ({exc})"
            ) from exc
        self.stdout.write(f"Removed {count} entries older than {cutoff:%Y-%m-%d}.")
