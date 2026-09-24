from typing import Any, ClassVar

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.gis.db import models as gis
from django.db import models


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.update(is_staff=True, is_superuser=True, is_system_admin=True)
        return self._create(email, password, **extra)


class User(AbstractUser):
    """A person using the platform. Signs in with email.

    Users are global (one account can belong to several districts); what they
    may do is decided per district by their Membership role, or everywhere by
    is_system_admin.
    """

    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)
    is_system_admin = models.BooleanField(
        default=False, help_text="Full access to every district and system settings."
    )
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects: ClassVar[UserManager] = UserManager()  # type: ignore[assignment]

    class Meta:
        ordering = ["email"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = self.email.lower()
        super().save(*args, **kwargs)


class Region(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class District(models.Model):
    """A Metropolitan, Municipal or District Assembly (MMDA): the tenant."""

    class Kind(models.TextChoices):
        METROPOLITAN = "metropolitan", "Metropolitan"
        MUNICIPAL = "municipal", "Municipal"
        DISTRICT = "district", "District"

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="districts")
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=20, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    is_active = models.BooleanField(default=True)
    # Official district boundary (WGS 84), if loaded: planning areas are checked
    # against it.
    boundary = gis.MultiPolygonField(srid=4326, null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Role(models.TextChoices):
    """Roles a user holds within one district. System admin is a user flag,
    not a membership role. Permissions per role: core/permissions.py."""

    DISTRICT_ADMIN = "district_admin", "District administrator"
    PLANNER = "planner", "Physical planner"
    FIELD_OFFICER = "field_officer", "Field officer"
    VIEWER = "viewer", "Viewer"


class Membership(models.Model):
    """A user's role in one district. Tenant-scoped (row-level security)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__email"]
        constraints = [
            models.UniqueConstraint(fields=["user", "district"], name="unique_membership"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.district_id}: {self.role}"


class AuditLog(models.Model):
    """One row per insert, update or delete on an audited table.

    Written only by the database trigger app_audit() (see migration 0002), never
    by application code; the app role has read-only access. user_id and
    district_id are plain integers, not foreign keys, so audit history survives
    deletion of the user or district it mentions.
    """

    class Action(models.TextChoices):
        INSERT = "INSERT"
        UPDATE = "UPDATE"
        DELETE = "DELETE"

    occurred_at = models.DateTimeField(db_index=True)
    table_name = models.CharField(max_length=100)
    row_id = models.CharField(max_length=64)
    action = models.CharField(max_length=6, choices=Action.choices)
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    user_id = models.BigIntegerField(null=True, db_index=True)
    district_id = models.BigIntegerField(null=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [models.Index(fields=["table_name", "row_id"])]

    def __str__(self) -> str:
        return f"{self.action} {self.table_name}#{self.row_id}"

    def changed_fields(self) -> list[str]:
        before, after = self.before or {}, self.after or {}
        return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
