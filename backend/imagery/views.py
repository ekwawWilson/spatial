from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.permissions import district_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from core.throttling import UploadThrottle
from projects.models import PlanProject
from transfer.safety import MAX_UPLOAD_BYTES

from . import raster, services, uploads
from .models import Imagery


class ImagerySerializer(serializers.ModelSerializer[Imagery]):
    tile_url = serializers.SerializerMethodField()

    class Meta:
        model = Imagery
        fields = [
            "id",
            "project",
            "name",
            "kind",
            "status",
            "error",
            "original_name",
            "capture_date",
            "source",
            "crs",
            "width",
            "height",
            "bands",
            "resolution_m",
            "bounds",
            "value_range",
            "min_zoom",
            "max_zoom",
            "size_bytes",
            "basemap",
            "tile_url",
            "created_at",
        ]
        read_only_fields = [f for f in fields if f not in ("name", "capture_date", "source")]

    def get_tile_url(self, obj: Imagery) -> str | None:
        return services.tile_url(obj) if obj.status == Imagery.Status.READY else None


class ImageryUploadSerializer(serializers.Serializer[Any]):
    project = serializers.IntegerField()
    file = serializers.FileField()
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    kind = serializers.ChoiceField(choices=Imagery.Kind.choices, default=Imagery.Kind.ORTHO)
    capture_date = serializers.DateField(required=False, allow_null=True)
    # Stored as the image's "source" (a serializer field can't be called that).
    captured_by = serializers.CharField(max_length=200, required=False, allow_blank=True)
    crs = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        help_text="Only for files that carry no CRS",
    )


class ImageryDetailsSerializer(serializers.Serializer[Any]):
    """What the person says about an image, given when a piecewise upload finishes."""

    project = serializers.IntegerField()
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    kind = serializers.ChoiceField(choices=Imagery.Kind.choices, default=Imagery.Kind.ORTHO)
    capture_date = serializers.DateField(required=False, allow_null=True)
    captured_by = serializers.CharField(max_length=200, required=False, allow_blank=True)
    crs = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        help_text="Only for files that carry no CRS",
    )


class UploadStartSerializer(serializers.Serializer[Any]):
    file_name = serializers.CharField(max_length=255)
    size = serializers.IntegerField(min_value=1)


class UploadStateSerializer(serializers.Serializer[Any]):
    id = serializers.CharField()
    file_name = serializers.CharField()
    size = serializers.IntegerField()
    received = serializers.IntegerField()
    chunk_size = serializers.IntegerField(help_text="The largest piece the server accepts")


UPLOAD_ID = OpenApiParameter("upload_id", str, OpenApiParameter.PATH)
UPLOAD_PATH = r"uploads/(?P<upload_id>[0-9a-f]{32})"


class ContourSerializer(serializers.Serializer[Any]):
    interval = serializers.FloatField(min_value=0.01, help_text="In the elevation model's units")


