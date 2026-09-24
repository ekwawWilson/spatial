from rest_framework import serializers

from .models import BasemapSource
from .presets import PRESETS


class BasemapSerializer(serializers.ModelSerializer[BasemapSource]):
    scope = serializers.SerializerMethodField()
    has_key = serializers.SerializerMethodField()
    api_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Write-only. Stored encrypted; an empty string removes it.",
    )

    class Meta:
        model = BasemapSource
        fields = [
            "id",
            "name",
            "kind",
            "preset",
            "url",
            "layers",
            "attribution",
            "min_zoom",
            "max_zoom",
            "requires_key",
            "has_key",
            "api_key",
            "offline_cache_allowed",
            "notes",
            "is_active",
            "order",
            "scope",
        ]
        read_only_fields = ["preset"]

    def get_scope(self, obj: BasemapSource) -> str:
        return "district" if obj.district_id else "global"

    def get_has_key(self, obj: BasemapSource) -> bool:
        return bool(obj.api_key_encrypted)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        kind = attrs.get("kind", self.instance.kind if self.instance else None)
        url = str(attrs.get("url", self.instance.url if self.instance else ""))
        if kind == BasemapSource.Kind.XYZ and not all(p in url for p in ("{z}", "{x}", "{y}")):
            raise serializers.ValidationError({"url": "An XYZ URL needs {z}, {x} and {y}."})
        if kind in (BasemapSource.Kind.WMS, BasemapSource.Kind.WMTS) and not url.startswith(
            "https://"
        ):
            raise serializers.ValidationError({"url": "Use an https:// URL."})
        if url and not url.startswith("https://") and kind == BasemapSource.Kind.XYZ:
            raise serializers.ValidationError({"url": "Use an https:// URL."})
        min_zoom = attrs.get("min_zoom", self.instance.min_zoom if self.instance else 0)
        max_zoom = attrs.get("max_zoom", self.instance.max_zoom if self.instance else 19)
        if not (0 <= int(str(min_zoom)) <= int(str(max_zoom)) <= 24):
            raise serializers.ValidationError("Zoom levels must satisfy 0 <= min <= max <= 24.")
        return attrs


class PresetSerializer(serializers.Serializer[None]):
    preset = serializers.ChoiceField(choices=sorted(PRESETS))
    api_key = serializers.CharField(required=False, allow_blank=True, write_only=True)
    scope = serializers.ChoiceField(choices=["district", "global"], default="district")
