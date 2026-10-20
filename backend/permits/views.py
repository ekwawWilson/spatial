from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, QuerySet
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, has_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from core.tenancy import tenant_context
from core.throttling import UploadThrottle
from crs.models import CoordinateSystem
from crs.services import transform_geojson
from projects.models import Feature, PlanProject

from . import checks, documents, registry, services
from .models import Application, Challenge, Comment, Document, Fee, Inspection

MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
Status = Application.Status


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "message_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": exc.messages})


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _money(value: Any) -> str | None:
    return None if value is None else f"{value:.2f}"


def application_json(application: Application, request: Request, *, full: bool) -> dict[str, Any]:
    personal = has_permission(request, "data.sensitive")
    today = date.today()
    due = services.next_due(application, today)
    out: dict[str, Any] = {
        "id": application.pk,
        "project": application.project_id,
        "number": application.number,
        "kind": application.kind,
        "category": application.category,
        "category_label": registry.CATEGORY_BY_CODE[application.category].label,
        "status": application.status,
        "status_label": application.get_status_display(),
        "applicant_name": application.applicant_name,
        "proposed_use": application.proposed_use,
        "proposed_floors": application.proposed_floors,
        "site": application.site_id,
        "received_on": _day(application.received_on),
        "decided_on": _day(application.decided_on),
        "issued_on": _day(application.issued_on),
        "expires_on": _day(application.expires_on),
        "expired": bool(application.expires_on and application.expires_on < today),
        "habitation_on": _day(application.habitation_on),
        "next_due": due,
        "check_counts": (application.checks or {}).get("counts"),
    }
    if not full:
        return out
    hidden = None if personal else "restricted"
    out.update(
        {
            "applicant_phone": application.applicant_phone if personal else hidden,
            "applicant_email": application.applicant_email if personal else hidden,
            "applicant_address": application.applicant_address if personal else hidden,
            "description": application.description,
            "acknowledged_on": _day(application.acknowledged_on),
            "inspected_on": _day(application.inspected_on),
            "reported_on": _day(application.reported_on),
            "clocks": services.clocks(application, today),
            "completion": services.completion(application, today),
            "requirements": services.required_documents(application),
            "extra_requirements": application.extra_requirements,
            "documents": [
                {
                    "id": d.pk,
                    "requirement": d.requirement,
                    "name": d.name,
                    "size": d.size,
                    "uploaded_at": d.uploaded_at.isoformat(),
                }
                for d in application.documents.all()
            ],
            "comments": [
                {
                    "id": c.pk,
                    "agency": c.agency,
                    "body": c.body,
                    "objection": c.objection,
                    "recorded_by": c.recorded_by.email if c.recorded_by else None,
                    "recorded_at": c.recorded_at.isoformat(),
                }
                for c in application.comments.select_related("recorded_by")
            ],
            "inspections": [
                {
                    "id": i.pk,
                    "purpose": i.purpose,
                    "inspected_on": _day(i.inspected_on),
                    "findings": i.findings,
                    "summary": i.summary,
                    "inspected_by": i.inspected_by.email if i.inspected_by else None,
                }
                for i in application.inspections.select_related("inspected_by")
            ],
            "checks": application.checks or None,
            "checked_at": application.checked_at.isoformat() if application.checked_at else None,
            "recommendation": application.recommendation,
            "report": application.report,
            "reasons": application.reasons,
            "conditions": application.conditions,
            "processing_fee": _money(application.processing_fee),
            "processing_receipt": application.processing_receipt,
            "processing_paid_on": _day(application.processing_paid_on),
            "permit_fee": _money(application.permit_fee),
            "permit_receipt": application.permit_receipt,
            "permit_paid_on": _day(application.permit_paid_on),
            "verify_url": documents.verify_url(application) if application.token else None,
            "challenges": [
                {
                    "id": c.pk,
                    "kind": c.kind,
                    "kind_label": c.get_kind_display(),
                    "form": registry.CHALLENGE_FORMS[c.kind][0],
                    "rule": registry.CHALLENGE_FORMS[c.kind][1],
                    "body": c.body,
                    "body_label": dict(registry.CHALLENGE_BODIES[c.kind]).get(c.body, c.body),
                    "lodged_on": _day(c.lodged_on),
                    "grounds": c.grounds,
                    "decided_on": _day(c.decided_on),
                    "outcome": c.outcome,
                    "outcome_label": c.get_outcome_display() if c.outcome else "",
                    "decision": c.decision,
                    "clock": services.challenge_clock(c),
                }
                for c in application.challenges.all()
            ],
            "events": [
                {
                    "kind": e.kind,
                    "on": _day(e.on),
                    "note": e.note,
                    "by": e.by.email if e.by else None,
                }
                for e in application.events.select_related("by")
            ],
        }
    )
    return out


