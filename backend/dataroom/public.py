"""What the public sees, without signing in: the register, the documents on
display, a plot's zone and what it allows, an application's status, and a
form to ask for information.

Every view finds the district by its code, checks its room is open, and then
reads as that district only (row-level security does the scoping). Personal
data stays out: no contact details, and names only where the district has
chosen to show them (r.68(2)(b))."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import District
from core.tenancy import tenant_context
from enforcement import registry as enforcement_registry
from enforcement.models import Notice
from landchange import documents as land_documents
from landchange import registry as land_registry
from landchange import services as land_services
from landchange.models import Application as LandApplication
from permits import registry as permit_registry
from permits import services as permit_services
from permits.models import Application, Counter, Fee
from planmaking import registry as plan_registry
from planmaking import services as plan_services
from planmaking.models import Consultation, PlanProcess
from relations import procedures, zoning
from relations.models import DevelopmentStandard, LayerRole, ZoningScheme

from .models import DataRoom, InformationRequest, RoomDocument

ANSWER_WITHIN_DAYS = 5  # r.64(7)
Status = Application.Status
# What the register shows of an application's progress.
PUBLIC_STATUS = {
    Status.RECEIVED: "Pending",
    Status.REVIEW: "Pending",
    Status.REPORTED: "Pending",
    Status.DEFERRED: "Deferred",
    Status.GRANTED: "Granted",
    Status.ISSUED: "Permit issued",
    Status.REFUSED: "Refused",
    Status.WITHDRAWN: "Withdrawn",
}


@contextmanager
def room(code: str) -> Iterator[tuple[District, DataRoom]]:
    """The open data room with this district code, read as that district."""
    district = District.objects.filter(code__iexact=code, is_active=True).first()
    if district is None:
        raise Http404
    with tenant_context(district.pk):
        found = DataRoom.objects.filter(district=district, is_open=True).first()
        if found is None:
            raise Http404
        yield district, found


class PublicView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _locality(application: Application) -> str:
    return application.project.community or application.project.name


class RoomsView(PublicView):
    """The Assemblies whose Public Data Room is open online."""

    @extend_schema(operation_id="public_rooms_list", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        with tenant_context(None, is_system_admin=True):
            rooms = list(
                DataRoom.objects.filter(is_open=True, district__is_active=True)
                .select_related("district")
                .order_by("district__name")
            )
            body = [{"code": r.district.code, "assembly": r.district.name} for r in rooms]
        return Response(body)


@extend_schema(responses=OpenApiTypes.OBJECT)
class RoomView(PublicView):
    """One Assembly's data room: its welcome, how to reach the office, and the fees."""

    def get(self, request: Request, code: str) -> Response:
        with room(code) as (district, found):
            today = date.today()
            body = {
                "code": district.code,
                "assembly": district.name,
                "welcome": found.welcome,
                "contact": found.contact,
                "answer_within_days": ANSWER_WITHIN_DAYS,
                "fees": [
                    {
                        "label": f.label,
                        "stage": f.stage,
                        "kind": f.kind,
                        "amount": f"{f.amount:.2f}",
                    }
                    for f in Fee.objects.all()
                ],
                "documents": [
                    {
                        "id": d.pk,
                        "kind": d.kind,
                        "kind_label": d.get_kind_display(),
                        "title": d.title,
                        "description": d.description,
                        "name": d.name,
                        "size": d.size,
                        "display_from": _day(d.display_from),
                        "display_until": _day(d.display_until),
                    }
                    for d in RoomDocument.objects.filter(display_from__lte=today).filter(
                        Q(display_until__isnull=True) | Q(display_until__gte=today)
                    )
                ],
                "zoning_schemes": [
                    {
                        "name": s.name,
                        "status": s.get_status_display(),
                        "approved_on": _day(s.approved_on),
                        "effective_on": _day(s.effective_on),
                        "locality": s.project.community or s.project.name,
                    }
                    for s in ZoningScheme.objects.exclude(status=ZoningScheme.Status.DRAFT)
                    .filter(project__publication__zoning=True)
                    .select_related("project")
                ],
            }
        return Response(body)


