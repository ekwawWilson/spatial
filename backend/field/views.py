import tempfile
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from basemaps.models import BasemapSource
from basemaps.services import OfflineCachingNotAllowed
from core.permissions import district_permission, require_district_id
from core.schema import DISTRICT_HEADER
from projects.models import PlanProject

from . import mbtiles, services


def _project(request: Request, project_id: int) -> PlanProject:
    return get_object_or_404(PlanProject, pk=project_id, district_id=require_district_id(request))


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    return serializers.ValidationError(
        exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
    )


class _RemoveWhenClosed:
    """A file that deletes its temporary directory once it has been sent."""

    def __init__(self, path: Path, directory: tempfile.TemporaryDirectory[str]) -> None:
        self._file = open(path, "rb")  # closed by the response
        self._directory = directory

    def read(self, size: int = -1) -> bytes:
        return self._file.read(size)

    def close(self) -> None:
        self._file.close()
        self._directory.cleanup()


@extend_schema(
    parameters=[
        DISTRICT_HEADER,
        OpenApiParameter("layers", str, description="Layer ids, comma-separated (default: all)"),
    ],
    responses=OpenApiTypes.OBJECT,
)
class FieldPackageView(APIView):
    """What the field app downloads to work offline: the chosen layers (their
    forms and the features inside the planning area), the planning area, and
    the project's coordinate system."""

    def get_permissions(self) -> list[BasePermission]:
        return [IsAuthenticated(), district_permission("field.package")()]

    def get(self, request: Request, project_id: int) -> Response:
        project = _project(request, project_id)
        layer_ids: list[int] | None = None
        raw = request.query_params.get("layers", "").strip()
        if raw:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            if not all(p.isdigit() for p in parts):
                raise serializers.ValidationError({"layers": "Use layer ids separated by commas."})
            layer_ids = [int(p) for p in parts]
        try:
            return Response(services.build_package(project, layer_ids))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc


@extend_schema(
    parameters=[
        DISTRICT_HEADER,
        OpenApiParameter("source", int, required=True, description="Basemap id"),
        OpenApiParameter("max_zoom", int, description="Lower it to make the file smaller"),
    ],
    responses={200: OpenApiTypes.BINARY},
)
class FieldBasemapView(APIView):
    """An offline basemap (MBTiles) of the planning area, from a basemap whose
    terms allow storing tiles on a device. Others are refused."""

    def get_permissions(self) -> list[BasePermission]:
        return [IsAuthenticated(), district_permission("field.package")()]

    def get(self, request: Request, project_id: int) -> Any:
        project = _project(request, project_id)
        source_id = request.query_params.get("source", "")
        max_zoom = request.query_params.get("max_zoom", "")
        if not source_id.isdigit() or (max_zoom and not max_zoom.isdigit()):
            raise serializers.ValidationError(
                {"source": "Give the basemap's id (and a whole max_zoom)."}
            )
        # Row-level security limits this to global sources and the district's own.
        source = get_object_or_404(BasemapSource, pk=int(source_id), is_active=True)
        bbox = services.boundary_bbox(project)
        if bbox is None:
            raise serializers.ValidationError(
                {"detail": "Set the planning area first: the offline basemap covers it."}
            )
        directory = tempfile.TemporaryDirectory(prefix="field-basemap-")
        try:
            target = Path(directory.name) / "basemap.mbtiles"
            try:
                mbtiles.build(source, bbox, int(max_zoom) if max_zoom else None, target)
            except OfflineCachingNotAllowed as exc:
                raise serializers.ValidationError({"source": str(exc)}) from exc
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
        except BaseException:
            directory.cleanup()
            raise
        return FileResponse(
            _RemoveWhenClosed(target, directory),
            as_attachment=True,
            filename=(
                f"{slugify(project.name) or 'project'}-{slugify(source.name) or 'basemap'}.mbtiles"
            ),
            content_type="application/vnd.sqlite3",
        )
