from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, has_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from projects.models import PlanProject

from . import documents, registry, services
from .models import Consultation, PlanComment, PlanProcess

HIDDEN = "restricted"


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "message_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": exc.messages})


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _project(request: Request, project_id: int) -> PlanProject:
    return get_object_or_404(
        PlanProject.objects.select_related("district"),
        pk=project_id,
        district_id=require_district_id(request),
    )


def consultation_json(c: Consultation) -> dict[str, Any]:
    return {
        "id": c.pk,
        "stage": c.stage,
        "stage_label": registry.STAGE_BY_CODE.get(c.stage, c.stage),
        "held_on": _day(c.held_on),
        "venue": c.venue,
        "groups": c.groups,
        "attendance": c.attendance,
        "issues": c.issues,
        "outcome": c.outcome,
        "displayed_on": _day(c.displayed_on),
    }


def comment_json(c: PlanComment, personal: bool) -> dict[str, Any]:
    return {
        "id": c.pk,
        "name": c.name if personal else HIDDEN,
        "contact": c.contact if personal else HIDDEN,
        "topic": c.topic,
        "topic_label": registry.CONTENT_BY_CODE.get(c.topic, ""),
        "text": c.text,
        "received_on": _day(c.received_on),
        "online": c.online,
        "response": c.response,
        "responded_on": _day(c.responded_on),
    }


def process_json(process: PlanProcess, request: Request) -> dict[str, Any]:
    project = process.project
    today = date.today()
    items = services.content(process)
    comments = list(project.plan_comments.all())
    personal = has_permission(request, "data.sensitive")
    return {
        "project": project.pk,
        "origin": process.origin,
        "origin_label": process.get_origin_display(),
        "prepared_by": process.prepared_by,
        "structure_plan_on": _day(process.structure_plan_on),
        "application_on": _day(process.application_on),
        "conditions": process.conditions,
        "valid_until": _day(process.valid_until),
        "clocks": services.clocks(process, today),
        "next_step": services.next_due(process, today),
        "comment_days": registry.COMMENT_DAYS,
        "comment_rule": registry.COMMENT_RULE,
        "comments_close_on": _day(services.comments_close(process)),
        "comments_open": services.comments_open(process, today),
        "content": items,
        "content_rule": registry.CONTENT_RULE,
        "content_covered": sum(1 for i in items if i["covered"]),
        "possible_conditions": list(registry.CONDITIONS),
        "stages": [{"code": c, "label": label} for c, label in registry.STAGES],
        "consultations": [consultation_json(c) for c in project.consultations.all()],
        "comments": [comment_json(c, personal) for c in comments],
        "comments_unanswered": sum(1 for c in comments if not c.response),
        "papers": [
            {"code": code, "label": label}
            for code, label in documents.PAPERS.items()
            if code != "publish_approval" or "approve" in process.steps
        ],
    }


class PlanSettingsSerializer(serializers.Serializer[Any]):
    origin = serializers.CharField(max_length=10, required=False)
    prepared_by = serializers.CharField(max_length=200, required=False, allow_blank=True)
    structure_plan_on = serializers.DateField(required=False, allow_null=True)
    application_on = serializers.DateField(required=False, allow_null=True)
    conditions = serializers.CharField(required=False, allow_blank=True)
    valid_until = serializers.DateField(required=False, allow_null=True)

    def validate_origin(self, value: str) -> str:
        if value not in PlanProcess.Origin.values:
            raise serializers.ValidationError("committee or applicant.")
        return value


class PlanStepSerializer(serializers.Serializer[Any]):
    step = serializers.CharField(max_length=24)
    on = serializers.DateField(required=False, help_text="Default: today")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class PlanContentSerializer(serializers.Serializer[Any]):
    items = serializers.DictField(child=serializers.DictField())


class ConsultationWriteSerializer(serializers.Serializer[Any]):
    stage = serializers.CharField(max_length=8)
    held_on = serializers.DateField()
    venue = serializers.CharField(max_length=200)
    groups = serializers.CharField(required=False, allow_blank=True)
    attendance = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    issues = serializers.CharField()
    outcome = serializers.CharField(required=False, allow_blank=True)

    def validate_stage(self, value: str) -> str:
        if value not in registry.STAGE_BY_CODE:
            raise serializers.ValidationError("before or draft.")
        return value

    def validate_held_on(self, value: date) -> date:
        if value > date.today():
            raise serializers.ValidationError("That date is in the future.")
        return value


class PlanCommentWriteSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=200)
    contact = serializers.CharField(max_length=200, required=False, allow_blank=True)
    topic = serializers.CharField(max_length=2, required=False, allow_blank=True)
    text = serializers.CharField(max_length=5000)
    on = serializers.DateField(required=False, help_text="Received on. Default: today")


