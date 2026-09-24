from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Max, Q, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.permissions import has_permission, is_system_admin, request_district_id, request_user

from . import crypto, services
from .models import BasemapSource
from .presets import PRESETS
from .serializers import BasemapSerializer, PresetSerializer


def _next_order() -> int:
    """New sources go to the end of the list, so adding one never changes
    which basemap projects show by default (the first in the list)."""
    top = BasemapSource.objects.aggregate(m=Max("order"))["m"]
    return 0 if top is None else top + 1


def _check_can_manage(request: Request, scope: str) -> int | None:
    """The district the new/edited source belongs to (None = global)."""
    if scope == "global":
        if not is_system_admin(request):
            raise PermissionDenied(
                "Only system administrators can manage basemaps for every district."
            )
        return None
    district_id = request_district_id(request)
    if district_id is None:
        raise PermissionDenied("Select a district: send its id in the X-District-ID header.")
    if not has_permission(request, "basemap.manage"):
        raise PermissionDenied("Your role in this district does not allow this.")
    return district_id


class BasemapViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[BasemapSource],
):
    """Basemaps available in the current district: platform-wide ones and the
    district's own. Sources are deactivated, not deleted."""

    serializer_class = BasemapSerializer
    queryset = BasemapSource.objects.none()  # schema hint; get_queryset() is used
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet[BasemapSource]:
        qs = BasemapSource.objects.filter(
            Q(district__isnull=True) | Q(district_id=request_district_id(self.request))
        )
        if self.request.query_params.get("include_inactive") != "true":
            qs = qs.filter(is_active=True)
        return qs.order_by("order", "name")

    def perform_create(self, serializer: serializers.BaseSerializer[BasemapSource]) -> None:
        scope = self.request.data.get("scope", "district")
        district_id = _check_can_manage(self.request, scope)
        key = serializer.validated_data.pop("api_key", "")
        serializer.save(
            district_id=district_id,
            api_key_encrypted=crypto.encrypt(key),
            created_by=request_user(self.request),
            order=serializer.validated_data.get("order") or _next_order(),
        )

    def perform_update(self, serializer: serializers.BaseSerializer[BasemapSource]) -> None:
        source = serializer.instance
        assert source is not None
        _check_can_manage(self.request, "district" if source.district_id else "global")
        extra: dict[str, Any] = {}
        if "api_key" in serializer.validated_data:
            extra["api_key_encrypted"] = crypto.encrypt(serializer.validated_data.pop("api_key"))
        serializer.save(**extra)

    @extend_schema(request=PresetSerializer, responses={201: BasemapSerializer})
    @action(detail=False, methods=["post"])
    def presets(self, request: Request) -> Response:
        """Adds a ready-made basemap (OpenStreetMap, Esri imagery, Google, Bing)."""
        data = PresetSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        district_id = _check_can_manage(request, data.validated_data["scope"])
        preset = PRESETS[data.validated_data["preset"]]
        source = BasemapSource.objects.create(
            district_id=district_id,
            preset=data.validated_data["preset"],
            api_key_encrypted=crypto.encrypt(data.validated_data.get("api_key", "")),
            created_by=request_user(request),
            order=_next_order(),
            **preset,
        )
        return Response(BasemapSerializer(source).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"], url_path="client-config")
    def client_config(self, request: Request, pk: str | None = None) -> Response:
        """What the map needs to draw this basemap. A missing or rejected API
        key gives a 400 with a plain explanation."""
        try:
            return Response(services.client_config(self.get_object()))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc
