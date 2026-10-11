from datetime import date
from decimal import Decimal
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
from imagery.models import Imagery
from permits.models import Application
from projects.models import Feature, PlanProject

from . import documents, registry, services
from .models import Case, DetectionRun, Notice


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "message_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": exc.messages})


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def notice_json(notice: Notice, today: date) -> dict[str, Any]:
    spec = registry.NOTICE_BY_CODE[notice.kind]
    return {
        "id": notice.pk,
        "kind": notice.kind,
        "label": spec.label,
        "form": spec.form,
        "rule": spec.rule,
        "grounds": notice.grounds,
        "required": notice.required,
        "issued_on": _day(notice.issued_on),
        "comply_by": _day(notice.comply_by),
        "served_on": _day(notice.served_on),
        "served_by": notice.served_by,
        "served_by_label": registry.SERVICE_BY_CODE.get(notice.served_by, ""),
        "served_note": notice.served_note,
        "complied_on": _day(notice.complied_on),
        "dates": services.notice_dates(notice, today),
    }


def case_json(case: Case, request: Request, *, full: bool) -> dict[str, Any]:
    personal = has_permission(request, "data.sensitive")
    today = date.today()
    label, section = registry.CONTRAVENTION_BY_CODE[case.contravention]
    out: dict[str, Any] = {
        "id": case.pk,
        "project": case.project_id,
        "number": case.number,
        "origin": case.origin,
        "origin_label": case.get_origin_display(),
        "contravention": case.contravention,
        "contravention_label": label,
        "section": section,
        "description": case.description,
        "status": case.status,
        "status_label": case.get_status_display(),
        "feature": case.feature_id,
        "permit": case.permit_id,
        "permit_number": case.permit.number if case.permit else None,
        "opened_on": _day(case.opened_on),
        "closed_on": _day(case.closed_on),
        "next_action": services.next_action(case, today),
    }
    if not full:
        return out
    hidden = "restricted"
    out.update(
        {
            "owner_name": case.owner_name if personal else hidden,
            "owner_address": case.owner_address if personal else hidden,
            "owner_contact": case.owner_contact if personal else hidden,
            "outcome": case.outcome,
            "cost": None if case.cost is None else f"{case.cost:.2f}",
            "cost_recovered": None if case.cost_recovered is None else f"{case.cost_recovered:.2f}",
            "opened_by": case.opened_by.email if case.opened_by else None,
            "notices": [notice_json(n, today) for n in case.notices.all()],
        }
    )
    return out


