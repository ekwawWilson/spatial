# ruff: noqa: E501 - comments and messages read better unbroken
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER

from . import documents, registry, services
from .models import Meeting


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "error_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": exc.messages})


def meeting_json(meeting: Meeting, *, full: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": meeting.pk,
        "committee": meeting.committee.kind,
        "committee_label": registry.COMMITTEES[meeting.committee.kind],
        "held_on": meeting.held_on.isoformat(),
        "venue": meeting.venue,
        "items": len(meeting.agenda),
        "considered": sum(1 for i in meeting.agenda if i.get("outcome")),
        "notice": services.notice_clock(meeting),
        "quorum": services.quorum(meeting),
    }
    if full:
        out.update(
            {
                "members": meeting.committee.members,
                "attendance": meeting.attendance,
                "agenda": meeting.agenda,
                "notes": meeting.notes,
            }
        )
    return out


class MembersSerializer(serializers.Serializer[Any]):
    members = serializers.ListField(child=serializers.DictField())


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class CommitteesView(APIView):
    """The district's two planning committees and their members (GET), or
    one committee's members set (PUT ?kind=dspc|tsc)."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("permit.view" if self.request.method == "GET" else "permit.decide")

    def get(self, request: Request) -> Response:
        district_id = require_district_id(request)
        return Response(
            {
                "committees": [
                    {
                        "kind": kind,
                        "label": label,
                        "members": services.committee(district_id, kind).members,
                    }
                    for kind, label in registry.COMMITTEES.items()
                ],
                "offices": [{"code": c, "label": label} for c, label in registry.OFFICES],
                "outcomes": [{"code": c, "label": label} for c, label in registry.OUTCOMES.items()],
            }
        )

    @extend_schema(request=MembersSerializer, parameters=[OpenApiParameter("kind", str)])
    def put(self, request: Request) -> Response:
        data = MembersSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            found = services.committee(
                require_district_id(request), request.query_params.get("kind", "")
            )
            found.members = services.check_members(data.validated_data["members"])
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        found.save()
        return self.get(request)


class MeetingWriteSerializer(serializers.Serializer[Any]):
    committee = serializers.ChoiceField(choices=list(registry.COMMITTEES), required=False)
    held_on = serializers.DateField(required=False)
    venue = serializers.CharField(max_length=200, required=False, allow_blank=True)
    notice_served_on = serializers.DateField(required=False, allow_null=True)
    attendance = serializers.ListField(child=serializers.CharField(max_length=200), required=False)
    agenda = serializers.ListField(child=serializers.DictField(), required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


@extend_schema(parameters=[DISTRICT_HEADER])
class MeetingViewSet(viewsets.GenericViewSet[Meeting]):
    """Meetings of the planning committees: the agenda built from what is
    waiting, the notice (Form 5), attendance and quorum, and the minutes."""

    queryset = Meeting.objects.none()
    serializer_class = MeetingWriteSerializer

    def get_permissions(self) -> list[BasePermission]:
        return _perms(
            "permit.view" if self.action in ("list", "retrieve", "paper") else "permit.process"
        )

    def get_queryset(self) -> QuerySet[Meeting]:
        return Meeting.objects.filter(district_id=require_district_id(self.request)).select_related(
            "committee", "committee__district"
        )

    @extend_schema(responses=OpenApiTypes.OBJECT, operation_id="committees_meetings_list")
    def list(self, request: Request) -> Response:
        return Response(
            {"results": [meeting_json(m, full=False) for m in self.get_queryset()[:200]]}
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(meeting_json(self.get_object(), full=True))

    @extend_schema(request=MeetingWriteSerializer, responses={201: OpenApiTypes.OBJECT})
    def create(self, request: Request) -> Response:
        data = MeetingWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if "committee" not in values or "held_on" not in values:
            raise serializers.ValidationError({"held_on": "Say which committee meets, and when."})
        district_id = require_district_id(request)
        meeting = Meeting(
            district_id=district_id,
            committee=services.committee(district_id, values["committee"]),
            held_on=values["held_on"],
            venue=values.get("venue", ""),
            created_by=request_user(request),
        )
        services.build_agenda(meeting)
        meeting.save()
        return Response(meeting_json(meeting, full=True), status=status.HTTP_201_CREATED)

    @extend_schema(request=MeetingWriteSerializer, responses=OpenApiTypes.OBJECT)
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        meeting = self.get_object()
        data = MeetingWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            if "agenda" in values:
                meeting.agenda = services.check_agenda(values["agenda"], meeting.agenda)
            if "attendance" in values:
                names = {m["name"] for m in meeting.committee.members}
                strangers = [n for n in values["attendance"] if n not in names]
                if strangers:
                    raise DjangoValidationError(
                        {"attendance": [f"Not members: {', '.join(strangers)}."]}
                    )
                meeting.attendance = list(dict.fromkeys(values["attendance"]))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        for name in ("held_on", "venue", "notice_served_on", "notes"):
            if name in values:
                setattr(meeting, name, values[name])
        if meeting.notice_served_on and meeting.notice_served_on > date.today():
            raise serializers.ValidationError({"notice_served_on": "That date is in the future."})
        meeting.save()
        return Response(meeting_json(meeting, full=True))

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="refresh-agenda")
    def refresh_agenda(self, request: Request, pk: str | None = None) -> Response:
        """Adds what has come in since the agenda was made."""
        meeting = self.get_object()
        added = services.build_agenda(meeting)
        meeting.save(update_fields=["agenda"])
        return Response({**meeting_json(meeting, full=True), "added": added})

    @extend_schema(
        parameters=[OpenApiParameter("kind", str, description="notice or minutes")],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def paper(self, request: Request, pk: str | None = None) -> HttpResponse:
        meeting = self.get_object()
        kind = request.query_params.get("kind", "notice")
        if kind not in ("notice", "minutes"):
            raise serializers.ValidationError({"kind": "notice or minutes."})
        pdf = documents.notice_pdf(meeting) if kind == "notice" else documents.minutes_pdf(meeting)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{meeting.committee.kind}-{kind}-{meeting.held_on.isoformat()}.pdf"'
        )
        return response
