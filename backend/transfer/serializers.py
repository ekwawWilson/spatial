from typing import Any

from django.core.cache import cache
from rest_framework import serializers

from .importer import progress_key
from .models import DataJob

FORMATS = ["gpkg", "shp", "geojson", "kml", "kmz", "dxf", "dwg"]


class DataJobSerializer(serializers.ModelSerializer[DataJob]):
    live_progress = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DataJob
        fields = [
            "id",
            "uuid",
            "kind",
            "project",
            "status",
            "file_format",
            "original_name",
            "inspection",
            "plan",
            "live_progress",
            "report",
            "error",
            "result_name",
            "download_url",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields

    def get_live_progress(self, obj: DataJob) -> dict[str, Any] | None:
        value: dict[str, Any] | None = cache.get(progress_key(obj))
        return value

    def get_download_url(self, obj: DataJob) -> str | None:
        if obj.kind == DataJob.Kind.EXPORT and obj.status == DataJob.Status.DONE:
            return f"/api/transfer/jobs/{obj.pk}/download/"
        return None


class UploadSerializer(serializers.Serializer[None]):
    project = serializers.IntegerField()
    file = serializers.FileField()
    encoding = serializers.CharField(required=False, allow_blank=True)


class ImportPlanSerializer(serializers.Serializer[None]):
    layers = serializers.ListField(child=serializers.DictField(), min_length=1)


class ExportSerializer(serializers.Serializer[None]):
    project = serializers.IntegerField()
    layer_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    format = serializers.ChoiceField(choices=FORMATS)
    crs = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    feature_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_null=True
    )
