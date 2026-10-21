from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, has_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from projects.models import PlanProject
from work.people import officer_json

from . import documents, drawing, registry, services
from .models import Application, Comment

HIDDEN = "restricted"


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "message_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": exc.messages})


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def comment_json(comment: Comment, personal: bool) -> dict[str, Any]:
    return {
        "id": comment.pk,
        "kind": comment.kind,
        "kind_label": registry.COMMENT_KIND_BY_CODE.get(comment.kind, comment.kind),
        "name": comment.name if personal else HIDDEN,
        "contact": comment.contact if personal else HIDDEN,
        "text": comment.text,
        "received_on": _day(comment.received_on),
        "response": comment.response,
        "responded_on": _day(comment.responded_on),
    }


def application_json(application: Application, request: Request, *, full: bool) -> dict[str, Any]:
    spec = registry.KIND_BY_CODE[application.kind]
    today = date.today()
    out: dict[str, Any] = {
        "id": application.pk,
        "project": application.project_id,
        "number": application.number,
        "kind": application.kind,
        "kind_label": spec.label,
        "applicant_name": application.applicant_name,
        "summary": documents.what(application) if full else "",
        "status": application.status,
        "status_label": application.get_status_display(),
        "received_on": _day(application.received_on),
        "decided_on": _day(application.decided_on),
        "comments_close_on": _day(services.comments_close(application)),
        "next_step": services.next_due(application, today),
        "officer": officer_json(application.officer),
    }
    if not full:
        return out
    personal = has_permission(request, "data.sensitive")
    abutting = services.abutting(application)
    if not personal:
        abutting = [{**a, "owner": HIDDEN if a["owner"] else ""} for a in abutting]
    out.update(
        {
            "form": spec.form,
            "rule": spec.rule,
            "applicant_phone": application.applicant_phone if personal else HIDDEN,
            "applicant_email": application.applicant_email if personal else HIDDEN,
            "applicant_address": application.applicant_address if personal else HIDDEN,
            "description": application.description,
            "parcels": services.parcels(application),
            "abutting": abutting,
            "current_zone": application.current_zone,
            "proposed_zone": application.proposed_zone,
            "ground": application.ground,
            "circumstance": application.circumstance,
            "current_use": application.current_use,
            "proposed_use": application.proposed_use,
            "lots": application.lots,
            "zone": services.zone_of(application),
            "assessment": application.assessment,
            "clocks": services.clocks(application, today),
            "comment_rule": spec.comment_rule,
            "comments": [comment_json(c, personal) for c in application.comments.all()],
            "deferred_on": _day(application.deferred_on),
            "defer_reason": application.defer_reason,
            "conditions": application.conditions,
            "reasons": application.reasons,
            "applied_on": _day(application.applied_on),
            "papers": [
                {"code": code, "label": label}
                for code, label in documents.PAPERS.items()
                if _paper_applies(application, code)
            ],
        }
    )
    return out


def _paper_applies(application: Application, paper: str) -> bool:
    decided = application.status in (Application.Status.APPROVED, Application.Status.REFUSED)
    if paper == "notice":
        return application.kind != "change_of_use"
    if paper == "abutting":
        return application.kind == "rezoning"
    if paper == "decision":
        return decided
    return (
        application.kind in ("subdivision", "consolidation")
        and application.status == Application.Status.APPROVED
    )


