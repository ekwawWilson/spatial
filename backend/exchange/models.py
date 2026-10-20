"""Keys that let a national body (LUSPA, the Lands Commission, a Regional
Coordinating Council) read a district's planning records through the
exchange API. The district administrator issues them, chooses what each
may read, and can revoke them. Only a hash of each key is kept."""

from django.conf import settings
from django.db import models


class ExchangeKey(models.Model):
    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    # Who it is for, e.g. "LUSPA, Accra".
    name = models.CharField(max_length=200)
    # The start of the key, to recognise it by; the key itself is shown once.
    prefix = models.CharField(max_length=24, unique=True)
    digest = models.CharField(max_length=64)
    # What it may read: permits, plans, zoning, enforcement, returns.
    scopes = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}…)"
