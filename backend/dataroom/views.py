"""What staff do with the Public Data Room: open it, choose what is
published, put documents on display, and answer requests for information."""

from datetime import date
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from django.http import FileResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from core.throttling import UploadThrottle
from projects.models import PlanProject

from .models import DataRoom, InformationRequest, Publication, RoomDocument
from .public import ANSWER_WITHIN_DAYS, due_on

MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


class RoomSerializer(serializers.ModelSerializer[DataRoom]):
    code = serializers.CharField(source="district.code", read_only=True)

    class Meta:
        model = DataRoom
        fields = ["code", "is_open", "show_applicants", "welcome", "contact", "updated_at"]


@extend_schema(parameters=[DISTRICT_HEADER])
class RoomSettingsView(APIView):
    """The district's Public Data Room: whether it is open online, whether
    the register names applicants, and what the public is told."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("dataroom.view" if self.request.method == "GET" else "dataroom.manage")

    def _room(self, request: Request) -> DataRoom:
        room, _ = DataRoom.objects.get_or_create(district_id=require_district_id(request))
        return room

    @extend_schema(responses=RoomSerializer)
    def get(self, request: Request) -> Response:
        return Response(RoomSerializer(self._room(request)).data)

    @extend_schema(request=RoomSerializer, responses=RoomSerializer)
    def patch(self, request: Request) -> Response:
        data = RoomSerializer(self._room(request), data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        return Response(data.data)


class PublicationSerializer(serializers.ModelSerializer[Publication]):
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = Publication
        fields = ["id", "project", "project_name", "permits", "zoning", "published_at"]


@extend_schema(parameters=[DISTRICT_HEADER])
class PublicationViewSet(viewsets.ModelViewSet[Publication]):
    """The projects whose permits and zoning are in the public register."""

    serializer_class = PublicationSerializer
    queryset = Publication.objects.none()
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        safe = self.request.method in ("GET", "HEAD", "OPTIONS")
        return _perms("dataroom.view" if safe else "dataroom.manage")

    def get_queryset(self) -> QuerySet[Publication]:
        return Publication.objects.filter(
            district_id=require_district_id(self.request)
        ).select_related("project")

    def perform_create(self, serializer: Any) -> None:
        district_id = require_district_id(self.request)
        project: PlanProject = serializer.validated_data["project"]
        if project.district_id != district_id:
            raise serializers.ValidationError({"project": "Pick a project of this district."})
        serializer.save(district_id=district_id, published_by=request_user(self.request))

    def perform_update(self, serializer: Any) -> None:
        if "project" in serializer.validated_data:
            if serializer.validated_data["project"].pk != serializer.instance.project_id:
                raise serializers.ValidationError({"project": "Publish the other project instead."})
        serializer.save()


class DocumentSerializer(serializers.ModelSerializer[RoomDocument]):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = RoomDocument
        fields = [
            "id",
            "kind",
            "kind_label",
            "title",
            "description",
            "name",
            "size",
            "display_from",
            "display_until",
            "uploaded_at",
        ]
        read_only_fields = ["name", "size"]


class RoomDocumentUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField()
    kind = serializers.ChoiceField(choices=RoomDocument.Kind.choices)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    display_from = serializers.DateField(required=False, help_text="Default: today")
    display_until = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start = attrs.get("display_from") or date.today()
        end = attrs.get("display_until")
        if end is not None and end < start:
            raise serializers.ValidationError({"display_until": "Before it goes on display."})
        return attrs


@extend_schema(parameters=[DISTRICT_HEADER])
class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[RoomDocument],
):
    """Documents on display in the data room: plans, notices, records of
    consultation (r.64(2)). Each shows from a day, and optionally until one."""

    serializer_class = DocumentSerializer
    queryset = RoomDocument.objects.none()
    pagination_class = None
    parser_classes = [JSONParser, MultiPartParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        safe = self.request.method in ("GET", "HEAD", "OPTIONS")
        return _perms("dataroom.view" if safe else "dataroom.manage")

    def get_throttles(self) -> list[Any]:
        throttles = super().get_throttles()
        return [*throttles, UploadThrottle()] if self.action == "create" else throttles

    def get_queryset(self) -> QuerySet[RoomDocument]:
        return RoomDocument.objects.filter(district_id=require_district_id(self.request))

    @extend_schema(
        request={"multipart/form-data": RoomDocumentUploadSerializer},
        responses={201: DocumentSerializer},
    )
    def create(self, request: Request) -> Response:
        data = RoomDocumentUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        upload = values["file"]
        if upload.size > MAX_DOCUMENT_BYTES:
            raise serializers.ValidationError({"file": "Documents are limited to 50 MB."})
        district_id = require_district_id(request)
        name = Path(upload.name).name or "document"
        document = RoomDocument.objects.create(
            district_id=district_id,
            kind=values["kind"],
            title=values["title"],
            description=values.get("description", ""),
            name=name,
            path="",
            size=upload.size,
            display_from=values.get("display_from") or date.today(),
            display_until=values.get("display_until"),
            uploaded_by=request_user(request),
        )
        relative = Path("dataroom") / str(district_id) / f"{document.pk}-{name}"
        target = Path(settings.MEDIA_ROOT) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        document.path = str(relative)
        document.save(update_fields=["path"])
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        document = self.get_object()
        path = Path(settings.MEDIA_ROOT) / document.path
        if not document.path or not path.is_file():
            raise Http404("The file is missing.")
        return FileResponse(open(path, "rb"), as_attachment=True, filename=document.name)

    def perform_destroy(self, instance: RoomDocument) -> None:
        path = Path(settings.MEDIA_ROOT) / instance.path
        instance.delete()
        if instance.path and path.is_file():
            path.unlink()


def request_json(item: InformationRequest, today: date) -> dict[str, Any]:
    due = due_on(item.received_on)
    return {
        "id": item.pk,
        "reference": item.reference,
        "name": item.name,
        "phone": item.phone,
        "email": item.email,
        "subject": item.subject,
        "body": item.body,
        "received_on": item.received_on.isoformat(),
        "status": item.status,
        "answer": item.answer,
        "answered_on": item.answered_on.isoformat() if item.answered_on else None,
        "answered_by": item.answered_by.email if item.answered_by else None,
        "due_on": due.isoformat(),
        "late": bool(item.answered_on and item.answered_on > due),
        "overdue": item.status == InformationRequest.Status.OPEN and today > due,
    }


class AnswerSerializer(serializers.Serializer[Any]):
    answer = serializers.CharField()
    declined = serializers.BooleanField(default=False)


@extend_schema(parameters=[DISTRICT_HEADER])
class RequestViewSet(viewsets.GenericViewSet[InformationRequest]):
    """The record of requests for information (r.64(8)), each due an answer
    within five days of being received (r.64(7))."""

    queryset = InformationRequest.objects.none()
    serializer_class = AnswerSerializer
    pagination_class = None

    def get_permissions(self) -> list[BasePermission]:
        return _perms("dataroom.answer")

    def get_queryset(self) -> QuerySet[InformationRequest]:
        return InformationRequest.objects.filter(
            district_id=require_district_id(self.request)
        ).select_related("answered_by")

    @extend_schema(responses=OpenApiTypes.OBJECT, operation_id="dataroom_requests_list")
    def list(self, request: Request) -> Response:
        today = date.today()
        rows = [request_json(item, today) for item in self.get_queryset()[:500]]
        return Response(
            {
                "answer_within_days": ANSWER_WITHIN_DAYS,
                "open": sum(1 for r in rows if r["status"] == "open"),
                "overdue": sum(1 for r in rows if r["overdue"]),
                "results": rows,
            }
        )

    @extend_schema(request=AnswerSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def answer(self, request: Request, pk: str | None = None) -> Response:
        """Records the answer given (or that the request was declined, with why)."""
        item = self.get_object()
        if item.status != InformationRequest.Status.OPEN:
            raise serializers.ValidationError("This request has already been answered.")
        data = AnswerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        declined = data.validated_data["declined"]
        item.status = (
            InformationRequest.Status.DECLINED if declined else InformationRequest.Status.ANSWERED
        )
        item.answer = data.validated_data["answer"]
        item.answered_on = date.today()
        item.answered_by = request_user(request)
        item.save(update_fields=["status", "answer", "answered_on", "answered_by"])
        return Response(request_json(item, date.today()))
