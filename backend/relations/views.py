import calendar
from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from projects import privacy
from projects.models import Feature, Layer, PlanProject
from projects.styles import DEFAULT_SYMBOL, validate_style

from . import procedures, services, zoning
from .models import DevelopmentStandard, LayerRole, Relationship, Run, ZoningScheme
from .registry import (
    LINK_TYPES,
    PROCEDURES,
    ROLE_BY_CODE,
    ROLES,
    TYPE_BY_CODE,
)


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


def _project(request: Request, project_id: int) -> PlanProject:
    return get_object_or_404(PlanProject, pk=project_id, district_id=require_district_id(request))


def run_json(run: Run | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.pk,
        "trigger": run.trigger,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "started_by": run.started_by.email if run.started_by else None,
        "report": run.report,
        "summary": run.summary,
        "error": run.error.split("\n", 1)[0] if run.error else "",
    }


@extend_schema(responses=OpenApiTypes.OBJECT)
class RegistryView(APIView):
    """The roles layers can play, the kinds of link, and the procedures, in run order."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "roles": [
                    {
                        "code": r.code,
                        "label": r.label,
                        "domain": r.domain,
                        "geometry": list(r.geometry),
                        "fields": [
                            {"key": key, "label": label, "default": default}
                            for key, label, default in r.fields
                        ],
                    }
                    for r in ROLES
                ],
                "link_types": [
                    {
                        "code": t.code,
                        "subject": t.subject,
                        "verb": t.verb,
                        "object": t.object,
                        "inverse": t.inverse,
                        "procedure": t.procedure,
                    }
                    for t in LINK_TYPES
                ],
                "procedures": [{"code": code, "does": does} for code, does in PROCEDURES],
                "defaults": {
                    "located_on_max_m": procedures.LOCATED_ON_MAX_M,
                    "access_max_m": procedures.ACCESS_MAX_M,
                    "drain_max_m": procedures.DRAIN_MAX_M,
                    "catchment_m": procedures.CATCHMENT_M,
                    "need_match_m": procedures.NEED_MATCH_M,
                    "standard": procedures.PLATFORM_STANDARD,
                },
            }
        )


class RoleSerializer(serializers.Serializer[Any]):
    # Plain text, checked below: as a choice field it would need its own name
    # in the API schema beside the staff "role" list.
    role = serializers.CharField(max_length=20)
    layer = serializers.IntegerField(allow_null=True)
    config = serializers.JSONField(required=False)

    def validate_role(self, value: str) -> str:
        if value not in ROLE_BY_CODE:
            raise serializers.ValidationError(f"Unknown part {value!r}.")
        return value


class RolesSerializer(serializers.Serializer[Any]):
    roles = RoleSerializer(many=True)


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class LayerRolesView(APIView):
    """Which layer of the project plays each part. GET also suggests layers
    for the parts not set yet. PUT sets them (a null layer clears a part)."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view" if self.request.method == "GET" else "relations.edit")

    def _body(self, project: PlanProject) -> dict[str, Any]:
        current = {r.role: r for r in LayerRole.objects.filter(project=project)}
        suggested = services.suggest_roles(project)
        return {
            "roles": [
                {
                    "role": role.code,
                    "layer": current[role.code].layer_id if role.code in current else None,
                    "config": current[role.code].config if role.code in current else {},
                    "suggested": None if role.code in current else suggested.get(role.code),
                }
                for role in ROLES
            ]
        }

    def get(self, request: Request, project_id: int) -> Response:
        return Response(self._body(_project(request, project_id)))

    @extend_schema(request=RolesSerializer)
    def put(self, request: Request, project_id: int) -> Response:
        project = _project(request, project_id)
        data = RolesSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        layers = {layer.pk: layer for layer in project.layers.all()}
        errors: dict[str, str] = {}
        for row in data.validated_data["roles"]:
            role = ROLE_BY_CODE[row["role"]]
            layer_id = row["layer"]
            if layer_id is None:
                continue
            layer: Layer | None = layers.get(layer_id)
            if layer is None:
                errors[role.code] = "Pick a layer of this project."
            elif layer.geometry_type not in role.geometry:
                errors[role.code] = (
                    f"{role.label} needs a {' or '.join(role.geometry)} layer;"
                    f" {layer.name} is a {layer.geometry_type} layer."
                )
            config = row.get("config", {})
            if not isinstance(config, dict):
                errors[role.code] = "The settings must be an object."
        if errors:
            raise serializers.ValidationError(errors)
        with transaction.atomic():
            for row in data.validated_data["roles"]:
                if row["layer"] is None:
                    # Delete one by one, so the role cache is told.
                    for existing in LayerRole.objects.filter(project=project, role=row["role"]):
                        existing.delete()
                    continue
                LayerRole.objects.update_or_create(
                    project=project,
                    role=row["role"],
                    defaults={
                        "district_id": project.district_id,
                        "layer_id": row["layer"],
                        "config": row.get("config", {}),
                    },
                )
        return Response(self._body(project))