class PlanReplySerializer(serializers.Serializer[Any]):
    response = serializers.CharField()


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class PlanProcessView(APIView):
    """The making of a project's local plan (L.I. 2384 r.23-27): GET the
    steps with their dates, what the plan covers, the consultations and the
    comments; PATCH what the Assembly knows about it."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view" if self.request.method == "GET" else "project.edit")

    def get(self, request: Request, project_id: int) -> Response:
        return Response(process_json(services.process_of(_project(request, project_id)), request))

    @extend_schema(request=PlanSettingsSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request: Request, project_id: int) -> Response:
        process = services.process_of(_project(request, project_id))
        data = PlanSettingsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        for name, value in data.validated_data.items():
            setattr(process, name, value)
        process.updated_by = request_user(request)
        process.save()
        return Response(process_json(process, request))


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class PlanStepView(APIView):
    """Records that a step was taken, and when. The approval and the
    confirmation are recorded by those who may decide."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PlanStepSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, project_id: int) -> Response:
        data = PlanStepSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        step = registry.STEP_BY_CODE.get(values["step"])
        needed = "permit.decide" if step is not None and step.decision else "project.edit"
        if not has_permission(request, needed):
            self.permission_denied(request)
        process = services.process_of(_project(request, project_id))
        try:
            services.record_step(
                process,
                values["step"],
                values.get("on") or date.today(),
                values.get("note", ""),
                request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response(process_json(process, request))


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class PlanContentView(APIView):
    """Marks which items of r.24(1) the plan covers."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.edit")

    @extend_schema(request=PlanContentSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, project_id: int) -> Response:
        data = PlanContentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        process = services.process_of(_project(request, project_id))
        try:
            services.set_content(process, data.validated_data["items"], request_user(request))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response(process_json(process, request))


@extend_schema(parameters=[DISTRICT_HEADER])
class PlanPaperView(APIView):
    """A notice of the plan's making, as a PDF."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view")

    @extend_schema(
        parameters=[
            OpenApiParameter("kind", str, description="commence, notice, publish_approval")
        ],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request, project_id: int) -> HttpResponse:
        process = services.process_of(_project(request, project_id))
        kind = request.query_params.get("kind", "notice")
        if kind not in documents.PAPERS or (
            kind == "publish_approval" and "approve" not in process.steps
        ):
            raise serializers.ValidationError({"kind": "Not a paper of this plan yet."})
        response = HttpResponse(documents.paper_pdf(process, kind), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{kind}-plan-{project_id}.pdf"'
        return response


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class ConsultationsView(APIView):
    """Records a consultation and its minutes (r.65(2))."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.edit")

    @extend_schema(request=ConsultationWriteSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, project_id: int) -> Response:
        project = _project(request, project_id)
        data = ConsultationWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        Consultation.objects.create(
            district_id=project.district_id,
            project=project,
            recorded_by=request_user(request),
            **data.validated_data,
        )
        return Response(
            process_json(services.process_of(project), request), status=status.HTTP_201_CREATED
        )


def _consultation(request: Request, consultation_id: int) -> Consultation:
    return get_object_or_404(
        Consultation.objects.select_related("project", "project__district"),
        pk=consultation_id,
        district_id=require_district_id(request),
    )


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class ConsultationDisplayView(APIView):
    """r.65(3): the minutes are displayed in the Public Data Room from today."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.edit")

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, consultation_id: int) -> Response:
        consultation = _consultation(request, consultation_id)
        if consultation.displayed_on is None:
            consultation.displayed_on = date.today()
            consultation.save(update_fields=["displayed_on"])
        return Response(process_json(services.process_of(consultation.project), request))


@extend_schema(parameters=[DISTRICT_HEADER])
class ConsultationMinutesView(APIView):
    """The minutes of a consultation, as a PDF."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view")

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request: Request, consultation_id: int) -> HttpResponse:
        consultation = _consultation(request, consultation_id)
        response = HttpResponse(documents.minutes_pdf(consultation), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="minutes-{consultation.held_on.isoformat()}.pdf"'
        )
        return response


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class PlanCommentsView(APIView):
    """Records a comment on the draft received at the office (Form 59)."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.edit")

    @extend_schema(request=PlanCommentWriteSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, project_id: int) -> Response:
        project = _project(request, project_id)
        data = PlanCommentWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            services.add_comment(
                project,
                name=values["name"],
                contact=values.get("contact", ""),
                topic=values.get("topic", ""),
                text=values["text"],
                on=values.get("on") or date.today(),
                online=False,
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response(
            process_json(services.process_of(project), request), status=status.HTTP_201_CREATED
        )


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class PlanCommentReplyView(APIView):
    """The Committee's response to a comment."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.edit")

    @extend_schema(request=PlanReplySerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, comment_id: int) -> Response:
        comment = get_object_or_404(
            PlanComment.objects.select_related("project", "project__district"),
            pk=comment_id,
            district_id=require_district_id(request),
        )
        data = PlanReplySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        comment.response = data.validated_data["response"]
        comment.responded_on = date.today()
        comment.save(update_fields=["response", "responded_on"])
        return Response(process_json(services.process_of(comment.project), request))
