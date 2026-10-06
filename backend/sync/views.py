from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import BaseParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from projects import geometry as geo
from projects.models import Feature, PlanProject
from readiness.models import Item

from . import photos, services
from .models import Capture, Conflict, FieldTask, Photo


def _perms(*codes: str) -> list[BasePermission]:
    return [IsAuthenticated(), *(district_permission(code)() for code in codes)]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    return serializers.ValidationError(
        exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
    )


class OctetStreamParser(BaseParser):
    """Raw bytes (photo chunks)."""

    media_type = "application/octet-stream"

    def parse(  # type: ignore[override]  # raw bytes, not a mapping
        self, stream: Any, media_type: Any = None, parser_context: Any = None
    ) -> bytes:
        data: bytes = stream.read()
        return data


# --- Push and pull ---------------------------------------------------------------------------


class PushSerializer(serializers.Serializer[Any]):
    device_id = serializers.CharField(max_length=64)
    changes = serializers.ListField(child=serializers.JSONField(), allow_empty=True)


@extend_schema(parameters=[DISTRICT_HEADER], request=PushSerializer, responses=OpenApiTypes.OBJECT)
class PushView(APIView):
    """Changes made on a device: new captures (create), edits (update, with
    the version they were based on) and ground-truthing results (task). Each
    change has its own result; sending a change again returns the first result."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("field.sync")

    def post(self, request: Request) -> Response:
        data = PushSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        changes = data.validated_data["changes"]
        if len(changes) > services.MAX_CHANGES:
            raise serializers.ValidationError(
                {"changes": f"Send at most {services.MAX_CHANGES} changes at a time."}
            )
        district_id = require_district_id(request)
        user = request_user(request)
        results = [
            services.apply_change(change, district_id, data.validated_data["device_id"], user)
            for change in changes
        ]
        return Response({"results": results})


@extend_schema(
    parameters=[
        DISTRICT_HEADER,
        OpenApiParameter("project", int, required=True),
        OpenApiParameter("layers", str, description="Layer ids, comma-separated (default: all)"),
        OpenApiParameter("since", str, description="server_time of the last pull (ISO 8601)"),
    ],
    responses=OpenApiTypes.OBJECT,
)
class PullView(APIView):
    """What changed on the server since the device's last pull: features to add
    or replace, features deleted, layer definitions and ground-truthing tasks."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("field.sync")

    def get(self, request: Request) -> Response:
        project_id = request.query_params.get("project", "")
        if not project_id.isdigit():
            raise serializers.ValidationError({"project": "Give the project's id."})
        project = get_object_or_404(
            PlanProject, pk=int(project_id), district_id=require_district_id(request)
        )
        raw_layers = [p for p in request.query_params.get("layers", "").split(",") if p.strip()]
        if not all(p.strip().isdigit() for p in raw_layers):
            raise serializers.ValidationError({"layers": "Use layer ids separated by commas."})
        since = None
        raw_since = request.query_params.get("since", "")
        if raw_since:
            since = parse_datetime(raw_since)
            if since is None or since.tzinfo is None:
                raise serializers.ValidationError(
                    {"since": "Use the server_time from the last pull."}
                )
        return Response(services.pull(project, [int(p) for p in raw_layers], since))


# --- Photos ----------------------------------------------------------------------------------


class PhotoStartSerializer(serializers.Serializer[Any]):
    uuid = serializers.UUIDField()
    feature_uuid = serializers.UUIDField()
    size = serializers.IntegerField(min_value=1, max_value=photos.MAX_PHOTO_BYTES)
    sha256 = serializers.RegexField(r"^[0-9a-fA-F]{64}$")
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    accuracy_m = serializers.FloatField(required=False, allow_null=True)
    taken_at = serializers.DateTimeField(required=False, allow_null=True)


def photo_json(photo: Photo) -> dict[str, Any]:
    return {
        "uuid": str(photo.uuid),
        "feature": photo.feature_id,
        "size": photo.size,
        "received": photos.received_bytes(photo),
        "complete": photo.complete,
        "latitude": photo.latitude,
        "longitude": photo.longitude,
        "accuracy_m": photo.accuracy_m,
        "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
    }