@extend_schema(parameters=[DISTRICT_HEADER], request=None, responses=OpenApiTypes.OBJECT)
class RunView(APIView):
    """GET: the latest run and its totals. POST: run every procedure now."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view" if self.request.method == "GET" else "relations.edit")

    def get(self, request: Request, project_id: int) -> Response:
        project = _project(request, project_id)
        latest = Run.objects.filter(project=project).select_related("started_by").first()
        done = Run.objects.filter(project=project, status=Run.Status.DONE).first()
        return Response({"latest": run_json(latest), "summary": done.summary if done else None})

    def post(self, request: Request, project_id: int) -> Response:
        project = _project(request, project_id)
        if not LayerRole.objects.filter(project=project).exists():
            raise serializers.ValidationError(
                {"detail": "First say which layers hold the properties, streets and so on."}
            )
        run = services.run_project(project, Run.Trigger.MANUAL, request_user(request))
        return Response(run_json(run), status=status.HTTP_201_CREATED)


def link_json(link: Relationship, labels: dict[int, tuple[str, str]]) -> dict[str, Any]:
    kind = TYPE_BY_CODE.get(link.type)

    def side(feature_id: int | None) -> dict[str, Any] | None:
        if feature_id is None:
            return None
        layer_name, label = labels.get(feature_id, ("", f"#{feature_id}"))
        return {"feature": feature_id, "layer": layer_name, "label": label}

    return {
        "id": link.pk,
        "type": link.type,
        "verb": kind.verb if kind else link.type,
        "inverse": kind.inverse if kind else link.type,
        "subject": side(link.subject_id),
        "object": side(link.object_id),
        "rule": link.rule,
        "method": link.method,
        "status": link.status,
        "confidence": link.confidence,
        "details": link.details,
        "decided_by": link.decided_by.email if link.decided_by else None,
        "decided_at": link.decided_at.isoformat() if link.decided_at else None,
        "note": link.note,
        "created_at": link.created_at.isoformat(),
    }


def labels_for(links: list[Relationship], project_ids: set[int]) -> dict[int, tuple[str, str]]:
    """(layer name, label) for every feature the links mention."""
    ids = {link.subject_id for link in links} | {
        link.object_id for link in links if link.object_id is not None
    }
    config_of: dict[int, dict[str, Any]] = {}
    for role in LayerRole.objects.filter(project_id__in=project_ids):
        config_of.setdefault(role.layer_id, {}).update(role.config or {})
        # A role's default field names count too.
        for key, _label, default in ROLE_BY_CODE[role.role].fields:
            config_of[role.layer_id].setdefault(key, default)
    result: dict[int, tuple[str, str]] = {}
    features = Feature.objects.filter(pk__in=ids).select_related("layer")
    for feature in features:
        config = config_of.get(feature.layer_id, {})
        # A restricted value (an owner's name) must not become a label.
        visible = privacy.redact(feature.properties, privacy.hidden_fields(feature.layer))
        result[feature.pk] = (feature.layer.name, services.label_of(feature.pk, visible, config))
    return result


class DecisionSerializer(serializers.Serializer[Any]):
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ManualLinkSerializer(serializers.Serializer[Any]):
    type = serializers.ChoiceField(choices=[t.code for t in LINK_TYPES if t.object])
    subject = serializers.IntegerField()
    object = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


@extend_schema(parameters=[DISTRICT_HEADER])
class RelationshipViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet[Relationship]
):
    """Links between features. Filter with ?project=, ?type=, ?method=,
    ?status= and ?feature= (links from or to one feature)."""

    queryset = Relationship.objects.none()
    serializer_class = ManualLinkSerializer

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view" if self.action == "list" else "relations.edit")

    def get_queryset(self) -> QuerySet[Relationship]:
        qs = Relationship.objects.filter(
            district_id=require_district_id(self.request)
        ).select_related("decided_by")
        params = self.request.query_params
        for name in ("project", "feature"):
            if params.get(name) and not params[name].isdigit():
                raise serializers.ValidationError({name: "Must be a number."})
        if params.get("project"):
            qs = qs.filter(project_id=int(params["project"]))
        if params.get("feature"):
            feature = int(params["feature"])
            qs = qs.filter(Q(subject_id=feature) | Q(object_id=feature))
        for name in ("type", "method", "status", "rule"):
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        return qs.order_by("type", "subject_id", "id")

    @extend_schema(
        operation_id="relationships_list",
        parameters=[
            OpenApiParameter("project", int),
            OpenApiParameter("feature", int),
            OpenApiParameter("type", str),
            OpenApiParameter("method", str),
            OpenApiParameter("status", str),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        links = list(page if page is not None else self.get_queryset()[:1000])
        labels = labels_for(links, {link.project_id for link in links})
        rows = [link_json(link, labels) for link in links]
        return self.get_paginated_response(rows) if page is not None else Response(rows)

    @extend_schema(request=ManualLinkSerializer, responses=OpenApiTypes.OBJECT)
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """A link a person knows to be true. Procedures never change it."""
        data = ManualLinkSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        district_id = require_district_id(request)
        kind = TYPE_BY_CODE[values["type"]]
        features = {
            f.pk: f
            for f in Feature.objects.filter(
                pk__in=[values["subject"], values["object"]], district_id=district_id
            ).select_related("layer")
        }
        subject, target = features.get(values["subject"]), features.get(values["object"])
        if subject is None or target is None:
            raise serializers.ValidationError(
                {"detail": "Both features must exist in this district."}
            )
        project = subject.layer.project
        if target.layer.project_id != project.pk:
            raise serializers.ValidationError(
                {"detail": "Both features must be in the same project."}
            )
        roles = services.roles_of(project)
        for feature, role, name in (
            (subject, kind.subject, "subject"),
            (target, kind.object, "object"),
        ):
            if role not in roles or roles[role].layer_id != feature.layer_id:
                raise serializers.ValidationError(
                    {name: f"Must be a feature of the layer set as {ROLE_BY_CODE[role].label}."}
                )
        now = timezone.now()
        link, _ = Relationship.objects.update_or_create(
            project=project,
            type=kind.code,
            subject=subject,
            object=target,
            rule="",
            defaults={
                "district_id": district_id,
                "method": Relationship.Method.CONFIRMED,
                "status": Relationship.Status.ACTIVE,
                "confidence": 1.0,
                "checked_at": now,
                "decided_by": request_user(request),
                "decided_at": now,
                "note": values.get("note", ""),
            },
        )
        return Response(
            link_json(link, labels_for([link], {project.pk})), status=status.HTTP_201_CREATED
        )

    def _decide(self, request: Request, pk: str | None, confirm: bool) -> Response:
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            link = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
            if confirm:
                # What the procedure thought stays on record.
                link.details = {
                    **link.details,
                    "was": link.details.get("was", link.method),
                    "confidence_was": link.details.get("confidence_was", link.confidence),
                }
                link.method = Relationship.Method.CONFIRMED
                link.status = Relationship.Status.ACTIVE
                link.confidence = 1.0
            else:
                link.status = Relationship.Status.REJECTED
            link.decided_by = request_user(request)
            link.decided_at = timezone.now()
            link.note = data.validated_data.get("note", link.note)
            link.save()
        return Response(link_json(link, labels_for([link], {link.project_id})))

    @extend_schema(request=DecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def confirm(self, request: Request, pk: str | None = None) -> Response:
        """A person confirms the link. It is kept as it is from now on."""
        return self._decide(request, pk, True)

    @extend_schema(request=DecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        """A person says the link is wrong. It is kept as rejected, so
        procedures don't make it again."""
        return self._decide(request, pk, False)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        """Hands the link back to the procedures (undoes a confirm or reject)."""
        with transaction.atomic():
            link = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
            was = link.details.get("was")
            link.method = was if was in Relationship.Method.values else Relationship.Method.INFERRED
            link.confidence = float(link.details.get("confidence_was", link.confidence))
            link.status = Relationship.Status.ACTIVE
            link.decided_by, link.decided_at = None, None
            link.save()
        return Response(link_json(link, labels_for([link], {link.project_id})))