# --- What the Regulations fix --------------------------------------------------------------------


@extend_schema(responses=OpenApiTypes.OBJECT)
class RegistryView(APIView):
    """Permit categories, the documents an application carries, the statutory
    deadlines and the points of a site inspection."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "categories": [
                    {"code": c.code, "label": c.label, "kind": c.kind} for c in registry.CATEGORIES
                ],
                "requirements": [
                    {"code": r.code, "label": r.label, "applies": list(r.applies), "rule": r.rule}
                    for r in registry.REQUIREMENTS
                ],
                "clocks": [
                    {"code": c.code, "label": c.label, "days": c.days, "rule": c.rule}
                    for c in registry.CLOCKS
                ],
                "inspection_points": [
                    {"code": code, "label": label} for code, label in registry.INSPECTION_POINTS
                ],
                "considerations": list(registry.CONSIDERATIONS),
                "permit_valid_years": registry.PERMIT_VALID_YEARS,
            }
        )


# --- Applications --------------------------------------------------------------------------------


class ApplicationWriteSerializer(serializers.Serializer[Any]):
    project = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=Application.Kind.choices)
    category = serializers.CharField(max_length=20)
    applicant_name = serializers.CharField(max_length=200)
    applicant_phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    applicant_email = serializers.EmailField(required=False, allow_blank=True)
    applicant_address = serializers.CharField(max_length=300, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    proposed_use = serializers.CharField(max_length=200, required=False, allow_blank=True)
    proposed_floors = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=200
    )
    received_on = serializers.DateField(required=False)
    extra_requirements = serializers.ListField(
        child=serializers.CharField(max_length=30), required=False
    )
    site_geometry = serializers.JSONField(required=False, help_text="GeoJSON, in site_crs")
    site_crs = serializers.CharField(
        max_length=64, required=False, allow_blank=True, help_text="Default: the project's CRS"
    )
    site_feature = serializers.IntegerField(
        required=False, help_text="Use this feature's shape (e.g. a parcel) as the site"
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        category = attrs.get("category")
        if category is not None:
            known = registry.CATEGORY_BY_CODE.get(category)
            kind = attrs.get("kind") or getattr(self.instance, "kind", None)
            if known is None:
                raise serializers.ValidationError({"category": "Not a category of permit."})
            if kind is not None and known.kind != kind:
                raise serializers.ValidationError(
                    {"category": f"{known.label} needs a {known.kind} permit."}
                )
        extra = attrs.get("extra_requirements")
        if extra is not None:
            unknown = [c for c in extra if c not in registry.REQUIREMENT_BY_CODE]
            if unknown:
                raise serializers.ValidationError(
                    {"extra_requirements": f"Unknown: {', '.join(unknown)}."}
                )
        received = attrs.get("received_on")
        if received is not None and received > date.today():
            raise serializers.ValidationError({"received_on": "That date is in the future."})
        return attrs


class DatedSerializer(serializers.Serializer[Any]):
    on = serializers.DateField(required=False, help_text="Default: today")


class InspectionSerializer(DatedSerializer):
    purpose = serializers.ChoiceField(
        choices=Inspection.Purpose.choices, default=Inspection.Purpose.APPLICATION
    )
    findings = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False)
    summary = serializers.CharField(required=False, allow_blank=True)


class ReportSerializer(DatedSerializer):
    recommendation = serializers.ChoiceField(choices=Application.Recommendation.choices)
    report = serializers.CharField(required=False, allow_blank=True)


class PermitDecisionSerializer(DatedSerializer):
    decision = serializers.ChoiceField(choices=Application.Recommendation.choices)
    reasons = serializers.CharField(required=False, allow_blank=True)
    conditions = serializers.CharField(required=False, allow_blank=True)


class FeesSerializer(serializers.Serializer[Any]):
    stage = serializers.ChoiceField(choices=[("processing", "Processing"), ("permit", "Permit")])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    receipt = serializers.CharField(max_length=60)
    paid_on = serializers.DateField(required=False)


class CommentSerializer(serializers.Serializer[Any]):
    agency = serializers.CharField(max_length=120)
    body = serializers.CharField()
    objection = serializers.BooleanField(default=False)


class DocumentUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField()
    requirement = serializers.CharField(max_length=30, required=False, allow_blank=True)


class NoteSerializer(serializers.Serializer[Any]):
    note = serializers.CharField(required=False, allow_blank=True)


class LodgeSerializer(DatedSerializer):
    kind = serializers.ChoiceField(choices=Challenge.Kind.choices)
    body = serializers.CharField(max_length=8)
    grounds = serializers.CharField()


class ChallengeDecisionSerializer(DatedSerializer):
    challenge = serializers.IntegerField()
    outcome = serializers.ChoiceField(choices=Challenge.Outcome.choices)
    decision = serializers.CharField(required=False, allow_blank=True)


class RenewSerializer(DatedSerializer):
    note = serializers.CharField(required=False, allow_blank=True)


@extend_schema(parameters=[DISTRICT_HEADER])
class ApplicationViewSet(viewsets.GenericViewSet[Application]):
    """Planning and development permit applications (L.I. 2384 r.43-46): from
    receipt, through the Technical Sub-Committee's checks and inspection and the
    Spatial Planning Committee's decision, to the certificate."""

    queryset = Application.objects.none()
    serializer_class = ApplicationWriteSerializer
    parser_classes = [JSONParser, MultiPartParser]
    PERMISSIONS = {
        "list": "permit.view",
        "retrieve": "permit.view",
        "acknowledgement": "permit.view",
        "letter": "permit.view",
        "certificate": "permit.view",
        "habitation_certificate": "permit.view",
        "land_use_certificate": "permit.view",
        "habitation": "permit.decide",
        "inspect": "permit.inspect",
        "decide": "permit.decide",
        "issue": "permit.decide",
        "decide_challenge": "permit.decide",
        "renew": "permit.decide",
    }

    def get_permissions(self) -> list[BasePermission]:
        return _perms(self.PERMISSIONS.get(self.action or "", "permit.process"))

    def get_throttles(self) -> list[Any]:
        throttles = super().get_throttles()
        return [*throttles, UploadThrottle()] if self.action == "documents" else throttles

    def get_queryset(self) -> QuerySet[Application]:
        return Application.objects.filter(district_id=require_district_id(self.request))

    def _answer(self, application: Application, code: int = status.HTTP_200_OK) -> Response:
        application.refresh_from_db()
        return Response(application_json(application, self.request, full=True), status=code)

    def _on(self, data: dict[str, Any]) -> date:
        day: date = data.get("on") or date.today()
        return day

    @extend_schema(
        parameters=[
            OpenApiParameter("project", int),
            OpenApiParameter("status", str),
            OpenApiParameter("q", str, description="Application number or applicant"),
            OpenApiParameter("overdue", bool, description="Only those with a deadline passed"),
        ],
        responses=OpenApiTypes.OBJECT,
        operation_id="permits_applications_list",
    )
    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        params = request.query_params
        if params.get("project", "").isdigit():
            qs = qs.filter(project_id=int(params["project"]))
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("q"):
            qs = qs.filter(
                Q(number__icontains=params["q"]) | Q(applicant_name__icontains=params["q"])
            )
        rows = [application_json(a, request, full=False) for a in qs[:500]]
        if params.get("overdue") in ("true", "1"):
            rows = [r for r in rows if r["next_due"] and r["next_due"]["overdue"]]
        open_rows = [r for r in rows if r["status"] in services.OPEN]
        return Response(
            {
                "results": rows,
                "summary": {
                    "total": len(rows),
                    "open": len(open_rows),
                    "overdue": sum(
                        1 for r in open_rows if r["next_due"] and r["next_due"]["overdue"]
                    ),
                    "by_status": {
                        code: sum(1 for r in rows if r["status"] == code)
                        for code, _ in Status.choices
                    },
                },
            }
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(application_json(self.get_object(), request, full=True))

    def _site(self, application: Application, values: dict[str, Any]) -> None:
        user = request_user(self.request)
        try:
            if "site_feature" in values:
                source = get_object_or_404(
                    Feature.objects.select_related("layer", "layer__crs"),
                    pk=values["site_feature"],
                    layer__project_id=application.project_id,
                )
                services.site_from_feature(application, source, user)
            elif values.get("site_geometry") is not None:
                geometry = values["site_geometry"]
                layer = services.permits_layer(application.project, user)
                code = (values.get("site_crs") or "").strip().upper()
                if code and code != layer.crs.code:
                    source_crs = CoordinateSystem.objects.filter(code=code, is_active=True).first()
                    if source_crs is None:
                        raise serializers.ValidationError(
                            {"site_crs": f"Unknown coordinate system {code!r}."}
                        )
                    geometry, _ = transform_geojson(geometry, source_crs, layer.crs)
                services.set_site(application, geometry, user)
        except DjangoValidationError as exc:
            raise _drf(exc) from exc

    @extend_schema(request=ApplicationWriteSerializer, responses={201: OpenApiTypes.OBJECT})
    def create(self, request: Request) -> Response:
        """Receives an application: it gets its number (r.44(7)(b)) and the
        statutory deadlines start from the day it was received."""
        data = ApplicationWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        district_id = require_district_id(request)
        project = get_object_or_404(
            PlanProject.objects.select_related("district"),
            pk=values["project"],
            district_id=district_id,
        )
        user = request_user(request)
        received = values.get("received_on") or date.today()
        application = Application.objects.create(
            district_id=district_id,
            project=project,
            number=services.next_number(
                district_id, project.district.code, values["kind"], received.year
            ),
            kind=values["kind"],
            category=values["category"],
            applicant_name=values["applicant_name"],
            applicant_phone=values.get("applicant_phone", ""),
            applicant_email=values.get("applicant_email", ""),
            applicant_address=values.get("applicant_address", ""),
            description=values.get("description", ""),
            proposed_use=values.get("proposed_use", ""),
            proposed_floors=values.get("proposed_floors"),
            extra_requirements=values.get("extra_requirements", []),
            received_on=received,
            created_by=user,
        )
        services.event(application, "received", received, user)
        self._site(application, values)
        checks.run(application)
        return self._answer(application, status.HTTP_201_CREATED)

    @extend_schema(request=ApplicationWriteSerializer, responses=OpenApiTypes.OBJECT)
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        """Corrects the application's details or its site while it is open."""
        application = self.get_object()
        if application.status not in services.OPEN:
            raise serializers.ValidationError("This application is closed: it can't be changed.")
        data = ApplicationWriteSerializer(application, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        for name in ("project", "kind", "received_on"):
            if name in values:
                raise serializers.ValidationError({name: "This can't be changed once received."})
        changed = []
        for name in (
            "category",
            "applicant_name",
            "applicant_phone",
            "applicant_email",
            "applicant_address",
            "description",
            "proposed_use",
            "proposed_floors",
            "extra_requirements",
        ):
            if name in values:
                setattr(application, name, values[name])
                changed.append(name)
        if changed:
            application.save(update_fields=[*changed, "updated_at"])
        self._site(application, values)
        services.sync_site(application, request_user(request))
        checks.run(application)
        return self._answer(application)

    # --- Steps -------------------------------------------------------------------------------

    def _step(
        self, request: Request, serializer: type[serializers.Serializer[Any]]
    ) -> tuple[Application, dict[str, Any]]:
        data = serializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.get_object(), data.validated_data

    @extend_schema(request=DatedSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request: Request, pk: str | None = None) -> Response:
        """r.44(6): receipt acknowledged in writing, within 7 days."""
        application, values = self._step(request, DatedSerializer)
        try:
            services.acknowledge(application, self._on(values), request_user(request))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def check(self, request: Request, pk: str | None = None) -> Response:
        """Runs the automatic zoning checks again (r.44(7)(a))."""
        application = self.get_object()
        checks.run(application)
        return self._answer(application)

    @extend_schema(request=InspectionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def inspect(self, request: Request, pk: str | None = None) -> Response:
        """r.44(7)(f): records the site inspection, point by point."""
        application, values = self._step(request, InspectionSerializer)
        try:
            services.inspect(
                application,
                self._on(values),
                values.get("findings", {}),
                values.get("summary", ""),
                request_user(request),
                values["purpose"],
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=CommentSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def comments(self, request: Request, pk: str | None = None) -> Response:
        """r.44(7)(d): what a department or agency said about the application."""
        application, values = self._step(request, CommentSerializer)
        Comment.objects.create(
            district_id=application.district_id,
            application=application,
            recorded_by=request_user(request),
            **values,
        )
        return self._answer(application, status.HTTP_201_CREATED)

    @extend_schema(request=ReportSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def report(self, request: Request, pk: str | None = None) -> Response:
        """r.44(8): the Technical Sub-Committee's report and recommendation."""
        application, values = self._step(request, ReportSerializer)
        try:
            services.submit_report(
                application,
                values["recommendation"],
                values.get("report", ""),
                self._on(values),
                request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=PermitDecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        """r.44(9): the Spatial Planning Committee's decision."""
        application, values = self._step(request, PermitDecisionSerializer)
        try:
            services.decide(
                application,
                values["decision"],
                values.get("reasons", ""),
                values.get("conditions", ""),
                self._on(values),
                request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=FeesSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def fees(self, request: Request, pk: str | None = None) -> Response:
        """Records a receipt: the processing fee (r.44(5)) or, once granted, the
        permit fee (r.44(11))."""
        application, values = self._step(request, FeesSerializer)
        stage = values["stage"]
        if stage == "permit" and application.status != Status.GRANTED:
            raise serializers.ValidationError(
                "The permit fee is paid once the application is granted (r.44(11))."
            )
        paid_on = values.get("paid_on") or date.today()
        if paid_on > date.today():
            raise serializers.ValidationError({"paid_on": "That date is in the future."})
        setattr(application, f"{stage}_fee", values["amount"])
        setattr(application, f"{stage}_receipt", values["receipt"])
        setattr(application, f"{stage}_paid_on", paid_on)
        application.save(
            update_fields=[f"{stage}_fee", f"{stage}_receipt", f"{stage}_paid_on", "updated_at"]
        )
        services.event(
            application, f"{stage}_fee_paid", paid_on, request_user(request), values["receipt"]
        )
        return self._answer(application)

    @extend_schema(request=DatedSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def issue(self, request: Request, pk: str | None = None) -> Response:
        """r.44(10): issues the certificate, within 30 days of receipt."""
        application, values = self._step(request, DatedSerializer)
        try:
            services.issue(application, self._on(values), request_user(request))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=DatedSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def habitation(self, request: Request, pk: str | None = None) -> Response:
        """r.45(15)-(18): issues the Certificate of Habitation, within 14 days
        of the inspection of the completed development."""
        application, values = self._step(request, DatedSerializer)
        try:
            services.certify_habitation(application, self._on(values), request_user(request))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=LodgeSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def challenge(self, request: Request, pk: str | None = None) -> Response:
        """r.62-63: a request for review (Form 53) or an appeal (Form 54) against the decision."""
        application, values = self._step(request, LodgeSerializer)
        try:
            services.lodge(
                application,
                values["kind"],
                values["body"],
                self._on(values),
                values["grounds"],
                request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=ChallengeDecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="decide-challenge")
    def decide_challenge(self, request: Request, pk: str | None = None) -> Response:
        """The decision on a review or appeal, served within 21 days (r.62(3), r.63(8))."""
        application, values = self._step(request, ChallengeDecisionSerializer)
        challenge = get_object_or_404(Challenge, pk=values["challenge"], application=application)
        try:
            services.decide_challenge(
                challenge,
                self._on(values),
                values["outcome"],
                values.get("decision", ""),
                request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=RenewSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def renew(self, request: Request, pk: str | None = None) -> Response:
        """Renews an issued permit for another five years."""
        application, values = self._step(request, RenewSerializer)
        try:
            services.renew(
                application, self._on(values), request_user(request), values.get("note", "")
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    @extend_schema(request=NoteSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def withdraw(self, request: Request, pk: str | None = None) -> Response:
        application, values = self._step(request, NoteSerializer)
        try:
            services.withdraw(application, values.get("note", ""), request_user(request))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(application)

    # --- Documents ---------------------------------------------------------------------------

    @extend_schema(
        request={"multipart/form-data": DocumentUploadSerializer},
        responses={201: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def documents(self, request: Request, pk: str | None = None) -> Response:
        """Adds a submitted document, against the requirement it meets."""
        application = self.get_object()
        data = DocumentUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        requirement = data.validated_data.get("requirement", "")
        if requirement and requirement not in registry.REQUIREMENT_BY_CODE:
            raise serializers.ValidationError({"requirement": "Not a kind of document."})
        if upload.size > MAX_DOCUMENT_BYTES:
            raise serializers.ValidationError({"file": "Documents are limited to 50 MB."})
        name = Path(upload.name).name or "document"
        document = Document.objects.create(
            district_id=application.district_id,
            application=application,
            requirement=requirement,
            name=name,
            path="",
            size=upload.size,
            uploaded_by=request_user(request),
        )
        relative = Path("permits") / str(application.district_id) / f"{document.pk}-{name}"
        target = Path(settings.MEDIA_ROOT) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        document.path = str(relative)
        document.save(update_fields=["path"])
        return self._answer(application, status.HTTP_201_CREATED)

    # --- Papers ------------------------------------------------------------------------------

    def _pdf(self, data: bytes, name: str) -> HttpResponse:
        response = HttpResponse(data, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{name}.pdf"'
        return response

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def acknowledgement(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The written acknowledgement of receipt, with the dates that follow."""
        application = self.get_object()
        stem = application.number.replace("/", "-")
        return self._pdf(documents.acknowledgement(application), f"acknowledgement-{stem}")

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def letter(self, request: Request, pk: str | None = None) -> HttpResponse:
        """r.44(13): the letter giving the reasons for a refusal or deferral."""
        application = self.get_object()
        if application.status not in (Status.REFUSED, Status.DEFERRED):
            raise Http404("Only refused or deferred applications have this letter.")
        stem = application.number.replace("/", "-")
        return self._pdf(documents.decision_letter(application), f"decision-{stem}")

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def certificate(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The permit certificate, with its QR code."""
        application = self.get_object()
        if application.status != Status.ISSUED:
            raise Http404("The permit hasn't been issued.")
        stem = application.number.replace("/", "-")
        return self._pdf(documents.certificate(application), f"permit-{stem}")

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="habitation-certificate")
    def habitation_certificate(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The Certificate of Habitation (Form 43E)."""
        application = self.get_object()
        if application.habitation_on is None:
            raise Http404("The Certificate of Habitation hasn't been issued.")
        stem = application.number.replace("/", "-")
        return self._pdf(documents.habitation_certificate(application), f"habitation-{stem}")

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="land-use-certificate")
    def land_use_certificate(self, request: Request, pk: str | None = None) -> HttpResponse:
        """A Land Use Certificate for the site (Form 43F; r.46): its zone, from
        the approved plan on the map."""
        application = self.get_object()
        # As found by the last check (checks run whenever the site or details change).
        zone = (application.checks or {}).get("zone") or {}
        if not zone.get("value"):
            raise serializers.ValidationError(
                "The site isn't in a zone on the map: put the site on the map, and say which"
                " layer holds the zoning (or the parcels with their land use)."
            )
        stem = application.number.replace("/", "-")
        return self._pdf(documents.land_use_certificate(application, zone), f"land-use-{stem}")


@extend_schema(parameters=[DISTRICT_HEADER])
class DocumentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet[Document]):
    """An application's documents: download or remove."""

    queryset = Document.objects.none()
    serializer_class = DocumentUploadSerializer

    def get_permissions(self) -> list[BasePermission]:
        return _perms("permit.view" if self.action == "download" else "permit.process")

    def get_queryset(self) -> QuerySet[Document]:
        return Document.objects.filter(district_id=require_district_id(self.request))

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        document = self.get_object()
        path = Path(settings.MEDIA_ROOT) / document.path
        if not document.path or not path.is_file():
            raise Http404("The file is missing.")
        return FileResponse(open(path, "rb"), as_attachment=True, filename=document.name)

    def perform_destroy(self, instance: Document) -> None:
        path = Path(settings.MEDIA_ROOT) / instance.path
        instance.delete()
        if instance.path and path.is_file():
            path.unlink()


# --- Fees ----------------------------------------------------------------------------------------


class FeeSerializer(serializers.ModelSerializer[Fee]):
    class Meta:
        model = Fee
        fields = ["id", "stage", "kind", "category", "label", "amount", "updated_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        current = self.instance if isinstance(self.instance, Fee) else None
        stage = attrs.get("stage", current.stage if current else None)
        kind = attrs.get("kind", current.kind if current else None)
        category = attrs.get("category", current.category if current else "")
        if stage not in ("processing", "permit"):
            raise serializers.ValidationError({"stage": "processing or permit."})
        if kind not in Application.Kind.values:
            raise serializers.ValidationError({"kind": "planning or development."})
        if category:
            known = registry.CATEGORY_BY_CODE.get(category)
            if known is None or known.kind != kind:
                raise serializers.ValidationError({"category": "Not a category of that permit."})
        amount = attrs.get("amount")
        if amount is not None and amount < 0:
            raise serializers.ValidationError({"amount": "Can't be negative."})
        return attrs


@extend_schema(parameters=[DISTRICT_HEADER])
class FeeViewSet(viewsets.ModelViewSet[Fee]):
    """The lines of the Assembly's fee-fixing resolution that permits use: a
    processing fee and a permit fee per kind of permit, or per category."""

    serializer_class = FeeSerializer
    queryset = Fee.objects.none()
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        safe = self.request.method in ("GET", "HEAD", "OPTIONS")
        return _perms("permit.view" if safe else "permit.settings")

    def get_queryset(self) -> QuerySet[Fee]:
        return Fee.objects.filter(district_id=require_district_id(self.request))

    def perform_create(self, serializer: Any) -> None:
        district_id = require_district_id(self.request)
        values = serializer.validated_data
        if Fee.objects.filter(
            district_id=district_id,
            stage=values["stage"],
            kind=values["kind"],
            category=values.get("category", ""),
        ).exists():
            raise serializers.ValidationError("There is already a fee for that line.")
        serializer.save(district_id=district_id)


# --- Anyone: is this certificate genuine? --------------------------------------------------------


@extend_schema(responses=OpenApiTypes.OBJECT)
class VerifyView(APIView):
    """Checks a permit certificate against the Assembly's record, from the
    code in its QR. Open to anyone holding the certificate: no sign-in."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request: Request, token: str) -> Response:
        if len(token) < 20:
            raise Http404
        # The token names one permit of one district: looked up across districts.
        with tenant_context(None, is_system_admin=True):
            application = (
                Application.objects.filter(token=token, status=Status.ISSUED)
                .select_related("project", "project__district")
                .first()
            )
            if application is None:
                raise Http404
            today = date.today()
            body = {
                "assembly": application.project.district.name,
                "number": application.number,
                "permit": application.get_kind_display(),
                "for": registry.CATEGORY_BY_CODE[application.category].label,
                "applicant": application.applicant_name,
                "locality": application.project.community or application.project.name,
                "proposed_use": application.proposed_use,
                "issued_on": _day(application.issued_on),
                "expires_on": _day(application.expires_on),
                "valid": bool(application.expires_on and application.expires_on >= today),
            }
        return Response(body)