@extend_schema(parameters=[DISTRICT_HEADER])
class ImageryViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[Imagery],
):
    """Orthophotos and elevation models of the district's projects (filter
    with ?project=). Upload a GeoTIFF; it is checked, converted and, for an
    orthophoto, offered as a basemap."""

    serializer_class = ImagerySerializer
    queryset = Imagery.objects.none()
    pagination_class = None  # a project has a handful of images
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_throttles(self) -> list[Any]:
        throttles = super().get_throttles()
        counted = ("create", "start_upload")
        return [*throttles, UploadThrottle()] if self.action in counted else throttles

    def get_permissions(self) -> list[BasePermission]:
        if self.action in ("list", "retrieve", "tile"):
            code = "project.view"
        elif self.action == "contours":
            return [
                IsAuthenticated(),
                district_permission("data.import")(),
                district_permission("layer.edit")(),
            ]
        else:
            code = "data.import"
        return [IsAuthenticated(), district_permission(code)()]

    def get_queryset(self) -> QuerySet[Imagery]:
        qs = Imagery.objects.filter(district_id=require_district_id(self.request))
        project = self.request.query_params.get("project", "")
        if project.isdigit():
            qs = qs.filter(project_id=int(project))
        return qs

    @extend_schema(
        request={"multipart/form-data": ImageryUploadSerializer}, responses={201: ImagerySerializer}
    )
    def create(self, request: Request) -> Response:
        """Uploads a GeoTIFF. Processing runs in the background; poll the item
        until its status is ready or failed."""
        data = ImageryUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        upload = values["file"]
        if upload.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError({"file": "Files are limited to 500 MB."})
        original = Path(upload.name).name
        if Path(original).suffix.lower() not in (".tif", ".tiff"):
            raise serializers.ValidationError({"file": "Upload a GeoTIFF (.tif or .tiff)."})
        imagery = self._add(request, values, original)
        target = services.source_path(imagery)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        self._process(request, imagery)
        return Response(ImagerySerializer(imagery).data, status=status.HTTP_201_CREATED)

    def _add(self, request: Request, values: dict[str, Any], original: str) -> Imagery:
        district_id = require_district_id(request)
        project = get_object_or_404(PlanProject, pk=values["project"], district_id=district_id)
        return Imagery.objects.create(
            district_id=district_id,
            project=project,
            name=(values.get("name") or Path(original).stem)[:200],
            kind=values["kind"],
            original_name=original,
            capture_date=values.get("capture_date"),
            source=values.get("captured_by", ""),
            assigned_crs=values.get("crs", "").strip().upper(),
            created_by=request_user(request),
        )

    def _process(self, request: Request, imagery: Imagery) -> None:
        imagery_id, district_id, user_id = imagery.pk, imagery.district_id, request_user(request).pk
        transaction.on_commit(
            lambda: services.process_imagery.delay(imagery_id, district_id, user_id)
        )

    # --- Uploading in pieces --------------------------------------------------------------
    # For large files on slow connections: each piece is one short request, and a
    # broken connection carries on where the server's copy ends (imagery/uploads.py).

    def _upload(self, request: Request, upload_id: str) -> dict[str, Any]:
        return uploads.load(upload_id, require_district_id(request), request_user(request).pk)

    @extend_schema(request=UploadStartSerializer, responses={201: UploadStateSerializer})
    @action(detail=False, methods=["post"], url_path="uploads")
    def start_upload(self, request: Request) -> Response:
        """Starts uploading a GeoTIFF in pieces. Send the pieces with PUT
        .../chunk/?offset=, then POST .../finish/ with the image's details."""
        data = UploadStartSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = uploads.start(
                require_district_id(request),
                request_user(request).pk,
                data.validated_data["file_name"],
                data.validated_data["size"],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc
        return Response(result, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[UPLOAD_ID], responses={200: UploadStateSerializer})
    @action(detail=False, methods=["get"], url_path=UPLOAD_PATH)
    def upload_status(self, request: Request, upload_id: str) -> Response:
        """How much of the file the server has."""
        return Response(uploads.state(upload_id, self._upload(request, upload_id)))

    @extend_schema(
        parameters=[UPLOAD_ID, OpenApiParameter("offset", int, required=True)],
        request={"application/octet-stream": OpenApiTypes.BINARY},
        responses={200: UploadStateSerializer, 409: UploadStateSerializer},
    )
    @action(detail=False, methods=["put"], url_path=UPLOAD_PATH + "/chunk")
    def upload_chunk(self, request: Request, upload_id: str) -> Response:
        """One piece of the file (the raw bytes, at most chunk_size), starting at
        ?offset=. If the offset isn't where the server's copy ends, nothing is
        written and the answer is 409 with what the server has: carry on from there."""
        meta = self._upload(request, upload_id)
        offset = request.query_params.get("offset", "")
        if not offset.isdigit():
            raise serializers.ValidationError({"offset": "Give the piece's position in bytes."})
        try:
            uploads.append(upload_id, meta, int(offset), request._request)
        except uploads.WrongOffset:
            return Response(uploads.state(upload_id, meta), status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc
        return Response(uploads.state(upload_id, meta))

    @extend_schema(
        parameters=[UPLOAD_ID],
        request=ImageryDetailsSerializer,
        responses={201: ImagerySerializer},
    )
    @action(detail=False, methods=["post"], url_path=UPLOAD_PATH + "/finish")
    def finish_upload(self, request: Request, upload_id: str) -> Response:
        """Ends a piecewise upload: the image is added and processed, as after a
        single-request upload."""
        meta = self._upload(request, upload_id)
        data = ImageryDetailsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        have = uploads.received(upload_id)
        if have != meta["size"]:
            message = f"The upload isn't complete ({have} of {meta['size']} bytes)."
            raise serializers.ValidationError({"file": message})
        imagery = self._add(request, data.validated_data, meta["file_name"])
        try:
            uploads.take(upload_id, meta, services.source_path(imagery))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc
        self._process(request, imagery)
        return Response(ImagerySerializer(imagery).data, status=status.HTTP_201_CREATED)

    def get_parsers(self) -> list[Any]:
        return [MultiPartParser(), JSONParser()]

    def perform_update(self, serializer: Any) -> None:
        imagery = serializer.save()
        if imagery.basemap is not None:
            imagery.basemap.name = f"{imagery.name} (imagery)"[:120]
            imagery.basemap.attribution = imagery.source[:300]
            imagery.basemap.save(update_fields=["name", "attribution"])

    def perform_destroy(self, instance: Imagery) -> None:
        services.remove(instance)

    @extend_schema(
        parameters=[
            OpenApiParameter("z", int, OpenApiParameter.PATH),
            OpenApiParameter("x", int, OpenApiParameter.PATH),
            OpenApiParameter("y", int, OpenApiParameter.PATH),
        ],
        responses={200: OpenApiTypes.BINARY, 204: None},
    )
    @action(detail=True, methods=["get"], url_path=r"tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)\.png")
    def tile(
        self, request: Request, pk: str | None = None, z: str = "0", x: str = "0", y: str = "0"
    ) -> HttpResponse:
        """One map tile (PNG, transparent outside the image). 204 when empty."""
        imagery = self.get_object()
        zoom, column, row = int(z), int(x), int(y)
        if imagery.status != Imagery.Status.READY or imagery.bounds is None:
            return HttpResponse(status=204)
        if zoom > raster.MAX_ZOOM or column >= 2**zoom or row >= 2**zoom:
            return HttpResponse(status=204)
        if not raster.tile_intersects(imagery.bounds, zoom, column, row):
            return HttpResponse(status=204)
        data = raster.render_tile(
            services.cog_path(imagery), zoom, column, row, scale=imagery.value_range
        )
        if data is None:
            return HttpResponse(status=204)
        response = HttpResponse(data, content_type="image/png")
        response["Cache-Control"] = "private, max-age=3600"
        return response

    @extend_schema(request=ContourSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def contours(self, request: Request, pk: str | None = None) -> Response:
        """Makes contour lines from an elevation model, as a line layer of the project."""
        data = ContourSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = services.make_contours(
                self.get_object(), data.validated_data["interval"], request_user(request)
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
            ) from exc
        return Response(result, status=status.HTTP_201_CREATED)