class StandardSerializer(serializers.ModelSerializer[DevelopmentStandard]):
    class Meta:
        model = DevelopmentStandard
        fields = [
            "id",
            "zone",
            "min_setback_m",
            "front_setback_m",
            "side_setback_m",
            "rear_setback_m",
            "min_floors",
            "max_floors",
            "max_coverage_pct",
            "min_plot_m2",
            "min_width_m",
            "prohibited_uses",
            "permit_required",
            "build_in_flood_area",
            "source",
            "notes",
            "updated_at",
        ]
        read_only_fields = ["source"]

    def validate_prohibited_uses(self, value: Any) -> list[str]:
        if not isinstance(value, list) or not all(isinstance(word, str) for word in value):
            raise serializers.ValidationError("A list of words.")
        return [word.strip().lower() for word in value if word.strip()][:50]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        for name in (
            "min_setback_m",
            "front_setback_m",
            "side_setback_m",
            "rear_setback_m",
            "max_coverage_pct",
            "min_plot_m2",
            "min_width_m",
        ):
            value = attrs.get(name)
            if value is not None and value < 0:
                raise serializers.ValidationError({name: "Can't be negative."})
        cover = attrs.get("max_coverage_pct")
        if cover is not None and cover > 100:
            raise serializers.ValidationError({"max_coverage_pct": "At most 100."})
        current = self.instance if isinstance(self.instance, DevelopmentStandard) else None
        low = attrs.get("min_floors", current.min_floors if current else None)
        high = attrs.get("max_floors", current.max_floors if current else None)
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError(
                {"min_floors": "The fewest storeys can't be more than the most."}
            )
        return attrs