@extend_schema(responses=OpenApiTypes.OBJECT)
class RegistryView(APIView):
    """The contraventions, the notices and their forms, the ways a notice may
    be served, and the days between steps."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "contraventions": [
                    {"code": code, "label": label, "section": section}
                    for code, label, section in registry.CONTRAVENTIONS
                ],
                "notices": [
                    {
                        "code": n.code,
                        "label": n.label,
                        "form": n.form,
                        "rule": n.rule,
                        "dated": n.dated,
                    }
                    for n in registry.NOTICES
                ],
                "service_methods": [
                    {"code": code, "label": label} for code, label in registry.SERVICE_METHODS
                ],
                "days": {
                    "enforcement_after": registry.ENFORCEMENT_AFTER_DAYS,
                    "act_after": registry.ACT_AFTER_DAYS,
                    "entry_notice": registry.ENTRY_NOTICE_DAYS,
                    "show_cause": registry.SHOW_CAUSE_DAYS,
                },
            }
        )


class CaseWriteSerializer(serializers.Serializer[Any]):
    project = serializers.IntegerField()
    origin = serializers.ChoiceField(choices=Case.Origin.choices, default=Case.Origin.INSPECTION)
    contravention = serializers.CharField(max_length=20)
    description = serializers.CharField(required=False, allow_blank=True)
    feature = serializers.IntegerField(required=False, allow_null=True)
    permit = serializers.IntegerField(required=False, allow_null=True)
    owner_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    owner_address = serializers.CharField(max_length=300, required=False, allow_blank=True)
    owner_contact = serializers.CharField(max_length=120, required=False, allow_blank=True)
    opened_on = serializers.DateField(required=False)

    def validate_contravention(self, value: str) -> str:
        if value not in registry.CONTRAVENTION_BY_CODE:
            raise serializers.ValidationError("Not a kind of contravention.")
        return value

    def validate_opened_on(self, value: date) -> date:
        if value > date.today():
            raise serializers.ValidationError("That date is in the future.")
        return value


class NoticeWriteSerializer(serializers.Serializer[Any]):
    kind = serializers.CharField(max_length=14)
    grounds = serializers.CharField()
    required = serializers.CharField(required=False, allow_blank=True)
    comply_by = serializers.DateField(required=False, allow_null=True)
    on = serializers.DateField(required=False, help_text="Issued on. Default: today")


class ServeSerializer(serializers.Serializer[Any]):
    method = serializers.CharField(max_length=16)
    on = serializers.DateField(required=False, help_text="Default: today")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class CloseSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[
            (Case.Status.RECTIFIED, "Rectified by the owner"),
            (Case.Status.ENFORCED, "Rectified by the Assembly"),
            (Case.Status.DROPPED, "No contravention found"),
        ]
    )
    outcome = serializers.CharField(required=False, allow_blank=True)
    cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    cost_recovered = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    on = serializers.DateField(required=False, help_text="Default: today")


@extend_schema(parameters=[DISTRICT_HEADER])
class CaseViewSet(viewsets.GenericViewSet[Case]):
    """Enforcement cases (Act 925 s.160-167; L.I. 2384 r.55-58): a
    contravention, the notices served for it, and how it ended."""

    queryset = Case.objects.none()
    serializer_class = CaseWriteSerializer
    PERMISSIONS = {
        "list": "enforcement.view",
        "retrieve": "enforcement.view",
        "create": "enforcement.open",
    }

    def get_permissions(self) -> list[BasePermission]:
        return _perms(self.PERMISSIONS.get(self.action or "", "enforcement.act"))

    def get_queryset(self) -> QuerySet[Case]:
        return Case.objects.filter(district_id=require_district_id(self.request)).select_related(
            "permit", "opened_by"
        )

    def _answer(self, case: Case, code: int = status.HTTP_200_OK) -> Response:
        case.refresh_from_db()
        return Response(case_json(case, self.request, full=True), status=code)

    @extend_schema(
        parameters=[OpenApiParameter("project", int), OpenApiParameter("status", str)],
        responses=OpenApiTypes.OBJECT,
    )
    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        params = request.query_params
        if params.get("project", "").isdigit():
            qs = qs.filter(project_id=int(params["project"]))
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        rows = [case_json(c, request, full=False) for c in qs.prefetch_related("notices")[:500]]
        open_rows = [r for r in rows if r["next_action"]]
        return Response(
            {
                "results": rows,
                "summary": {
                    "total": len(rows),
                    "open": len(open_rows),
                    "overdue": sum(1 for r in open_rows if r["next_action"]["overdue"]),
                },
            }
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(case_json(self.get_object(), request, full=True))

    def _links(self, project: PlanProject, values: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if values.get("feature") is not None:
            out["feature"] = get_object_or_404(
                Feature, pk=values["feature"], layer__project_id=project.pk
            )
        elif "feature" in values:
            out["feature"] = None
        if values.get("permit") is not None:
            out["permit"] = get_object_or_404(
                Application, pk=values["permit"], project_id=project.pk
            )
        elif "permit" in values:
            out["permit"] = None
        return out

    @extend_schema(request=CaseWriteSerializer, responses={201: OpenApiTypes.OBJECT})
    def create(self, request: Request) -> Response:
        data = CaseWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        district_id = require_district_id(request)
        project = get_object_or_404(
            PlanProject.objects.select_related("district"),
            pk=values["project"],
            district_id=district_id,
        )
        opened = values.get("opened_on") or date.today()
        user = request_user(request)
        case = Case.objects.create(
            district_id=district_id,
            project=project,
            number=services.next_number(district_id, project.district.code, opened.year),
            origin=values["origin"],
            contravention=values["contravention"],
            description=values.get("description", ""),
            owner_name=values.get("owner_name", ""),
            owner_address=values.get("owner_address", ""),
            owner_contact=values.get("owner_contact", ""),
            opened_on=opened,
            opened_by=user,
            **self._links(project, values),
        )
        # A change found between images now carries its case number on the map.
        feature = case.feature
        if feature is not None and feature.layer.name == services.DETECTIONS_LAYER:
            feature.properties = {**feature.properties, "case_no": case.number}
            feature.save(update_fields=["properties"])
        return self._answer(case, status.HTTP_201_CREATED)

    @extend_schema(request=CaseWriteSerializer, responses=OpenApiTypes.OBJECT)
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        case = self.get_object()
        if case.status not in services.OPEN:
            raise serializers.ValidationError("This case is closed: it can't be changed.")
        data = CaseWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if "project" in values or "opened_on" in values:
            raise serializers.ValidationError("The project and the opening date can't be changed.")
        changed = []
        for name in (
            "contravention",
            "description",
            "owner_name",
            "owner_address",
            "owner_contact",
        ):
            if name in values:
                setattr(case, name, values[name])
                changed.append(name)
        for name, value in self._links(case.project, values).items():
            setattr(case, name, value)
            changed.append(name)
        if changed:
            case.save(update_fields=[*changed, "updated_at"])
        return self._answer(case)

    @extend_schema(request=NoticeWriteSerializer, responses={201: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"])
    def notices(self, request: Request, pk: str | None = None) -> Response:
        """Issues a notice in the case: a stop notice (Form 48A), a notice to
        rectify (49), an enforcement notice (47), and the others of r.55."""
        case = self.get_object()
        data = NoticeWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            services.issue_notice(
                case,
                values["kind"],
                values["grounds"],
                values.get("required", ""),
                values.get("comply_by"),
                values.get("on") or date.today(),
                request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(case, status.HTTP_201_CREATED)

    @extend_schema(request=CloseSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def close(self, request: Request, pk: str | None = None) -> Response:
        """Ends the case: rectified by the owner; rectified by the Assembly at
        a cost to be recovered (r.57(4)); or no contravention found."""
        case = self.get_object()
        data = CloseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            services.close(
                case,
                values["status"],
                values.get("outcome", ""),
                values.get("cost"),
                values.get("cost_recovered"),
                values.get("on") or date.today(),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return self._answer(case)


@extend_schema(parameters=[DISTRICT_HEADER])
class NoticeViewSet(viewsets.GenericViewSet[Notice]):
    """A notice: record how it was served and whether it was complied with,
    and download it to serve."""

    queryset = Notice.objects.none()
    serializer_class = ServeSerializer

    def get_permissions(self) -> list[BasePermission]:
        return _perms("enforcement.view" if self.action == "paper" else "enforcement.act")

    def get_queryset(self) -> QuerySet[Notice]:
        return Notice.objects.filter(district_id=require_district_id(self.request)).select_related(
            "case", "case__project", "case__project__district", "case__permit"
        )

    @extend_schema(request=ServeSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def serve(self, request: Request, pk: str | None = None) -> Response:
        """r.56: how and when the notice was served."""
        notice = self.get_object()
        data = ServeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            services.serve(
                notice, values.get("on") or date.today(), values["method"], values.get("note", "")
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response(case_json(notice.case, request, full=True))

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def complied(self, request: Request, pk: str | None = None) -> Response:
        """The notice has been complied with (today)."""
        notice = self.get_object()
        if notice.complied_on is None:
            notice.complied_on = date.today()
            notice.save(update_fields=["complied_on"])
        return Response(case_json(notice.case, request, full=True))

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def paper(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The notice as a PDF, worded after the Schedule's form."""
        notice = self.get_object()
        response = HttpResponse(documents.notice_pdf(notice), content_type="application/pdf")
        stem = f"{notice.kind}-{notice.case.number.replace('/', '-')}"
        response["Content-Disposition"] = f'attachment; filename="{stem}.pdf"'
        return response