@extend_schema(responses=OpenApiTypes.OBJECT)
class RegistryView(APIView):
    """The kinds of application, the steps of each with the days the
    Regulations give, the grounds for re-zoning and the tests of r.34."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "kinds": [
                    {
                        "code": k.code,
                        "label": k.label,
                        "form": k.form,
                        "rule": k.rule,
                        "comment_days": k.comment_days,
                        "decide_days": k.decide_days,
                        "decide_rule": k.decide_rule,
                        "steps": [
                            {
                                "code": s.code,
                                "label": s.label,
                                "rule": s.rule,
                                "days": s.days,
                                "after": s.after,
                                "when": s.when,
                            }
                            for s in k.steps
                        ],
                    }
                    for k in registry.KINDS
                ],
                "grounds": [{"code": c, "label": label} for c, label in registry.GROUNDS],
                "circumstances": [
                    {"code": c, "label": label} for c, label in registry.CIRCUMSTANCES
                ],
                "use_tests": [
                    {"code": c, "label": label, "rule": rule}
                    for c, label, rule in registry.USE_TESTS
                ],
                "comment_kinds": [
                    {"code": c, "label": label} for c, label in registry.COMMENT_KINDS
                ],
                "deferred_decision_days": registry.DEFERRED_DECISION_DAYS,
            }
        )


class LandApplicationWriteSerializer(serializers.Serializer[Any]):
    project = serializers.IntegerField()
    kind = serializers.CharField(max_length=14)
    applicant_name = serializers.CharField(max_length=200)
    applicant_phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    applicant_email = serializers.EmailField(required=False, allow_blank=True)
    applicant_address = serializers.CharField(max_length=300, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    parcels = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False, max_length=200
    )
    current_zone = serializers.CharField(max_length=80, required=False, allow_blank=True)
    proposed_zone = serializers.CharField(max_length=80, required=False, allow_blank=True)
    ground = serializers.CharField(max_length=16, required=False, allow_blank=True)
    circumstance = serializers.CharField(max_length=20, required=False, allow_blank=True)
    current_use = serializers.CharField(max_length=120, required=False, allow_blank=True)
    proposed_use = serializers.CharField(max_length=120, required=False, allow_blank=True)
    lots = serializers.IntegerField(min_value=2, max_value=5000, required=False, allow_null=True)
    received_on = serializers.DateField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind = attrs["kind"]
        if kind not in registry.KIND_BY_CODE:
            raise serializers.ValidationError({"kind": "Not a kind of application."})
        received = attrs.get("received_on")
        if received is not None and received > date.today():
            raise serializers.ValidationError({"received_on": "That date is in the future."})
        if kind == "rezoning":
            if not attrs.get("proposed_zone"):
                raise serializers.ValidationError({"proposed_zone": "Name the zone asked for."})
            # r.33(2): the application states which of the two it is.
            if attrs.get("ground") not in dict(registry.GROUNDS):
                raise serializers.ValidationError(
                    {"ground": "To comply with the structure plan, or a special circumstance?"}
                )
            if attrs["ground"] == "special" and attrs.get("circumstance") not in dict(
                registry.CIRCUMSTANCES
            ):
                raise serializers.ValidationError(
                    {"circumstance": "Say which special circumstance."}
                )
        if kind == "change_of_use" and not attrs.get("proposed_use"):
            raise serializers.ValidationError({"proposed_use": "Name the use asked for."})
        if kind == "consolidation" and len(set(attrs["parcels"])) < 2:
            raise serializers.ValidationError(
                {"parcels": "A consolidation joins two parcels or more."}
            )
        return attrs


class LandStepSerializer(serializers.Serializer[Any]):
    step = serializers.CharField(max_length=20)
    on = serializers.DateField(required=False, help_text="Default: today")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class LandCommentSerializer(serializers.Serializer[Any]):
    kind = serializers.CharField(max_length=16)
    name = serializers.CharField(max_length=200)
    contact = serializers.CharField(max_length=200, required=False, allow_blank=True)
    text = serializers.CharField()
    on = serializers.DateField(required=False, help_text="Received on. Default: today")


class LandResponseSerializer(serializers.Serializer[Any]):
    comment = serializers.IntegerField()
    response = serializers.CharField()
    on = serializers.DateField(required=False, help_text="Default: today")


class LandAssessmentSerializer(serializers.Serializer[Any]):
    answers = serializers.DictField(child=serializers.DictField())


class LandDeferSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField()
    on = serializers.DateField(required=False, help_text="Default: today")


class LandDecisionSerializer(serializers.Serializer[Any]):
    approve = serializers.BooleanField()
    conditions = serializers.CharField(required=False, allow_blank=True)
    reasons = serializers.CharField(required=False, allow_blank=True)
    on = serializers.DateField(required=False, help_text="Default: today")


@extend_schema(parameters=[DISTRICT_HEADER])
class LandApplicationViewSet(viewsets.GenericViewSet[Application]):
    """Applications for re-zoning (L.I. 2384 r.33), change of use (r.34) and
    the subdivision or consolidation of land (r.54): the steps taken, the
    comments received and the decision."""

    queryset = Application.objects.none()
    serializer_class = LandApplicationWriteSerializer
    PERMISSIONS = {
        "list": "permit.view",
        "retrieve": "permit.view",
        "paper": "permit.view",
        "decide": "permit.decide",
        "defer": "permit.decide",
        "apply": "permit.decide",
        "draw": "permit.process",
    }

    def get_permissions(self) -> list[BasePermission]:
        return _perms(self.PERMISSIONS.get(self.action or "", "permit.process"))

    def get_queryset(self) -> QuerySet[Application]:
        return Application.objects.filter(
            district_id=require_district_id(self.request)
        ).select_related("project", "project__district", "project__crs", "officer")

    def _answer(self, application: Application, code: int = status.HTTP_200_OK) -> Response:
        application.refresh_from_db()
        return Response(application_json(application, self.request, full=True), status=code)

    @extend_schema(
        parameters=[
            OpenApiParameter("project", int),
            OpenApiParameter("status", str),
            OpenApiParameter("kind", str),
        ],
        responses=OpenApiTypes.OBJECT,
        operation_id="land_applications_list",
    )
    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        params = request.query_params
        if params.get("project", "").isdigit():
            qs = qs.filter(project_id=int(params["project"]))
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        rows = [
            application_json(a, request, full=False) for a in qs.prefetch_related("comments")[:500]
        ]
        waiting = [r for r in rows if r["next_step"]]
        return Response(
            {
                "results": rows,
                "summary": {
                    "total": len(rows),
                    "open": sum(1 for r in rows if r["status"] in services.OPEN),
                    "overdue": sum(1 for r in waiting if r["next_step"]["overdue"]),
                },
            }
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(application_json(self.get_object(), request, full=True))

    @extend_schema(request=LandApplicationWriteSerializer, responses={201: OpenApiTypes.OBJECT})
    def create(self, request: Request) -> Response:
        """Receives an application: it gets its number, and the Regulations'
        days run from the day it was received."""
        data = LandApplicationWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        district_id = require_district_id(request)
        project = get_object_or_404(
            PlanProject.objects.select_related("district"),
            pk=values["project"],
            district_id=district_id,
        )
        try:
            parcels = services.check_parcels(project, values["parcels"])
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        received = values.get("received_on") or date.today()
        application = Application.objects.create(
            district_id=district_id,
            project=project,
            number=services.next_number(
                district_id, project.district.code, values["kind"], received.year
            ),
            kind=values["kind"],
            applicant_name=values["applicant_name"],
            applicant_phone=values.get("applicant_phone", ""),
            applicant_email=values.get("applicant_email", ""),
            applicant_address=values.get("applicant_address", ""),
            description=values.get("description", ""),
            parcels=parcels,
            current_zone=values.get("current_zone", ""),
            proposed_zone=values.get("proposed_zone", ""),
            ground=values.get("ground", ""),
            circumstance=values.get("circumstance", ""),
            current_use=values.get("current_use", ""),
            proposed_use=values.get("proposed_use", ""),
            lots=values.get("lots"),
            received_on=received,
            created_by=request_user(request),
        )
        if application.kind == "rezoning" and not application.current_zone:
            # The zone the map gives the land now.
            application.current_zone = services.zone_of(application)["value"]
            application.save(update_fields=["current_zone"])
        return self._answer(application, status.HTTP_201_CREATED)

    @extend_schema(request=LandStepSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def step(self, request: Request, pk: str | None = None) -> Response:
        """Records that a step was taken, and when."""
        application = self.get_object()
        data = LandStepSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            services.record_step(
                application,
                values["step"],
                values.get("on") or date.today(),
                values.get("note", ""),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=LandCommentSerializer, responses={201: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"])
    def comments(self, request: Request, pk: str | None = None) -> Response:
        """A comment, objection or representation received (Form 59)."""
        application = self.get_object()
        data = LandCommentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            services.add_comment(
                application,
                kind=values["kind"],
                name=values["name"],
                contact=values.get("contact", ""),
                text=values["text"],
                on=values.get("on") or date.today(),
                user=request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application, status.HTTP_201_CREATED)

    @extend_schema(request=LandResponseSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def respond(self, request: Request, pk: str | None = None) -> Response:
        """What the applicant said in reply to a comment or objection."""
        application = self.get_object()
        data = LandResponseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        comment = get_object_or_404(Comment, pk=values["comment"], application=application)
        comment.response = values["response"]
        comment.responded_on = values.get("on") or date.today()
        comment.save(update_fields=["response", "responded_on"])
        return self._answer(application)

    @extend_schema(request=LandAssessmentSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def assess(self, request: Request, pk: str | None = None) -> Response:
        """A change of use against the tests of r.34."""
        application = self.get_object()
        data = LandAssessmentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.assess(application, data.validated_data["answers"])
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=LandDeferSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def defer(self, request: Request, pk: str | None = None) -> Response:
        """r.33(16)-(17): defers the decision; it is then due in thirty days."""
        application = self.get_object()
        data = LandDeferSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            services.defer(application, values.get("on") or date.today(), values["reason"])
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=LandDecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        application = self.get_object()
        data = LandDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            services.decide(
                application,
                approve=values["approve"],
                on=values.get("on") or date.today(),
                conditions=values.get("conditions", ""),
                reasons=values.get("reasons", ""),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def withdraw(self, request: Request, pk: str | None = None) -> Response:
        application = self.get_object()
        try:
            services.withdraw(application)
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def apply(self, request: Request, pk: str | None = None) -> Response:
        """Writes an approved re-zoning to the map: the new zone on each parcel."""
        application = self.get_object()
        try:
            written = services.apply_zone(application, request_user(request))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        application.refresh_from_db()
        return Response(
            {"written": written, "application": application_json(application, request, full=True)}
        )

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def draw(self, request: Request, pk: str | None = None) -> Response:
        """Draws an approved subdivision (equal plots across the parcel's
        long side) or consolidation (the parcels joined) in the layer
        "Approved subdivisions"."""
        application = self.get_object()
        try:
            drawn = drawing.draw(application, request_user(request))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response(drawn)

    @extend_schema(
        parameters=[OpenApiParameter("kind", str, description="notice, abutting, decision, lands")],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def paper(self, request: Request, pk: str | None = None) -> HttpResponse:
        """One of the application's papers, as a PDF."""
        application = self.get_object()
        kind = request.query_params.get("kind", "notice")
        if kind not in documents.PAPERS or not _paper_applies(application, kind):
            raise serializers.ValidationError({"kind": "Not a paper of this application yet."})
        response = HttpResponse(
            documents.paper_pdf(application, kind), content_type="application/pdf"
        )
        name = application.number.replace("/", "-")
        response["Content-Disposition"] = f'attachment; filename="{kind}-{name}.pdf"'
        return response