class AdoptSerializer(serializers.Serializer[Any]):
    zones = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        help_text="National zone codes; all zones with site standards when left out",
    )
    replace = serializers.BooleanField(
        default=False, help_text="Also overwrite standards the district has changed"
    )


@extend_schema(parameters=[DISTRICT_HEADER])
class StandardViewSet(viewsets.ModelViewSet[DevelopmentStandard]):
    """The district's development-control standards, one per zone. The
    standard with an empty zone is the district's default."""

    serializer_class = StandardSerializer
    queryset = DevelopmentStandard.objects.none()
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        safe = self.request.method in ("GET", "HEAD", "OPTIONS")
        return _perms("project.view" if safe else "standards.manage")

    def get_queryset(self) -> QuerySet[DevelopmentStandard]:
        return DevelopmentStandard.objects.filter(district_id=require_district_id(self.request))

    def perform_create(self, serializer: Any) -> None:
        district_id = require_district_id(self.request)
        zone = serializer.validated_data.get("zone", "").strip()
        if DevelopmentStandard.objects.filter(district_id=district_id, zone__iexact=zone).exists():
            raise serializers.ValidationError(
                {"zone": "This district already has a standard for that zone."}
            )
        serializer.save(district_id=district_id, zone=zone)

    def perform_update(self, serializer: Any) -> None:
        # Once changed by the district it is the district's own standard.
        serializer.save(source="")

    @extend_schema(request=AdoptSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="adopt-national")
    def adopt_national(self, request: Request) -> Response:
        """Adopts the national zoning standards (LUSPA, 2025) for this district:
        one standard per zone that has site standards. Standards the district
        has set or changed itself are left alone unless `replace` is true."""
        data = AdoptSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        district_id = require_district_id(request)
        wanted = data.validated_data.get("zones")
        chosen = []
        for code in wanted or [z.code for z in zoning.ZONES if z.site is not None]:
            zone = zoning.match(code)
            if zone is None or zone.site is None:
                raise serializers.ValidationError(
                    {"zones": f"{code!r} isn't a national zone with site standards."}
                )
            chosen.append(zone)
        existing = list(DevelopmentStandard.objects.filter(district_id=district_id))
        report: dict[str, list[str]] = {"added": [], "updated": [], "kept": []}
        for zone in chosen:
            row = next((s for s in existing if zoning.match(s.zone) == zone), None)
            values = zoning.standard_values(zone)
            if row is None:
                DevelopmentStandard.objects.create(
                    district_id=district_id,
                    zone=zone.code,
                    source=zoning.SOURCE_CODE,
                    notes=f"{zoning.SOURCE}. Height: {zone.site.height}." if zone.site else "",
                    **values,
                )
                report["added"].append(zone.code)
            elif row.source == zoning.SOURCE_CODE or data.validated_data["replace"]:
                for name, value in values.items():
                    setattr(row, name, value)
                row.source = zoning.SOURCE_CODE
                row.save()
                report["updated"].append(zone.code)
            else:
                report["kept"].append(zone.code)
        return Response(report)


