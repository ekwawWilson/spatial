from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from crs.models import CoordinateSystem

from . import schema as schema_rules
from . import styles
from .models import Domain, GeometryType, Layer, PlanProject


def _as_drf(exc: DjangoValidationError) -> serializers.ValidationError:
    return serializers.ValidationError(
        exc.message_dict if hasattr(exc, "error_dict") else exc.messages
    )


class CrsBriefSerializer(serializers.ModelSerializer[CoordinateSystem]):
    class Meta:
        model = CoordinateSystem
        fields = ["id", "code", "name", "units", "kind"]


class ProjectSerializer(serializers.ModelSerializer[PlanProject]):
    crs = serializers.PrimaryKeyRelatedField(
        queryset=CoordinateSystem.objects.filter(is_active=True),
        required=False,
        help_text="Omit to use the default for new projects (see /api/crs/defaults/)",
    )
    crs_detail = CrsBriefSerializer(source="crs", read_only=True)
    layer_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PlanProject
        fields = [
            "id",
            "name",
            "community",
            "description",
            "crs",
            "crs_detail",
            "status",
            "layer_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_crs(self, value: CoordinateSystem) -> CoordinateSystem:
        if self.instance is not None and value != self.instance.crs:
            raise serializers.ValidationError(
                "A project's coordinate system is fixed when it is created."
            )
        return value


class LayerSerializer(serializers.ModelSerializer[Layer]):
    crs = serializers.PrimaryKeyRelatedField(
        queryset=CoordinateSystem.objects.filter(is_active=True),
        required=False,
        help_text="Native CRS of the layer's coordinates; defaults to the project's",
    )
    crs_detail = CrsBriefSerializer(source="crs", read_only=True)
    feature_count = serializers.IntegerField(read_only=True)
    domain = serializers.ChoiceField(choices=Domain.choices, default=Domain.OTHER)
    geometry_type = serializers.ChoiceField(choices=GeometryType.choices)

    class Meta:
        model = Layer
        fields = [
            "id",
            "project",
            "name",
            "domain",
            "geometry_type",
            "crs",
            "crs_detail",
            "schema",
            "style",
            "order",
            "visible",
            "opacity",
            "source",
            "feature_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["source", "created_at", "updated_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is not None:
            if "project" in attrs and attrs["project"] != self.instance.project:
                raise serializers.ValidationError(
                    {"project": "A layer can't move between projects."}
                )
            if "geometry_type" in attrs and attrs["geometry_type"] != self.instance.geometry_type:
                raise serializers.ValidationError({"geometry_type": "Can't change once created."})
        schema = attrs.get("schema", self.instance.schema if self.instance else [])
        try:
            attrs["schema"] = schema_rules.validate_schema(schema)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"schema": exc.messages}) from exc
        if "style" in attrs or self.instance is None:
            try:
                attrs["style"] = styles.validate_style(attrs.get("style"), attrs["schema"])
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"style": exc.messages}) from exc
        return attrs


class LayerOrderSerializer(serializers.Serializer[None]):
    layer_ids = serializers.ListField(
        child=serializers.IntegerField(), help_text="All of the project's layer ids, top first"
    )


class FeatureWriteSerializer(serializers.Serializer[None]):
    geometry = serializers.JSONField(
        required=False, allow_null=True, help_text="GeoJSON geometry in the layer's native CRS"
    )
    properties = serializers.JSONField(required=False)
    version = serializers.IntegerField(
        required=False, help_text="Required when updating: the version you edited"
    )


class GeoJSONFeatureSerializer(serializers.Serializer[None]):
    """Documents the shape of a returned feature (GeoJSON Feature)."""

    type = serializers.CharField(default="Feature")
    id = serializers.IntegerField()
    geometry = serializers.JSONField(allow_null=True)
    properties = serializers.JSONField()