@extend_schema(responses={200: OpenApiTypes.BINARY})
class DocumentView(PublicView):
    """A document on display in the data room."""

    def get(self, request: Request, code: str, document_id: int) -> FileResponse:
        with room(code):
            today = date.today()
            document = (
                RoomDocument.objects.filter(pk=document_id, display_from__lte=today)
                .filter(Q(display_until__isnull=True) | Q(display_until__gte=today))
                .first()
            )
            if document is None:
                raise Http404
            path = Path(settings.MEDIA_ROOT) / document.path
            if not document.path or not path.is_file():
                raise Http404
            name = document.name
        return FileResponse(open(path, "rb"), as_attachment=True, filename=name)


@extend_schema(
    parameters=[
        OpenApiParameter("q", str, description="Application number or locality"),
        OpenApiParameter(
            "status", str, description="pending, granted, issued, refused or deferred"
        ),
    ],
    responses=OpenApiTypes.OBJECT,
)
class RegisterView(PublicView):
    """The register of permits (r.67(3)): permits issued, applications
    pending, and those refused, in the projects the Assembly has published."""

    def get(self, request: Request, code: str) -> Response:
        with room(code) as (_district, found):
            qs = (
                Application.objects.filter(project__publication__permits=True)
                .exclude(status=Status.WITHDRAWN)
                .select_related("project")
            )
            q = request.query_params.get("q", "").strip()
            if q:
                qs = qs.filter(
                    Q(number__icontains=q)
                    | Q(project__community__icontains=q)
                    | Q(project__name__icontains=q)
                )
            wanted = request.query_params.get("status", "")
            groups = {
                "pending": [Status.RECEIVED, Status.REVIEW, Status.REPORTED],
                "granted": [Status.GRANTED],
                "issued": [Status.ISSUED],
                "refused": [Status.REFUSED],
                "deferred": [Status.DEFERRED],
            }
            if wanted in groups:
                qs = qs.filter(status__in=groups[wanted])
            today = date.today()
            rows = [
                {
                    "number": a.number,
                    "permit": a.get_kind_display(),
                    "for": permit_registry.CATEGORY_BY_CODE[a.category].label,
                    "proposed_use": a.proposed_use,
                    "locality": _locality(a),
                    "applicant": a.applicant_name if found.show_applicants else None,
                    "status": PUBLIC_STATUS[Status(a.status)],
                    "received_on": _day(a.received_on),
                    "decided_on": _day(a.decided_on),
                    "issued_on": _day(a.issued_on),
                    "expires_on": _day(a.expires_on),
                    "expired": bool(a.expires_on and a.expires_on < today),
                    # r.67(3)(b): the grounds, where a permit was refused.
                    "reasons": a.reasons if a.status == Status.REFUSED else "",
                }
                for a in qs[:500]
            ]
        return Response({"results": rows})


@extend_schema(
    parameters=[OpenApiParameter("number", str, required=True)], responses=OpenApiTypes.OBJECT
)
class StatusView(PublicView):
    """Where an application stands, from its number (as on the acknowledgement)."""

    def get(self, request: Request, code: str) -> Response:
        number = request.query_params.get("number", "").strip()
        with room(code):
            application = (
                Application.objects.filter(number__iexact=number).select_related("project").first()
                if number
                else None
            )
            if application is None:
                raise Http404
            due = permit_services.next_due(application)
            body = {
                "number": application.number,
                "permit": application.get_kind_display(),
                "status": PUBLIC_STATUS[Status(application.status)],
                "received_on": _day(application.received_on),
                "decided_on": _day(application.decided_on),
                "issued_on": _day(application.issued_on),
                "next_step": {"label": due["label"], "due_on": due["due_on"]} if due else None,
            }
        return Response(body)


@extend_schema(responses=OpenApiTypes.OBJECT)
class NoticesView(PublicView):
    """The enforcement notices served (r.67(3)(d)), in the projects the
    Assembly has published: what, where and when, never on whom."""

    def get(self, request: Request, code: str) -> Response:
        with room(code):
            served = (
                Notice.objects.filter(
                    served_on__isnull=False, case__project__publication__permits=True
                )
                .select_related("case", "case__project")
                .order_by("-served_on", "-id")[:300]
            )
            rows = [
                {
                    "case": n.case.number,
                    "notice": enforcement_registry.NOTICE_BY_CODE[n.kind].label,
                    "contravention": enforcement_registry.CONTRAVENTION_BY_CODE[
                        n.case.contravention
                    ][0],
                    "locality": n.case.project.community or n.case.project.name,
                    "served_on": _day(n.served_on),
                    "comply_by": _day(n.comply_by),
                    "complied_on": _day(n.complied_on),
                }
                for n in served
            ]
        return Response({"results": rows})


