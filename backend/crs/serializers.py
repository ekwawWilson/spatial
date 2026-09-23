from typing import Any

from rest_framework import serializers

from .models import CoordinateSystem
from .services import Operation, ResolvedDefault, web_proj4


class CoordinateSystemSerializer(serializers.ModelSerializer[CoordinateSystem]):
    scope = serializers.SerializerMethodField()
    proj4 = serializers.SerializerMethodField(
        help_text="PROJ string for web maps, including the server's datum shift"
    )

    class Meta:
        model = CoordinateSystem
        fields = [
            "id",
            "code",
            "name",
            "srid",
            "kind",
            "units",
            "unit_to_metre",
            "area_of_use",
            "bounds",
            "notes",
            "is_builtin",
            "scope",
            "is_active",
            "proj4",
            "wkt",
        ]
        read_only_fields = [f for f in fields if f not in ("name", "notes", "is_active")]

    def get_proj4(self, obj: CoordinateSystem) -> str:
        return web_proj4(obj)

    def get_scope(self, obj: CoordinateSystem) -> str:
        if obj.is_builtin:
            return "builtin"
        return "district" if obj.district_id else "global"


class CustomSystemSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    definition = serializers.CharField(help_text="EPSG code, WKT or PROJ string")
    notes = serializers.CharField(allow_blank=True, required=False, default="")
    scope = serializers.ChoiceField(choices=["district", "global"], default="district")


class DefinitionSerializer(serializers.Serializer[None]):
    definition = serializers.CharField()


class DefinitionPreviewSerializer(serializers.Serializer[None]):
    name = serializers.CharField()
    kind = serializers.CharField()
    units = serializers.CharField()
    area_of_use = serializers.CharField()
    bounds = serializers.ListField(child=serializers.FloatField(), allow_null=True)
    proj4 = serializers.CharField()
    epsg = serializers.IntegerField(allow_null=True)


class SetDefaultSerializer(serializers.Serializer[None]):
    crs = serializers.PrimaryKeyRelatedField(
        queryset=CoordinateSystem.objects.filter(is_active=True), allow_null=True
    )


class OperationSerializer(serializers.Serializer[Operation]):
    name = serializers.CharField()
    pipeline = serializers.CharField()
    accuracy_m = serializers.FloatField(allow_null=True)
    pinned = serializers.BooleanField()


def resolved_data(resolved: ResolvedDefault) -> dict[str, Any]:
    return {"crs": CoordinateSystemSerializer(resolved.crs).data, "source": resolved.source}


class TransformRequestSerializer(serializers.Serializer[None]):
    MAX_POINTS = 10_000

    from_crs = serializers.CharField(help_text="Code, e.g. EPSG:2136")
    to_crs = serializers.CharField(help_text="Code, e.g. EPSG:4326")
    points = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=3),
        required=False,
        max_length=MAX_POINTS,
        help_text="[[x, y], ...]: east/north, or lon/lat for geographic systems",
    )
    geometry = serializers.JSONField(required=False, help_text="A GeoJSON geometry")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if ("points" in attrs) == ("geometry" in attrs):
            raise serializers.ValidationError("Send either points or geometry.")
        return attrs


class PinOperationSerializer(serializers.Serializer[None]):
    from_crs = serializers.CharField()
    to_crs = serializers.CharField()
    pipeline = serializers.CharField()
    name = serializers.CharField(required=False, allow_blank=True, default="")
    accuracy_m = serializers.FloatField(required=False, allow_null=True, default=None)
