"""Keeps links up to date as data changes, and the role cache honest."""

from typing import Any

from django.db.models.signals import post_delete, post_save

from projects.models import Feature

from . import services
from .models import LayerRole


def _feature_saved(sender: Any, instance: Feature, raw: bool = False, **kwargs: Any) -> None:
    if not raw:
        services.feature_changed(instance)


def _feature_deleted(sender: Any, instance: Feature, **kwargs: Any) -> None:
    services.feature_changed(instance)


def _role_changed(sender: Any, instance: LayerRole, **kwargs: Any) -> None:
    services.forget_layer_roles(instance.layer_id)


def connect() -> None:
    post_save.connect(_feature_saved, sender=Feature, dispatch_uid="relations-feature-saved")
    post_delete.connect(_feature_deleted, sender=Feature, dispatch_uid="relations-feature-deleted")
    post_save.connect(_role_changed, sender=LayerRole, dispatch_uid="relations-role-saved")
    post_delete.connect(_role_changed, sender=LayerRole, dispatch_uid="relations-role-deleted")