@extend_schema(responses=OpenApiTypes.OBJECT)
class LandApplicationsView(PublicView):
    """Applications for re-zoning, subdivision and consolidation put on
    display (L.I. 2384 r.33(5)(a), r.54(6) and (10)): what is asked for,
    until when the public may comment, and what was decided."""

    def get(self, request: Request, code: str) -> Response:
        with room(code):
            shown = [
                a
                for a in LandApplication.objects.filter(project__publication__permits=True)
                .exclude(status=LandApplication.Status.WITHDRAWN)
                .select_related("project")
                .order_by("-received_on", "-id")[:300]
                if "display" in a.steps or "advertise" in a.steps
            ]
            rows = [
                {
                    "number": a.number,
                    "kind": land_registry.KIND_BY_CODE[a.kind].label,
                    "proposal": land_documents.what(a),
                    "locality": a.project.community or a.project.name,
                    "received_on": _day(a.received_on),
                    "comments_close_on": _day(land_services.comments_close(a)),
                    "status": a.get_status_display(),
                    "decided_on": _day(a.decided_on),
                }
                for a in shown
            ]
        return Response({"results": rows})


def _plans_on_display() -> list[PlanProcess]:
    """The local plans of published projects whose making has been made public."""
    return [
        p
        for p in PlanProcess.objects.filter(project__publication__isnull=False).select_related(
            "project"
        )
        if "commence" in p.steps or "notice" in p.steps
    ]


@extend_schema(responses=OpenApiTypes.OBJECT)
class PlansView(PublicView):
    """Local plans being made (L.I. 2384 r.23, r.65): where each has got to,
    until when the public may comment on the draft, and the minutes of the
    consultations on display."""

    def get(self, request: Request, code: str) -> Response:
        with room(code):
            today = date.today()
            rows = []
            for process in _plans_on_display():
                project = process.project
                minutes = Consultation.objects.filter(project=project, displayed_on__isnull=False)
                rows.append(
                    {
                        "project": project.pk,
                        "name": project.name,
                        "locality": project.community or project.name,
                        "commenced_on": _day(plan_services.step_date(process, "commence")),
                        "draft_on_display_from": _day(plan_services.step_date(process, "notice")),
                        "comments_close_on": _day(plan_services.comments_close(process)),
                        "comments_open": plan_services.comments_open(process, today),
                        "approved_on": _day(plan_services.step_date(process, "approve")),
                        "consultations": [
                            {
                                "stage": plan_registry.STAGE_BY_CODE.get(c.stage, c.stage),
                                "held_on": _day(c.held_on),
                                "venue": c.venue,
                                "attendance": c.attendance,
                                "issues": c.issues,
                                "outcome": c.outcome,
                            }
                            for c in minutes
                        ],
                    }
                )
            body = {
                "results": rows,
                "topics": [{"code": c, "label": label} for c, label in plan_registry.CONTENT],
            }
        return Response(body)


class PublicPlanCommentSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=200)
    contact = serializers.CharField(max_length=200, required=False, allow_blank=True)
    topic = serializers.CharField(max_length=2, required=False, allow_blank=True)
    text = serializers.CharField(max_length=5000)

    def validate_topic(self, value: str) -> str:
        if value and value not in plan_registry.CONTENT_BY_CODE:
            raise serializers.ValidationError("Not an item of a local plan.")
        return value


class PlanCommentView(PublicView):
    """Sends a comment on a draft local plan (Form 59), while the sixty days
    for comments run (r.23(5))."""

    @extend_schema(request=PublicPlanCommentSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request: Request, code: str, project_id: int) -> Response:
        data = PublicPlanCommentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with room(code):
            process = next((p for p in _plans_on_display() if p.project_id == project_id), None)
            if process is None:
                raise Http404
            if not plan_services.comments_open(process):
                raise serializers.ValidationError(
                    {"detail": "This plan is not open for comments now."}
                )
            today = date.today()
            plan_services.add_comment(
                process.project,
                name=data.validated_data["name"],
                contact=data.validated_data.get("contact", ""),
                topic=data.validated_data.get("topic", ""),
                text=data.validated_data["text"],
                on=today,
                online=True,
            )
            body = {
                "received_on": _day(today),
                "comments_close_on": _day(plan_services.comments_close(process)),
            }
        return Response(body, status=status.HTTP_201_CREATED)


