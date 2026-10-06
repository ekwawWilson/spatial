import hashlib
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import (
    IsSystemAdmin,
    district_permission,
    has_permission,
    request_user,
    require_district_id,
)
from core.schema import DISTRICT_HEADER
from core.throttling import UploadThrottle, UserThrottle
from projects.models import PlanProject
from transfer.safety import MAX_UPLOAD_BYTES

from . import container, keys, package
from .models import FileRecord


class OpenSerializer(serializers.Serializer[Any]):
    file = serializers.FileField()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


@extend_schema(parameters=[DISTRICT_HEADER], request=None, responses={200: OpenApiTypes.BINARY})
class SaveView(APIView):
    """The whole project as a protected .spp file: layers and their features,
    history, styles, checklist with its documents, and basemap configuration."""

    def get_permissions(self) -> list[BasePermission]:
        return [IsAuthenticated(), district_permission("data.export")()]

    def post(self, request: Request, project_id: int) -> FileResponse:
        project = get_object_or_404(
            PlanProject, pk=project_id, district_id=require_district_id(request)
        )
        directory = tempfile.TemporaryDirectory(prefix="spp-save-")
        try:
            workdir = Path(directory.name)
            try:
                keys.active()  # fail before doing the work
                packed, summary = package.build(project, request_user(request), workdir)
                target = workdir / "project.spp"
                header = container.encrypt(packed, target)
            except keys.KeyError_ as exc:
                raise serializers.ValidationError({"detail": str(exc)}) from exc
            packed.unlink()
            FileRecord.objects.create(
                district_id=project.district_id,
                project=project,
                project_name=project.name,
                direction=FileRecord.Direction.SAVED,
                file_id=header["file_id"],
                key_id=header["key_id"],
                sha256=_sha256(target),
                size=target.stat().st_size,
                summary=summary,
                user=request_user(request),
            )
        except BaseException:
            directory.cleanup()
            raise
        name = f"{slugify(project.name) or 'project'}-{timezone.localtime():%Y%m%d-%H%M}.spp"
        return FileResponse(
            _RemoveWhenClosed(target, directory),
            as_attachment=True,
            filename=name,
            content_type="application/octet-stream",
        )


@extend_schema(
    parameters=[DISTRICT_HEADER],
    request={"multipart/form-data": OpenSerializer},
    responses={201: OpenApiTypes.OBJECT},
)
class OpenView(APIView):
    """Opens a .spp file as a new project in the current district. The file
    must have been protected with an organisation key this server holds."""

    parser_classes = [MultiPartParser]
    throttle_classes = [UserThrottle, UploadThrottle]

    def get_permissions(self) -> list[BasePermission]:
        return [
            IsAuthenticated(),
            district_permission("project.edit")(),
            district_permission("data.import")(),
        ]

    def post(self, request: Request) -> Response:
        data = OpenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        if upload.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError({"file": "Files are limited to 500 MB."})
        district_id = require_district_id(request)
        user = request_user(request)
        with tempfile.TemporaryDirectory(prefix="spp-open-") as directory:
            workdir = Path(directory)
            received = workdir / "received.spp"
            with open(received, "wb") as fh:
                for chunk in upload.chunks():
                    fh.write(chunk)
            try:
                header = container.decrypt(received, workdir / "package.zip")
                root, manifest = package.unpack(workdir / "package.zip", workdir)
                project, report = package.restore(
                    root,
                    manifest,
                    district_id,
                    user,
                    may_add_basemaps=has_permission(request, "basemap.manage"),
                )
            except (container.SppError, keys.KeyError_) as exc:
                raise serializers.ValidationError({"file": str(exc)}) from exc
            FileRecord.objects.create(
                district_id=district_id,
                project=project,
                project_name=project.name,
                direction=FileRecord.Direction.OPENED,
                file_id=header.get("file_id") or uuid4(),
                key_id=header["key_id"],
                sha256=_sha256(received),
                size=received.stat().st_size,
                summary=report,
                user=user,
            )
        return Response(report, status=status.HTTP_201_CREATED)


@extend_schema(responses=OpenApiTypes.OBJECT)
class KeysView(APIView):
    """Which organisation keys this server holds: ids and fingerprints, never
    the keys. Two servers can open each other's files when a fingerprint matches."""

    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request: Request) -> Response:
        try:
            ring = keys.ring()
        except keys.KeyError_ as exc:
            return Response({"configured": False, "problem": str(exc), "keys": []})
        return Response(
            {
                "configured": bool(ring),
                "problem": None,
                "keys": [
                    {"key_id": k.key_id, "fingerprint": k.fingerprint, "active": i == 0}
                    for i, k in enumerate(ring)
                ],
            }
        )