@extend_schema(responses=OpenApiTypes.OBJECT)
class ZonesView(APIView):
    """The national zones (LUSPA, 2025): codes, colours, permissible and
    prohibited uses, and the site standards of the zones that have them."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "source": zoning.SOURCE,
                "zones": [zoning.zone_json(zone) for zone in zoning.ZONES],
            }
        )


@extend_schema(parameters=[DISTRICT_HEADER], request=None, responses=OpenApiTypes.OBJECT)
class ZoningStyleView(APIView):
    """Colours the project's zoning layer by zone, in the national colour
    codes. Zones the standards don't name keep the layer's default symbol."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("relations.edit")

    def post(self, request: Request, project_id: int) -> Response:
        project = _project(request, project_id)
        role = (
            LayerRole.objects.filter(project=project, role="zoning").select_related("layer").first()
        )
        if role is None:
            raise serializers.ValidationError(
                {"detail": "Say which layer holds the zoning first (Relationships, layer roles)."}
            )
        layer = role.layer
        field = role.config.get("zone_field", "zone")
        values = (
            Feature.objects.filter(layer=layer)
            .values_list(f"properties__{field}", flat=True)
            .distinct()
        )
        categories: list[dict[str, Any]] = []
        unknown: list[str] = []
        for value in sorted({str(v) for v in values if v not in (None, "")}):
            zone = zoning.match(value)
            if zone is None:
                unknown.append(value)
                continue
            categories.append(
                {
                    **DEFAULT_SYMBOL,
                    "value": value,
                    "fill": zone.colour,
                    "stroke": "#333333",
                    "fill_opacity": 0.6,
                }
            )
        style = {
            "kind": "categorized",
            "field": field,
            "categories": categories,
            "default": {**DEFAULT_SYMBOL, "fill": "#bbbbbb", "stroke": "#555555"},
            "label_field": field,
        }
        try:
            layer.style = validate_style(style, layer.schema)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc
        layer.save(update_fields=["style"])
        return Response(
            {"layer": layer.pk, "coloured": [c["value"] for c in categories], "unknown": unknown}
        )


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class ZoningSchemeSerializer(serializers.ModelSerializer[ZoningScheme]):
    deadlines = serializers.SerializerMethodField()

    class Meta:
        model = ZoningScheme
        fields = [
            "id",
            "project",
            "name",
            "status",
            "structure_plan_approved_on",
            "approved_on",
            "effective_on",
            "sent_to_luspa_on",
            "update_every_months",
            "notes",
            "deadlines",
            "updated_at",
        ]

    def validate_update_every_months(self, value: int) -> int:
        if not 1 <= value <= 240:
            raise serializers.ValidationError("Between 1 and 240 months.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        current = self.instance if isinstance(self.instance, ZoningScheme) else None
        status_now = attrs.get("status", current.status if current else ZoningScheme.Status.DRAFT)
        approved = attrs.get("approved_on", current.approved_on if current else None)
        if status_now != ZoningScheme.Status.DRAFT and approved is None:
            raise serializers.ValidationError(
                {"approved_on": "Give the date the scheme was approved or adopted."}
            )
        return attrs

    def get_deadlines(self, obj: ZoningScheme) -> dict[str, Any]:
        """The dates L.I. 2384 r.29 sets, and whether each has been met."""
        today = date.today()
        out: dict[str, Any] = {}
        if obj.structure_plan_approved_on and obj.status == ZoningScheme.Status.DRAFT:
            due = obj.structure_plan_approved_on + timedelta(days=90)
            out["prepare"] = {
                "rule": "r.29(1): within 90 days of the structure plan's approval",
                "due_on": due.isoformat(),
                "overdue": today > due,
            }
        if obj.approved_on:
            due = obj.approved_on + timedelta(days=28)
            out["send_to_luspa"] = {
                "rule": "r.29(6): a copy to LUSPA within 28 days of approval",
                "due_on": due.isoformat(),
                "done_on": obj.sent_to_luspa_on.isoformat() if obj.sent_to_luspa_on else None,
                "overdue": obj.sent_to_luspa_on is None and today > due,
            }
            due = _add_months(obj.approved_on, obj.update_every_months)
            out["update"] = {
                "rule": "r.29(3): the scheme's schedule for periodic updates",
                "due_on": due.isoformat(),
                "overdue": today > due,
            }
        return out


@extend_schema(parameters=[DISTRICT_HEADER])
class ZoningSchemeViewSet(viewsets.ModelViewSet[ZoningScheme]):
    """The register of zoning schemes (filter with ?project=): when each was
    approved, sent to LUSPA, and is next due for update."""

    serializer_class = ZoningSchemeSerializer
    queryset = ZoningScheme.objects.none()
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        safe = self.request.method in ("GET", "HEAD", "OPTIONS")
        return _perms("project.view" if safe else "relations.edit")

    def get_queryset(self) -> QuerySet[ZoningScheme]:
        qs = ZoningScheme.objects.filter(district_id=require_district_id(self.request))
        project = self.request.query_params.get("project", "")
        return qs.filter(project_id=int(project)) if project.isdigit() else qs

    def perform_create(self, serializer: Any) -> None:
        district_id = require_district_id(self.request)
        project = serializer.validated_data["project"]
        if project.district_id != district_id:
            raise serializers.ValidationError({"project": "Pick a project of this district."})
        serializer.save(district_id=district_id, created_by=request_user(self.request))

    def perform_update(self, serializer: Any) -> None:
        if "project" in serializer.validated_data:
            current = serializer.instance
            if serializer.validated_data["project"].pk != current.project_id:
                raise serializers.ValidationError({"project": "A scheme stays with its project."})
        serializer.save()