@extend_schema(parameters=[DISTRICT_HEADER])
class PhotoViewSet(viewsets.GenericViewSet[Photo]):
    """Field photos. Start an upload, send it in chunks (resuming from
    `received` after a break), then anyone who can see the project can view it."""

    queryset = Photo.objects.none()
    serializer_class = PhotoStartSerializer
    lookup_field = "uuid"

    def get_permissions(self) -> list[BasePermission]:
        if self.action in ("list", "retrieve", "file"):
            return _perms("project.view")
        return _perms("field.sync")

    def get_queryset(self) -> QuerySet[Photo]:
        return Photo.objects.filter(district_id=require_district_id(self.request))

    @extend_schema(
        parameters=[OpenApiParameter("feature", int, required=True)], responses=OpenApiTypes.OBJECT
    )
    def list(self, request: Request) -> Response:
        feature = request.query_params.get("feature", "")
        if not feature.isdigit():
            raise serializers.ValidationError({"feature": "Give the feature's id."})
        rows = self.get_queryset().filter(feature_id=int(feature), complete=True)
        return Response([photo_json(p) for p in rows])

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, uuid: str | None = None) -> Response:
        """Where an upload has got to (`received`), to resume it."""
        return Response(photo_json(self.get_object()))

    @extend_schema(request=PhotoStartSerializer, responses=OpenApiTypes.OBJECT)
    def create(self, request: Request) -> Response:
        """Starts an upload, or returns the one already started for this photo."""
        data = PhotoStartSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        district_id = require_district_id(request)
        existing = Photo.objects.filter(uuid=values["uuid"], district_id=district_id).first()
        if existing is not None:
            return Response(photo_json(existing))
        feature = Feature.objects.filter(
            uuid=values["feature_uuid"], district_id=district_id
        ).first()
        if feature is None:
            raise serializers.ValidationError(
                {"feature_uuid": "Send the feature first: it isn't on the server yet."}
            )
        photo = Photo.objects.create(
            district_id=district_id,
            feature=feature,
            uuid=values["uuid"],
            size=values["size"],
            sha256=values["sha256"].lower(),
            latitude=values.get("latitude"),
            longitude=values.get("longitude"),
            accuracy_m=values.get("accuracy_m"),
            taken_at=values.get("taken_at"),
            uploaded_by=request_user(request),
        )
        return Response(photo_json(photo), status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[OpenApiParameter("offset", int, required=True)],
        request={"application/octet-stream": OpenApiTypes.BINARY},
        responses={200: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["put"], parser_classes=[OctetStreamParser])
    def chunk(self, request: Request, uuid: str | None = None) -> Response:
        """Adds bytes at `offset`. 409 with `received` if that isn't where the
        server's copy ends (resume from there)."""
        offset = request.query_params.get("offset", "")
        if not offset.isdigit():
            raise serializers.ValidationError({"offset": "Give the position of this chunk."})
        with transaction.atomic():
            photo = get_object_or_404(self.get_queryset().select_for_update(), uuid=uuid)
            body = request.data if isinstance(request.data, bytes) else b""
            try:
                photo = photos.append_chunk(photo, int(offset), body)
            except photos.WrongOffset as exc:
                return Response(
                    {"detail": "Resume from `received`.", "received": exc.args[0]},
                    status=status.HTTP_409_CONFLICT,
                )
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
        return Response(photo_json(photo))

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def file(self, request: Request, uuid: str | None = None) -> FileResponse:
        photo = self.get_object()
        path = Path(settings.MEDIA_ROOT) / photo.path
        if not photo.complete or not photo.path or not path.is_file():
            raise Http404("The photo hasn't finished uploading.")
        return FileResponse(open(path, "rb"), content_type="image/jpeg")


# --- Captures (how a field feature was recorded) --------------------------------------------


@extend_schema(
    parameters=[DISTRICT_HEADER, OpenApiParameter("feature", int, required=True)],
    responses=OpenApiTypes.OBJECT,
)
class CapturesView(APIView):
    """Who recorded a feature in the field, how, and how accurately."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view")

    def get(self, request: Request) -> Response:
        feature = request.query_params.get("feature", "")
        if not feature.isdigit():
            raise serializers.ValidationError({"feature": "Give the feature's id."})
        rows = Capture.objects.filter(
            district_id=require_district_id(request), feature_id=int(feature)
        ).select_related("captured_by")
        return Response(
            [
                {
                    "feature_version": c.feature_version,
                    "method": c.method,
                    "accuracy_m": c.accuracy_m,
                    "fix_time": c.fix_time.isoformat() if c.fix_time else None,
                    "readings": c.readings,
                    "captured_at": c.captured_at.isoformat() if c.captured_at else None,
                    "captured_by": c.captured_by.email if c.captured_by else None,
                    "device_id": c.device_id,
                    "notes": c.notes,
                    "received_at": c.received_at.isoformat(),
                }
                for c in rows
            ]
        )


# --- Conflicts -------------------------------------------------------------------------------


class ResolveSerializer(serializers.Serializer[Any]):
    resolution = serializers.ChoiceField(choices=Conflict.Resolution.choices)
    properties = serializers.JSONField(required=False)
    use_field_geometry = serializers.BooleanField(required=False, default=False)


def conflict_json(conflict: Conflict, *, detail: bool = False) -> dict[str, Any]:
    feature = conflict.feature
    row: dict[str, Any] = {
        "id": conflict.pk,
        "project": conflict.project_id,
        "feature": feature.pk,
        "layer": feature.layer_id,
        "layer_name": feature.layer.name,
        "status": conflict.status,
        "resolution": conflict.resolution,
        "submitted_by": conflict.submitted_by.email if conflict.submitted_by else None,
        "created_at": conflict.created_at.isoformat(),
        "base_version": conflict.base_version,
        "server_version": conflict.server_version,
        "resolved_by": conflict.resolved_by.email if conflict.resolved_by else None,
        "resolved_at": conflict.resolved_at.isoformat() if conflict.resolved_at else None,
    }
    if detail:
        row.update(
            {
                "schema": feature.layer.schema,
                "office": {
                    "version": feature.version,
                    "properties": feature.properties,
                    "geometry": geo.read_geometries([feature.pk], native=False)[feature.pk],
                },
                "field": {
                    "properties": conflict.field_properties,
                    "geometry": conflict.field_geometry,
                    "capture": conflict.capture,
                },
            }
        )
    return row


@extend_schema(parameters=[DISTRICT_HEADER])
class ConflictViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet[Conflict]
):
    """Field edits that were based on an older version than the server's.
    Filter with ?project= and ?status=open."""

    queryset = Conflict.objects.none()
    serializer_class = ResolveSerializer

    def get_permissions(self) -> list[BasePermission]:
        return _perms("sync.resolve" if self.action == "resolve" else "project.view")

    def get_queryset(self) -> QuerySet[Conflict]:
        qs = Conflict.objects.filter(district_id=require_district_id(self.request)).select_related(
            "feature", "feature__layer", "submitted_by", "resolved_by"
        )
        project = self.request.query_params.get("project", "")
        if project.isdigit():
            qs = qs.filter(project_id=int(project))
        state = self.request.query_params.get("status", "")
        if state in Conflict.Status.values:
            qs = qs.filter(status=state)
        return qs

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response([conflict_json(c) for c in self.get_queryset()[:500]])

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(conflict_json(self.get_object(), detail=True))

    @extend_schema(request=ResolveSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def resolve(self, request: Request, pk: str | None = None) -> Response:
        """keep_office, keep_field, or merged (send the chosen value per field
        in `properties`, and `use_field_geometry`)."""
        data = ResolveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        properties = values.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise serializers.ValidationError({"properties": "Must be an object."})
        with transaction.atomic():
            conflict = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
            try:
                services.resolve_conflict(
                    conflict,
                    values["resolution"],
                    request_user(request),
                    properties=properties,
                    use_field_geometry=values["use_field_geometry"],
                )
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
        conflict.refresh_from_db()
        return Response(conflict_json(conflict, detail=True))


# --- Ground-truthing --------------------------------------------------------------------------


@extend_schema(parameters=[DISTRICT_HEADER], request=None, responses=OpenApiTypes.OBJECT)
class SendToFieldView(APIView):
    """Makes ground-truthing tasks for a checklist item's layer: one for every
    feature that isn't verified yet. Field officers get them at their next sync."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("checklist.edit")

    def post(self, request: Request, item_id: int) -> Response:
        item = get_object_or_404(
            Item.objects.select_related("linked_layer"),
            pk=item_id,
            district_id=require_district_id(request),
        )
        if item.linked_layer is None:
            raise serializers.ValidationError(
                {"detail": "This item has no layer yet. Import or draw its data first."}
            )
        return Response(
            services.send_layer_to_field(item.linked_layer, item, request_user(request)),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    parameters=[DISTRICT_HEADER, OpenApiParameter("project", int, required=True)],
    responses=OpenApiTypes.OBJECT,
)
class TasksView(APIView):
    """Ground-truthing progress for a project: counts and the tasks."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view")

    def get(self, request: Request) -> Response:
        project = request.query_params.get("project", "")
        if not project.isdigit():
            raise serializers.ValidationError({"project": "Give the project's id."})
        tasks = FieldTask.objects.filter(
            district_id=require_district_id(request), project_id=int(project)
        ).select_related("feature", "item", "completed_by")
        rows = [
            {
                **services.task_json(t),
                "feature": t.feature_id,
                "notes": t.notes,
                "completed_by": t.completed_by.email if t.completed_by else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks[:2000]
        ]
        counts = {"open": 0, "confirmed": 0, "corrected": 0, "not_found": 0}
        for t in tasks:
            counts[t.outcome if t.status == FieldTask.Status.DONE else "open"] += 1
        return Response({"counts": counts, "tasks": rows})