class DetectSerializer(serializers.Serializer[Any]):
    before = serializers.IntegerField(help_text="The earlier orthophoto")
    after = serializers.IntegerField(help_text="The later orthophoto")


def run_json(run: DetectionRun) -> dict[str, Any]:
    return {
        "id": run.pk,
        "before": run.before.name if run.before else None,
        "after": run.after.name if run.after else None,
        "layer": run.layer_id,
        "found": run.found,
        "summary": run.summary,
        "kinds": services.KINDS,
        "at": run.at.isoformat(),
        "started_by": run.started_by.email if run.started_by else None,
    }


@extend_schema(parameters=[DISTRICT_HEADER])
class DetectionView(APIView):
    """Compares two of the project's orthophotos for changes on the ground:
    places to look for development without a permit. GET lists past runs."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("enforcement.view" if self.request.method == "GET" else "enforcement.act")

    def _project(self, request: Request, project_id: int) -> PlanProject:
        return get_object_or_404(
            PlanProject, pk=project_id, district_id=require_district_id(request)
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, project_id: int) -> Response:
        project = self._project(request, project_id)
        runs = DetectionRun.objects.filter(project=project).select_related(
            "before", "after", "started_by"
        )[:50]
        return Response({"results": [run_json(run) for run in runs]})

    @extend_schema(request=DetectSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request: Request, project_id: int) -> Response:
        project = self._project(request, project_id)
        data = DetectSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        images = Imagery.objects.filter(project=project)
        before = get_object_or_404(images, pk=data.validated_data["before"])
        after = get_object_or_404(images, pk=data.validated_data["after"])
        try:
            run = services.detect(project, before, after, request_user(request))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response(run_json(run), status=status.HTTP_201_CREATED)
