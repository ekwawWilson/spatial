"""Creates demo districts and one user per role, for demos and end-to-end tests.

Idempotent: re-running updates the same records. Refuses to run unless DEBUG is
on or --force is given, because every demo account shares one known password.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from core.models import District, Membership, Region, Role, User

DEFAULT_PASSWORD = "Demo-Pass-2026!"  # noqa: S105 - demo accounts only, refused without DEBUG

DISTRICTS = [
    # (code, name, kind)
    ("SMA", "Sample Municipal Assembly", District.Kind.MUNICIPAL),
    ("ODA", "Other District Assembly", District.Kind.DISTRICT),
]

# (email, first name, last name, district code or None, role or None, system admin)
USERS: list[tuple[str, str, str, str | None, Role | None, bool]] = [
    ("admin@example.test", "System", "Admin", None, None, True),
    ("sma.admin@example.test", "Ama", "Mensah", "SMA", Role.DISTRICT_ADMIN, False),
    ("sma.planner@example.test", "Kofi", "Boateng", "SMA", Role.PLANNER, False),
    ("sma.field@example.test", "Yaw", "Owusu", "SMA", Role.FIELD_OFFICER, False),
    ("sma.viewer@example.test", "Efua", "Asante", "SMA", Role.VIEWER, False),
    ("oda.admin@example.test", "Kwame", "Addo", "ODA", Role.DISTRICT_ADMIN, False),
]


class Command(BaseCommand):
    help = "Create demo districts and users (one per role). Development only."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--force", action="store_true", help="Run even if DEBUG is off.")
        parser.add_argument("--password", default=DEFAULT_PASSWORD)

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to create demo accounts with DEBUG off (use --force).")

        region, _ = Region.objects.update_or_create(code="GA", defaults={"name": "Greater Accra"})
        districts = {}
        for code, name, kind in DISTRICTS:
            districts[code], _ = District.objects.update_or_create(
                code=code, defaults={"name": name, "kind": kind, "region": region}
            )

        for email, first, last, district_code, role, sysadmin in USERS:
            user = User.objects.filter(email=email).first() or User(email=email)
            user.first_name, user.last_name = first, last
            user.is_system_admin = sysadmin
            user.is_staff = user.is_superuser = sysadmin
            user.is_active = True
            user.failed_login_count, user.locked_until = 0, None
            user.set_password(options["password"])
            user.save()
            if district_code and role:
                Membership.objects.update_or_create(
                    user=user,
                    district=districts[district_code],
                    defaults={"role": role, "is_active": True},
                )
            self.stdout.write(f"  {email:28} {role or 'system admin'}")

        self.stdout.write(self.style.SUCCESS("Demo data ready. Password: " + options["password"]))
