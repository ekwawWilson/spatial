from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.permissions import district_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from projects.models import PlanProject

from . import gdal_io
from .models import DataJob
from .safety import MAX_UPLOAD_BYTES
from .serializers import DataJobSerializer, ExportSerializer, ImportPlanSerializer, UploadSerializer
from .tasks import job_dir, run_job, source_file


def _project(request: Request, project_id: int) -> PlanProject:
    return get_object_or_404(PlanProject, pk=project_id, district_id=require_district_id(request))


def _dispatch(job: DataJob, request: Request) -> None:
    """Runs the job after this request's transaction commits, so the worker
    sees the job row."""
    district_id = job.district_id
    user_id = request_user(request).pk
    transaction.on_commit(lambda: run_job.delay(job.pk, district_id, user_id))


def validate_import_plan(job: DataJob, plan: dict[str, Any]) -> None:
    """Refuses plans that skip a required decision, most importantly the CRS:
    files without one (and CAD/CSV files, which never carry a reliable one)
    need the user's explicit choice, marked crs_confirmed."""
    by_name = {layer["name"]: layer for layer in job.inspection.get("layers", [])}
    errors: list[str] = []
    for i, item in enumerate(plan["layers"], start=1):
        source = by_name.get(item.get("source", ""))
        if source is None:
            errors.append(f"Layer {i}: the file has no layer called {item.get('source')!r}.")
            continue
        where = f"{source['name']}"
        if not item.get("crs"):
            errors.append(f"{where}: choose the coordinate system of the file's coordinates.")
        needs_confirmation = (
            job.inspection.get("crs_confirmation_required") or not source["crs"]["found"]
        )
        if needs_confirmation and not item.get("crs_confirmed"):
            reason = (
                "has no coordinate system"
                if not source["crs"]["found"]
                else f"is a {job.file_format.upper()} file"
            )
            errors.append(
                f"{where} {reason}: confirm which coordinate system its coordinates are in."
            )
        if bool(item.get("target_layer")) == bool(item.get("new_layer")):
            errors.append(f"{where}: choose an existing layer or describe a new one.")
        if item.get("new_layer") and item["new_layer"].get("geometry_type") not in (
            "point",
            "line",
            "polygon",
        ):
            errors.append(f"{where}: a new layer needs a geometry type (point, line or polygon).")
        for key, allowed in (
            ("invalid_geometry", ("fix", "skip", "abort")),
            ("duplicates", ("keep", "skip")),
            ("bad_values", ("blank", "skip_feature")),
        ):
            if key in item and item[key] not in allowed:
                errors.append(f"{where}: {key} must be one of {', '.join(allowed)}.")
    if errors:
        raise serializers.ValidationError({"plan": errors})


@extend_schema(parameters=[DISTRICT_HEADER])
class DataJobViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet[DataJob]
):
    """Import and export jobs of the current district (filter with ?project=)."""

    serializer_class = DataJobSerializer
    queryset = DataJob.objects.none()  # schema hint; get_queryset() is used

    def get_permissions(self) -> list[BasePermission]:
        code = "data.export" if self.action in ("export", "download") else "data.import"
        if self.action in ("list", "retrieve"):
            code = "project.view"
        return [IsAuthenticated(), district_permission(code)()]

    def get_queryset(self) -> QuerySet[DataJob]:
        qs = DataJob.objects.filter(district_id=require_district_id(self.request)).order_by(
            "-created_at"
        )
        project = self.request.query_params.get("project")
        if project and project.isdigit():
            qs = qs.filter(project_id=int(project))
        return qs

    @extend_schema(
        request={"multipart/form-data": UploadSerializer}, responses={201: DataJobSerializer}
    )
    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser], url_path="imports")
    def upload(self, request: Request) -> Response:
        """Uploads a file and inspects it: layers, geometry, fields, CRS."""
        data = UploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        project = _project(request, data.validated_data["project"])
        upload = data.validated_data["file"]
        if upload.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError({"file": "Files are limited to 500 MB."})
        name = Path(upload.name).name
        try:
            fmt = gdal_io.detect_format(name)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc
        job = DataJob.objects.create(
            kind=DataJob.Kind.IMPORT,
            district_id=project.district_id,
            project=project,
            status=DataJob.Status.UPLOADED,
            file_format=fmt,
            original_name=name,
            created_by=request_user(request),
        )
        target = source_file(job)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        try:
            encoding = data.validated_data.get("encoding") or None
            job.inspection = gdal_io.inspect(target, fmt, encoding=encoding)
        except DjangoValidationError as exc:
            job.status = DataJob.Status.FAILED
            job.error = "; ".join(exc.messages)
            job.save(update_fields=["status", "error"])
            raise serializers.ValidationError({"file": exc.messages}) from exc
        job.status = DataJob.Status.INSPECTED
        job.save(update_fields=["inspection", "status"])
        return Response(DataJobSerializer(job).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ImportPlanSerializer, responses={202: DataJobSerializer})
    @action(detail=True, methods=["post"])
    def run(self, request: Request, pk: str | None = None) -> Response:
        """Starts an inspected import with the user's choices."""
        job = self.get_object()
        if job.kind != DataJob.Kind.IMPORT or job.status != DataJob.Status.INSPECTED:
            raise serializers.ValidationError("Only an inspected import can be started.")
        data = ImportPlanSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        validate_import_plan(job, data.validated_data)
        job.plan = data.validated_data
        job.status = DataJob.Status.QUEUED
        job.save(update_fields=["plan", "status"])
        _dispatch(job, request)
        return Response(DataJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=ExportSerializer, responses={202: DataJobSerializer})
    @action(detail=False, methods=["post"], url_path="exports")
    def export(self, request: Request) -> Response:
        """Exports layers (or a selection of one layer's features)."""
        data = ExportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        project = _project(request, data.validated_data["project"])
        plan = {k: v for k, v in data.validated_data.items() if k != "project"}
        job = DataJob.objects.create(
            kind=DataJob.Kind.EXPORT,
            district_id=project.district_id,
            project=project,
            status=DataJob.Status.QUEUED,
            file_format=plan["format"],
            plan=plan,
            created_by=request_user(request),
        )
        _dispatch(job, request)
        return Response(DataJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        job = self.get_object()
        if job.kind != DataJob.Kind.EXPORT or job.status != DataJob.Status.DONE:
            raise Http404("This export isn't ready.")
        path = job_dir(job) / "result" / job.result_name
        if not path.exists():
            raise Http404("The export file has expired.")
        return FileResponse(open(path, "rb"), as_attachment=True, filename=job.result_name)  # noqa: SIM115
