# ruff: noqa: E501 - comments and messages read better unbroken
"""The district's planning committees, their members, and their meetings:
the agenda, who attended, and the minute on each item."""

from django.conf import settings
from django.db import models


class Committee(models.Model):
    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=4)  # registry.COMMITTEES
    # [{"name": ..., "office": registry.OFFICES code}]
    members = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(fields=["district", "kind"], name="one_committee_kind")
        ]

    def __str__(self) -> str:
        return f"{self.kind} of {self.district_id}"


class Meeting(models.Model):
    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    committee = models.ForeignKey(Committee, on_delete=models.CASCADE, related_name="meetings")
    held_on = models.DateField()
    venue = models.CharField(max_length=200, blank=True)
    # r.6: notice in writing (Form 5), at least three days before.
    notice_served_on = models.DateField(null=True, blank=True)
    # The names of the members present.
    attendance = models.JSONField(default=list, blank=True)
    # [{"type": "permit"|"land"|"plan"|"other", "ref": id, "title": ..., "outcome": ..., "minute": ...}]
    agenda = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-held_on", "-id"]

    def __str__(self) -> str:
        return f"{self.committee_id} on {self.held_on}"