def _standard_json(standard: dict[str, Any]) -> dict[str, Any]:
    return {name: standard[name] for name in procedures.STANDARD_FIELDS}


@extend_schema(
    parameters=[
        OpenApiParameter("lon", float, required=True, description="Longitude (WGS 84)"),
        OpenApiParameter("lat", float, required=True, description="Latitude (WGS 84)"),
    ],
    responses=OpenApiTypes.OBJECT,
)
class ZoneView(PublicView):
    """What can I build here? The zone at a place, what it permits and
    prohibits, and the site standards the Assembly applies there."""

    def get(self, request: Request, code: str) -> Response:
        try:
            lon = float(request.query_params.get("lon", ""))
            lat = float(request.query_params.get("lat", ""))
        except ValueError as exc:
            raise serializers.ValidationError({"detail": "Give lon and lat as numbers."}) from exc
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise serializers.ValidationError({"detail": "That isn't a place on the earth."})
        with room(code) as (district, _found):
            value, source, locality = None, "", ""
            # The zoning layer first, then the parcel's land use.
            for role_code, field_default, label in (
                ("zoning", "zone", "the zoning scheme"),
                ("parcels", "land_use", "the parcel's land use"),
            ):
                roles = LayerRole.objects.filter(
                    role=role_code, project__publication__zoning=True
                ).select_related("project")
                for role in roles:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT properties FROM projects_feature WHERE layer_id = %s"
                            " AND ST_Intersects(geom_4326, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
                            " ORDER BY ST_Area(geom_4326) LIMIT 1",
                            [role.layer_id, lon, lat],
                        )
                        row = cursor.fetchone()
                    if row is None:
                        continue
                    found_value = procedures._obj(row[0]).get(
                        role.config.get("zone_field", field_default)
                    )
                    if found_value not in (None, ""):
                        value, source = found_value, label
                        locality = role.project.community or role.project.name
                        break
                if value is not None:
                    break
            if value is None:
                return Response(
                    {
                        "found": False,
                        "detail": "No zoning is published for that place. Ask at the Physical"
                        " Planning Department.",
                    }
                )
            national = zoning.match(value)
            standard = procedures.standard_for(district.pk, str(value))
            adopted = DevelopmentStandard.objects.filter(pk=standard["id"]).exists()
            body = {
                "found": True,
                "zone": str(value),
                "from": source,
                "locality": locality,
                "code": national.code if national else None,
                "name": national.name if national else str(value),
                "colour": national.colour if national else None,
                "permitted": list(national.permitted) if national else [],
                "prohibited": list(national.prohibited) if national else [],
                # The Assembly's own standard for the zone, where it has set one.
                "standard": _standard_json(standard) if adopted and standard["zone"] else None,
                "note": "Every development needs a permit from the Assembly before work starts."
                " This is guidance: the Spatial Planning Committee decides each application.",
            }
        return Response(body)


class RequestSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(max_length=5000)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("phone") and not attrs.get("email"):
            raise serializers.ValidationError(
                {"phone": "Give a phone number or an email address, so the office can answer."}
            )
        return attrs


def due_on(received: date) -> date:
    return received + timedelta(days=ANSWER_WITHIN_DAYS)


@extend_schema(request=RequestSerializer, responses={201: OpenApiTypes.OBJECT})
class RequestsView(PublicView):
    """Asks the data room for information (Form 55). The Assembly answers
    within five days (r.64(7))."""

    def post(self, request: Request, code: str) -> Response:
        data = RequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with room(code) as (district, _found):
            today = date.today()
            with transaction.atomic():
                counter, _ = Counter.objects.select_for_update().get_or_create(
                    district=district, kind="info", year=today.year
                )
                counter.last += 1
                counter.save(update_fields=["last"])
            made = InformationRequest.objects.create(
                district=district,
                reference=f"{district.code}/IR/{today.year}/{counter.last:04d}",
                received_on=today,
                **data.validated_data,
            )
            body = {
                "reference": made.reference,
                "received_on": _day(made.received_on),
                "answer_due_on": _day(due_on(made.received_on)),
            }
        return Response(body, status=status.HTTP_201_CREATED)
